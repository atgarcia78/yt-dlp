import logging
import re
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
    raise_extractor_error,
)

from ..utils import ExtractorError, sanitize_filename, try_get

logger = logging.getLogger("gayforiteu")


class getvideourl:
    def __init__(self, inc_id=False):
        self.inc_id = inc_id

    def __call__(self, driver):
        if not self.inc_id:
            el_video = driver.find_element(By.ID, 'my-video')
            if (_sources := el_video.find_elements(By.TAG_NAME, 'source')):
                _res = {}
                for i, _source in enumerate(_sources):
                    if (video_url := _source.get_attribute('src')):
                        video_url = unquote(video_url).replace("medialatest-cdn.gayforit.eu", "media.gayforit.eu")
                        res = _source.get_attribute('res') or f'NORES{i}'
                        _res[res.strip()] = video_url
                return _res
            else:
                return False
        else:
            el_video = driver.find_element(By.CSS_SELECTOR, 'video')
            if (_poster := el_video.get_attribute('poster')) and (video_url := el_video.get_attribute('src')):
                videoid = _poster.split('/')[-1].split('_')[-1].split('.')[0]
                return {'videoid': videoid, 'videourl': video_url}
            else:
                return False


class GayForITEUIE(SeleniumInfoExtractor):

    _VALID_URL = r'https?://(?:www\.)?gayforit\.eu/(?:(playvideo.php\?vkey\=.+)|(video/(?P<id>\d+)))'
    _SITE_URL = 'https://gayforit.eu'

    @dec_on_exception
    @limiter_1.ratelimit("gayforiteu2", delay=True)
    def _send_request(self, url, **kwargs):

        if (driver := kwargs.get('driver')):
            driver.get(url)

    @dec_on_exception3
    @dec_on_exception2
    @limiter_1.ratelimit("gayforiteu1", delay=True)
    def _get_video_info(self, url, **kwargs):

        try:
            return self.get_info_for_format(url, **kwargs)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    @SeleniumInfoExtractor.syncsem()
    def _get_entry(self, url, **kwargs):

        _pre = f"[get_entry][{url}]"
        videoid = self._match_id(url)
        if 'www.' in url:
            self._SITE_URL = 'https://www.gayforit.eu'
        _url = None
        driver = self.get_driver()
        try:
            if not driver:
                raise_extractor_error('error driver')
            else:
                driver.delete_all_cookies()
                self._send_request(url, driver=driver)
                if not videoid:
                    if (_res := self.wait_until(driver, 10, getvideourl(inc_id=True))):
                        videoid = _res['videoid']
                        _url = f'{self._SITE_URL}/video/{videoid}'
                        if 'THIS-VIDEO-HAS-BEEN-REMOVED' in _res["videourl"]:
                            raise_extractor_error('404 video not found')
                        driver.delete_all_cookies()
                        self._send_request(_url, driver=driver)

                if 'error.php' in driver.current_url:
                    raise_extractor_error('404 video not found')

                _sources = self.wait_until(driver, 30, getvideourl())
                if not isinstance(_sources, dict):
                    raise_extractor_error("no video url")
                else:
                    self.logger_debug(f"{_pre} video_url [{_sources}]")
                    if not (title := (
                        try_get(driver.find_elements(By.XPATH, "//li[label[text()='Title:']]"), lambda x: x[0].text.split('\n')[1].strip('[ ,_-]'))
                        or try_get(re.findall(r'GayForIt\.eu - Free Gay Porn Videos - (.+)', driver.title, re.IGNORECASE), lambda x: x[0]))
                    ):
                        raise_extractor_error("no title")
                    else:
                        _headers = {"Referer": self._SITE_URL + "/"}

                        _formats = []
                        for _res, _vurl in _sources.items():

                            if not _res.replace('p', '').isdecimal():
                                _res = try_get(re.search(r'_(?P<res>\d+p)\.mp4', _vurl), lambda x: x.groupdict()['res'])

                            _format = {
                                'format_id': f"http-{_res}" if _res else "http",
                                'height': int(_res[:-1]) if _res else None,
                                'url': _vurl,
                                'http_headers': _headers,
                                'ext': 'mp4'
                            }

                            _info_video = self._get_video_info(_vurl, headers=_headers)

                            if not isinstance(_info_video, dict):
                                self.report_warning(f"{_pre} {_res} no video info")
                            else:
                                _info_video['url'] = _info_video['url'].replace("medialatest-cdn.gayforit.eu", "media.gayforit.eu")
                                _format.update(_info_video)

                            _formats.append(_format)

                        entry = {
                            'id': videoid,
                            'title': sanitize_filename(title.strip(), restricted=True).replace('-', ''),
                            'formats': _formats,
                            'ext': 'mp4',
                            'webpage_url': url,
                            'extractor': self.IE_NAME,
                            'extractor_key': self.ie_key()
                        }

                        return entry

        except Exception as e:
            logger.debug(f"{_pre} {repr(e)}")
            return {'error': e, '_all_urls': [_el for _el in (url, _url) if _el]}
        finally:
            self.rm_driver(driver)

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        try:
            if 'error' in (_info := self._get_entry(url)):
                raise _info['error']
            else:
                return _info
        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))
