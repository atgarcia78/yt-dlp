import logging
import re
import threading

from .commonwebdriver import (
    By,
    ConnectError,
    HTTPStatusError,
    SeleniumInfoExtractor,
    dec_on_exception2,
    dec_on_exception3,
    dec_on_driver_timeout,
    ec,
    limiter_0_1,
    cast,
    WebElement
)

from ..utils import (
    ExtractorError,
    traverse_obj,
    sanitize_filename,
    try_get,
)

logger = logging.getLogger('mrman')


class MrManBaseIE(SeleniumInfoExtractor):
    _SITE_URL = 'https://www.mrman.com/'
    _NETRC_MACHINE = 'mrman'
    _LOCK = threading.Lock()
    _CLIENT = None
    _HEADERS = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'X-Requested-With': 'XMLHttpRequest',
        'X-MOD-SBB-CTYPE': 'xhr',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache'}

    @classmethod
    @dec_on_exception3
    @dec_on_exception2
    @dec_on_driver_timeout
    @limiter_0_1.ratelimit("mrman2", delay=True)
    def _send_request(cls, url, driver=None, **kwargs):

        if driver:
            driver.get(url)
        else:
            try:
                return cls._send_http_request(url, client=MrManBaseIE._CLIENT, **kwargs)
            except (HTTPStatusError, ConnectError) as e:
                logger.debug(f"[send_request] {cls._get_url_print(url)}: error - {repr(e)}")

    def _login(self, driver):

        username, password = self._get_login_info()

        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)

        self.report_login()

        MrManBaseIE._send_request(self._SITE_URL, driver)
        el_menu = self.wait_until(driver, 10, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))
        if el_menu:
            self.logger_debug("Login already")
            return

        el_login = cast(WebElement, self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a#login-url"))))
        if el_login:
            el_login.click()
        el_username = cast(WebElement, self.wait_until(driver, 30, ec.presence_of_element_located(
            (By.CSS_SELECTOR, "input#login.form-control"))))
        el_password = cast(WebElement, self.wait_until(driver, 30, ec.presence_of_element_located(
            (By.CSS_SELECTOR, "input#password.form-control"))))
        el_login = cast(WebElement, self.wait_until(driver, 30, ec.presence_of_element_located(
            (By.CSS_SELECTOR, "input.btn.btn-submit"))))
        if el_username and el_password and el_login:
            el_username.send_keys(username)
            self.wait_until(driver, 2)
            el_password.send_keys(password)
            self.wait_until(driver, 2)
            el_login.submit()
            el_menu = self.wait_until(driver, 10, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))

            if not el_menu:
                self.raise_login_required("Invalid username/password")
            else:
                self.logger_debug("Login OK")

    def _real_initialize(self):

        super()._real_initialize()

        with MrManBaseIE._LOCK:
            if not MrManBaseIE._CLIENT:
                MrManBaseIE._CLIENT = self._CLIENT
                for cookie in self._COOKIES_JAR:
                    if 'mrman.com' in cookie.domain:
                        MrManBaseIE._CLIENT.cookies.set(name=cookie.name, value=cookie.value, domain=cookie.domain)
                if 'toniomad' in cast(str, try_get(MrManBaseIE._send_request(self._SITE_URL), lambda x: x.text if x else '')):
                    self.logger_info("Already logged with cookies")

                # else:
                #     driver = self.get_driver()
                #     try:
                #         MrManBaseIE._send_request(self._SITE_URL, driver)
                #         driver.add_cookie({'name': 'rta_terms_accepted', 'value': 'true', 'domain': '.mrman.com'})
                #         driver.add_cookie({'name': 'videosPerRow', 'value': '5', 'domain': '.mrman.com'})
                #         self._login(driver)
                #         MrManBaseIE._COOKIES = driver.get_cookies()
                #         for cookie in MrManBaseIE._COOKIES:
                #             MrManBaseIE._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
                #         if 'atgarcia' in cast(str, try_get(MrManBaseIE._send_request(self._SITE_URL), lambda x: x.text if x else '')):
                #             self.logger_debug("Already logged with cookies")
                #             MrManBaseIE._MRMANINIT = True
                #     except Exception:
                #         self.to_screen("error when login")
                #         raise
                #     finally:
                #         self.rm_driver(driver)


class MrManPlayListIE(MrManBaseIE):
    IE_NAME = 'mrman:playlist'  # type: ignore
    IE_DESC = 'mrman:playlist'
    _VALID_URL = r'https?://(?:www\.)?mrman\.com/(?:playlist/|.*-p)(?P<playlist_id>\d*)/?(\?(?P<query>.+))?'

    def _get_playlist(self, url):

        premsg = f"[get_playlist][{url}]"
        playlist_id, query = try_get(re.match(self._VALID_URL, url), lambda x: x.group('playlist_id', 'query'))  # type: ignore
        if query:
            params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
        else:
            params = {}

        self.logger_debug(f"{premsg} playlist_id: {playlist_id} params: {params}")

        _url = url
        if '/playlist/' not in _url:
            _url = f'https://www.mrman.com/playlist/{playlist_id}'

        info = try_get(MrManBaseIE._send_request(_url, headers=MrManBaseIE._HEADERS), lambda x: x.json().get('config') if x else None)

        _entries = []
        _headers = {'Origin': 'https://www.mrman.com', 'Referer': 'https://www.mrman.com/'}
        for clip in info['playlist']:
            _url = traverse_obj(clip, ('sources', 0, 'file'))
            _id = try_get(clip, lambda x: str(clip['id']))
            _title = try_get(clip, lambda x: sanitize_filename(clip['title'], restricted=True))
            _m3u8doc = try_get(self._send_request(_url, headers=MrManBaseIE._HEADERS), lambda x: re.sub(r'(#EXT-X-I-FRAME-STREAM-INF:.*\n)', '', x.text) if x else None)
            _fmts, _ = self._parse_m3u8_formats_and_subtitles(_m3u8doc, m3u8_url=_url, video_id=_id, ext='mp4', m3u8_id='hls')
            list(map(lambda x: try_get(x.get('http_headers'), lambda y: y.update(_headers) if y else x.update({'http_headers': _headers})), _fmts))
            _entry = {
                "id": _id,
                "title": _title,
                "webpage_url": f"https://www.mrman.com/clipplayer/{_id}",
                "original_url": url,
                "formats": _fmts,
                "ext": "mp4"
            }
            _entries.append(_entry)

        if not _entries:
            raise ExtractorError("cant find any video", expected=True)

        return self.playlist_result(_entries, playlist_id, sanitize_filename(info['title'], restricted=True))

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        try:
            return self._get_playlist(url)
        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(repr(e), expected=True)
