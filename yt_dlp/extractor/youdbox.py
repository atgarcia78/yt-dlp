import sys
import traceback


from ..utils import ExtractorError, sanitize_filename
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_15, By


class getvideourl:
    def __call__(self, driver):
        el_video = driver.find_element(By.ID, "vjsplayer_html5_api")
        if not (_videourl := el_video.get_attribute('src')):
            el_source = el_video.find_element(By.TAG_NAME, "source")
            _videourl = el_source.get_attribute('src')
            if not _videourl:
                return False
            else:
                return _videourl
        else:
            return _videourl


class YoudBoxIE(SeleniumInfoExtractor):

    IE_NAME = 'youdbox'
    _VALID_URL = r'https?://(?:www\.)?you?dbox\.(?:net|org|com)/(embed-)?(?P<id>[^\./]+)[\./]'

    def _get_video_info(self, url):
        self.logger_debug(f"[get_video_info] {url}")
        return self.get_info_for_format(url)

    def _send_request(self, driver, url):
        self.logger_debug(f"[send_request] {url}")
        driver.get(url)

    @dec_on_exception
    @limiter_15.ratelimit("youdbox", delay=True)
    def request_to_host(self, _type, *args):

        if _type == "video_info":
            return self._get_video_info(*args)
        elif _type == "url_request":
            self._send_request(*args)

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        driver = self.get_driver()

        try:

            _url = url.replace("embed-", "")

            self.request_to_host("url_request", driver, _url)

            video_url = self.wait_until(driver, 60, getvideourl())

            if not video_url:
                raise ExtractorError("no video url")
            title = driver.title.replace("mp4", "").replace("Download", "").replace("download", "").strip()
            videoid = self._match_id(url)

            # _videoinfo = self._get_video_info(video_url)
            _videoinfo = self.request_to_host("video_info", video_url)

            if not _videoinfo:
                raise Exception("error video info")

            _format = {
                'format_id': 'http-mp4',
                'url': _videoinfo['url'],
                'filesize': _videoinfo['filesize'],
                'ext': 'mp4'
            }

            _entry_video = {
                'id': videoid,
                'title': sanitize_filename(title, restricted=True),
                'formats': [_format],
                'ext': 'mp4'
            }

            if not _entry_video:
                raise ExtractorError("no video info")
            else:
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
