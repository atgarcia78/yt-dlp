import logging
import re
from urllib.parse import unquote

from .commonwebdriver import (
    raise_extractor_error,
    By,
    ConnectError,
    HTTPStatusError,
    SeleniumInfoExtractor,
    dec_on_exception,
    dec_on_exception2,
    dec_on_exception3,
    ec,
    limiter_1,
)
from ..utils import ExtractorError, sanitize_filename, try_get

logger = logging.getLogger("gayforiteu")


class getvideourl:
    def __call__(self, driver):
        el_video = driver.find_element(By.CSS_SELECTOR, 'video')
        if (video_url := el_video.get_attribute('src')):
            return unquote(video_url).replace("medialatest-cdn.gayforit.eu", "media.gayforit.eu")
        else:
            return False


class GayForITEUIE(SeleniumInfoExtractor):

    _VALID_URL = r'https?://(?:www\.)?gayforit\.eu/(?:(playvideo.php\?vkey\=.+)|(video/(?P<id>\d+)))'
    _SITE_URL = 'https://gayforit.eu'

    @dec_on_exception
    @limiter_1.ratelimit("gayforiteu", delay=True)
    def _send_request(self, url, **kwargs):

        if (driver := kwargs.get('driver')):
            driver.get(url)

    @dec_on_exception3
    @dec_on_exception2
    @limiter_1.ratelimit("gayforiteu", delay=True)
    def _get_video_info(self, url, **kwargs):

        try:
            return self.get_info_for_format(url, **kwargs)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    def _get_entry(self, url, **kwargs):

        driver = self.get_driver()
        try:

            _url = url
            self._send_request(_url, driver=driver)
            videoid = self._match_id(_url)
            if not videoid:
                el_video = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, 'video')))
                if not el_video:
                    raise_extractor_error('no el video')
                assert el_video
                videoid = el_video.get_attribute('poster').split('/')[-1].split('_')[-1].split('.')[0]
                _url = f'{self._SITE_URL}/video/{videoid}'
                self.to_screen({_url})
                driver.delete_all_cookies()
                self._send_request(_url, driver=driver)

            video_url = self.wait_until(driver, 30, getvideourl())

            if not video_url:
                raise ExtractorError("no video url")

            title = try_get(driver.find_elements(By.XPATH, "//li[label[text()='Title:']]"), lambda x: x[0].text.split('\n')[1].strip('[ ,_-]'))

            if not title:
                title = try_get(re.findall(r'GayForIt\.eu - Free Gay Porn Videos - (.+)', driver.title, re.IGNORECASE), lambda x: x[0])

            assert isinstance(title, str)

            self.logger_debug(f"[video_url] {video_url}")

            _headers = {"Referer": self._SITE_URL + "/"}

            el_quality = driver.find_elements(By.CLASS_NAME, 'item-quality')

            if el_quality:
                _formats = []
                for _el in el_quality:

                    _quality = try_get(re.search(r'(\d+p)', _el.get_attribute('innerText')), lambda x: x.groups()[0])
                    assert _quality
                    self.to_screen(f"quality:[{_quality}]")
                    _vurl = f"{video_url.split('_')[0]}_{_quality}.mp4?&{_quality}"
                    _format_id = f'http-{_quality}'
                    _format = {
                        'format_id': _format_id,
                        'height': int(_quality[:-1]),
                        'url': _vurl,
                        'http_headers': _headers,
                        'ext': 'mp4'
                    }

                    _info_video = self._get_video_info(_vurl, headers=_headers)

                    if not _info_video:
                        self.report_warning(f"[{url}] {_format_id} no video info")
                    else:
                        assert isinstance(_info_video, dict)
                        _info_video['url'] = _info_video['url'].replace("medialatest-cdn.gayforit.eu", "media.gayforit.eu")
                        _format.update(_info_video)

                    _formats.append(_format)

            else:
                _formats = [{
                    'format_id': 'http-mp4',
                    'url': video_url,
                    'http_headers': _headers,
                    'ext': 'mp4'
                }]
                _info_video = self._get_video_info(video_url, headers=_headers)
                if not _info_video:
                    raise ExtractorError("no video info")
                else:
                    assert isinstance(_info_video, dict)
                    _info_video['url'] = _info_video['url'].replace("medialatest-cdn.gayforit.eu", "media.gayforit.eu")
                    _formats[0].update(_info_video)

            entry = {
                'id': videoid,
                'title': sanitize_filename(title.strip(), restricted=True).replace('-', ''),
                'formats': _formats,
                'ext': 'mp4',
                'webpage_url': _url,
                'extractor': self.IE_NAME,
                'extractor_key': self.ie_key()
            }

            return entry

        except ExtractorError as e:
            logger.exception(repr(e))
            raise
        except Exception as e:
            logger.exception(repr(e))
            raise ExtractorError({repr(e)})
        finally:
            self.rm_driver(driver)

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        try:
            return self._get_entry(url)
        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(f"{repr(e)}")
            raise ExtractorError(repr(e))
