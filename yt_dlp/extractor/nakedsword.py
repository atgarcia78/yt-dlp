from __future__ import annotations

import base64
import contextlib
import html
import json
import logging
import netrc
import os
import re
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from .commonwebdriver import (
    By,
    ConnectError,
    HTTPStatusError,
    ProgressTimer,
    ReExtractInfo,
    Response,
    SeleniumInfoExtractor,
    StatusStop,
    cached_classproperty,
    dec_on_driver_timeout,
    dec_retry,
    ec,
    limiter_0_1,
    my_dec_on_exception,
    my_jitter,
    raise_extractor_error,
    raise_reextract_info,
    run_operation_in_executor,
)
from ..utils import (
    ExtractorError,
    YoutubeDLError,
    extract_timezone,
    int_or_none,
    js_to_json,
    sanitize_filename,
    str_or_none,
    traverse_obj,
    try_call,
    try_get,
)
from ..utils.networking import random_user_agent

_SCRIPT_IS_LOGGED = '''
if (localStorage.getItem("fe-token")) {
    return true
} else {
    return false
}
'''

_SCRIPT_SETTINGS = '''
localStorage.removeItem("fe-user-data");
localStorage.removeItem("fe-expires");
localStorage.removeItem("fe-token");
localStorage.removeItem("nats_code");
localStorage.removeItem("refreshTimeoutId");
localStorage.setItem("user-settings", '{"volume":0,"defaultFormat":"application/x-mpegURL"}');
'''

logger = logging.getLogger('nakedsword')


@dataclass
class info_scene:
    index: int
    sceneid: str | None
    title: str
    url: str
    m3u8_url: str
    movieurl: str
    movieid: str
    nentries: int


dec_on_reextract = my_dec_on_exception(
    ReExtractInfo, max_time=300, jitter='my_jitter', raise_on_giveup=True, interval=30)

dec_on_reextract_1 = my_dec_on_exception(
    ReExtractInfo, max_time=300, jitter='my_jitter', raise_on_giveup=True, interval=1)

dec_on_exception = my_dec_on_exception(
    (TimeoutError, ExtractorError),
    max_tries=3, jitter='my_jitter', raise_on_giveup=False, interval=1)


def _wait_for_either(progress_bar, check: Callable, timeout: float | int):

    start = time.monotonic()
    while (time.monotonic() - start < timeout):
        check()
        time.sleep(1)
        progress_bar.update()
        progress_bar.print('Waiting')  # type: ignore
    return ''


class forlogin:
    def __call__(self, driver):
        el_uas = driver.find_element(By.CSS_SELECTOR, "div.UserActions")
        el_loggin = el_uas.find_element(By.CLASS_NAME, "LoginWrapper")
        el_loggin.click()
        return True


class forlogout:
    def __call__(self, driver):
        el_uas = driver.find_element(By.CSS_SELECTOR, "div.UserActions")
        el_loggin = el_uas.find_element(By.CLASS_NAME, "UserAction")
        el_loggin.click()
        time.sleep(1)
        return True


class closeDeals:
    def __call__(self, driver):
        el_but = driver.find_elements(by=By.CLASS_NAME, value="MemberDealsModalCLoseBtn")
        logger.debug(f"[closedeals] but:{el_but}")
        if not el_but:
            return False
        _ok = False
        for _el_but in el_but:
            try:
                _el_but.click()
                _ok = True
            except Exception as e:
                logger.debug(f"[closedeals] click but error - {repr(e)}")
        if _ok:
            logger.debug("[closedeals] click but ok")
            return True
        else:
            return False


class NakedSwordError(YoutubeDLError):
    pass


class NakedSwordBaseIE(SeleniumInfoExtractor):

    _SITE_URL = 'https://www.nakedsword.com/'
    _API_URLS = {
        'login': 'https://ns-api.nakedsword.com/frontend/auth/login',
        'logout': 'https://ns-api.nakedsword.com/frontend/auth/logout',
        'refresh': 'https://ns-api.nakedsword.com/frontend/auth/refresh',
        'movies': 'https://ns-api.nakedsword.com/frontend/movies',
        'scenes': 'https://ns-api.nakedsword.com/frontend/scenes',
        'streaming': 'https://ns-api.nakedsword.com/frontend/streaming'
    }
    _NETRC_MACHINE = 'nakedsword'
    _LOCK = Lock()
    _HAR_LOCK = Lock()
    _TAGS = {}
    _MAXPAGE_SCENES_LIST = 2
    _CLASSCLIENT = None
    _UA = {}
    _INST_IE = None
    _USERTOKEN = None
    _INFO_DRIVER = None
    headers_api = {}
    timer = ProgressTimer()
    call_lock = Lock()
    _JS_SCRIPT = '/Users/antoniotorres/.config/yt-dlp/nsword_getxident.js'
    _HEADERS = {
        "POST": {
            "AUTH": {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept-Language': 'en-US,en;q=0.5',
                'Authorization': None,
                'Connection': 'keep-alive',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://www.nakedsword.com',
                'Referer': 'https://www.nakedsword.com/',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'TE': 'trailers',
                'User-Agent': None,
                'x-ident': None}},
        "DELETE": {
            "LOGOUT": {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept-Language': 'en-US,en;q=0.5',
                'Authorization': None,
                'Connection': 'keep-alive',
                'doNotRefreshToken': 'true',
                'Origin': 'https://www.nakedsword.com',
                'Referer': 'https://www.nakedsword.com/',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'TE': 'trailers',
                'User-Agent': None,
                'x-ident': None}},
        "FINAL": {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.5',
            'Authorization': None,
            'Connection': 'keep-alive',
            'Origin': 'https://www.nakedsword.com',
            'Referer': 'https://www.nakedsword.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'TE': 'trailers',
            'User-Agent': None,
            'X-CSRF-TOKEN': None,
            'x-ident': None},
        "MPD": {
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Origin': 'https://www.nakedsword.com',
            'Referer': 'https://www.nakedsword.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'TE': 'trailers',
            'User-Agent': None},
        "HTTP_HEADERS": {
            'Origin': 'https://www.nakedsword.com',
            'Referer': 'https://www.nakedsword.com/'}}
    _MOVIES = {}

    def close(self):
        try:
            NakedSwordBaseIE.API_LOGOUT(msg='[close]', _logger=self.logger_info)
        except Exception:
            pass
        finally:
            super().close()

    @cached_classproperty
    def _APP_DATA_PASSPHRASE(cls):
        logger.debug("get app_data['PASSPHRASE']")
        return cls._get_app_data_passphrase()

    @classmethod
    @dec_retry
    @dec_on_reextract
    def API_LOGIN(cls, force=False, msg=None, _logger=None):
        _pre = msg or ''
        if not _logger:
            _logger = logger.debug
        if cls._USERTOKEN and cls.headers_api and not force:
            _logger(f'{_pre}[API_LOGIN] skipping login')
            return True
        _logout = False

        try:
            if cls._get_api_basic_auth(force=force):
                _logger(f"{_pre}[API_LOGIN] OK")
                return True
            else:
                raise_extractor_error("couldnt auth")
        except ReExtractInfo:
            raise
        except ExtractorError as e:
            _logout = True
            raise_reextract_info(f"{_pre}[API_LOGIN] couldnt auth {str(e)}", _from=e)
        except Exception as e:
            _logger(f"{_pre}[API_LOGIN] {str(e)}")
            raise_extractor_error(f"{_pre}[API_LOGIN] error get auth {str(e)}", _from=e)
        finally:
            if _logout:
                cls._logout_api()

    @classmethod
    def _get_api_basic_auth(cls, force=False) -> bool:
        if cls._USERTOKEN and cls.headers_api and not force:
            logger.debug('[get_api_auth] skipping getting new auth')
            return True

        if (xident := cls._get_api_xident()):
            username, pwd = try_get(
                netrc.netrc(os.path.expandvars('$HOME/.netrc')).authenticators(cls._NETRC_MACHINE),
                lambda x: (x[0], x[2])) or (None, None)
            _headers_post = cls._HEADERS["POST"]["AUTH"].copy()
            _auth = base64.urlsafe_b64encode(f"{username}:{pwd}".encode()).decode('utf-8')
            _headers_post.update({'x-ident': xident, 'Authorization': f'Basic {_auth}'})
            if (token := try_get(
                    cls._send_request(cls._API_URLS['login'], _type="POST", headers=_headers_post),
                    lambda x: traverse_obj(x.json(), ('data', 'jwt')))):

                cls._USERTOKEN = token
                _final = cls._HEADERS["FINAL"].copy()
                _final.update({
                    'x-ident': xident, 'Authorization': f'Bearer {token}', 'X-CSRF-TOKEN': token})
                cls.headers_api = _final
                return True
            else:
                return False
        return False

    @classmethod
    @dec_retry
    def API_REFRESH(cls, msg=None, _logger=None):
        _pre = msg or ''
        if not _logger:
            _logger = logger.debug
        try:
            with cls.call_lock:
                if cls.headers_api:
                    cls.API_GET_XIDENT()
                    if cls._refresh_api():
                        _logger(f"{_pre}[refresh_api] ok")
                        return True
                    else:
                        raise_extractor_error(f"{_pre}[refresh_api] nok")
                else:
                    _logger(f"{_pre}[refresh api] is not logged torefresh")
        except ExtractorError:
            raise
        except Exception as e:
            _logger(f"{_pre}[refresh_api] {str(e)}")
            raise_extractor_error(f"{_pre}[refresh_api] error refresh {str(e)}", _from=e)

    @classmethod
    def _refresh_api(cls):
        if (
            data := try_get(
                cls._send_request(cls._API_URLS['refresh'], headers=cls.headers_api),
                lambda x: x.json())
        ):
            if token := traverse_obj(data, ('data', 'jwt')):
                cls._USERTOKEN = token
                cls.headers_api.update({'Authorization': f'Bearer {token}', 'X-CSRF-TOKEN': token})
                return True
            return False
        return False

    @classmethod
    @dec_retry
    def API_GET_XIDENT(cls):
        try:
            if (xident := cls._get_api_xident()):
                cls.headers_api['x-ident'] = xident
                logger.debug("[get_xident] OK")
                return True
            else:
                raise ExtractorError("couldnt get new xident")
        except Exception as e:
            logger.error(f"[get_xident] {str(e)}")
            raise_extractor_error(f"[get_xident] error new xident {str(e)}", _from=e)

    @classmethod
    def _get_api_xident(cls):
        proc = subprocess.run(
            ['node', cls._JS_SCRIPT, cls._APP_DATA_PASSPHRASE],
            capture_output=True, encoding="utf-8")

        if (proc.returncode == 0) and (xident := proc.stdout.strip('\n')):
            cls.timer.reset()
            return xident
        else:
            logger.warning(f'[get_api_xident] couldnt get xident: {proc}')

    @classmethod
    def API_LOGOUT(cls, msg=None, _logger=None):
        _pre = msg or ''
        if not _logger:
            _logger = logger.debug
        with cls.call_lock:
            if not cls.headers_api:
                _logger(f"{_pre}[API_LOGOUT] Already logged out")
                return "OK"
            if cls._logout_api():
                _logger(f"{_pre}[API_LOGOUT] OK")
                return "OK"
            else:
                _logger(f"{_pre}[API_LOGOUT] NOK")
                return "NOK"

    @classmethod
    def _logout_api(cls):
        _headers_del = cls._HEADERS["DELETE"]["LOGOUT"].copy()
        if (_headers := cls.headers_api):
            cls.API_GET_XIDENT()
            _headers_del.update(
                {'x-ident': _headers['x-ident'], 'Authorization': _headers['Authorization']})
            if not (
                resdel := cls._send_request(
                    cls._API_URLS['logout'],
                    _type="DELETE",
                    headers=_headers_del),
            ):
                return False
            if resdel.status_code != 204:  # type: ignore
                return False
            cls.headers_api = {}
        if cls._CLASSCLIENT:
            cls._CLASSCLIENT.cookies = {}
        cls._USERTOKEN = None
        return True

    @classmethod
    def API_GET_HTTP_HEADERS(cls):
        with cls.call_lock:
            if not cls.headers_api:
                if cls.API_LOGIN():
                    return cls.headers_api
            elif not cls.timer.has_elapsed(50):
                return cls.headers_api
            else:
                logger.debug("[call] timeout to new xident")
                if cls.API_GET_XIDENT():
                    return cls.headers_api

    @classmethod
    @dec_on_driver_timeout
    @dec_on_exception
    @limiter_0_1.ratelimit("nakedsword", delay=True)
    def _send_request(cls, url, **kwargs) -> None | Response:

        pre = '[send_request]'
        if (msg := kwargs.pop('msg', None)):
            pre = f'{msg}{pre}'
        if (driver := kwargs.pop('driver', None)):
            driver.get(url)
        else:
            try:
                if not (_client := kwargs.get('client', cls._CLASSCLIENT)):
                    raise NakedSwordError('CLIENT is None')
                upt_headers = {}
                if (_headers := kwargs.get('headers', None)):
                    upt_headers = {**(_headers() if callable(_headers) else _headers), **cls._UA}
                _kwargs = {**kwargs, **{'client': _client, 'headers': upt_headers}}
                return (cls._send_http_request(url, **_kwargs))
            except (HTTPStatusError, ConnectError, TimeoutError) as e:
                if cls._INST_IE:
                    cls._INST_IE.report_warning(f"{pre}: error - {str(e)}")
            except Exception as e:
                if cls._INST_IE:
                    cls._INST_IE.report_warning(f"{pre}: error - {str(e)}")
                raise

    @classmethod
    def _get_app_data_passphrase(cls) -> str | None:
        try:
            if js_content := try_get(
                cls._send_request(
                    try_get(
                        re.findall(
                            r'src="(/static/js/main[^"]+)',  # type: ignore
                            try_get(
                                cls._send_request(cls._SITE_URL),  # type: ignore
                                lambda z: html.unescape(z.text))),
                        lambda x: f"https://www.nakedsword.com{x[0]}")),
                lambda y: html.unescape(y.text)
            ):
                if data_js := re.findall(r'REACT_APP_([A-Z_]+:"[^"]+")', js_content):
                    if data := json.loads(js_to_json("{" + f"{','.join(data_js)}" + "}")):
                        return data.get('PASSPHRASE')
        except Exception as e:
            logger.exception(str(e))

    def get_formats(self, _types, _info: info_scene):
        self.logger_debug(f"[get_formats] {_info}")

        m3u8_url = _info.m3u8_url
        formats = []
        for _type in _types:
            self.check_stop()
            try:
                if _type == "dash":
                    mpd_url = m3u8_url.replace('playlist.m3u8', 'manifest.mpd')
                    if not (_doc := try_get(
                        NakedSwordBaseIE._send_request(mpd_url, headers=NakedSwordBaseIE._HEADERS["MPD"]),
                        lambda x: (x.content).decode('utf-8', 'replace'))
                    ):
                        raise ExtractorError("couldnt get mpd doc")

                    mpd_doc = self._parse_xml(_doc, None)

                    if formats_dash := self._parse_mpd_formats(
                        mpd_doc, mpd_id="dash", mpd_url=mpd_url,
                        mpd_base_url=(mpd_url.rsplit('/', 1))[0],
                    ):
                        formats.extend(formats_dash)

                elif _type == "hls":
                    if not (m3u8_doc := try_get(
                        NakedSwordBaseIE._send_request(
                            m3u8_url, headers=NakedSwordBaseIE._HEADERS["MPD"],
                            msg=f'[{_info.sceneid}][get_formats]'),
                        lambda x: (x.content).decode('utf-8', 'replace'))
                    ):
                        raise_reextract_info("couldnt get m3u8 doc")

                    formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                        m3u8_doc, m3u8_url, ext='mp4', entry_protocol='m3u8_native', m3u8_id='hls')
                    if formats_m3u8:
                        for fmt in formats_m3u8:
                            fmt['http_headers'] = NakedSwordBaseIE._HEADERS["HTTP_HEADERS"]
                        formats.extend(formats_m3u8)

                elif _type == "ism":
                    ism_url = m3u8_url.replace('playlist.m3u8', 'Manifest')
                    if _doc := try_get(
                        NakedSwordBaseIE._send_request(
                            ism_url, headers=NakedSwordBaseIE._HEADERS["MPD"]),
                        lambda x: (x.content).decode('utf-8', 'replace'),
                    ):
                        ism_doc = self._parse_xml(_doc, None)
                        formats_ism, _ = self._parse_ism_formats_and_subtitles(ism_doc, ism_url)
                        if formats_ism:
                            formats.extend(formats_ism)

            except ReExtractInfo:
                raise
            except Exception as e:
                logger.error(f"[get_formats][{_type}][{_info.url}] {str(e)}")

        if not formats:
            raise ExtractorError("couldnt find any format")
        else:
            return formats

    @classmethod
    def _get_api_details(cls, _id_movie):
        if (
            details := try_get(
                cls._send_request(
                    f"{cls._API_URLS['movies']}/{_id_movie}/details",
                    headers=cls.API_GET_HTTP_HEADERS),
                lambda x: x.json().get('data'))
        ):
            NakedSwordBaseIE._MOVIES[_id_movie]['nentries'] = len(details.get('scenes'))  # type: ignore
            NakedSwordBaseIE._MOVIES[_id_movie]['title'] = f"{sanitize_filename(details.get('title'), restricted=True)}"
            NakedSwordBaseIE._MOVIES[_id_movie]['urls_api'] = cls._get_api_scene_urls(details)
            return details

    def _get_api_newest_movies(self, pages=2):
        _pre = f"{NakedSwordBaseIE._API_URLS['movies']}/feed?subset_sort_by=newest&subset_limit=480&page="
        _list_urls = [f"{_pre}{i}&sort_by=newest" for i in range(1, pages + 1)]
        _movies_info = []
        for _url in _list_urls:
            try:
                _movies_info.extend(
                    try_get(
                        NakedSwordBaseIE._send_request(_url, headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS),  # type: ignore
                        lambda x: traverse_obj(x.json(), ('data', 'movies'))) or [])
            except Exception as e:
                logger.exception(repr(e))
        _movies_info.reverse()
        return _movies_info

    def _get_api_tags(self):

        feed = try_get(
            NakedSwordBaseIE._send_request(
                f"{NakedSwordBaseIE._API_URLS['tags']}/feed",
                headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS),
            lambda x: x.json().get('data'))
        if feed and feed.get('categories') and feed.get('sex-acts'):
            themes = [
                el['name'].lower().replace(' ', '-').replace(',', '-')
                for el in feed['categories']]
            sex_acts = [
                el['name'].lower().replace(' ', '-').replace(',', '-')
                for el in feed['sex_acts']]
            NakedSwordBaseIE._TAGS.update({'themes': themes, 'sex_acts': sex_acts})

    def _get_api_info_playlist(self, url, label) -> tuple:
        _info = try_get(
            NakedSwordBaseIE._send_request(url, headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS),  # type: ignore
            lambda x: x.json())
        _name = None
        _target_info = []
        if _info:
            _target_info = traverse_obj(_info, ('data', label)) or []
            _name = traverse_obj(_info, ('data', 'name'))
        return _name, _target_info

    def _get_api_scenes_playlist(self, playlistid):
        _url = f'https://ns-api.nakedsword.com/frontend/scene_playlist/{playlistid}'
        return self._get_api_info_playlist(_url, "scenes_in_playlist")

    def _get_api_movies_playlist(self, playlistid) -> tuple:
        _url = f'https://ns-api.nakedsword.com/frontend/movie_playlist/{playlistid}'
        return self._get_api_info_playlist(_url, "movies_in_playlist")

    def _get_api_most_watched_scenes(self, query: str, limit: None | int = 60):

        _query = "" if query == 'most_watched' else f'{query}&'
        _limit = limit or 60
        pages = int(_limit) // 30 + 1
        _pre1 = f"{NakedSwordBaseIE._API_URLS['scenes']}/feed?"
        _pre2 = "per_page=30&subset_sort_by=most_watched"
        _subset = f"&subset_limit={int(_limit)}"
        _list_urls = [
            f"{_pre1}{_query}{_pre2}{_subset}&page={i}&sort_by=most_watched"
            for i in range(1, pages + 1)]
        _scenes_info = []
        for _url in _list_urls:
            self.to_screen(_url)
            _scenes_info.extend(
                try_get(
                    NakedSwordBaseIE._send_request(_url, headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS),  # type: ignore
                    lambda x: traverse_obj(x.json(), ('data', 'scenes'))) or [])

        return _scenes_info

    def _get_api_most_watched_movies(self, query: str, limit: None | int = 60):

        if query == 'top_movies':
            _query = ""
            _pre2 = ""
            _limit = 10
            _sort_by = 'top_movies'
            pages = 1
            _subset = "per_page=10"
        else:
            _query = "" if query == 'most_watched' else f'{query}&'
            _limit = limit or 60
            pages = int(_limit) // 30 + 1
            _pre2 = "per_page=30&subset_sort_by=most_watched"
            _sort_by = 'most_watched'
            _subset = f"&subset_limit={_limit}"

        _pre1 = f"{NakedSwordBaseIE._API_URLS['movies']}/feed?"

        _list_urls = [
            f"{_pre1}{_query}{_pre2}{_subset}&page={i}&sort_by={_sort_by}"
            for i in range(1, pages + 1)]
        _movies_info = []
        for _url in _list_urls:
            _movies_info.extend(
                try_get(
                    NakedSwordBaseIE._send_request(_url, headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS),  # type: ignore
                    lambda x: traverse_obj(x.json(), ('data', 'movies'))) or [])

        return _movies_info

    @staticmethod
    def _get_api_scene_urls(details, _type="HLS"):
        _id_movie = details.get('id')
        _pre1 = f"{NakedSwordBaseIE._API_URLS['streaming']}/aebn/movie/"
        _pre2 = "?max_bitrate=10500&scenes_id="
        _res = []
        for sc in details.get('scenes'):
            _url = f"{_pre1}{_id_movie}{_pre2}{sc['id']}&start_time={sc['startTimeSeconds']}&duration="
            _url += f"{sc['endTimeSeconds'] - sc['startTimeSeconds']}&format={_type}"
            _res.append(_url)
        return _res

    def _get_api_scene_info(self, urlsc):
        return try_get(
            NakedSwordBaseIE._send_request(
                urlsc, headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS),
            lambda x: x.json().get('data'))

    def get_streaming_info(self, _id_movie, **kwargs) -> list[info_scene] | info_scene:
        premsg = f"[get_streaming_info][{_id_movie}]"
        index_scene = int_or_none(kwargs.get('index'))
        scenes = kwargs.get('scenes')

        details = NakedSwordBaseIE._MOVIES[_id_movie]['details']
        num_scenes = NakedSwordBaseIE._MOVIES[_id_movie]['nentries']
        _movietitle = NakedSwordBaseIE._MOVIES[_id_movie]['title']
        _url_movie = NakedSwordBaseIE._MOVIES[_id_movie]['url_movie']
        _urls_api = NakedSwordBaseIE._MOVIES[_id_movie]['urls_api']

        if index_scene:
            scenes = [index_scene]
        elif not scenes:
            scenes = [n for n in range(1, num_scenes + 1)]

        info_scenes_list = []
        for ind in range(1, num_scenes + 1):
            _scene_id = str_or_none(
                traverse_obj(details, ('scenes', ind - 1, 'id')))
            _scene_title = f"{_movietitle}_scene_{ind}"
            _scene_url = f"{_url_movie}/scene/{ind}"
            _m3u8_url = ""
            if ind in scenes:
                if not (_m3u8_url := self._get_api_scene_info(_urls_api[ind - 1])):  # type: ignore
                    logger.error(f"{premsg}[{ind}] couldnt get m3u8url")
                    raise ReExtractInfo(f"{premsg}[{ind}] couldnt get m3u8url")
            info_scenes_list.append(
                info_scene(
                    ind, _scene_id, _scene_title, _scene_url,
                    _m3u8_url, _url_movie, _id_movie, num_scenes))

        if index_scene:
            return info_scenes_list[0]
        else:
            return info_scenes_list

    def get_movie_url(self, _id_movie):
        return try_get(
            NakedSwordBaseIE._send_request(
                f"https://www.nakedsword.com/movies/{_id_movie}/_", _type="HEAD"),
            lambda x: str(x.url))

    def _is_logged(self, driver):
        if 'nakedsword.com' not in driver.current_url:
            NakedSwordBaseIE._send_request(self._SITE_URL, driver=driver)
        logged_ok = driver.execute_script(_SCRIPT_IS_LOGGED)
        self.logger_debug(f"[is_logged] {logged_ok}")
        return logged_ok

    def _logout(self, driver):
        try:
            logged_out = True
            if self._is_logged(driver):
                self.wait_until(driver, 5, forlogout())
                logged_out = not self._is_logged(driver)
            self.logger_info(f'[logout] Logout[{"OK" if logged_out else "NOK"}]')
            driver.get('about:blank')
        except Exception as e:
            self.report_warning(f"[logout] Logout NOK {repr(e)}")

    def _login(self, driver):

        _method_class = lambda x: ec.presence_of_element_located((By.CLASS_NAME, x))
        try:
            driver.maximize_window()
            if not self._is_logged(driver):
                self.check_stop()
                self.report_login()
                driver.execute_script(_SCRIPT_SETTINGS)
                username, password = self._get_login_info()
                if not username or not password:
                    self.raise_login_required(
                        'A valid %s account is needed to access this media.'
                        % self._NETRC_MACHINE)
                self.wait_until(driver, 5, forlogin())

                if not (el_username := self.wait_until(
                        driver, 15, _method_class("Input.Username"))):
                    raise ExtractorError("login nok")
                if not (el_psswd := self.wait_until(
                        driver, 1, _method_class("Input.Password"))):
                    raise ExtractorError("login nok")
                if not (el_submit := self.wait_until(
                        driver, 1, _method_class("SignInButton"))):
                    raise ExtractorError("login nok")

                el_username.send_keys(username)  # type: ignore
                el_psswd.send_keys(password)  # type: ignore
                el_submit.click()  # type: ignore

                self.wait_until(driver, 3)
                self.wait_until(driver, 10, closeDeals())

                logged = self._is_logged(driver)
                self.logger_info(f'[login] Login[{"OK" if logged else "NOK"}]')
                if logged:
                    return True
                else:
                    raise ExtractorError("login nok")
            else:
                self.logger_info("[login] Already logged")
                return True
        except Exception as e:
            logger.exception(repr(e))

    @run_operation_in_executor('har')
    def _get_m3u8_url_logs(self, id_movie, msg, **kwargs):
        with NakedSwordBaseIE._HAR_LOCK:
            premsg = f'{msg}[get_har]'
            exit_event = kwargs["stop_event"]
            _THIS_MOVIE = NakedSwordBaseIE._MOVIES[id_movie]
            _har_file = None
            try:
                driver, _port = traverse_obj(
                    NakedSwordBaseIE._INFO_DRIVER, (('driver', 'port'),),
                    default=[None, None])  # type: ignore
                if driver:
                    if (not driver.service.is_connectable() or not driver.window_handles):
                        self.rm_driver(driver)
                        driver = None
                        NakedSwordBaseIE._INFO_DRIVER = None
                if not driver:
                    _port = self.find_free_port()
                    driver = self.get_driver(noheadless=True, port=_port, host='127.0.0.1')
                    self.clear_firefox_cache(driver)  # type: ignore
                    NakedSwordBaseIE._INFO_DRIVER = {'driver': driver, 'port': _port}
                if driver:
                    with self.get_har_logs('nakedsword', id_movie, port=_port) as harlogs:  # type: ignore
                        _har_file = harlogs.har_file
                        self._login(driver)
                        NakedSwordBaseIE._send_request(_THIS_MOVIE['url_movie'], driver=driver)
                        self.wait_until(driver, 180, ec.url_contains('about:'))  # type: ignore
                        self._logout(driver)

                    for _, _nok_sc in _THIS_MOVIE['nok'].items():
                        _api_url, _m3u8_url = try_get(
                            self.scan_for_json(
                                r"\?max_bitrate=10500&scenes_id=%s&.+$" % _nok_sc['id'],
                                har=_har_file),  # type: ignore
                            lambda x: (x.get('url'), traverse_obj(x, ('json', 'data')))) or (None, None)
                        _nok_sc |= {'api_url': _api_url, 'new_m3u8_url': _m3u8_url}

            except Exception as e:
                self.logger_debug(f"{premsg} {repr(e)}")
            finally:
                exit_event.set()
                with contextlib.suppress(OSError):
                    if _har_file:
                        os.remove(_har_file)

    def wait_with_pb(self, timeout, msg, id_movie, use_driver=False):

        premsg = f'{msg}[wait]'
        _simple_counter = None
        if isinstance(_klasses := self.get_param('_util_classes'), dict):
            _simple_counter = _klasses.get('SimpleCountDown')

        _index = getattr(self, "indexdl", None)

        try:
            NakedSwordBaseIE.API_REFRESH(msg=premsg, _logger=self.logger_debug)
            NakedSwordBaseIE.API_LOGOUT(msg=premsg, _logger=self.logger_debug)

            exit_event = False
            if use_driver:
                exit_event, _ = self._get_m3u8_url_logs(id_movie, msg)

            self.logger_debug(f'{premsg} start[{timeout}] indexdl[{_index}]')

            with self.create_progress_bar(timeout, block_logging=False, msg=f'{premsg}') as pb:
                if _simple_counter:
                    _reswait = _simple_counter(
                        pb, check=self.check_stop, timeout=timeout, indexdl=_index)()
                else:
                    _reswait = _wait_for_either(pb, self.check_stop, timeout=timeout)

            self.logger_debug(f'{premsg} end[{_reswait}] indexdl[{_index}]')
            if use_driver and exit_event:
                exit_event.wait()
                for _index, _nok_sc in NakedSwordBaseIE._MOVIES[id_movie]['nok'].items():
                    self.logger_info(f"{premsg} nok_sc[{_nok_sc}]")

        except Exception as e:
            logger.error(f'{premsg} {repr(e)}')

    def build_entry(self, info: info_scene):
        return {
            "id": info.sceneid,
            "_id_movie": info.movieid,
            "title": info.title,
            "formats": [],
            "ext": "mp4",
            "webpage_url": info.url,
            "original_url": info.movieurl,
            "_index_scene": info.index,
            "_n_entries": info.nentries,
            "extractor_key": 'NakedSwordScene',
            "extractor": 'nakedswordscene'
        }

    def _real_initialize(self):
        try:
            super()._real_initialize()
            with NakedSwordBaseIE._LOCK:
                if not NakedSwordBaseIE._CLASSCLIENT:
                    NakedSwordBaseIE._INST_IE = self
                    NakedSwordBaseIE._CLASSCLIENT = self._CLIENT
                    NakedSwordBaseIE._UA = {'User-Agent': try_get(
                        self.get_param('http_headers'),
                        lambda x: x.get('User-Agent')) or random_user_agent()}
                    NakedSwordBaseIE.API_LOGIN(_logger=self.logger_info)
        except Exception as e:
            logger.error(repr(e))


class NakedSwordSceneIE(NakedSwordBaseIE):
    IE_NAME = 'nakedswordscene'  # type: ignore
    _VALID_URL = r'''(?x)
        https?://(?:www\.)?nakedsword\.com/movies/
        (?P<movieid>\d+)/[^\/]+/scene/(?P<id>\d+)'''

    @dec_on_reextract_1
    def get_entry(self, url, **kwargs):
        _type = kwargs.get('_type', 'all')
        _types = ['hls', 'dash', 'ism'] if _type == 'all' else [_type]
        index_scene = kwargs.get('index') or int_or_none(self._match_id(url)) or 1
        premsg = "[get_entry]"
        if msg := kwargs.get('msg'):
            premsg = f"{msg}{premsg}"

        url = url.strip('/')

        _id_movie = try_get(self._match_valid_url(url), lambda x: x.group('movieid'))

        if _id_movie not in NakedSwordBaseIE._MOVIES:
            NakedSwordBaseIE._MOVIES.update(
                {_id_movie: {'nok': {}, 'ok': [], 'entries': {}, 'final': True}})

        _THIS_MOVIE = NakedSwordBaseIE._MOVIES[_id_movie]

        if 'url_movie' not in _THIS_MOVIE:
            _THIS_MOVIE['url_movie'] = self.get_movie_url(_id_movie)

        if not (_url_movie := _THIS_MOVIE.get('url_movie')):
            NakedSwordBaseIE._MOVIES.pop(_id_movie, None)
            raise_extractor_error(f"{premsg}[{url}] error 404 - movie doesnt exist")

        premsg += f"[{_url_movie.split('movies/')[1]}]"

        _THIS_MOVIE.setdefault('scenes', {})

        if index_scene not in _THIS_MOVIE['scenes']:
            _THIS_MOVIE['scenes'][index_scene] = {'final': True}

        if not _THIS_MOVIE['scenes'][index_scene]['final']:
            self.wait_with_pb(my_jitter(60), premsg, _url_movie)

        try:
            if 'details' not in _THIS_MOVIE:
                _THIS_MOVIE['details'] = self._get_api_details(_id_movie)

            if not _THIS_MOVIE['details']:
                raise_extractor_error(f"{premsg} no details info")

            if index_scene > (num_scenes := _THIS_MOVIE['nentries']):
                _THIS_MOVIE['scenes'].pop(index_scene, None)
                raise_extractor_error(
                    f"{premsg} movie has #{num_scenes} scenes, index scene[{index_scene}] not valid")

            _info = self.get_streaming_info(_id_movie, index=index_scene)
            if isinstance(_info, info_scene):
                _entry = self.build_entry(_info)
                if not (formats := self.get_formats(_types, _info)):
                    raise_reextract_info(f'{premsg}: error - no formats')
                _entry['formats'] = formats
                self.logger_info(f"{premsg}: OK got entr")
                _THIS_MOVIE['scenes'][index_scene]['final'] = True
                try:
                    _entry['duration'] = self._extract_m3u8_vod_duration(
                        formats[0]['url'], _info.sceneid,
                        headers=NakedSwordBaseIE._HEADERS["MPD"])
                except Exception as e:
                    self.logger_info(f"{premsg}: error trying to get vod {repr(e)}")
                return _entry
            else:
                raise_reextract_info(f'{premsg}: error in get streaming info')
        except ReExtractInfo:
            self.logger_debug(f"{premsg}: error format, will retry again")
            _THIS_MOVIE['scenes'][index_scene]['final'] = False
            raise
        except (StatusStop, ExtractorError):
            raise
        except Exception as e:
            self.logger_debug(f"{premsg} {repr(e)}")
            raise_extractor_error(f'{premsg}: error - {str(e)}', _from=e)

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):
        try:
            self.report_extraction(url)
            nscene = int(self._match_id(url))
            return self.get_entry(url, index=nscene, _type="hls")
        except (ExtractorError, StatusStop):
            raise
        except (ReExtractInfo, Exception) as e:
            raise_extractor_error(str(e), _from=e)


class NakedSwordMovieIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:movie:playlist'  # type: ignore
    _VALID_URL = r'''(?x)
        https?://(?:www\.)?nakedsword\.com/
        movies/(?P<id>\d+)/[^/$#?]+/?(?:$|\?|\#)'''

    @classmethod
    def save_images(cls, _id_movie, download_path, include_scenes=True):
        if _id_movie not in NakedSwordBaseIE._MOVIES:
            NakedSwordBaseIE._MOVIES.update(
                {_id_movie: {'nok': {}, 'ok': [], 'entries': {}, 'final': True}})
        if not (
            (details := (
                traverse_obj(NakedSwordBaseIE._MOVIES, (_id_movie, 'details'))
                or NakedSwordBaseIE._get_api_details(_id_movie))) and isinstance(details, dict)
        ):
            raise_extractor_error("no details info")
        else:
            NakedSwordBaseIE._MOVIES[_id_movie]['details'] = details
            _client = None
            try:
                _client = SeleniumInfoExtractor.get_temp_client()
                if include_scenes:
                    for i in range(1, len(details['scenes']) + 1):
                        for key in ('gallery', 'cover_images'):
                            for n, el in enumerate(details['scenes'][i - 1][key]):
                                if (
                                    _img_bin := try_get(
                                        NakedSwordBaseIE._send_request(el['url'], client=_client),
                                        lambda x: x.content if x else None)
                                ):
                                    _file = f"{str(download_path)}/scene_{i}_{key.split('_')[0]}_{n}.jpg"
                                    with open(_file, "wb") as f:
                                        f.write(_img_bin)
                if _images := traverse_obj(details['images'], (lambda _, x: '_xl' in x['url'])):
                    for el in _images:  # type: ignore
                        if (
                            _img_bin := try_get(
                                NakedSwordBaseIE._send_request(el['url'], client=_client),
                                lambda x: x.content if x else None)
                        ):
                            _file = f"{str(download_path)}/movie_{_id_movie}_{sanitize_filename(el['type'], restricted=True)}.jpg"
                            with open(_file, "wb") as f:
                                f.write(_img_bin)
            finally:
                if _client:
                    _client.close()

    @dec_on_reextract_1
    def get_entries(self, url, **kwargs):
        _type = kwargs.get('_type', 'all')
        _types = ['hls', 'dash', 'ism'] if _type == 'all' else [_type]
        premsg = "[get_entries]"
        if msg := kwargs.get('msg'):
            premsg = f"{msg}{premsg}"

        _force_list = kwargs.get('force', False)

        _id_movie = self._match_id(url)

        if _id_movie not in NakedSwordBaseIE._MOVIES:
            NakedSwordBaseIE._MOVIES.update(
                {_id_movie: {'nok': {}, 'ok': [], 'entries': {}, 'final': True}})

        _THIS_MOVIE = NakedSwordBaseIE._MOVIES[_id_movie]

        if 'url_movie' not in _THIS_MOVIE:
            _THIS_MOVIE['url_movie'] = self.get_movie_url(_id_movie)

        if not (_url_movie := _THIS_MOVIE.get('url_movie')):
            NakedSwordBaseIE._MOVIES.pop(_id_movie, None)
            raise_extractor_error(f"{premsg}[{url}] error 404 - movie doesnt exist")

        premsg += f'[{_url_movie.split("movies/")[1]}]'

        if not _THIS_MOVIE['final']:
            self.wait_with_pb(my_jitter(60), premsg, _id_movie, use_driver=True)

        try:
            if 'details' not in _THIS_MOVIE:
                _THIS_MOVIE['details'] = self._get_api_details(_id_movie)
            if not _THIS_MOVIE['details']:
                raise_extractor_error(f"{premsg} no details info")
            if (
                self.get_param('embed')
                or (self.get_param('extract_flat', '') != 'in_playlist')
            ):
                sublist = []
                if getattr(self, 'args_ie', None):
                    sublist = traverse_obj(self.args_ie, (_id_movie, 'listreset'))
                    self.logger_debug(
                        f"{premsg} sublist of movie scenes: {sublist}")
                if not sublist:
                    sublist = [n for n in range(1, _THIS_MOVIE['nentries'] + 1)]
                _raise_reextract = []
                for _sc in _THIS_MOVIE['ok']:
                    if not traverse_obj(_THIS_MOVIE, ('entries', _sc, 'formats')):
                        _THIS_MOVIE['ok'].remove(_sc)
                if _scenes_to_get := list(set(sublist) - set(_THIS_MOVIE['ok'])):  # type: ignore
                    info_streaming_scenes = self.get_streaming_info(
                        _id_movie, scenes=_scenes_to_get)
                    _entries = _THIS_MOVIE['entries']
                    for _info in info_streaming_scenes:  # type: ignore
                        self.check_stop()
                        i = _info.index
                        _entries.setdefault(i, self.build_entry(_info))
                        if _info.m3u8_url and i not in _THIS_MOVIE['ok']:
                            try:
                                if formats := self.get_formats(_types, _info):
                                    _entries[i]['formats'] = formats
                                    self.logger_debug(f"{premsg}[{i}]: OK got entry")
                                    _THIS_MOVIE['ok'].append(i)
                                    _THIS_MOVIE['nok'].pop(i, None)
                                    try:
                                        _entries[i]['duration'] = self._extract_m3u8_vod_duration(
                                            formats[0]['url'], _info.sceneid,
                                            headers=NakedSwordBaseIE._HEADERS["MPD"])
                                    except Exception as e:
                                        self.logger_info(
                                            f"{premsg}: error trying to get vod {str(e)}")
                            except ReExtractInfo:
                                self.logger_debug(f"{premsg}[{i}]: NOK, will try again")
                                _raise_reextract.append(i)
                                _THIS_MOVIE['nok'][i] = {'id': _info.sceneid, 'm3u8_url': _info.m3u8_url}
                                _THIS_MOVIE['final'] = False
                                try_call(lambda: _THIS_MOVIE['ok'].remove(i))
                if _raise_reextract:
                    _msg = (
                        f"{premsg} ERROR in {_raise_reextract} from sublist:{sublist} out of "
                        + f"#{_THIS_MOVIE['nentries']} evaluated:{_scenes_to_get} "
                        + f"final:[{_THIS_MOVIE['final']}] ok:{_THIS_MOVIE['ok']} "
                        + f"nok:{list(_THIS_MOVIE['nok'].keys())}")
                    self.logger_info(_msg)
                    raise ReExtractInfo("error in scenes of movie")
                self.logger_info(
                    f"{premsg} OK format sublist:{sublist} out of #{_THIS_MOVIE['nentries']} "
                    + f"evaluated:{_scenes_to_get} final:[{_THIS_MOVIE['final']}] ok:{_THIS_MOVIE['ok']} "
                    + f"nok:{list(_THIS_MOVIE['nok'].keys())}")

                _entries = list(map(lambda x: x[1], sorted(_THIS_MOVIE['entries'].items())))
                _THIS_MOVIE.update({'nok': {}, 'ok': [], 'entries': {}, 'final': True})
                if _force_list:
                    return _entries
                return self.playlist_result(
                    _entries, playlist_id=_id_movie, playlist_title=_THIS_MOVIE['title'],
                    webpage_url=_THIS_MOVIE['url_movie'], original_url=_THIS_MOVIE['url_movie'])

            else:
                details = _THIS_MOVIE['details']
                pl_title = _THIS_MOVIE['title']
                if _force_list:
                    return [
                        self.url_result(
                            f"{_url_movie.strip('/')}/scene/{x['index']}",
                            ie=NakedSwordSceneIE)
                        for x in details.get('scenes', [])]
                return self.playlist_from_matches(
                    traverse_obj(details, 'scenes'),
                    getter=lambda x: f"{_url_movie.strip('/')}/scene/{x['index']}",
                    ie=NakedSwordSceneIE, playlist_id=_id_movie, playlist_title=pl_title,
                    webpage_url=_url_movie, original_url=_url_movie)

        except ReExtractInfo:
            _THIS_MOVIE['final'] = False
            raise
        except StatusStop:
            raise
        except Exception as e:
            logger.exception(
                f"{premsg} info streaming error - {repr(e)}")
            raise

    @dec_on_reextract_1
    def get_entries_from_full_movie(self, _id_movie, **kwargs):

        premsg = f"[get_entries_from_full_movie][{_id_movie}]"

        if not (_movie_url := self.get_movie_url(_id_movie)):
            raise_extractor_error(f"{premsg}[{_id_movie}] error 404 - movie doesnt exist")

        if _id_movie not in NakedSwordBaseIE._MOVIES:
            NakedSwordBaseIE._MOVIES.update({_id_movie: {'url_movie': _movie_url, 'on_backoff': False}})

        if NakedSwordBaseIE._MOVIES[_id_movie]['on_backoff']:
            self.wait_with_pb(my_jitter(60), premsg, _movie_url)

        details = NakedSwordBaseIE._get_api_details(_id_movie)
        if not details:
            raise ReExtractInfo(f"{premsg} no details info")
        _pre = f"{NakedSwordBaseIE._API_URLS['streaming']}/aebn/movie/"
        _api_movie_url = f"{_pre}{_id_movie}?max_bitrate=10500&format=HLS"

        _formats_m3u8 = {}
        try:
            if (
                (m3u8_url := try_get(
                    NakedSwordBaseIE._send_request(_api_movie_url, headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS),
                    lambda x: x.json().get('data') if x else None))
                and (m3u8_doc := try_get(
                    NakedSwordBaseIE._send_request(
                        m3u8_url, headers=NakedSwordBaseIE._HEADERS["MPD"]),
                    lambda x: (x.content).decode('utf-8', 'replace')))
            ):
                _formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                    m3u8_doc, m3u8_url, ext='mp4', entry_protocol='m3u8_native', m3u8_id='hls')
                if not _formats_m3u8:
                    raise_reextract_info("couldnt get formats m3u8")
            else:
                raise_reextract_info("couldnt get m3u8 doc")

        except ReExtractInfo as e:
            logger.info(f"{premsg} reextractinfo {str(e)}")
            NakedSwordBaseIE._MOVIES[_id_movie]['on_backoff'] = True
            raise
        except Exception as e:
            logger.error(f"{premsg} {repr(e)}")
            NakedSwordBaseIE._MOVIES[_id_movie]['on_backoff'] = True
            raise_reextract_info(str(e), _from=e)

        _entries = []
        for sc in details.get('scenes'):
            _entry = {
                "id": str(sc['id']) + "bm",
                "_id_movie": _id_movie,
                "title": f"{sanitize_filename(details.get('title'), restricted=True)}_bm_scene_{sc.get('index')}",
                "formats": _formats_m3u8,
                "ext": "mp4",
                "webpage_url": f"{_movie_url}?by=movie&scene={sc.get('index')}",
                "original_url": f"{_movie_url}?by=movie",
                "_index_scene": sc.get('index'),
                "_start_time": int(sc['startTimeSeconds']),
                "_end_time": int(sc['endTimeSeconds']),
                "_n_entries": len(details.get('scenes')),
                "extractor_key": "NakedSwordMovie",
                "extractor": "nakedsword:movie:playlist"
            }
            _entries.append(_entry)

        playlist_id = _id_movie
        pl_title = sanitize_filename(details.get('title'), restricted=True) + '_bm'
        return self.playlist_result(
            _entries,
            playlist_id=playlist_id,
            playlist_title=pl_title,
            webpage_url=f"{_movie_url}?by=movie",
            original_url=f"{_movie_url}?by=movie")

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        try:
            self.report_extraction(url)
            info_url = try_get(self._match_valid_url(url), lambda x: x.groupdict())
            if not info_url or not info_url.get('by'):
                return self.get_entries(url, _type="hls")
            if info_url and info_url.get('by'):
                return self.get_entries_from_full_movie(info_url.get('id'))
        except (ExtractorError, StatusStop):
            raise
        except ReExtractInfo as e:
            raise_extractor_error(str(e), _from=e)
        except Exception as e:
            raise_extractor_error(str(e), _from=e)


class NakedSwordScenesPlaylistIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:scenes:playlist'  # type: ignore
    _VALID_URL = r'''(?x)
            https?://(?:www\.)?nakedsword.com/(?:
                ((((studios|stars)/(?P<id>\d+)/(?P<name>[^/?#&]+))|
                (tag/(?P<tagname>[^/?#&]+))|most-watched)\?content=Scenes(&limit=(?P<limit>\d+))?)|
                playlists/(?P<plid>\d+)/scenes/.*)'''

    @dec_on_reextract
    def get_entries_from_scenes_list(self, url, **kwargs):
        _type = kwargs.get('_type', 'hls')
        premsg = "[get_entries]"
        if msg := kwargs.get('msg'):
            premsg = f"{msg}{premsg}"

        try:
            info_url = try_get(self._match_valid_url(url), lambda x: x.groupdict())
            if isinstance(info_url, dict):
                if (_plid := info_url.get('plid')):
                    playlist_id = _plid
                    playlist_title, _scenes = self._get_api_scenes_playlist(_plid)
                else:
                    query = "most_watched"

                    if _tagname := info_url.get('tagname'):
                        with NakedSwordBaseIE._LOCK:
                            if not NakedSwordBaseIE._TAGS:
                                self._get_api_tags()
                        _tagname = _tagname.lower().replace(' ', '-').replace(',', '-')
                        if _tagname in (NakedSwordBaseIE._TAGS['themes'] + NakedSwordBaseIE._TAGS['sex_acts']):
                            query = f'tags_name={_tagname}'
                        else:
                            self.report_warning(f"{premsg} wrong tagname")

                    elif _id := info_url.get('id'):
                        if '/stars/' in url:
                            query = f'stars_id={_id}'
                        elif '/studios/' in url:
                            query = f'studios_id={_id}'
                        else:
                            self.report_warning(f"{premsg} wrong url, thre is an id but not for stars or studios")

                    limit = info_url.get('limit')

                    _scenes = self._get_api_most_watched_scenes(query, limit=limit)

                    playlist_id = query
                    playlist_title = "Search"

                def _getter(_id_movie, index):
                    return f'{self.get_movie_url(_id_movie)}/scene/{index}'

                if not _scenes:
                    raise ExtractorError('no scenes found')

                _info_scenes = [
                    (_getter(sc['movie']['id'], sc['index']), int(sc['index']))
                    for sc in _scenes]

                self.logger_debug(f"{premsg} url scenes [{len(_info_scenes)}]\n{_info_scenes}")

                if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

                    isc = self._get_extractor('NakedSwordScene')

                    _entries = []
                    with ThreadPoolExecutor(thread_name_prefix='nsscmwatch') as ex:
                        futures = {
                            ex.submit(isc.get_entry, _info[0], index=_info[1], _type=_type): _info[0]
                            for _info in _info_scenes}

                    for fut in futures:
                        if _res := fut.result():
                            _res.update({'original_url': url})
                            _entries.append(_res)

                    return self.playlist_result(
                        _entries,
                        playlist_id=playlist_id,
                        playlist_title=playlist_title)

                else:
                    return self.playlist_from_matches(
                        _info_scenes,
                        getter=lambda x: x[0],
                        ie=NakedSwordMovieIE,
                        playlist_id=playlist_id,
                        playlist_title=playlist_title)

        except Exception as e:
            logger.exception(f"{premsg} {str(e)}")
            raise

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        try:
            self.report_extraction(url)
            return self.get_entries_from_scenes_list(url, _type="hls")
        except (ExtractorError, StatusStop):
            raise
        except ReExtractInfo as e:
            raise_extractor_error(str(e), _from=e)
        except Exception as e:
            raise_extractor_error(str(e), _from=e)


class NakedSwordMoviesPlaylistIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:movies:playlist'  # type: ignore
    _VALID_URL = r'''(?x)
        https?://(?:www\.)?nakedsword.com/(?:
            ((((studios|stars)/(?P<id>[\d]+)/(?P<name>[^/?#&]+))|
            (tag/(?P<tagname>[^/?#&]+))|most-watched)\?content=Movies(&limit=(?P<limit>\d+))?)|
            playlists/(?P<plid>\d+)/movies/.*|top-10)'''

    def get_entries_from_movies_list(self, url: str, **kwargs):

        premsg = "[get_entries]"
        if msg := kwargs.get('msg'):
            premsg = f"{msg}{premsg}"

        try:
            info_url = try_get(self._match_valid_url(url), lambda x: x.groupdict())
            _movies = []
            playlist_title = None
            playlist_id = None
            if isinstance(info_url, dict):
                if (_plid := info_url.get('plid')):
                    playlist_id = _plid
                    playlist_title, _movies = self._get_api_movies_playlist(_plid)
                else:
                    if url.endswith('top-10'):
                        playlist_id = 'top-10'
                        playlist_title = 'top-10'
                        query = "top_movies"
                        limit = None
                    else:
                        query = "most_watched"
                        if _tagname := info_url.get('tagname'):
                            with NakedSwordBaseIE._LOCK:
                                if not NakedSwordBaseIE._TAGS:
                                    self._get_api_tags()
                            _tagname = _tagname.lower().replace(' ', '-').replace(',', '-')
                            if _tagname in (
                                    NakedSwordBaseIE._TAGS['themes'] + NakedSwordBaseIE._TAGS['sex_acts']):
                                query = f'tags_name={_tagname}'
                            else:
                                self.report_warning(f"{premsg} wrong tagname")

                        elif _id := info_url.get('id'):
                            if '/stars/' in url:
                                query = f'stars_id={_id}'
                            elif '/studios/' in url:
                                query = f'studios_id={_id}'
                            else:
                                self.report_warning(f"{premsg} wrong url")

                        limit = info_url.get('limit')
                        playlist_id = f'{sanitize_filename(query, restricted=True)}'
                        playlist_title = "MoviesPlaylist"

                    _movies = self._get_api_most_watched_movies(query, limit=limit)

            if not _movies or not playlist_id or not playlist_title:
                raise ExtractorError('no movies found')
            else:
                _url_movies = list(dict.fromkeys([
                    self.get_movie_url(x['id']) for x in _movies]))

                self.logger_debug(f"{premsg} url movies [{len(_url_movies)}]\n{_url_movies}")

                if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):
                    imov = self._get_extractor('NakedSwordMovie')
                    _entries = []
                    with ThreadPoolExecutor(thread_name_prefix='nsmvmwatched') as ex:
                        futures = {
                            ex.submit(imov.get_entries, _url, _type="hls", force=True): _url
                            for _url in _url_movies}

                    for fut in futures:
                        if _res := fut.result():
                            list(map(lambda x: x.update({'playlist_url': url}), _res))
                            _entries.extend(_res)

                    return self.playlist_result(
                        _entries, playlist_id=playlist_id, playlist_title=playlist_title)

                else:
                    return self.playlist_from_matches(
                        _url_movies,
                        getter=lambda x: x,
                        ie=NakedSwordMovieIE, playlist_id=playlist_id,
                        playlist_title=playlist_title)

        except Exception as e:
            logger.exception(f"{premsg} {str(e)}")
            raise

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        try:
            self.report_extraction(url)
            return self.get_entries_from_movies_list(url)
        except (ExtractorError, StatusStop):
            raise
        except ReExtractInfo as e:
            raise_extractor_error(str(e), _from=e)
        except Exception as e:
            raise_extractor_error(str(e), _from=e)


class NakedSwordJustAddedMoviesPlaylistIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:justaddedmovies:playlist'  # type: ignore
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/just-added(\?(?P<query>.+))?"

    def get_entries_from_justadded_movies_list(self, url, **kwargs):

        premsg = f"[get_entries][{url}]"
        if msg := kwargs.get('msg'):
            premsg = f"{msg}{premsg}"

        try:
            _movies = self._get_api_newest_movies()
            _movies_str = '\n'.join(
                [f"{_movie['publish_start']} {_movie['title']}" for _movie in _movies])
            self.logger_debug(f"{premsg} newest movies:\n{_movies_str}")
            _query = try_get(self._match_valid_url(url), lambda x: x.groupdict().get('query'))
            if _query:
                _params = {
                    el.split('=')[0]: el.split('=')[1]
                    for el in _query.split('&') if el.count('=') == 1}
            else:
                _params = {}
                _query = "noquery"
            if _f := _params.get('from'):
                _from = datetime.fromisoformat(f'{_f}T00:00:00.000001')
            else:
                _from = try_get(
                    _movies[0].get('publish_start'),
                    lambda x: datetime.fromisoformat(extract_timezone(x)[1]))
            if _t := _params.get('to'):
                _to = datetime.fromisoformat(f'{_t}T23:59:59.999999')
            else:
                _to = try_get(
                    _movies[-1].get('publish_start'),
                    lambda x: datetime.fromisoformat(extract_timezone(x)[1]))

            self.logger_debug(f"{premsg} from {str(_from)} to {str(_to)}")

            assert isinstance(_from, datetime)
            assert isinstance(_to, datetime)
            _movies_filtered = [
                _mov for _mov in _movies
                if _from <= datetime.fromisoformat(extract_timezone(_mov.get('publish_start'))[1]) <= _to]

            _url_movies = list(dict.fromkeys([
                self.get_movie_url(x['id']) for x in _movies_filtered]))

            self.logger_debug(f"{premsg} url movies [{len(_url_movies)}]\n{_url_movies}")

            if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

                imov = self._get_extractor('NakedSwordMovie')

                _entries = []
                with ThreadPoolExecutor(thread_name_prefix='nsmvnewest') as ex:
                    futures = {
                        ex.submit(imov.get_entries, _url, _type="hls", force=True): _url
                        for _url in _url_movies}

                for fut in futures:
                    if _res := fut.result():
                        list(map(lambda x: x.update({'playlist_url': url}), _res))
                        _entries.extend(_res)

                return self.playlist_result(
                    _entries,
                    playlist_id=f'{sanitize_filename(_query, restricted=True)}',
                    playlist_title="JustAddedMovies")

            else:
                return self.playlist_from_matches(
                    _url_movies,
                    getter=lambda x: x,
                    ie=NakedSwordMovieIE,
                    playlist_id=f'{sanitize_filename(_query, restricted=True)}',
                    playlist_title="JustAddedMovies")

        except Exception as e:
            logger.exception(f"{premsg} {str(e)}")
            raise

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        try:
            self.report_extraction(url)
            return self.get_entries_from_justadded_movies_list(url)
        except (ExtractorError, StatusStop):
            raise
        except ReExtractInfo as e:
            raise_extractor_error(str(e), _from=e)
        except Exception as e:
            raise_extractor_error(str(e), _from=e)
