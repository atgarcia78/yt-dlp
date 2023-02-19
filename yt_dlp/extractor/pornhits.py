import sys
import traceback
import html
import re
import time

from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import (
    dec_on_driver_timeout,
    dec_on_exception2,
    dec_on_exception3,
    SeleniumInfoExtractor,
    limiter_2,
    By,
    ec,
    HTTPStatusError,
    ConnectError)


class get_title:
    def __call__(self, driver):
        if any(_ == driver.title.strip() for _ in ("TXXX.com", "HotMovs.com")):
            return False
        else:
            return (driver.title)


class getvideourl:
    def __init__(self, logger):
        self.logger = logger

    def __call__(self, driver):
        el_player = driver.find_elements(By.CSS_SELECTOR, "#player-1")
        self.logger(f"[getvideourl] el_player {el_player}")
        if not el_player:
            return False
        try:
            el_player[0].click()
            time.sleep(1)
        except Exception as e:
            self.logger(f"[getvideourl] el_player_click error {str(e)}")

        el_media = driver.find_elements(By.CSS_SELECTOR, ".jw-media")
        self.logger(f"[getvideourl] el_media {el_media}")
        try:
            el_media[0].click()
            time.sleep(1)
        except Exception as e:
            self.logger(f"[getvideourl] el_media_click error {str(e)}")

        el_video = el_media[0].find_elements(By.TAG_NAME, "video")
        self.logger(f"[getvideourl] el_video {el_video}")
        try:
            el_video[0].click()
            time.sleep(1)
        except Exception as e:
            self.logger(f"[getvideourl] el_video_click error {str(e)}")

        videourl = el_video[0].get_attribute('src')
        el_video[0].click()
        self.logger(f"[getvideourl] videourl {videourl}")
        if videourl:
            return {"OK": videourl}
        else:
            return False


class BasePornhitsIE(SeleniumInfoExtractor):

    _SITE_URL = ""

    @dec_on_exception2
    @dec_on_exception3
    def _get_video_info(self, url, msg=None, headers={}):

        with limiter_2.ratelimit(self.IE_NAME, delay=True):
            try:
                pre = '[get_video_info]'
                if msg:
                    pre = f'{msg}{pre}'
                self.logger_debug(f"{pre} {self._get_url_print(url)}")
                _headers = {'Range': 'bytes=0-', 'Referer': headers.get('Referer') or self._SITE_URL,
                            'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'same-origin',
                            'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}

                return self.get_info_for_format(url, headers=_headers)
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    @dec_on_driver_timeout
    @dec_on_exception2
    @dec_on_exception3
    def send_multi_request(self, url, driver=None, _type=None, headers=None):

        with limiter_2.ratelimit(self.IE_NAME, delay=True):

            if driver:
                driver.execute_script("window.stop();")
                driver.get(url)
            else:
                try:
                    if not _type:
                        return self.send_http_request(url, headers=headers)
                    else:
                        return self.get_info_for_format(url, headers=headers)
                except (HTTPStatusError, ConnectError) as e:
                    self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    def _get_entry(self, url, **kwargs):

        check = kwargs.get('check', False)
        msg = kwargs.get('msg', None)

        driver = None

        try:

            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg:
                pre = f'{msg}{pre}'
            videoid = self._match_id(url)
            driver = self.get_driver(devtools=True)

            if self.IE_NAME == 'pornhits' and 'embed.php' in url:
                webpage = try_get(
                    self.send_multi_request(url),
                    lambda x: re.sub('[\t\n]', '', html.unescape(x.text)) if x else None)

                assert webpage
                url = try_get(
                    re.findall(r'/video/%s/([^\'\")]+)[\'\"]' % videoid, webpage),
                    lambda x: f'{self._SITE_URL}video/{videoid}/{x[0]}')

                assert url

            self.send_multi_request(url, driver)

            if self.IE_NAME == "pornhits" or (
                    (self.IE_NAME == 'txxx' or self.IE_NAME == 'hotmovs') and '/videos/' in url):
                title = try_get(
                    self.wait_until(driver, 60, ec.presence_of_element_located((By.TAG_NAME, "h1"))),
                    lambda x: x.text)

            else:
                title = try_get(
                    self.wait_until(driver, 60, get_title()),
                    lambda x: x.replace('Porn Video | HotMovs.com', '').strip())

            _formats = []

            if self.IE_NAME == 'txxx':
                videourl = try_get(self.wait_until(driver, 30, getvideourl(self.to_screen)), lambda x: x.get("OK"))

                if videourl:

                    _headers = {'Referer': driver.current_url}

                    _format = {
                        'format_id': 'http-mp4',
                        'url': videourl,
                        'ext': 'mp4',
                        'http_headers': _headers,
                    }
                    if check:
                        _videoinfo = self._get_video_info(videourl, msg=pre, headers=_headers)
                        if not _videoinfo:
                            raise ExtractorError("error 404: no video info")
                        else:
                            _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})

                    _formats.append(_format)

            if not _formats:

                _headers = {'Referer': self._SITE_URL}

                m3u8_url, m3u8_doc = try_get(
                    self.scan_for_request(driver, r".mp4$"),  # type: ignore
                    lambda x: (x.get('url'), x.get('content'))
                    if x else (None, None))
                if m3u8_url:
                    if not m3u8_doc:
                        m3u8_doc = try_get(
                            self.send_multi_request(m3u8_url, headers=_headers),
                            lambda x: (x.content).decode('utf-8', 'replace'))

                    if m3u8_doc:
                        _formats, _ = self._parse_m3u8_formats_and_subtitles(
                            m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")

                if not _formats:
                    raise ExtractorError("no formats")

                for _format in _formats:
                    if (_head := _format.get('http_headers')):
                        _head.update(_headers)
                    else:
                        _format.update({'http_headers': _headers})

            return ({
                "id": videoid,
                "title": sanitize_filename(title, restricted=True),
                "formats": _formats,
                "webpage_url": url,
                "ext": "mp4"})

        except ExtractorError as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(repr(e))
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


class TxxxIE(BasePornhitsIE):
    IE_NAME = "txxx"  # type: ignore
    _SITE_URL = "https://txxx.com/"
    _VALID_URL = r'https?://(video)?txxx.com/(?:embed|videos)/(?P<id>\d+)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https://(video)?txxx\.com/embed/.+?)\1']


class HotMovsIE(BasePornhitsIE):
    IE_NAME = "hotmovs"  # type: ignore
    _SITE_URL = "https://hotmovs.com/"
    _VALID_URL = r'https?://hotmovs.com/(?:embed|videos)/(?P<id>\d+)'


class PornhitsIE(BasePornhitsIE):
    IE_NAME = "pornhits"  # type: ignore
    _SITE_URL = "https://www.pornhits.com/"
    _VALID_URL = r'https?://(?:www)?.pornhits.com/(?:embed\.php\?id=|video/)(?P<id>\d+)'
