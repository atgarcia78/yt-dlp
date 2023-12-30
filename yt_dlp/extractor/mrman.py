import logging
import re
import threading

from .commonwebdriver import (
    ConnectError,
    HTTPStatusError,
    SeleniumInfoExtractor,
    dec_on_exception2,
    dec_on_exception3,
    limiter_0_1,
)
from ..utils import (
    ExtractorError,
    get_elements_by_class,
    sanitize_filename,
    traverse_obj,
    try_get,
    urlencode_postdata,
)

logger = logging.getLogger('mrman')


class MrManBaseIE(SeleniumInfoExtractor):
    _SITE_URL = 'https://www.mrman.com/'
    _LOGIN_URL = 'https://www.mrman.com/account/login'
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

    _HEADERS_POST = {
        'Accept': "".join(
            [
                '*/*;q=0.5, text/javascript, application/javascript, ',
                'application/ecmascript, application/x-ecmascript'
            ]),
        'Referer': 'https://www.mrman.com/',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest',
        'X-MOD-SBB-CTYPE': 'xhr',
        'Origin': 'https://www.mrman.com',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache'}

    _LOGIN_OK = '"accountState":"premium"'

    @classmethod
    @dec_on_exception3
    @dec_on_exception2
    @limiter_0_1.ratelimit("mrman2", delay=True)
    def _send_request(cls, url, **kwargs):

        try:
            return cls._send_http_request(url, client=MrManBaseIE._CLIENT, **kwargs)
        except (HTTPStatusError, ConnectError) as e:
            logger.debug(f"[send_request] {cls._get_url_print(url)}: error - {repr(e)}")

    def _login(self):

        username, password = self._get_login_info()

        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)

        self.report_login()

        _result_login = False

        webpage = self._download_webpage(self._SITE_URL, None)
        if self._LOGIN_OK in webpage:
            _result_login = True
            self.logger_info("[login] already logged")
            return _result_login

        csrf_token = self._html_search_meta(
            'csrf-token', webpage, 'csrf token', default=None)
        _headers = MrManBaseIE._HEADERS_POST | {'X-CSRF-Token': csrf_token}

        _hidden = try_get(
            get_elements_by_class('new_customer', webpage),
            lambda x: self._hidden_inputs(x[0]) if x else None)

        _req = {
            'customer[username]': username,
            'customer[password]': password,
            'customer[remember_me]': '0'} | _hidden

        if _respost := self._download_json(
                self._LOGIN_URL, None, note=None, fatal=False,
                data=urlencode_postdata(_req), headers=_headers):

            if _respost.get('success'):
                webpage = self._download_webpage(self._SITE_URL, None)
                if self._LOGIN_OK in webpage:
                    _result_login = True

        self.logger_info(
            f'[login] result login: {"OK" if _result_login else "NOK"}')

        return _result_login

    def _real_initialize(self):

        super()._real_initialize()

        with MrManBaseIE._LOCK:
            if not MrManBaseIE._CLIENT:
                MrManBaseIE._CLIENT = self._CLIENT
                for cookie in self._FF_COOKIES_JAR.get_cookies_for_url(self._SITE_URL):
                    MrManBaseIE._CLIENT.cookies.jar.set_cookie(cookie)
                if self._LOGIN_OK in try_get(
                        MrManBaseIE._send_request(self._SITE_URL),
                        lambda x: x.text if x else ''):
                    self.logger_info("Already logged with cookies")

                else:
                    if self._login():
                        for cookie in self.cookiejar.get_cookies_for_url(self._SITE_URL):
                            MrManBaseIE._CLIENT.cookies.jar.set_cookie(cookie)
                        if self._LOGIN_OK in try_get(
                                MrManBaseIE._send_request(self._SITE_URL),
                                lambda x: x.text if x else ''):
                            self.logger_info("Logged OK with cookies after login")


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
