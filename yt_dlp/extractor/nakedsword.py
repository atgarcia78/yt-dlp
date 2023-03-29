import html
import json
import logging
import re
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock, Event
import base64
import subprocess
import time
import os.path
import functools
import contextlib

from .commonwebdriver import (
    ConnectError,
    StatusStop,
    HTTPStatusError,
    ProgressTimer,
    ReExtractInfo,
    dec_on_exception2,
    dec_on_exception3,
    my_dec_on_exception,
    my_jitter,
    dec_retry,
    limiter_0_1,
    limiter_1,
    SeleniumInfoExtractor,
    Dict,
    Union,
    Response,
    Callable,
    ec,
    By
)

from ..utils import (
    ExtractorError,
    extract_timezone,
    int_or_none,
    sanitize_filename,
    traverse_obj,
    try_get,
    js_to_json
)

logger = logging.getLogger('nakedsword')

dec_on_reextract = my_dec_on_exception(
    ReExtractInfo, max_time=300, jitter='my_jitter', raise_on_giveup=True, interval=30)

dec_on_reextract_1 = my_dec_on_exception(
    ReExtractInfo, max_time=300, jitter='my_jitter', raise_on_giveup=True, interval=1)

dec_on_reextract_3 = my_dec_on_exception(
    ReExtractInfo, max_tries=3, jitter='my_jitter', raise_on_giveup=True, interval=2)


class checkLogged:

    def __init__(self, ifnot=False):
        self.ifnot = ifnot

    def __call__(self, driver):

        el_uas = driver.find_element(By.CSS_SELECTOR, "div.UserActions")
        if not self.ifnot:
            el_loggin = try_get(el_uas.find_elements(By.CLASS_NAME, "LoginWrapper"), lambda x: x[0])
            if not el_loggin:
                el_loggin = try_get(el_uas.find_elements(By.CLASS_NAME, "UserAction"), lambda x: x[1])
                if el_loggin and el_loggin.text.upper() == "MY STUFF":
                    return "TRUE"
                else:
                    return False
            else:
                el_loggin.click()
                return "FALSE"

        elif self.ifnot:
            el_loggin = try_get(el_uas.find_elements(By.CLASS_NAME, "LoginWrapper"), lambda x: x[0])
            if not el_loggin:
                el_loggin = try_get(el_uas.find_elements(By.CLASS_NAME, "UserAction"), lambda x: x[0])
                if el_loggin and el_loggin.text.upper() == "SIGN OUT":
                    el_loggin.click()
                    return "CHECK"
                else:
                    return False
            else:
                return "TRUE"


class toggleVideo:
    def __init__(self, logger, msg=None):
        self.init = False
        self.logger = logger
        self.pre = '[togglevideo]'
        if msg:
            self.pre = f'{msg}{self.pre}'

    def __call__(self, driver):
        try:
            if not self.init:
                el_play = driver.find_elements(By.CSS_SELECTOR, "button.vjs-big-play-button")
                if not el_play:
                    # self.logger.info('[play] button not present yet')
                    time.sleep(2)
                    return False
                # self.logger.info('[play] button present')
                el_play[0].click()
                self.init = True
                time.sleep(1)

            el_pause = driver.find_elements(By.CSS_SELECTOR, "button.vjs-play-control.vjs-control.vjs-button.vjs-playing")
            if not el_pause:
                # self.logger.info('[pause] button not present yet')
                time.sleep(2)
                return False
            # self.logger.info('[pause] button present')
            try:
                el_pause[0].click()
                self.logger(f'{self.pre} play-pause ok')
                return "ok"
            except Exception as e:
                self.logger(f'{self.pre} error click pause {repr(e)}')
                return "error"
        except Exception:
            # self.logger.info(f'[outer] {repr(e)}')
            raise


class NSAPI:

    def __init__(self):

        self.logger = logging.getLogger("NSAPI")
        self.call_lock = Lock()
        self.headers_api = {}
        self.ready = Event()
        self.timer = ProgressTimer()

    def init(self, iens):

        self.ready.set()
        self.iens = iens
        self.timer.reset()
        self.get_auth()

    def logout(self, msg=None):

        _pre = ''
        if msg:
            _pre = msg

        if self.iens._logout_api():
            self.headers_api = {}
            self.logger.debug(f"{_pre}[logout] OK")
            return "OK"
        else:
            self.logger.warning(f"{_pre}[logout] NOK")
            return "NOK"

    @dec_retry
    @dec_on_reextract
    def get_auth(self, msg=None):

        _pre = ''
        if msg:
            _pre = msg

        with self.call_lock:

            _logout = False
            try:
                _headers = self.iens._get_api_basic_auth()
                if _headers:
                    self.headers_api = _headers
                    self.logger.debug(f"{_pre}[get_auth] OK")
                    self.timer.reset()
                    return True
                else:
                    raise ExtractorError("couldnt auth")
            except ReExtractInfo:
                raise
            except ExtractorError:
                _logout = True
                raise ReExtractInfo("couldnt auth")
            except Exception as e:
                self.logger.exception(f"{_pre}[get_auth] {str(e)}")
                raise ExtractorError("error get auth")
            finally:
                if _logout:
                    self.logout()

    @dec_retry
    def get_refresh(self):

        with self.call_lock:

            try:
                if self.iens._refresh_api():
                    self.logger.debug("[refresh] OK")
                    self.timer.reset()
                    return True
                else:
                    raise ExtractorError("couldnt refresh")
            except Exception as e:
                self.logger.error(f"[refresh] {str(e)}")
                raise ExtractorError("error refresh")

    def __call__(self):
        if not self.headers_api:
            self.get_auth()
            return self.headers_api

        if not self.timer.has_elapsed(50):
            return self.headers_api
        else:
            self.logger.debug("[call] timeout to token refresh")
            if self.get_refresh():
                return self.headers_api


class NakedSwordBaseIE(SeleniumInfoExtractor):

    _SITE_URL = "https://www.nakedsword.com/"
    _NETRC_MACHINE = 'nakedsword'
    _LOCK = Lock()
    _TAGS = {}
    _MAXPAGE_SCENES_LIST = 2
    _APP_DATA = {}
    _API = NSAPI()
    _STATUS: str = 'NORMAL'
    _LIMITERS = {
        '403': limiter_1.ratelimit("nakedswordscene", delay=True),
        'NORMAL': limiter_0_1.ratelimit("nakedswordscene", delay=True)}
    _SEM = {
        '403': Lock(),
        'NORMAL': contextlib.nullcontext()}
    _JS_SCRIPT = '/Users/antoniotorres/.config/yt-dlp/nsword_getxident.js'
    _HEADERS = {
        "OPTIONS": {
            "AUTH": {
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'authorization,x-ident',
                'Referer': 'https://www.nakedsword.com/',
                'Origin': 'https://www.nakedsword.com',
                'Connection': 'keep-alive',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'Pragma': 'no-cache',
                'Cache-Control': 'no-cache'},
            "LOGOUT": {
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Access-Control-Request-Method': 'DELETE',
                'Access-Control-Request-Headers': 'authorization,donotrefreshtoken,x-ident',
                'Referer': 'https://www.nakedsword.com/',
                'Origin': 'https://www.nakedsword.com',
                'Connection': 'keep-alive',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'Pragma': 'no-cache',
                'Cache-Control': 'no-cache'}},
        "POST": {
            "AUTH": {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://www.nakedsword.com',
                'Connection': 'keep-alive',
                'Referer': 'https://www.nakedsword.com/',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'Pragma': 'no-cache',
                'Cache-Control': 'no-cache',
                'Content-Length': '0',
                'TE': 'trailers'}},
        "DELETE": {
            "LOGOUT": {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'doNotRefreshToken': 'true',
                'Origin': 'https://www.nakedsword.com',
                'Connection': 'keep-alive',
                'Referer': 'https://www.nakedsword.com/',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'Pragma': 'no-cache',
                'Cache-Control': 'no-cache',
                'Content-Length': '0',
                'TE': 'trailers'}},
        "FINAL": {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Authorization': None,
            'x-ident': None,
            'X-CSRF-TOKEN': None,
            'Origin': 'https://www.nakedsword.com',
            'Connection': 'keep-alive',
            'Referer': 'https://www.nakedsword.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
            'TE': 'trailers'},
        "MPD": {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': 'https://www.nakedsword.com',
            'Connection': 'keep-alive',
            'Referer': 'https://www.nakedsword.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
            'TE': 'trailers'}}

    _CLIENT = None

    @dec_on_reextract_3
    def get_formats(self, _types, _info):

        with NakedSwordBaseIE._LIMITERS[NakedSwordBaseIE._STATUS]:

            self.logger_debug(f"[get_formats] {_info}")

            m3u8_url = _info.get('m3u8_url')

            formats = []

            for _type in _types:

                self.check_stop()
                try:
                    if _type == "hls":

                        m3u8_doc = try_get(
                            self._send_request(m3u8_url, headers=NakedSwordBaseIE._HEADERS["MPD"]),
                            lambda x: (x.content).decode('utf-8', 'replace'))
                        if not m3u8_doc:
                            raise ReExtractInfo("couldnt get m3u8 doc")

                        formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                            m3u8_doc, m3u8_url, ext='mp4', entry_protocol='m3u8_native', m3u8_id='hls')
                        if formats_m3u8:
                            formats.extend(formats_m3u8)

                    elif _type == "dash":

                        mpd_url = m3u8_url.replace('playlist.m3u8', 'manifest.mpd')
                        _doc = try_get(
                            self._send_request(mpd_url, headers=NakedSwordBaseIE._HEADERS["MPD"]),
                            lambda x: (x.content).decode('utf-8', 'replace'))
                        if not _doc:
                            raise ExtractorError("couldnt get mpd doc")
                        mpd_doc = self._parse_xml(_doc, None)

                        formats_dash = self._parse_mpd_formats(
                            mpd_doc, mpd_id="dash", mpd_url=mpd_url, mpd_base_url=(mpd_url.rsplit('/', 1))[0])
                        if formats_dash:
                            formats.extend(formats_dash)

                    elif _type == "ism":

                        ism_url = m3u8_url.replace('playlist.m3u8', 'Manifest')
                        _doc = try_get(
                            self._send_request(ism_url, headers=NakedSwordBaseIE._HEADERS["MPD"]),
                            lambda x: (x.content).decode('utf-8', 'replace'))
                        if _doc:
                            ism_doc = self._parse_xml(_doc, None)
                            formats_ism, _ = self._parse_ism_formats_and_subtitles(ism_doc, ism_url)
                            if formats_ism:
                                formats.extend(formats_ism)

                except ReExtractInfo:
                    raise
                except Exception as e:
                    logger.error(f"[get_formats][{_type}][{_info.get('url')}] {str(e)}")

            if not formats:
                raise ExtractorError("couldnt find any format")
            else:
                return formats

    @dec_on_exception2
    @dec_on_exception3
    @limiter_0_1.ratelimit("nakedsword", delay=True)
    def _send_request(self, url, **kwargs) -> Union[None, Response]:

        pre = f'[send_request][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'

        driver = kwargs.get('driver', None)

        if driver:
            driver.get(url)
        else:
            try:
                return (self.send_http_request(url, client=NakedSwordBaseIE._CLIENT, **kwargs))
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"[send_request_http] {self._get_url_print(url)}: error - {repr(e)} - {str(e)}")

    def _logout_api(self):

        self._send_request(
            "https://ns-api.nakedsword.com/frontend/auth/logout", _type="OPTIONS",
            headers=self._HEADERS["OPTIONS"]["LOGOUT"])
        _headers_del = self._HEADERS["DELETE"]["LOGOUT"].copy()
        if (_headers := self.API_GET_HTTP_HEADERS()):
            _headers_del.update({'x-ident': _headers['x-ident'], 'Authorization': _headers['Authorization']})
            if (resdel := self._send_request(
                    "https://ns-api.nakedsword.com/frontend/auth/logout", _type="DELETE", headers=_headers_del)):
                assert isinstance(resdel, Response)
                return (resdel.status_code == 204)
            else:
                return False

    def _get_data_app(self) -> Dict:

        app_data = {
            'PROPERTY_ID': None,
            'PASSPHRASE': None,
            'GTM_ID': None,
            'GTM_AUTH': None,
            'GTM_PREVIEW': None}

        try:

            _app_data = self.cache.load('nakedsword', 'app_data') or {}

            if not _app_data:

                js_content = try_get(
                    self._send_request(
                        try_get(
                            re.findall(
                                r'src="(/static/js/main[^"]+)',  # type: ignore
                                try_get(
                                    self._send_request(self._SITE_URL),  # type: ignore
                                    lambda z: html.unescape(z.text))),
                            lambda x: "https://www.nakedsword.com" + x[0])),
                    lambda y: html.unescape(y.text))
                if js_content:
                    data_js = re.findall(r'REACT_APP_([A-Z_]+:"[^"]+")', js_content)
                    data_js_str = "{" + f"{','.join(data_js)}" + "}"
                    data = json.loads(js_to_json(data_js_str))
                    if data:
                        for key in app_data:
                            app_data.update({key: data[key]})

                        self.cache.store('nakedsword', 'app_data', app_data)

            else:
                app_data = _app_data

            return app_data

        except Exception as e:
            logger.exception(str(e))
            return app_data

    def _get_api_basic_auth(self) -> Dict:

        self._send_request(
            "https://ns-api.nakedsword.com/frontend/auth/login",
            _type="OPTIONS", headers=self._HEADERS["OPTIONS"]["AUTH"])
        username, pwd = self._get_login_info()
        _headers_post = self._HEADERS["POST"]["AUTH"].copy()
        _headers_post['Authorization'] = "Basic " + base64.urlsafe_b64encode(
            f"{username}:{pwd}".encode()).decode('utf-8')
        xident = subprocess.run(
            ['node', self._JS_SCRIPT, NakedSwordBaseIE._APP_DATA['PASSPHRASE']],
            capture_output=True, encoding="utf-8").stdout.strip('\n')
        if xident:
            _headers_post['x-ident'] = xident
            token = try_get(
                self._send_request(
                    "https://ns-api.nakedsword.com/frontend/auth/login", _type="POST", headers=_headers_post),
                lambda x: traverse_obj(x.json(), ('data', 'jwt')))
            if token:
                _final = self._HEADERS["FINAL"].copy()
                _final.update({'x-ident': xident, 'Authorization': f'Bearer {token}', 'X-CSRF-TOKEN': token})

                return _final
        return {}

    def _refresh_api(self) -> bool:

        xident = subprocess.run(
            ['node', self._JS_SCRIPT, NakedSwordBaseIE._APP_DATA['PASSPHRASE']],
            capture_output=True, encoding="utf-8").stdout.strip('\n')
        if xident:
            NakedSwordBaseIE._API.headers_api['x-ident'] = xident
            return True
        else:
            return False

    def _get_api_details(self, movieid, headers=None):
        return try_get(
            self._send_request(
                f"https://ns-api.nakedsword.com/frontend/movies/{movieid}/details",
                headers=self.API_GET_HTTP_HEADERS()),
            lambda x: x.json().get('data') if x else None)

    def _get_api_newest_movies(self, pages=2):
        _pre = "https://ns-api.nakedsword.com/frontend/movies/feed?subset_sort_by=newest&subset_limit=480&page="
        _list_urls = [f"{_pre}{i}&sort_by=newest" for i in range(1, pages + 1)]
        _movies_info = []
        for _url in _list_urls:
            _movies_info.extend(
                try_get(
                    self._send_request(_url, headers=self.API_GET_HTTP_HEADERS()),  # type: ignore
                    lambda x: traverse_obj(x.json(), ('data', 'movies'), default=[]) if x else []))

        return _movies_info

    def _get_api_tags(self):

        feed = try_get(
            self._send_request("https://ns-api.nakedsword.com/frontend/tags/feed", headers=self.API_GET_HTTP_HEADERS()),
            lambda x: x.json().get('data'))
        if feed and feed.get('categories') and feed.get('sex-acts'):
            themes = [el['name'].lower().replace(' ', '-').replace(',', '-') for el in feed['categories']]
            sex_acts = [el['name'].lower().replace(' ', '-').replace(',', '-') for el in feed['sex_acts']]
            NakedSwordBaseIE._TAGS.update({'themes': themes, 'sex_acts': sex_acts})

    def _get_api_most_watched_scenes(self, query, limit=60):

        if query == 'most_watched':
            _query = ""
        else:
            _query = query + '&'
        _limit = limit or 60
        pages = int(_limit) // 30 + 1
        _pre1 = "https://ns-api.nakedsword.com/frontend/scenes/feed?"
        _pre2 = "per_page=30&subset_sort_by=most_watched&subset_limit="
        _list_urls = [f"{_pre1}{_query}{_pre2}{_limit}&page={i}&sort_by=most_watched" for i in range(1, pages + 1)]
        _scenes_info = []
        for _url in _list_urls:
            _scenes_info.extend(
                try_get(
                    self._send_request(_url, headers=self.API_GET_HTTP_HEADERS()),  # type: ignore
                    lambda x: traverse_obj(x.json(), ('data', 'scenes'), default=[]) if x else []))

        return _scenes_info

    def _get_api_scene_urls(self, details):

        movie_id = details.get('id')
        _pre1 = "https://ns-api.nakedsword.com/frontend/streaming/aebn/movie/"
        _pre2 = "?max_bitrate=10500&scenes_id="
        _res = []
        for sc in details.get('scenes'):
            _url = f"{_pre1}{movie_id}{_pre2}{sc['id']}&start_time={sc['startTimeSeconds']}&duration="
            _url += f"{sc['endTimeSeconds']-sc['startTimeSeconds']}&format=HLS"
            _res.append(_url)

        return _res

    def get_streaming_info(self, url, **kwargs):

        premsg = f"[get_streaming_info][{url}]"
        index_scene = int_or_none(kwargs.get('index'))

        try:

            _url_movie = try_get(self._send_request(url.split('/scene/')[0]), lambda x: str(x.url))
            movieid = NakedSwordMovieIE._match_id(_url_movie)
            details = None
            details = self._get_api_details(movieid)
            if not details:
                raise ReExtractInfo(f"{premsg} no details info")

            _urls_api = self._get_api_scene_urls(details)
            num_scenes = len(details.get('scenes'))

            if index_scene:
                _start_ind = index_scene
                _end_ind = _start_ind + 1
            else:
                _start_ind = 1
                _end_ind = num_scenes + 1

            info_scenes = []
            _urls_sc = []

            m3u8urls_scenes = []

            for ind in range(_start_ind, _end_ind):
                _urls_sc.append(f"{_url_movie}/scene/{ind}")
                _info_scene = try_get(
                    self._send_request(_urls_api[ind - 1], headers=self.API_GET_HTTP_HEADERS()),
                    lambda x: x.json().get('data') if x else None)
                if _info_scene:
                    m3u8urls_scenes.append(_info_scene)

            if len(m3u8urls_scenes) != len(_urls_sc):
                _text = f"{premsg} number of info scenes {len(m3u8urls_scenes)} doesnt match with number of urls sc "
                _text += f"{len(_urls_sc)}\n{_urls_sc}\n\n{m3u8urls_scenes}"
                logger.error(_text)
                _text2 = f"{premsg} number of info scenes {len(m3u8urls_scenes)} doesnt match with number of urls sc "
                _text2 += f"{len(_urls_sc)}"
                raise ReExtractInfo(_text2)

            if index_scene:
                info_scene = {'index': index_scene, 'url': _urls_sc[0], 'm3u8_url': m3u8urls_scenes[0]}
                return (info_scene, details)

            else:
                for i, (m3u8_url, _url) in enumerate(zip(m3u8urls_scenes, _urls_sc)):

                    if not m3u8_url:
                        raise ReExtractInfo(f"{premsg}[{_url}] couldnt find m3u8 url")

                    info_scenes.append({'index': i + 1, 'url': _url, 'm3u8_url': m3u8_url})

                return (info_scenes, details)

        except Exception as e:
            logger.exception(str(e))
            raise

    def _is_logged(self, driver):

        if 'nakedsword.com' not in driver.current_url:
            self._send_request(self._SITE_URL, driver=driver)
        logged_ok = (self.wait_until(driver, 10, checkLogged()) == "TRUE")
        self.logger_debug(f"[is_logged] {logged_ok}")

        return logged_ok

    def _logout(self, driver):
        try:

            logged_out = False
            if 'nakedsword.com' not in driver.current_url:
                self._send_request(self._SITE_URL, driver=driver)

            res = self.wait_until(driver, 10, checkLogged(ifnot=True))
            if res == "TRUE":
                logged_out = True
            elif res == "CHECK":
                self.wait_until(driver, 2)
                res = self.wait_until(driver, 10, checkLogged(ifnot=True))
                if res == "TRUE":
                    logged_out = True
                else:
                    driver.delete_all_cookies()
                    self.wait_until(driver, 2)
                    res = self.wait_until(driver, 10, checkLogged(ifnot=True))
                    if res == "TRUE":
                        logged_out = True
            if logged_out:
                self.logger_debug("[logout] Logout OK")
            else:
                self.logger_debug("[logout] Logout NOK")
        except Exception as e:
            self.report_warning(f"[logout] Logout NOK {repr(e)}")

    def _login(self, driver):

        try:
            if not self._is_logged(driver):

                self.check_stop()

                self.report_login()
                username, password = self._get_login_info()
                if not username or not password:
                    self.raise_login_required(
                        'A valid %s account is needed to access this media.'
                        % self._NETRC_MACHINE)

                el_username = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input.Input")))
                el_psswd = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input.Input.Password")))
                el_submit = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "button.SignInButton")))

                assert el_username and el_psswd and el_submit

                el_username.send_keys(username)
                el_psswd.send_keys(password)
                el_submit.click()

                self.wait_until(driver, 2)

                logged_ok = (self.wait_until(driver, 10, checkLogged()) == "TRUE")
                if logged_ok:
                    self.logger_debug("[login] Login OK")
                    return True
                else:
                    raise ExtractorError("login nok")

            else:
                self.logger_debug("[login] Already logged")
                return True
        except Exception as e:
            logger.exception(repr(e))
            self._logout(driver)
            raise

    class synchronized:

        def __call__(self, func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with NakedSwordBaseIE._LOCK:
                    return func(*args, **kwargs)
            return wrapper

    @synchronized()
    def get_formats_by_har(self, url, videoid, msg=None):

        pre = '[get_entry_by_har]'
        if msg:
            pre = f'{msg}{pre}'

        _har_file = f"/Users/antoniotorres/testing/dump_{videoid}_{time.strftime('%y%m%d-%H%M%S')}.har"
        cmd = f"mitmdump -s /Users/antoniotorres/Projects/async_downloader/har_dump.py --set hardump={_har_file}"

        ps = subprocess.Popen(cmd.split(' '), stdout=subprocess.PIPE)

        try:
            ps.poll()
            time.sleep(2)
            ps.poll()
            time.sleep(1)
            if ps.returncode is not None:
                _log = ''
                if ps.stdout:
                    _log = '\n'.join([line.decode('utf-8').strip() for line in ps.stdout])
                self.logger_debug(f"{pre} error executing mitmdump, returncode[{ps.returncode}]\n{_log}")
                raise ReExtractInfo("couldnt launch mitmdump")
            driver = self.get_driver(host='127.0.0.1', port='8080')
            try:
                self._login(driver)
                self._send_request(url, driver=driver)
                self.wait_until(driver, 3)
                elvid = self.wait_until(driver, 10, toggleVideo(self.logger_debug, msg=pre))
                if not elvid or elvid == "error":
                    raise ReExtractInfo("couldnt reproduce video")

                ps.terminate()

                def wait_for_file(file, timeout):
                    start = time.monotonic()
                    while (time.monotonic() - start < timeout):
                        if not os.path.exists(file):
                            time.sleep(0.2)
                        else:
                            return True
                    return False

                self.logger_debug(f'{pre} start wait for har file')
                if not wait_for_file(_har_file, 5):
                    raise ReExtractInfo("couldnt get har file")
                self.logger_debug(f'{pre} har file ready')
            finally:
                self._logout(driver)
                self.rm_driver(driver)

            m3u8_url, _status = try_get(
                self.scan_for_request(r"playlist.m3u8$", har=_har_file),  # type: ignore
                lambda x: (x.get('url'), x.get('status')) if x else (None, None))

            self.logger_debug(f'{pre} status[{_status}] m3u8url[{m3u8_url}]')
            _formats = []
            _headers = NakedSwordBaseIE._HEADERS["MPD"]
            if m3u8_url and _status:
                if int(_status) > 400:
                    raise ReExtractInfo(f"raise status {_status}")
                m3u8_doc = try_get(self._send_request(m3u8_url, headers=NakedSwordBaseIE._HEADERS["MPD"]), lambda x: (x.content).decode('utf-8', 'replace'))
                if not m3u8_doc:
                    raise ReExtractInfo("couldnt get m3u8 doc")
                _formats, _ = self._parse_m3u8_formats_and_subtitles(m3u8_doc, m3u8_url, ext="mp4", headers=_headers, entry_protocol='m3u8_native', m3u8_id="hls")

            if not _formats:
                raise ReExtractInfo('Couldnt get video formats')

            for _format in _formats:
                if (_head := _format.get('http_headers')):
                    _head.update(_headers)
                else:
                    _format.update({'http_headers': _headers})

            return _formats

        except ReExtractInfo as e:
            self.logger_debug(f'{pre}[reextractinfo] {repr(e)}')
            raise
        except Exception as e:
            self.logger_debug(f"{pre} {repr(e)}")
            raise ReExtractInfo(f"Couldnt get video formats - {repr(e)}")
        finally:
            ps.terminate()

    def _real_initialize(self):

        try:
            assert self._downloader
            super()._real_initialize()

            with NakedSwordBaseIE._LOCK:
                if not NakedSwordBaseIE._CLIENT:
                    NakedSwordBaseIE._CLIENT = self._CLIENT
                if not NakedSwordBaseIE._APP_DATA:
                    NakedSwordBaseIE._APP_DATA = self._get_data_app()
                if not NakedSwordBaseIE._API.ready.is_set():
                    NakedSwordBaseIE._API.init(self)

        except Exception as e:
            logger.error(repr(e))

    def API_AUTH(self, msg=None):
        return NakedSwordBaseIE._API.get_auth(msg=msg)

    def API_REFRESH(self):
        return NakedSwordBaseIE._API.get_refresh()

    def API_LOGOUT(self, msg=None):
        return NakedSwordBaseIE._API.logout(msg=msg)

    def API_GET_HTTP_HEADERS(self):
        return NakedSwordBaseIE._API()


class NakedSwordSceneIE(NakedSwordBaseIE):
    IE_NAME = 'nakedswordscene'  # type: ignore
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<movieid>[\d]+)/(?P<title>[^\/]+)/scene/(?P<id>[\d]+)"

    def get_entry(self, url, **kwargs):

        with NakedSwordBaseIE._SEM[NakedSwordBaseIE._STATUS]:

            return self._get_entry(url, **kwargs)

    @dec_on_reextract
    def _get_entry(self, url, **kwargs):

        _type = kwargs.get('_type', 'all')
        if _type == 'all':
            _types = ['hls', 'dash', 'ism']
        else:
            _types = [_type]
        msg = kwargs.get('msg')
        index_scene = try_get(
            kwargs.get('index') or try_get(self._match_valid_url(url), lambda x: x.groupdict().get('id')),
            lambda x: int(x) if x else 1)

        assert index_scene
        premsg = f"[get_entry][{url.split('movies/')[1]}]"
        if msg:
            premsg = f"{msg}{premsg}"

        self.logger_debug(f"{premsg} start to get entry")
        self.API_AUTH(msg='[get_entry]')
        _url_movie = try_get(self._send_request(url.split('/scene/')[0]), lambda x: str(x.url))
        _info, details = self.get_streaming_info(_url_movie, index=index_scene)

        _title = f"{sanitize_filename(details.get('title'), restricted=True)}_scene_{index_scene}"
        scene_id = traverse_obj(details, ('scenes', int(index_scene) - 1, 'id'))

        _entry = {
            "id": str(scene_id),
            "title": _title,
            "formats": [],
            "ext": "mp4",
            "webpage_url": url,
            "extractor_key": 'NakedSwordScene',
            "extractor": 'nakedswordscene'
        }

        try:

            formats = self.get_formats(_types, _info)

            if formats:
                _entry.update({'formats': formats})
                self.logger_info(f"{premsg}: OK got entr")
                return _entry

            else:
                raise ExtractorError(f'{premsg}: error - no formats')

        except ReExtractInfo:
            try:
                self.logger_info(f"{premsg}: error formats, will try with HAR")
                formats = self.get_formats_by_har(url, str(scene_id), msg=premsg)
                if formats:
                    _entry.update({'formats': formats})
                    self.logger_info(f"{premsg}: OK got formats by HAR")
                    return _entry
                else:
                    raise ExtractorError(f'{premsg}: error - no formats')
            except ReExtractInfo:
                self.logger_info(f"{premsg}: error formats with HAR. Will retry again")
                self.API_LOGOUT(msg='[get_entry]')
                time.sleep(5)
                if NakedSwordBaseIE._CLIENT:
                    try:
                        NakedSwordBaseIE._CLIENT.cookies.clear(domain='.nakedsword.com')
                    except KeyError:
                        pass
                    try:
                        NakedSwordBaseIE._CLIENT.cookies.clear(domain='nakedsword.com')
                    except KeyError:
                        pass
                raise

        except StatusStop:
            raise
        except Exception as e:
            logger.exception(repr(e))
            raise ExtractorError(f'{premsg}: error - {repr(e)}')

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        try:
            self.report_extraction(url)
            nscene = int(self._match_id(url))
            return self.get_entry(url, index=nscene, _type="hls")

        except (ExtractorError, StatusStop):
            raise
        except ReExtractInfo as e:
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')


class NakedSwordMovieIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:movie:playlist'  # type: ignore
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<id>[\d]+)/(?P<title>[^/?#&]+)"
    _MOVIES_URL = "https://www.nakedsword.com/movies/"
    _MOVIES = {}

    @dec_on_reextract_1
    def get_entries(self, url, **kwargs):
        _type = kwargs.get('_type', 'all')
        if _type == 'all':
            _types = ['hls', 'dash', 'ism']
        else:
            _types = [_type]
        msg = kwargs.get('msg')
        premsg = "[get_entries]"
        if msg:
            premsg = f"{msg}{premsg}"

        _force_list = kwargs.get('force', False)

        _url_movie = try_get(self._send_request(url), lambda x: str(x.url))

        assert _url_movie

        if _url_movie not in NakedSwordMovieIE._MOVIES:
            NakedSwordMovieIE._MOVIES.update({_url_movie: {'nok': [], 'ok': [], 'entries': {}, 'final': True}})

        if not NakedSwordMovieIE._MOVIES[_url_movie]['final']:

            self.API_LOGOUT(msg='[getentries]')
            time.sleep(5)
            if NakedSwordBaseIE._CLIENT:
                try:
                    NakedSwordBaseIE._CLIENT.cookies.clear(domain='.nakedsword.com')
                except KeyError:
                    pass
                try:
                    NakedSwordBaseIE._CLIENT.cookies.clear(domain='nakedsword.com')
                except KeyError:
                    pass

            _timeout = my_jitter(30)
            self.logger_info(f'{premsg}[{_url_movie.split("movies/")[1]}][wait] start[{_timeout}]')
            with self.create_progress_bar(msg=f'[{_url_movie.split("movies/")[1]}][wait]') as progress_bar:

                def _wait_for_either(check: Callable, timeout: Union[float, int]):
                    t = 0
                    start = time.monotonic()
                    while (time.monotonic() - start < timeout):
                        check()
                        time.sleep(1)
                        t += 1
                        progress_bar.print(f' Waiting {t}/{timeout}')  # type: ignore

                _wait_for_either(self.check_stop, timeout=_timeout)
                progress_bar.print('')  # type: ignore

            logger.info(f'[{_url_movie.split("movies/")[1]}][wait] end')

            self.API_AUTH(msg='[getentries]')
            time.sleep(5)

        if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

            try:

                for _ in range(2):

                    info_streaming_scenes, details = self.get_streaming_info(_url_movie)

                    #  _entries = []

                    sublist = []
                    if hasattr(self, 'args_ie'):
                        sublist = traverse_obj(self.args_ie, ('nakedswordmovie', 'listreset'), default=[])

                        self.logger_debug(f"{premsg} sublist of movie scenes: {sublist}")

                    _raise_reextract = []

                    for _info in info_streaming_scenes:

                        self.check_stop()

                        i = _info.get('index')

                        self.logger_debug(f"{premsg}[{i}]:\n{_info}")

                        _title = f"{sanitize_filename(details.get('title'), restricted=True)}_scene_{i}"
                        scene_id = traverse_obj(details, ('scenes', i - 1, 'id'))

                        _entry = {
                            "id": str(scene_id),
                            "title": _title,
                            "formats": [],
                            "ext": "mp4",
                            "webpage_url": _info.get('url'),
                            "original": _url_movie,
                            "extractor_key": 'NakedSwordScene',
                            "extractor": 'nakedswordscene'
                        }

                        if (not sublist or (sublist and i in sublist)):

                            if i in NakedSwordMovieIE._MOVIES[_url_movie]['ok']:
                                self.logger_debug(f"{premsg}[{i}][{_info.get('url')}]: already got entry")

                            else:

                                try:
                                    formats = self.get_formats(_types, _info)
                                    if formats:
                                        _entry.update({'formats': formats})
                                        self.logger_debug(f"{premsg}[{i}][{_info.get('url')}]: OK got entry")
                                        NakedSwordMovieIE._MOVIES[_url_movie]['ok'].append(i)
                                        NakedSwordMovieIE._MOVIES[_url_movie]['entries'][i] = _entry
                                        if i in NakedSwordMovieIE._MOVIES[_url_movie]['nok']:
                                            NakedSwordMovieIE._MOVIES[_url_movie]['nok'].remove(i)

                                except ReExtractInfo:
                                    try:
                                        formats = self.get_formats_by_har(_info.get('url'), scene_id, msg=f'[get_entries][{_info.get("url").split("movies/")[1]}]')
                                        if formats:
                                            _entry.update({'formats': formats})
                                            self.logger_info(f"{premsg}[{i}][{_info.get('url')}]: OK got entry by HAR\n{_entry}")
                                            NakedSwordMovieIE._MOVIES[_url_movie]['ok'].append(i)
                                            NakedSwordMovieIE._MOVIES[_url_movie]['entries'][i] = _entry
                                            if i in NakedSwordMovieIE._MOVIES[_url_movie]['nok']:
                                                NakedSwordMovieIE._MOVIES[_url_movie]['nok'].remove(i)

                                    except ReExtractInfo:
                                        _raise_reextract.append(i)
                                        if i not in NakedSwordMovieIE._MOVIES[_url_movie]['nok']:
                                            NakedSwordMovieIE._MOVIES[_url_movie]['nok'].append(i)
                                        NakedSwordMovieIE._MOVIES[_url_movie]['final'] = False

                        else:
                            NakedSwordMovieIE._MOVIES[_url_movie]['entries'][i] = _entry

                    if _raise_reextract:
                        self.logger_info(f"{premsg} ERROR in {_raise_reextract} from sublist of movie scenes: {sublist}. [final]:{NakedSwordMovieIE._MOVIES[_url_movie]['final']} [ok]:{NakedSwordMovieIE._MOVIES[_url_movie]['ok']} [nok]:{NakedSwordMovieIE._MOVIES[_url_movie]['nok']}")
                        #  self.API_LOGOUT()
                        #  self.API_AUTH()
                        raise ReExtractInfo("error in scenes of movie")

                    else:
                        self.logger_info(f"{premsg} OK format for sublist of movie scenes: {sublist}. [final]:{NakedSwordMovieIE._MOVIES[_url_movie]['final']} [ok]:{NakedSwordMovieIE._MOVIES[_url_movie]['ok']} [nok]:{NakedSwordMovieIE._MOVIES[_url_movie]['nok']}")
                        if not NakedSwordMovieIE._MOVIES[_url_movie]['final']:
                            NakedSwordMovieIE._MOVIES[_url_movie] = {'nok': [], 'ok': [], 'entries': {}, 'final': True}
                            # raise ReExtractInfo("error in scenes of movie")
                            continue
                        else:

                            _entries = [el[1] for el in sorted(NakedSwordMovieIE._MOVIES[_url_movie]['entries'].items())]

                            NakedSwordMovieIE._MOVIES.pop(_url_movie)

                            if _force_list:
                                return _entries
                            else:
                                playlist_id = str(details.get('id'))
                                pl_title = sanitize_filename(details.get('title'), restricted=True)
                                return self.playlist_result(_entries, playlist_id=playlist_id, playlist_title=pl_title,
                                                            webpage_url=_url_movie, original_url=_url_movie)

            except ReExtractInfo:
                raise
            except StatusStop:
                raise
            except Exception as e:
                logger.exception(f"{premsg} info streaming error - {repr(e)}")
                raise

        else:
            details = self._get_api_details(self._match_id(_url_movie))
            if details:
                if _force_list:
                    return [
                        self.url_result(f"{_url_movie.strip('/')}/scene/{x['index']}", ie=NakedSwordSceneIE)
                        for x in details.get('scenes')]
                else:
                    playlist_id = str(details.get('id'))
                    pl_title = sanitize_filename(details.get('title'), restricted=True)
                    return self.playlist_from_matches(
                        traverse_obj(details, 'scenes'),
                        getter=lambda x: f"{_url_movie.strip('/')}/scene/{x['index']}",
                        ie=NakedSwordSceneIE, playlist_id=playlist_id, playlist_title=pl_title,
                        webpage_url=_url_movie, original_url=_url_movie)

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        try:
            self.report_extraction(url)
            return self.get_entries(url, _type="hls")
        except (ExtractorError, StatusStop):
            raise
        except ReExtractInfo as e:
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')


class NakedSwordScenesPlaylistIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:scenes:playlist'  # type: ignore
    _VALID_URL = r'''(?x)
        https?://(?:www\.)?nakedsword.com/(?:
            ((studios|stars)/(?P<id>[\d]+)/(?P<name>[^/?#&]+))|
            (tag/(?P<tagname>[^/?#&]+))|most-watched)(\?limit=(?P<limit>\d+))?'''

    @dec_on_reextract
    def get_entries_from_scenes_list(self, url, **kwargs):

        _type = kwargs.get('_type', 'hls')
        msg = kwargs.get('msg')
        premsg = "[get_entries]"
        if msg:
            premsg = f"{msg}{premsg}"

        try:

            info_url = try_get(self._match_valid_url(url), lambda x: x.groupdict())

            assert info_url

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

            elif 'most-watched' in url:
                query = "most_watched"

            limit = info_url.get('limit')

            _scenes = self._get_api_most_watched_scenes(query, limit=limit)

            def _getter(movie_id, index):
                _movie_url = try_get(
                    self._send_request(f"https://www.nakedsword.com/movies/{movie_id}/_"),
                    lambda x: str(x.url))
                return f'{_movie_url}/scene/{index}'

            _info_scenes = [(_getter(sc['movie']['id'], sc['index']), int(sc['index'])) for sc in _scenes]

            self.logger_debug(f"{premsg} url scenes [{len(_info_scenes)}]\n{_info_scenes}")

            if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

                isc = self._get_extractor('NakedSwordScene')

                _entries = []
                with ThreadPoolExecutor(thread_name_prefix='nsmostwatch') as ex:
                    futures = {
                        ex.submit(isc.get_entry, _info[0], index=_info[1], _type=_type): _info[0]
                        for _info in _info_scenes}

                for fut in futures:
                    if _res := fut.result():
                        _res.update({'original_url': url})
                        _entries.append(_res)

                return self.playlist_result(_entries, playlist_id=query, playlist_title="Search")

            else:
                return self.playlist_from_matches(
                    _info_scenes,
                    getter=lambda x: x[0],
                    ie=NakedSwordMovieIE, playlist_id=query, playlist_title="Search")

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
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')


class NakedSwordJustAddedMoviesPlaylistIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:justaddedmovies:playlist'  # type: ignore
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/just-added(\?(?P<query>.+))?"

    def get_entries_from_movies_list(self, url, **kwargs):

        premsg = f"[get_entries][{url}]"
        msg = kwargs.get('msg')
        if msg:
            premsg = f"{msg}{premsg}"

        try:

            _movies = sorted(
                self._get_api_newest_movies(),
                key=lambda x: datetime.fromisoformat(extract_timezone(x.get('publish_start'))[1]))

            _query = try_get(self._match_valid_url(url), lambda x: x.groupdict().get('query'))
            if _query:
                _params = {el.split('=')[0]: el.split('=')[1] for el in _query.split('&') if el.count('=') == 1}
            else:
                _params = {}
                _query = "noquery"
            if _f := _params.get('from'):
                _from = datetime.fromisoformat(f'{_f}T00:00:00.000001')
            else:
                _from = try_get(
                    _movies[0].get('publish_start'),
                    lambda x: datetime.fromisoformat(extract_timezone(x)[1]))
            _t = _params.get('to')
            if _t:
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

            _url_movies = list(set([try_get(
                self._send_request(_url), lambda x: str(x.url))
                for _url in [f'https://www.nakedsword.com/movies/{x["id"]}/_' for x in _movies_filtered]]))

            self.logger_debug(f"{premsg} url movies [{len(_url_movies)}]\n{_url_movies}")

            if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

                imov = self._get_extractor('NakedSwordMovie')

                _entries = []
                with ThreadPoolExecutor(thread_name_prefix='nsnewest') as ex:
                    futures = {ex.submit(imov.get_entries, _url, _type="hls", force=True): _url for _url in _url_movies}

                for fut in futures:
                    _res = fut.result()
                    if _res:
                        _entries += [_r for _r in _res if not _r.update({'original_url': url})]

                return self.playlist_result(
                    _entries, playlist_id=f'{sanitize_filename(_query, restricted=True)}', playlist_title="Search")

            else:
                return self.playlist_from_matches(
                    _url_movies,
                    getter=lambda x: x,
                    ie=NakedSwordMovieIE, playlist_id=f'{sanitize_filename(_query, restricted=True)}',
                    playlist_title="Search")

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
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')
