import sys
import time
import traceback


from .commonwebdriver import (
    By,
    ConnectError,
    HTTPStatusError,
    Lock,
    SeleniumInfoExtractor,
    dec_on_exception,
    dec_on_exception2,
    dec_on_exception3,
    limiter_1,
)
from ..utils import ExtractorError, get_domain, sanitize_filename, traverse_obj, try_get


class video_or_error:

    def __call__(self, driver):

        if driver.find_elements(By.CSS_SELECTOR, '.alert'):
            return "error"
        button = driver.find_elements(By.CLASS_NAME, "vjs-icon-placeholder")
        if not button:
            return False
        button[0].click()
        time.sleep(2)
        video = driver.find_element(By.ID, 'my_video_html5_api')
        video.click()
        return True


class HexUploadIE(SeleniumInfoExtractor):

    IE_NAME = 'hexupload'
    _VALID_URL = r'https?://(?:www\.)?hexupload\.net/(embed-)?(?P<id>[^\/$]+)(?:\/|$)'
    _SITE_URL = 'https://hexupload.net/'

    @dec_on_exception2
    @dec_on_exception3
    @limiter_1.ratelimit("hexupload", delay=True)
    def _get_video_info(self, url, msg=None):
        try:
            pre = '[get_video_info]'
            if msg:
                pre = f'{msg}{pre}'
            self.logger_debug(f"{pre} {self._get_url_print(url)}")
            _headers = {'Range': 'bytes=0-', 'Referer': self._SITE_URL,
                        'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
                        'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
            _host = get_domain(url)

            with self.get_param('lock'):
                if not (_sem := traverse_obj(self.get_param('sem'), _host)):
                    _sem = Lock()
                    self.get_param('sem').update({_host: _sem})

            with _sem:
                return self.get_info_for_format(url, headers=_headers)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    @dec_on_exception
    @dec_on_exception3
    @dec_on_exception2
    def _send_request(self, url, **kwargs):

        driver = kwargs.get('driver', None)

        if driver:
            with limiter_1.ratelimit("hexupload2", delay=True):
                self.logger_debug(f"[send_request] {url}")
                driver.get(url)
        else:
            with limiter_1.ratelimit("hexupload2", delay=True):
                self.logger_debug(f"[send_request] {url}")
                try:
                    return self.send_http_request(url)
                except (HTTPStatusError, ConnectError) as e:
                    self.report_warning(f"[send_request] {self._get_url_print(url)}: error - {repr(e)}")

    def _get_entry(self, url, **kwargs):

        check = kwargs.get('check', False)
        msg = kwargs.get('msg', None)

        try:

            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg:
                pre = f'{msg}{pre}'
            videoid = self._match_id(url)
            driver = self.get_driver(devtools=True)
            self._send_request(f'{self._SITE_URL}{videoid}', driver=driver)
            res = self.wait_until(driver, 30, video_or_error())
            video_url = None
            if res and res != "error":
                video_url = try_get(self.scan_for_request(driver, 'video.mp4', response=False), lambda x: x.get('url'))
            if not video_url:
                raise ExtractorError('404 video not found')
            title = driver.title.replace("mp4", "").replace("Download", "").strip()

            _format = {
                'format_id': 'http-mp4',
                'url': video_url,
                'ext': 'mp4',
                'http_headers': {'Referer': self._SITE_URL}
            }

            if check:
                _videoinfo = self._get_video_info(video_url, msg=pre)
                if not _videoinfo:
                    raise ExtractorError("error 404: no video info")
                else:
                    _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})

            _entry_video = {
                'id': videoid,
                'title': sanitize_filename(title, restricted=True),
                'formats': [_format],
                'extractor_key': self.ie_key(),
                'extractor': self.IE_NAME,
                'ext': 'mp4',
                'webpage_url': url
            }
            return _entry_video

        except Exception:
            raise
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
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
