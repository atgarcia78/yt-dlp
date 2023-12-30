import logging
import os
from threading import Lock
from urllib.parse import unquote

from .commonwebdriver import (
    By,
    ConnectError,
    HTTPStatusError,
    ReExtractInfo,
    SeleniumInfoExtractor,
    dec_on_driver_timeout,
    dec_on_exception2,
    get_host,
    limiter_5,
    my_dec_on_exception,
    raise_extractor_error,
    raise_reextract_info,
)
from ..utils import ExtractorError, sanitize_filename, try_get

logger = logging.getLogger('vgembed')

on_exception = my_dec_on_exception(
    (TimeoutError, ExtractorError, ReExtractInfo), raise_on_giveup=False,
    max_tries=3, jitter="my_jitter", interval=1)

on_retry_vinfo = my_dec_on_exception(
    ReExtractInfo, raise_on_giveup=True, max_tries=3, jitter="my_jitter", interval=1)


class getvideourl:

    def __call__(self, driver):
        el_video = driver.find_element(By.CSS_SELECTOR, "video")
        video_url = el_video.get_attribute('src')
        if video_url:
            return unquote(video_url)
        else:
            return False


class VGEmbedIE(SeleniumInfoExtractor):

    _VALID_URL = r'https?://(?:.+?\.)?(?:vgembed|vgfplay|vembed)\.(com|net|org)/((?:d|e|v)/)?(?P<id>[\dA-Za-z]+)'
    IE_NAME = 'vgembed'  # type: ignore
    _LOCK = Lock()

    @on_exception
    @dec_on_exception2
    @limiter_5.ratelimit("vgembed", delay=True)
    def _get_video_info(self, url, **kwargs):

        msg = kwargs.get('msg')
        pre = f'[get_video_info][{self._get_url_print(url)}]'
        if msg:
            pre = f'{msg}{pre}'

        _headers = kwargs.get('headers', {})
        headers = {'Range': 'bytes=0-', 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors',
                   'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}

        headers.update(_headers)

        try:
            return self.get_info_for_format(url, headers=headers)
        except (HTTPStatusError, ConnectError) as e:
            self.logger_debug(f"{pre}: error - {repr(e)}")
        except ReExtractInfo as e:
            self.logger_debug(f"{pre}: error - {repr(e)}, will retry")
            raise

    @on_exception
    @dec_on_exception2
    @dec_on_driver_timeout
    @limiter_5.ratelimit("vgembed2", delay=True)
    def _send_request(self, url, **kwargs):

        pre = f'[send_request][{self._get_url_print(url)}]'
        _kwargs = kwargs.copy()
        if (msg := _kwargs.pop('msg', None)):
            pre = f'{msg}{pre}'

        driver = _kwargs.pop('driver', None)

        self.logger_debug(pre)
        if driver:
            driver.get(url)
        else:
            try:
                return self.send_http_request(url, **_kwargs)
            except (HTTPStatusError, ConnectError) as e:
                _msg_error = f"{repr(e)}"
                self.logger_debug(f"{pre}: {_msg_error}")
                return {"error": _msg_error}

    @SeleniumInfoExtractor.syncsem()
    @on_retry_vinfo
    def _get_entry(self, url, **kwargs):

        check = kwargs.get('check', True)
        videoid = self._match_id(url)
        host = 'vembed.org'
        url_dl = f"https://{host}/v/{videoid}"
        pre = f'[get_entry][{self._get_url_print(url)}][{videoid}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'

        _har_file = None
        title = ""

        try:
            self.logger_debug(f"{pre} start to get entry - check[{check}]")
            if "error" in (_res := self._is_valid(url_dl, inc_error=True)):
                raise_extractor_error(_res['error'])

            title = self._html_extract_title(_res['webpage'])

            videourl = None
            _port = self.find_free_port() or 8080
            driver = self.get_driver(host='127.0.0.1', port=_port)

            try:
                with self.get_har_logs('vgembed', videoid, msg=pre, port=_port) as harlogs:
                    _har_file = harlogs.har_file
                    self._send_request(url_dl.replace('/v/', '/e/'), driver=driver)
                    if (_vid := self.wait_until(driver, 60, getvideourl())) and 'blob:' not in _vid:
                        videourl = _vid
                        self.logger_info(f"{pre} videourl {videourl}")
            except ReExtractInfo:
                raise
            except Exception as e:
                logger.exception(f"{pre} {repr(e)}")
                raise_reextract_info(f'{pre} {repr(e)}')
            finally:
                self.rm_driver(driver)

            _headers = {
                'Origin': f"https://{host}",
                'Referer': f"https://{host}/"
            }
            _subtitles = {}
            _formats = []
            _entry = {}

            if videourl:

                _format = {
                    'format_id': 'http-mp4',
                    'url': videourl,
                    'http_headers': _headers,
                    'ext': 'mp4'
                }

                _host = get_host(videourl, shorten="vgembed")
                _sem = self.get_ytdl_sem(_host)
                if check:
                    with _sem:
                        _videoinfo = self._get_video_info(
                            videourl, msg=pre, headers=_headers)

                    if not _videoinfo:
                        raise_reextract_info(f"{pre} no video info")

                    _format.update(_videoinfo)

                _formats.append(_format)

            else:
                m3u8_url, m3u8_doc = try_get(
                    self.scan_for_request(r"master\.m3u8.*$", har=_har_file),  # type: ignore
                    lambda x: (x.get('url'), x.get('content')) if x else (None, None))

                if not m3u8_url or not m3u8_doc:
                    raise_reextract_info(f'{pre} no video info')

                _formats, _subtitles = self._parse_m3u8_formats_and_subtitles(
                    m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")

                if not _formats:
                    raise_extractor_error(f'{pre} Couldnt get video formats')

                for _format in _formats:
                    if (_head := _format.get('http_headers')):
                        _head.update(_headers)
                    else:
                        _format.update({'http_headers': _headers})

                try:
                    if (
                        _duration := self._extract_m3u8_vod_duration(
                            _formats[0]['url'], videoid, headers=_formats[0]['http_headers'])
                    ):
                        _entry.update({'duration': _duration})
                except Exception as e:
                    self.logger_info(f"{pre}: error trying to get vod {repr(e)}")

            _entry.update({
                'id': videoid,
                'title': sanitize_filename(title.replace('.mp4', ''), restricted=True),
                '_try_title': True,
                'formats': _formats,
                'subtitles': _subtitles,
                'ext': 'mp4',
                'extractor_key': 'VGEmbed',
                'extractor': 'vgembed',
                'webpage_url': url})

            return _entry

        except ReExtractInfo as e:
            logger.error(f"{pre} {repr(e)}")
            raise
        except Exception as e:
            logger.exception(f"{pre} {repr(e)}")
            raise ExtractorError(f"Couldnt get video entry - {repr(e)}")
        finally:
            if _har_file == 'dummy':
                try:
                    if os.path.exists(_har_file):
                        os.remove(_har_file)
                except OSError:
                    self.logger_debug(f"{pre}: Unable to remove the har file")

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
        try:
            _check = True
            return self._get_entry(url, check=_check)
        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(f"{repr(e)}")
            raise_extractor_error(repr(e))
