from .commonwebdriver import (
    SeleniumInfoExtractor,
    HTTPStatusError,
    ConnectError,
    ReExtractInfo,
    dec_on_driver_timeout,
    limiter_1,
    my_dec_on_exception,
    By,
    ec,
    cast,
    raise_reextract_info
)
from ..utils import (
    ExtractorError,
    sanitize_filename,
    try_get,
    get_domain
)


import logging
logger = logging.getLogger('streamsb')

on_exception = my_dec_on_exception(
    (TimeoutError, ExtractorError), raise_on_giveup=False, max_tries=3, jitter="my_jitter", interval=1)

on_retry_vinfo = my_dec_on_exception(
    ReExtractInfo, raise_on_giveup=False, max_tries=3, jitter="my_jitter", interval=1)


class VGEmbedIE(SeleniumInfoExtractor):

    _VALID_URL = r'https?://(?:.+?\.)?vgembed\.com/((?:d|e|v)/)?(?P<id>[\dA-Za-z]+)'
    IE_NAME = 'vgembed'  # type: ignore

    @on_exception
    @limiter_1.ratelimit("mixdrop", delay=True)
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
    @dec_on_driver_timeout
    @limiter_1.ratelimit("streamsb", delay=True)
    def _send_request(self, url, **kwargs):

        pre = f'[send_request][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'

        driver = kwargs.get('driver', None)

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

    @on_retry_vinfo
    def _get_entry(self, url, **kwargs):

        pre = f'[get_entry][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'

        check = kwargs.get('check', True)

        videoid = self._match_id(url)
        url_dl = f"https://vgembed.com/v/{videoid}"

        driver = self.get_driver()

        try:

            self._send_request(url_dl, driver=driver)
            el = self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "iframe")))
            if not el:
                raise_reextract_info(f'{pre} Couldnt get video info')
            title = driver.title
            driver.switch_to.frame(el)
            video_url = try_get(self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "video"))), lambda x: x.get_attribute('src') if x else None)
            if not video_url:
                raise_reextract_info(f'{pre} Couldnt get video info')
            _headers = {'Origin': "https://vgembed.com", 'Referer': "https://vgembed.com/"}

            _format = {
                'format_id': 'http-mp4',
                'url': video_url,
                'http_headers': _headers,
                'ext': 'mp4'
            }

            if check:
                _host = get_domain(video_url)
                _sem = self.get_ytdl_sem(_host)

                with _sem:
                    _videoinfo = self._get_video_info(video_url, msg=pre, headers=_headers)

                if not _videoinfo:
                    raise ReExtractInfo(f"{pre} error 404: no video info")

                _videoinfo = cast(dict, _videoinfo)
                if _videoinfo['filesize'] >= 1000000:
                    _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize'], 'accept_ranges': _videoinfo['accept_ranges']})
                else:
                    raise ReExtractInfo(f"{pre} error filesize[{_videoinfo['filesize']}] < 1MB")

            _entry = {
                'id': videoid,
                'title': sanitize_filename(title, restricted=True),
                'formats': [_format],
                'ext': 'mp4',
                'extractor_key': 'MixDrop',
                'extractor': 'mixdrop',
                'webpage_url': url
            }

            return _entry

        except ReExtractInfo:
            raise
        except ExtractorError:
            raise
        except Exception as e:
            self.logger_debug(f"{pre} {repr(e)}")
            raise ExtractorError(f"Couldnt get video entry - {repr(e)}")
        finally:
            self.rm_driver(driver)

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
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
