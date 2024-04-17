import re
import sys
import time
import traceback

from yt_dlp_plugins.extractor.commonwebdriver import (
    By,
    SeleniumInfoExtractor,
    dec_on_exception,
    limiter_5,
)

from ..utils import ExtractorError, sanitize_filename, try_get


class getvideourl:
    def __init__(self, logger):
        self.logger = logger

    def __call__(self, driver):

        el_uv = driver.find_element(By.ID, 'uverlay')
        try:
            el_uv.click()
            time.sleep(2)
        except Exception as e:
            self.logger(repr(e))

        el_video = driver.find_element(By.TAG_NAME, 'video')
        try:
            el_video.click()
            time.sleep(2)
        except Exception as e:
            self.logger(repr(e))
        if (videourl := el_video.get_attribute('src')):
            return videourl
        else:
            return False


class StreamplayIE(SeleniumInfoExtractor):

    IE_NAME = 'streamplay'
    _VALID_URL = r'https?://(?:www\.)?streamplay\.(?P<host>[^/]+)/(?P<id>[^\/$]+)(?:\/|$)'

    def _get_video_info(self, url, headers):
        self.logger_debug(f"[get_video_info] {url}")
        return self.get_info_for_format(url, headers=headers)

    def _send_request(self, url, driver):
        self.logger_debug(f"[send_request] {url}")
        driver.get(url)

    @dec_on_exception
    @limiter_5.ratelimit("streamplay", delay=True)
    def request_to_host(self, _type, url, driver=None, headers=None):

        if _type == "video_info":
            return self._get_video_info(url, headers)
        elif _type == "url_request":
            self._send_request(url, driver)

    @SeleniumInfoExtractor.syncsem()
    def _real_extract(self, url):

        self.report_extraction(url)

        driver = self.get_driver(noheadless=True)

        try:

            # self._send_request(driver, url)
            self.request_to_host("url_request", url, driver)
            video_url = self.wait_until(driver, 30, getvideourl(self.to_screen))
            if not video_url:
                raise ExtractorError("no video url")

            title = driver.title.replace("Watch ", "")
            videoid = self._match_id(url)
            host = try_get(re.search(self._VALID_URL, url), lambda x: x.group('host'))
            _headers = {'Referer': f'https://streamplay.{host}/'}
            # info_video = self._get_video_info(video_url)

            info_video = self.request_to_host("video_info", video_url, headers=_headers)

            if not info_video:
                raise Exception("error video info")

            _format = {
                'format_id': 'http-mp4',
                'url': info_video.get('url', video_url),
                'filesize': info_video.get('filesize'),
                'http_headers': _headers,
                'ext': 'mp4'
            }

            _entry_video = {
                'id': videoid,
                'title': sanitize_filename(title, restricted=True),
                'formats': [_format],
                'ext': 'mp4'
            }

            return _entry_video
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            try:
                self.rm_driver(driver)
            except Exception:
                pass
