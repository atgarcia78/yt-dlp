from .commonwebdriver import (
    By,
    ConnectError,
    ExtractorError,
    HTTPStatusError,
    ReExtractInfo,
    SeleniumInfoExtractor,
    dec_on_driver_timeout,
    limiter_1,
    my_dec_on_exception,
    raise_extractor_error,
)
from ..utils import get_domain, sanitize_filename

on_exception = my_dec_on_exception(
    (TimeoutError, ExtractorError), raise_on_giveup=False, max_tries=3, jitter="my_jitter", interval=5)


class get_videourl:
    def __call__(self, driver):
        elvideo = driver.find_elements(By.TAG_NAME, "video")
        if not elvideo:
            return False
        videourl = elvideo[0].get_attribute('src')
        if not videourl:
            return False
        else:
            return videourl


class DFlixIE(SeleniumInfoExtractor):

    _SITE_URL = "https://dflix.top"

    IE_NAME = 'dflix'
    _VALID_URL = r'https?://(?:www\.)?dflix\.top/(?:e|f|v)/(?P<id>[^\/$]+)(?:\/|$)'

    @on_exception
    @limiter_1.ratelimit("dflix", delay=True)
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

    @SeleniumInfoExtractor.syncsem()
    def _get_entry(self, url, check=False, msg=None):

        video_id = self._match_id(url)
        url = f'https://dflix.top/e/{video_id}'
        pre = f'[get_entry][{self._get_url_print(url)}]'
        if msg:
            pre = f'{msg}{pre}'

        driver = self.get_driver()

        try:

            self._send_request(url, driver=driver)
            video_url = self.wait_until(driver, 30, get_videourl())
            if not video_url:
                raise ExtractorError("coundt get videourl")

            title = (driver.title).replace('mp4', '').replace('mkv', '').strip(' \t\n\r\f\v-_.')

            headers = {'Referer': self._SITE_URL + '/', 'Origin': self._SITE_URL}

            _format = {
                'format_id': 'http-mp4',
                'url': video_url,
                'http_headers': headers,
                'ext': 'mp4'
            }

            if check:
                _host = get_domain(video_url)
                _sem = self.get_ytdl_sem(_host)

                with _sem:
                    _videoinfo = self._get_video_info(video_url, msg=pre, headers=headers)

                if not _videoinfo:
                    raise ReExtractInfo(f"{pre} error 404: no video info")

                if _videoinfo['filesize'] >= 1000000:
                    _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize'], 'accept_ranges': _videoinfo['accept_ranges']})
                else:
                    raise ReExtractInfo(f"{pre} error filesize[{_videoinfo['filesize']}] < 1MB")

            _entry = {
                'id': video_id,
                'title': sanitize_filename(title, restricted=True),
                'formats': [_format],
                'ext': 'mp4',
                'extractor_key': 'MixDrop',
                'extractor': 'doodstream',
                'webpage_url': url
            }

            return _entry

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
            raise_extractor_error(repr(e))
