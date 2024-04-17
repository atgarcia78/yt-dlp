import re
import sys
import traceback
from urllib.parse import unquote

from yt_dlp_plugins.extractor.commonwebdriver import (
    By,
    ConnectError,
    HTTPStatusError,
    SeleniumInfoExtractor,
    dec_on_exception,
    dec_on_exception2,
    dec_on_exception3,
    limiter_1,
)

from ..utils import ExtractorError, sanitize_filename


class get_videourl:

    def __call__(self, driver):
        el_video = driver.find_element(By.CSS_SELECTOR, "video")
        video_url = el_video.get_attribute('src')
        if video_url:
            if video_url.startswith('blob'):
                driver.delete_all_cookies()
                driver.refresh()
                return False
            else:
                return unquote(video_url)
        else:
            return False


class TheGayIE(SeleniumInfoExtractor):

    IE_NAME = 'thegay'
    _VALID_URL = r'https?://(?:www\.)?thegay\.com/(?P<type>(?:embed|videos))/(?P<id>\d+)/?'

    @dec_on_exception3
    @dec_on_exception2
    @limiter_1.ratelimit("thegay", delay=True)
    def _get_video_info(self, url, **kwargs):

        msg = kwargs.get('msg', None)
        headers = kwargs.get('headers', {})

        try:
            if msg:
                pre = f'{msg}[get_video_info]'
            else:
                pre = '[get_video_info]'
            self.logger_debug(f"{pre} {self._get_url_print(url)}")

            return self.get_info_for_format(url, headers={'Range': 'bytes=0-', 'Referer': headers['Referer'], 'Sec-Fetch-Dest': 'video',
                                                          'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'same-origin',
                                                          'Pragma': 'no-cache', 'Cache-Control': 'no-cache'})
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"{pre} {self._get_url_print(url)}: error - {repr(e)}")

    @dec_on_exception
    @limiter_1.ratelimit("thegay", delay=True)
    def _send_request(self, url, **kwargs):

        msg = kwargs.get('msg', None)
        driver = kwargs.get('driver', None)

        if msg:
            pre = f'{msg}[send_req]'
        else:
            pre = '[send_req]'
        if driver:
            self.logger_debug(f"{pre} {self._get_url_print(url)}")
            driver.get(url)

    @SeleniumInfoExtractor.syncsem()
    def _get_entry(self, url, **kwargs):

        check = kwargs.get('check', False)
        msg = kwargs.get('msg', None)

        try:

            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg:
                pre = f'{msg}{pre}'

            driver = self.get_driver()

            driver.delete_all_cookies()

            self._send_request(url, driver=driver)

            videoid = self._match_id(url)

            videourl = self.wait_until(driver, 60, get_videourl())
            if not videourl:
                raise ExtractorError("couldnt find videourl")

            _title = re.sub(r'(?i)( - %s\..+$)' % self.IE_NAME, '', driver.title.replace('.mp4', '')).strip('[_,-, ]')
            headers = {'Referer': url}

            _format = {
                'url': videourl,
                'format_id': 'http',
                'ext': 'mp4',
                'http_headers': headers
            }
            if check:
                _videoinfo = self._get_video_info(videourl, headers=headers)
                if not _videoinfo:
                    raise ExtractorError("error 404: no video info")
                else:
                    _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})

            return ({
                "id": videoid,
                "title": sanitize_filename(_title, restricted=True),
                "formats": [_format],
                "ext": "mp4",
                'extractor_key': self.ie_key(),
                'extractor': self.IE_NAME,
                'webpage_url': url})

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
            self.report_warning(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
