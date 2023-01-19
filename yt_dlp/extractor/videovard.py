import sys
import traceback
import time

from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import HTTPStatusError, ConnectError, WebDriverException, TimeoutException, dec_on_exception2, dec_on_exception3, dec_on_driver_timeout, SeleniumInfoExtractor, limiter_1, By, ec


class getvideourl:
    def __call__(self, driver):
        vpl = driver.find_element(By.ID, "vplayer")
        vid = driver.find_element(By.TAG_NAME, "video")

        try:
            vpl.click()
            time.sleep(3)
            vpl.click()
            if (_videourl := vid.get_attribute('src')):
                return _videourl
            else:
                return False

        except Exception:
            pass

        el_kal = driver.find_element(By.CSS_SELECTOR, "div.kalamana")
        el_kal.click()
        time.sleep(1)
        el_rul = driver.find_element(By.CSS_SELECTOR, "div.rulezco")
        el_rul.click()
        time.sleep(1)
        return False


class VideovardIE(SeleniumInfoExtractor):

    IE_NAME = "videovard"
    _SITE_URL = "https://videovard.sx/"
    _VALID_URL = r'https?://videovard\.\w\w/[e,v]/(?P<id>[^&]+)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https://videovard\.\w\w/[e,v]/.+?)\1']

    @dec_on_driver_timeout
    @dec_on_exception3
    @dec_on_exception2
    @limiter_1.ratelimit("videovard", delay=True)
    def send_multi_request(self, url, **kwargs):

        driver = kwargs.get('driver')
        pre = f'[send_req][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'

        if driver:
            try:
                driver.execute_script("window.stop();")
                driver.get(url)
            except Exception as e:
                self.report_warning(f"{pre}: error - {repr(e)}")
                e.msg = f'no webpage {e.msg}'
                raise e

        else:

            _type = kwargs.get('_type', None)
            headers = kwargs.get('headers', None)

            try:
                if not _type:
                    res = self.send_http_request(url, headers=headers)
                    return res
                else:
                    return self.get_info_for_format(url, headers=headers)
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"{pre}: error - {repr(e)}")

    def _real_initialize(self):

        super()._real_initialize()

    def _get_entry(self, url, **kwargs):

        driver = self.get_driver(devtools=True)
        driver.set_page_load_timeout(10)

        try:

            self.report_extraction(url)

            videoid = self._match_id(url)

            _formats = None

            self.send_multi_request(_wurl := (url.replace('/e/', '/v/').replace('videovard.to', 'videovard.sx')), driver=driver)

            title = try_get(self.wait_until(driver, 60, ec.presence_of_element_located((By.TAG_NAME, "h1"))), lambda x: x.text)

            video_url = self.wait_until(driver, 60, getvideourl())

            _headers = {'Referer': self._SITE_URL, 'Origin': self._SITE_URL.strip("/")}

            if video_url:
                if not video_url.startswith('blob'):

                    if ".m3u8" not in video_url:
                        _info_video = self.send_multi_request(video_url, _type="info_video", headers=_headers)
                        if not _info_video:
                            raise ExtractorError("no info video")
                        _formats = [{'format_id': 'http-mp4', 'url': _info_video['url'], 'filesize': _info_video['filesize'], 'ext': 'mp4'}]

                    elif "master.m3u8" in video_url:
                        _formats = self._extract_m3u8_formats_and_subtitles(video_url, video_id=videoid, ext="mp4",
                                                                            entry_protocol="m3u8_native", m3u8_id="hls", headers=_headers)
                else:
                    m3u8_url, m3u8_doc = try_get(self.scan_for_request(driver, r"master.m3u8"), lambda x: (x.get('url'), x.get('content')) if x else (None, None))
                    if m3u8_url:
                        if not m3u8_doc:
                            m3u8_doc = try_get(self.send_multi_request(m3u8_url, headers=_headers), lambda x: (x.content).decode('utf-8', 'replace'))

                        if m3u8_doc:
                            _formats, _ = self._parse_m3u8_formats_and_subtitles(
                                m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")

            if _formats:
                self._sort_formats(_formats)
            else:
                raise ExtractorError(f"[{url}] Couldnt find any video format")

            for _format in _formats:
                if (_head := _format.get('http_headers')):
                    _head.update(_headers)
                else:
                    _format.update({'http_headers': _headers})

            return ({
                "id": videoid,
                "title": sanitize_filename(title, restricted=True),
                "formats": _formats,
                "webpage_url": _wurl,
                "ext": "mp4"})

        except (WebDriverException, TimeoutException) as e:
            raise ExtractorError(f"error 404 - {e.msg}")
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(f"{repr(e)} {str(e)}")
        finally:
            self.rm_driver(driver)

    def _real_extract(self, url):
        self.report_extraction(url)

        try:

            if not self.get_param('embed'):
                _check = True
            else:
                _check = False

            return self._get_entry(url, check=_check)

        except (ExtractorError, WebDriverException, TimeoutException):
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
