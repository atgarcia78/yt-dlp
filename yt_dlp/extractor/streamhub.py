import logging
import os

from yt_dlp_plugins.extractor.commonwebdriver import (
    By,
    ConnectError,
    HTTPStatusError,
    ReExtractInfo,
    SeleniumInfoExtractor,
    dec_on_driver_timeout,
    dec_on_exception2,
    ec,
    limiter_5,
    my_dec_on_exception,
    raise_extractor_error,
    raise_reextract_info,
)

from ..utils import ExtractorError, sanitize_filename, try_call, try_get

logger = logging.getLogger('streamhub')

on_exception = my_dec_on_exception(
    (TimeoutError, ExtractorError, ReExtractInfo), raise_on_giveup=False,
    max_tries=3, jitter="my_jitter", interval=1)

on_retry_vinfo = my_dec_on_exception(
    ReExtractInfo, raise_on_giveup=True, max_tries=3, jitter="my_jitter", interval=1)


class StreamHubIE(SeleniumInfoExtractor):

    _VALID_URL = r'https?://(?:www\.)?streamhub\.[^/]+/(?:e/)?(?P<id>[a-z0-9]+)'
    IE_NAME = 'streamhub'  # type: ignore

    @dec_on_driver_timeout
    @dec_on_exception2
    @on_exception
    def _send_request(self, url, **kwargs):

        pre = f'[send_request][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'

        driver = kwargs.get('driver', None)

        with limiter_5.ratelimit(f"{self.IE_NAME}", delay=True):
            self.logger_debug(pre)
            if driver:
                driver.get(url)
            else:
                try:
                    return self.send_http_request(url)
                except (HTTPStatusError, ConnectError) as e:
                    _msg_error = f"{repr(e)}"
                    self.logger_debug(f"{pre}: {_msg_error}")
                    return {"error_res": _msg_error}

    @SeleniumInfoExtractor.syncsem()
    @on_retry_vinfo
    def _get_entry(self, url, **kwargs):

        pre = f'[get_entry_by_har][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'

        videoid = self._match_id(url)  # type: ignore
        url_dl = f"https://streamhub.to/{videoid}"
        _title = None
        _har_file = None

        if "error" in (_res := self._is_valid(url_dl, inc_error=True)):
            raise_extractor_error(_res['error'])

        try:
            _port = self.find_free_port() or 8080
            driver = self.get_driver(host='127.0.0.1', port=_port)
            try:
                with self.get_har_logs('streamhub', videoid, msg=pre, port=_port) as harlogs:
                    _har_file = harlogs.har_file
                    self._send_request(url_dl, driver=driver)
                    self.wait_until(driver, 60, ec.presence_of_element_located((By.TAG_NAME, "video")))
                    _title = try_get(
                        driver.find_element(by=By.TAG_NAME, value='h4'),
                        lambda x: x.text)
                    self.wait_until(driver, 1)
            except ReExtractInfo:
                raise
            except Exception as e:
                self.logger_debug(f"{pre} {repr(e)}")
                raise_reextract_info(f'{pre} {repr(e)}')
            finally:
                self.rm_driver(driver)

            _headers = {
                'Origin': "https://streamhub.to",
                'Referer': "https://streamhub.to/"
            }

            m3u8_url, m3u8_doc = try_get(
                self.scan_for_request(r"master\.m3u8.*$", har=_har_file),
                lambda x: (x.get('url'), x.get('content')) if x else (None, None))

            if not m3u8_url or not m3u8_doc:
                raise_reextract_info(f'{pre} no video info')

            _formats, _subtitles = self._parse_m3u8_formats_and_subtitles(
                m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")

            if not _formats:
                raise_extractor_error(f'{pre} Couldnt get video formats')

            for _format in _formats:
                if (_head := _format.get('http_headers')):
                    _head.update(**_headers)
                else:
                    _format.update({'http_headers': _headers})

            if not _subtitles:
                list_subt_urls = try_get(
                    self.scan_for_request(r"\.(?:srt|vtt)$", har=_har_file, _all=True),  # type: ignore
                    lambda x: [_url for el in x if "empty." not in (_url := el.get('url'))] if x else [])
                if list_subt_urls:
                    def _get_info_subt(subturl):
                        _cc_lang = {'spanish': 'es', 'english': 'en'}
                        if subturl:
                            ext = subturl.rsplit('.', 1)[-1]
                            lang = _cc_lang.get(try_call(lambda: subturl.rsplit('.', 1)[0].rsplit('_', 1)[-1].lower()) or 'dummy')
                            if lang:
                                return {'lang': lang, 'ext': ext}

                    for _url_subt in list_subt_urls:
                        _subt = _get_info_subt(_url_subt)
                        if not _subt:
                            continue
                        _subtitles.setdefault(_subt.get('lang'), []).append({'url': _url_subt, 'ext': _subt.get('ext')})

            _entry = {
                'id': videoid,
                'title': sanitize_filename(_title, restricted=True),
                'formats': _formats,
                'subtitles': _subtitles,
                'ext': 'mp4',
                'extractor_key': 'StreamHub',
                'extractor': 'streamhub',
                'webpage_url': url}

            try:
                if _duration := self._extract_m3u8_vod_duration(_formats[0]['url'], videoid, headers=_formats[0]['http_headers']):
                    _entry['duration'] = _duration
            except Exception as e:
                self.report_warning(f"{pre}: error trying to get vod {repr(e)}")

            return _entry

        except Exception as e:
            logger.debug(f"{pre} {repr(e)}")
            raise ExtractorError(f"Couldnt get video entry - {repr(e)}")
        finally:
            if _har_file:
                try:
                    if os.path.exists(_har_file):
                        os.remove(_har_file)
                except OSError:
                    self.logger_debug(f"{pre}: Unable to remove the har file")

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        # self.report_extraction(url)
        try:
            if not self.get_param('embed'):
                _check = True
            else:
                _check = False

            return self._get_entry(url, check=_check)
        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(f"{repr(e)}")
            raise ExtractorError(repr(e))
