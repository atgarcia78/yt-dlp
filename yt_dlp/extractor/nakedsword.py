import html
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock
import base64
import subprocess
import time
import contextlib

from .commonwebdriver import (
    ConnectError,
    StatusStop,
    HTTPStatusError,
    ProgressTimer,
    ReExtractInfo,
    dec_on_exception3,
    my_dec_on_exception,
    dec_on_driver_timeout,
    my_jitter,
    dec_retry,
    limiter_0_1,
    limiter_1,
    SeleniumInfoExtractor,
    Dict,
    Union,
    Response,
    ec,
    By,
    Callable,
    cast,
    WebElement,
    raise_extractor_error,
    raise_reextract_info
)

from ..utils import (
    ExtractorError,
    extract_timezone,
    int_or_none,
    sanitize_filename,
    traverse_obj,
    try_get,
    js_to_json,
    find_available_port

)

logger = logging.getLogger('nakedsword')

dec_on_reextract = my_dec_on_exception(
    ReExtractInfo, max_time=300, jitter='my_jitter', raise_on_giveup=True, interval=30)

dec_on_reextract_1 = my_dec_on_exception(
    ReExtractInfo, max_time=300, jitter='my_jitter', raise_on_giveup=True, interval=1)

dec_on_reextract_3 = my_dec_on_exception(
    ReExtractInfo, max_tries=3, jitter='my_jitter', raise_on_giveup=True, interval=2)


def _wait_for_either(progress_bar, check: Callable, timeout: Union[float, int]):

    start = time.monotonic()
    while (time.monotonic() - start < timeout):
        check()
        time.sleep(1)
        progress_bar.update()
        progress_bar.print('Waiting')  # type: ignore
    return ''


class checkLogged:

    def __init__(self, ifnot=False):
        self.ifnot = ifnot

    def __call__(self, driver):

        el_uas = driver.find_element(By.CSS_SELECTOR, "div.UserActions")
        el_loggin = try_get(el_uas.find_elements(By.CLASS_NAME, "LoginWrapper"), lambda x: x[0])

        if not self.ifnot:

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

    def __init__(self, msg=None):
        self.init = False
        self.logger = logger
        self.pre = '[togglevideo]'
        if msg:
            self.pre = f'{msg}{self.pre}'

    def __call__(self, driver):

        if not self.init:
            el_play = driver.find_elements(By.CSS_SELECTOR, "button.vjs-big-play-button")
            if not el_play:
                time.sleep(2)
                return False
            el_play[0].click()
            self.init = True
            time.sleep(2)

        el_video = driver.find_elements(By.TAG_NAME, "video")
        if not el_video:
            time.sleep(2)
            return False
        try:
            el_video[0].click()
            self.logger.debug(f'{self.pre} play-pause ok')
            return "ok"
        except Exception as e:
            self.logger.debug(f'{self.pre} error click video: {el_video[0].get_attribute("src")} {repr(e)}')
            return "error"


class selectHLS:
    def __call__(self, driver):
        el_menu = try_get(driver.find_elements(By.CSS_SELECTOR, "button.vjs-control.vjs-button.fas.fa-cog"), lambda x: x[0] if x and not x[0].click() else None)
        time.sleep(0.5)
        menu_hls = try_get(driver.find_elements(By.CLASS_NAME, "BaseVideoPlayerSettingsMenu-item-inner"), lambda x: x[1])
        if el_menu and menu_hls:
            if "checked=" not in menu_hls.get_attribute('outerHTML'):
                menu_hls.click()
                time.sleep(0.5)
                try_get(driver.find_elements(By.CSS_SELECTOR, "div.Button"), lambda x: (x[1].text, x[1].click()))
                time.sleep(0.5)
                el_menu.click()
                return "TRUE"
            else:
                el_menu.click()
                return "FALSE"
        else:
            return "error"


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
    _TAGS = {}
    _MAXPAGE_SCENES_LIST = 2
    _APP_DATA = {}
    _CLIENT = None
    _USERTOKEN = None
    ies = None
    headers_api = {}
    timer = ProgressTimer()
    call_lock = Lock()
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
                'Cache-Control': 'no-cache'},
            "REFRESH": {
                'Accept': '*/*',
                'Accept-Language': 'en,es-ES;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'authorization,x-csrf-token,x-ident',
                'Referer': 'https',
                'Origin': 'https',
                'Connection': 'keep-alive',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'Pragma': 'no-cache',
                'Cache-Control': 'no-cache',
                'TE': 'trailers'}},
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

    @classmethod
    @dec_retry
    @dec_on_reextract
    def API_LOGIN(cls, force=False, msg=None):
        _pre = msg if msg else ''
        if NakedSwordBaseIE._USERTOKEN and NakedSwordBaseIE.headers_api and not force:
            logger.debug(f'{_pre}[API_LOGIN] skipping login')
            return True
        _logout = False
        with NakedSwordBaseIE.call_lock:
            try:
                if NakedSwordBaseIE._get_api_basic_auth():
                    logger.debug(f"{_pre}[get_auth] OK")
                    return True
                else:
                    raise_extractor_error("couldnt auth")
            except ReExtractInfo:
                raise
            except ExtractorError as e:
                _logout = True
                raise_reextract_info(f"{_pre} couldnt auth {str(e)}", _from=e)
            except Exception as e:
                logger.debug(f"{_pre}[get_auth] {str(e)}", exc_info=True)
                raise_extractor_error(f"{_pre} error get auth {str(e)}", _from=e)
            finally:
                if _logout:
                    NakedSwordBaseIE.API_LOGOUT()

    @classmethod
    @dec_retry
    def API_REFRESH(cls):
        try:
            NakedSwordBaseIE.API_GET_XIDENT()
            with NakedSwordBaseIE.call_lock:
                if NakedSwordBaseIE._refresh_api():
                    logger.debug("[refresh_api] ok")
                    return True
                else:
                    raise_extractor_error("refresh nok")
        except ExtractorError:
            raise
        except Exception as e:
            logger.debug(f"[refresh_api] {str(e)}", exc_info=True)
            raise_extractor_error(f"error refresh {str(e)}", _from=e)

    @classmethod
    @dec_retry
    def API_GET_XIDENT(cls):
        with NakedSwordBaseIE.call_lock:
            try:
                if (xident := NakedSwordBaseIE._get_api_xident()):
                    NakedSwordBaseIE.headers_api['xident'] = xident
                    logger.debug("[get_xident] OK")

                    return True
                else:
                    raise ExtractorError("couldnt get new xident")
            except Exception as e:
                logger.error(f"[get_xident] {str(e)}")
                raise ExtractorError("error new xident")

    @classmethod
    def API_LOGOUT(cls, msg=None):
        _pre = msg if msg else ''
        NakedSwordBaseIE.API_GET_HTTP_HEADERS()
        if NakedSwordBaseIE._logout_api():
            NakedSwordBaseIE.headers_api = {}
            NakedSwordBaseIE._USERTOKEN = None
            logger.debug(f"{_pre}[logout] OK")
            return "OK"
        else:
            logger.warning(f"{_pre}[logout] NOK")
            return "NOK"

    @classmethod
    def API_GET_HTTP_HEADERS(cls):
        if not NakedSwordBaseIE.headers_api:
            NakedSwordBaseIE.API_LOGIN()
            return NakedSwordBaseIE.headers_api
        elif not NakedSwordBaseIE.timer.has_elapsed(50):
            return NakedSwordBaseIE.headers_api
        else:
            logger.debug("[call] timeout to new xident")
            NakedSwordBaseIE.API_GET_XIDENT()
            return NakedSwordBaseIE.headers_api

    @classmethod
    @dec_on_driver_timeout
    @dec_on_exception3
    @limiter_0_1.ratelimit("nakedsword", delay=True)
    def _send_request(cls, url, **kwargs) -> Union[None, Response]:

        pre = f'[send_request][{cls._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'

        driver = kwargs.get('driver', None)

        if driver:
            driver.get(url)
        else:
            try:
                return (cls._send_http_request(url, client=NakedSwordBaseIE._CLIENT, **kwargs))
            except (HTTPStatusError, ConnectError) as e:
                logger.warning(f"[send_request_http] {cls._get_url_print(url)}: error - {repr(e)} - {str(e)}")

    @classmethod
    def _logout_api(cls):

        cls._send_request(
            NakedSwordBaseIE._API_URLS['logout'], _type="OPTIONS",
            headers=cls._HEADERS["OPTIONS"]["LOGOUT"])
        _headers_del = cls._HEADERS["DELETE"]["LOGOUT"].copy()
        if (_headers := NakedSwordBaseIE.API_GET_HTTP_HEADERS()):
            _headers_del.update(
                {'x-ident': _headers['x-ident'], 'Authorization': _headers['Authorization']})
            if (resdel := cast(Response, cls._send_request(
                    NakedSwordBaseIE._API_URLS['logout'],
                    _type="DELETE",
                    headers=_headers_del))):

                return (resdel.status_code == 204)
            else:
                return False

    @classmethod
    def _get_api_basic_auth(cls, force=False) -> bool:

        if NakedSwordBaseIE._USERTOKEN and NakedSwordBaseIE.headers_api and not force:
            logger.debug('[get_api_auth] skipping getting new auth')
            return True

        if not NakedSwordBaseIE.ies:
            logger.error('[get_api_auth] no instance for loggin info')
            return False

        assert NakedSwordBaseIE.ies

        cls._send_request(
            NakedSwordBaseIE._API_URLS['login'],
            _type="OPTIONS", headers=cls._HEADERS["OPTIONS"]["AUTH"])
        username, pwd = NakedSwordBaseIE.ies._get_login_info()
        _headers_post = cls._HEADERS["POST"]["AUTH"].copy()
        _headers_post['Authorization'] = "Basic " + base64.urlsafe_b64encode(
            f"{username}:{pwd}".encode()).decode('utf-8')

        if (xident := NakedSwordBaseIE._get_api_xident()):
            _headers_post['x-ident'] = xident
            if (token := try_get(
                    cls._send_request(NakedSwordBaseIE._API_URLS['login'], _type="POST", headers=_headers_post),
                    lambda x: traverse_obj(x.json(), ('data', 'jwt')))):

                NakedSwordBaseIE._USERTOKEN = token
                _final = cls._HEADERS["FINAL"].copy()
                _final.update({'x-ident': xident, 'Authorization': f'Bearer {token}', 'X-CSRF-TOKEN': token})
                NakedSwordBaseIE.headers_api = _final
                return True

        return False

    @classmethod
    def _refresh_api(cls):
        cls._send_request(
            NakedSwordBaseIE._API_URLS['refresh'],
            _type="OPTIONS", headers=cls._HEADERS["OPTIONS"]["REFRESH"])
        time.sleep(0.5)
        if (data := try_get(
                cls._send_request(NakedSwordBaseIE._API_URLS['refresh'], headers=NakedSwordBaseIE.headers_api),
                lambda x: x.json())):

            token = traverse_obj(data, ('data', 'jwt'))
            print('DATA REFRESH', data, token)
            if token:
                NakedSwordBaseIE._USERTOKEN = token
                NakedSwordBaseIE.headers_api.update({'Authorization': f'Bearer {token}', 'X-CSRF-TOKEN': token})
                return True
        return False

    @classmethod
    def _get_api_xident(cls):
        proc = subprocess.run(
            ['node', NakedSwordBaseIE._JS_SCRIPT, NakedSwordBaseIE._APP_DATA['PASSPHRASE']],
            capture_output=True, encoding="utf-8")

        if (proc.returncode == 0) and (xident := proc.stdout.strip('\n')):
            NakedSwordBaseIE.timer.reset()
            return xident
        else:
            logger.warning(f'[get_api_xident] couldnt get xident: {proc}')

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

    @SeleniumInfoExtractor.syncsem()
    def get_formats_by_har(self, scenes: Union[dict, list], msg=None, **kwargs):

        _pre = '[get_entry_by_har]'
        if msg:
            _pre = f'{msg}{_pre}'

        if isinstance(scenes, dict):
            scenes = [scenes]

        _port = find_available_port() or 8080
        driver = self.get_driver(host='127.0.0.1', port=_port, **kwargs)
        _list_results = {}
        try:
            for i, scene in enumerate(scenes):
                _index = scene['_index_scene']
                pre = f"{_pre}[{_index}]"
                _list_results[_index] = {}
                try:
                    with self.get_har_logs('nakedsword', scene['id'], msg=pre, port=_port) as harlogs:

                        _list_results[_index]['har_file'] = harlogs.har_file
                        if i == 0:
                            self._send_request(self._SITE_URL, driver=driver)
                            if (_fetoken := driver.execute_script("return localStorage;").get('fe-token')):
                                self.logger_debug(f'{pre} already logged with token[{_fetoken}]. Will logout first')
                                self._logout(driver)
                            self.wait_until(driver, 0.5)
                            self._login(driver)
                            self._send_request(scene['webpage_url'], driver=driver)
                            self.wait_until(driver, 3)
                            elvid = self.wait_until(driver, 10, toggleVideo(msg=pre))
                            self.logger_debug(f'{pre} 1st toggle video result[{elvid}]')
                            if not elvid or elvid == "error":
                                return
                            repeat = self.wait_until(driver, 30, selectHLS())
                            self.logger_debug(f'{pre} selectHLS result[{repeat}]')
                            if not repeat or repeat == "error":
                                return
                            elif repeat == "TRUE":

                                self._send_request(scene['webpage_url'], driver=driver)
                                self.wait_until(driver, 3)
                                elvid = self.wait_until(driver, 10, toggleVideo(msg=pre))
                                self.logger_debug(f'{pre} 2nd toggle video result[{elvid}]')
                                if not elvid or elvid == "error":
                                    raise ReExtractInfo("couldnt reproduce video")
                        else:
                            self._send_request(scene['webpage_url'], driver=driver)
                            self.wait_until(driver, 3)
                            elvid = self.wait_until(driver, 10, toggleVideo(msg=pre))
                            self.logger_debug(f'{pre} toggle video result[{elvid}]')
                            if not elvid or elvid == "error":
                                raise ReExtractInfo("couldnt reproduce video")
                        if i == len(scenes) - 1:
                            self._logout(driver)

                    m3u8_url, _status = try_get(
                        self.scan_for_request(r"playlist.m3u8$", har=_list_results[_index]['har_file']),  # type: ignore
                        lambda x: (x.get('url'), x.get('status')) if x else (None, None))
                    self.logger_debug(f'{pre} status[{_status}] m3u8url[{m3u8_url}]')
                    _formats = []
                    _headers = NakedSwordBaseIE._HEADERS["MPD"]
                    if m3u8_url and _status:
                        if int(_status) > 400:
                            raise ReExtractInfo(f"raise status {_status}")
                        m3u8_doc = try_get(
                            self._send_request(m3u8_url, headers=_headers),
                            lambda x: (x.content).decode('utf-8', 'replace'))
                        if not m3u8_doc:
                            raise ReExtractInfo("couldnt get m3u8 doc")
                        _formats, _ = self._parse_m3u8_formats_and_subtitles(
                            m3u8_doc, m3u8_url, ext="mp4",
                            headers=_headers, entry_protocol='m3u8_native', m3u8_id="hls")

                    if not _formats:
                        raise ReExtractInfo('Couldnt get video formats')

                    for _format in _formats:
                        if (_head := _format.get('http_headers')):
                            _head.update(_headers)
                        else:
                            _format.update({'http_headers': _headers})

                    _list_results[_index]['formats'] = _formats

                except ReExtractInfo as e:
                    self.logger_debug(f'{pre}[reextractinfo] {repr(e)}')
                    _list_results[_index]['formats'] = []
                    _list_results[_index]['error'] = repr(e)
                except Exception as e:
                    self.logger_debug(f"{pre} {repr(e)}")
                    _list_results[_index]['formats'] = []
                    _list_results[_index]['error'] = repr(e)

            return _list_results
        finally:
            # self._logout(driver)
            self.rm_driver(driver)

    def _get_api_details(self, movieid):
        return try_get(
            self._send_request(
                f"{NakedSwordBaseIE._API_URLS['movies']}/{movieid}/details",
                headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS()),
            lambda x: x.json().get('data') if x else None)

    def _get_api_newest_movies(self, pages=2):
        _pre = f"{NakedSwordBaseIE._API_URLS['movies']}/feed?subset_sort_by=newest&subset_limit=480&page="
        _list_urls = [f"{_pre}{i}&sort_by=newest" for i in range(1, pages + 1)]
        _movies_info = []
        for _url in _list_urls:
            try:
                _movies_info.extend(
                    try_get(
                        self._send_request(_url, headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS()),  # type: ignore
                        lambda x: traverse_obj(x.json(), ('data', 'movies'))) or [])
            except Exception as e:
                logger.exception(repr(e))
        _movies_info.reverse()
        return _movies_info

    def _get_api_tags(self):

        feed = try_get(
            self._send_request(
                f"{NakedSwordBaseIE._API_URLS['tags']}/feed",
                headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS()),
            lambda x: x.json().get('data'))
        if feed and feed.get('categories') and feed.get('sex-acts'):
            themes = [
                el['name'].lower().replace(' ', '-').replace(',', '-')
                for el in feed['categories']]
            sex_acts = [
                el['name'].lower().replace(' ', '-').replace(',', '-')
                for el in feed['sex_acts']]
            NakedSwordBaseIE._TAGS.update({'themes': themes, 'sex_acts': sex_acts})

    def _get_api_scenes_playlist(self, playlistid):
        _url = f'https://ns-api.nakedsword.com/frontend/scene_playlist/{playlistid}'
        _info = try_get(
            self._send_request(_url, headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS()),  # type: ignore
            lambda x: x.json())
        _name = None
        _scenes_info = []
        if _info:
            _info = cast(dict, _info)
            _scenes_info = traverse_obj(_info, ('data', 'scenes_in_playlist')) or []
            _name = traverse_obj(_info, ('data', 'name'))
        return _name, _scenes_info

    def _get_api_movies_playlist(self, playlistid):
        _url = f'https://ns-api.nakedsword.com/frontend/movie_playlist/{playlistid}'
        _info = try_get(
            self._send_request(_url, headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS()),  # type: ignore
            lambda x: x.json())
        _name = None
        _movies_info = []
        if _info:
            _info = cast(dict, _info)
            _movies_info = traverse_obj(_info, ('data', 'movies_in_playlist')) or []
            _name = traverse_obj(_info, ('data', 'name'))
        return _name, _movies_info

    def _get_api_most_watched_scenes(self, query: str, limit: Union[None, int] = 60):

        if query == 'most_watched':
            _query = ""
        else:
            _query = query + '&'
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
                    self._send_request(_url, headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS()),  # type: ignore
                    lambda x: traverse_obj(x.json(), ('data', 'scenes'))) or [])

        return _scenes_info

    def _get_api_most_watched_movies(self, query: str, limit: Union[None, int] = 60):

        if query == 'top_movies':
            _query = ""
            _pre2 = ""
            _limit = 10
            _sort_by = 'top_movies'
            pages = 1
            _subset = "per_page=10"
        else:
            if query == 'most_watched':
                _query = ""
            else:
                _query = query + '&'
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
                    self._send_request(_url, headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS()),  # type: ignore
                    lambda x: traverse_obj(x.json(), ('data', 'movies'))) or [])

        return _movies_info

    def _get_api_scene_urls(self, details):

        movie_id = details.get('id')
        _pre1 = f"{NakedSwordBaseIE._API_URLS['streaming']}/aebn/movie/"
        _pre2 = "?max_bitrate=50000&scenes_id="
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

            _url_movie = try_get(
                self._send_request(url.split('/scene/')[0]),
                lambda x: str(x.url))
            movieid = NakedSwordMovieIE._match_id(_url_movie)
            details = None
            details = self._get_api_details(movieid)
            if not details:
                raise ReExtractInfo(f"{premsg} no details info")

            _urls_api = self._get_api_scene_urls(details)
            self.logger_debug(f"{premsg} urls api to get streaming info:\n{_urls_api}")
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
                    self._send_request(_urls_api[ind - 1], headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS()),
                    lambda x: x.json().get('data') if x else None)
                if _info_scene:
                    m3u8urls_scenes.append(_info_scene)

            if len(m3u8urls_scenes) != len(_urls_sc):
                _text = f"{premsg} # info scenes {len(m3u8urls_scenes)} doesnt match with # urls sc "
                _text += f"{len(_urls_sc)}\n{_urls_sc}\n\n{m3u8urls_scenes}"
                logger.error(_text)
                _text2 = f"{premsg} # info scenes {len(m3u8urls_scenes)} doesnt match with # urls sc "
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
            self.logger_debug(f"{premsg} {repr(e)}")
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

                _method_css = lambda x: ec.presence_of_element_located((By.CSS_SELECTOR, x))

                if not (el_username := cast(WebElement, self.wait_until(
                        driver, 60, _method_css("input.Input")))):
                    raise ExtractorError("login nok")
                if not (el_psswd := cast(WebElement, self.wait_until(
                        driver, 60, _method_css("input.Input.Password")))):
                    raise ExtractorError("login nok")
                if not (el_submit := cast(WebElement, self.wait_until(
                        driver, 60, _method_css("button.SignInButton")))):
                    raise ExtractorError("login nok")

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

    def wait_with_pb(self, timeout, premsg):

        NakedSwordBaseIE.API_LOGOUT(msg='[getentries]')
        _simple_counter = self.get_param('_util_classes', {}).get('SimpleCountDown')

        self.logger_info(
            f'{premsg}[wait] start[{timeout}] indexdl[{getattr(self, "indexdl", None)}]')

        with self.create_progress_bar(
                timeout, block_logging=False, msg=f'[{premsg}][wait]') as progress_bar:

            if _simple_counter:
                _counter = _simple_counter(
                    progress_bar, None, self.check_stop,
                    timeout=timeout, indexdl=getattr(self, 'indexdl', None))
                _reswait = _counter()
            else:
                _reswait = _wait_for_either(progress_bar, self.check_stop, timeout=timeout)

        self.logger_info(f'{premsg}[wait][{_reswait}] end')

        NakedSwordBaseIE.API_LOGIN(msg='[getentries]')
        time.sleep(1)

    def _real_initialize(self):

        try:
            super()._real_initialize()

            with NakedSwordBaseIE._LOCK:
                if not NakedSwordBaseIE._CLIENT:
                    NakedSwordBaseIE._CLIENT = self._CLIENT
                    NakedSwordBaseIE._APP_DATA = self._get_data_app()
                    NakedSwordBaseIE.ies = self
                    NakedSwordBaseIE.API_LOGIN()
        except Exception as e:
            logger.error(repr(e))


class NakedSwordSceneIE(NakedSwordBaseIE):
    IE_NAME = 'nakedswordscene'  # type: ignore
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<movieid>[\d]+)/(?P<title>[^\/]+)/scene/(?P<id>[\d]+)"
    _SCENES = {}

    def get_entry(self, url, **kwargs):

        with NakedSwordBaseIE._SEM[NakedSwordBaseIE._STATUS]:

            return self._get_entry(url, **kwargs)

    @dec_on_reextract_1
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

        if url not in NakedSwordSceneIE._SCENES:
            NakedSwordSceneIE._SCENES.update(
                {url: {'final': True}})

        if not NakedSwordSceneIE._SCENES[url]['final']:
            _timeout = my_jitter(30)
            self.wait_with_pb(_timeout, premsg)

        try:
            _url_movie = try_get(self._send_request(url.split('/scene/')[0]), lambda x: str(x.url))
            _info, details = self.get_streaming_info(_url_movie, index=index_scene)

            _title = f"{sanitize_filename(details.get('title'), restricted=True)}_scene_{index_scene}"
            scene_id = traverse_obj(details, ('scenes', int(index_scene) - 1, 'id'))
            _id_movie = str(details.get('id'))
            _n_entries = len(details.get('scenes', []))

            _entry = {
                "id": str(scene_id),
                "_id_movie": _id_movie,
                "title": _title,
                "formats": [],
                "ext": "mp4",
                "webpage_url": url,
                "_index_scene": int(index_scene),
                "_n_entries": _n_entries,
                "extractor_key": 'NakedSwordScene',
                "extractor": 'nakedswordscene'
            }

            formats = self.get_formats(_types, _info)
            if formats:
                _entry.update({'formats': formats})
                self.logger_info(f"{premsg}: OK got entr")
                try:
                    _entry.update(
                        {'duration': self._extract_m3u8_vod_duration(
                            formats[0]['url'],
                            str(scene_id),
                            headers=NakedSwordBaseIE._HEADERS["MPD"])})
                    NakedSwordSceneIE._SCENES[url]['final'] = True
                except Exception as e:
                    self.logger_info(f"{premsg}: error trying to get vod {repr(e)}")
                return _entry
            else:
                raise ReExtractInfo(f'{premsg}: error - no formats')
        except ReExtractInfo:
            self.logger_debug(f"{premsg}: error format, will retry again")
            NakedSwordSceneIE._SCENES[url]['final'] = False
            raise
        except StatusStop:
            raise
        except Exception as e:
            self.logger_debug(f"{premsg} {repr(e)}")
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
            raise ExtractorError(f'{repr(e)}')


class NakedSwordMovieIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:movie:playlist'  # type: ignore
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<id>[\d]+)/(?P<title>[^?#&/]+)(?:/?\?(?P<by>by=movie))?"
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

        premsg += f'[{_url_movie.split("movies/")[1]}]'

        _id_movie = self._match_id(_url_movie)

        if _url_movie not in NakedSwordMovieIE._MOVIES:
            NakedSwordMovieIE._MOVIES.update(
                {_url_movie: {'nok': [], 'ok': [], 'entries': {}, 'final': True}})

        if not NakedSwordMovieIE._MOVIES[_url_movie]['final']:

            _timeout = my_jitter(30)

            self.wait_with_pb(_timeout, premsg)

        if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

            try:

                for _ in range(2):

                    info_streaming_scenes, details = self.get_streaming_info(_url_movie)

                    sublist = []
                    if hasattr(self, 'args_ie'):
                        sublist = traverse_obj(self.args_ie, ('nakedswordmovie', 'listreset')) or []

                        self.logger_debug(f"{premsg} sublist of movie scenes: {sublist}")

                    _raise_reextract = []

                    for _info in info_streaming_scenes:

                        self.check_stop()

                        i = _info.get('index')

                        self.logger_debug(f"{premsg}[{i}]:\n{_info}")

                        _title = f"{sanitize_filename(details.get('title'), restricted=True)}_scene_{i}"
                        scene_id = try_get(traverse_obj(details, ('scenes', i - 1, 'id')), lambda x: str(x))
                        _n_entries = len(details.get('scenes', []))

                        _entry = {
                            "id": scene_id,
                            "_id_movie": _id_movie,
                            "title": _title,
                            "formats": [],
                            "ext": "mp4",
                            "webpage_url": _info.get('url'),
                            "original_url": _url_movie,
                            "_index_scene": i,
                            "_n_entries": _n_entries,
                            "extractor_key": 'NakedSwordScene',
                            "extractor": 'nakedswordscene'
                        }

                        if (not sublist or (sublist and i in sublist)):

                            if i in NakedSwordMovieIE._MOVIES[_url_movie]['ok']:
                                self.logger_debug(f"{premsg}[{i}]: already got entry")

                            else:
                                NakedSwordMovieIE._MOVIES[_url_movie]['entries'][i] = _entry
                                try:
                                    formats = self.get_formats(_types, _info)
                                    if formats:
                                        _entry.update({'formats': formats})
                                        self.logger_debug(f"{premsg}[{i}]: OK got entry")
                                        NakedSwordMovieIE._MOVIES[_url_movie]['ok'].append(i)
                                        NakedSwordMovieIE._MOVIES[_url_movie]['entries'][i] = _entry
                                        if i in NakedSwordMovieIE._MOVIES[_url_movie]['nok']:
                                            NakedSwordMovieIE._MOVIES[_url_movie]['nok'].remove(i)
                                        try:
                                            _entry.update(
                                                {'duration': self._extract_m3u8_vod_duration(
                                                    formats[0]['url'],
                                                    str(scene_id),
                                                    headers=NakedSwordBaseIE._HEADERS["MPD"])})
                                        except Exception as e:
                                            self.logger_info(f"{premsg}: error trying to get vod {str(e)}")

                                except ReExtractInfo:
                                    self.logger_info(f"{premsg}[{i}]: NOK, will try again")
                                    _raise_reextract.append(i)
                                    if i not in NakedSwordMovieIE._MOVIES[_url_movie]['nok']:
                                        NakedSwordMovieIE._MOVIES[_url_movie]['nok'].append(i)
                                    NakedSwordMovieIE._MOVIES[_url_movie]['final'] = False

                        else:
                            NakedSwordMovieIE._MOVIES[_url_movie]['entries'][i] = _entry

                    if _raise_reextract:
                        _msg = "".join(
                            [
                                f"{premsg} ERROR in {_raise_reextract} ",
                                f"from sublist of movie scenes: {sublist}. ",
                                f"[final]:{NakedSwordMovieIE._MOVIES[_url_movie]['final']} ",
                                f"[ok]:{NakedSwordMovieIE._MOVIES[_url_movie]['ok']} ",
                                f"[nok]:{NakedSwordMovieIE._MOVIES[_url_movie]['nok']}"
                            ])
                        self.logger_info(_msg)
                        raise ReExtractInfo("error in scenes of movie")

                    self.logger_info(
                        "".join(
                            [
                                f"{premsg} OK format for sublist of movie scenes: {sublist}. ",
                                f"[final]:{NakedSwordMovieIE._MOVIES[_url_movie]['final']} ",
                                f"[ok]:{NakedSwordMovieIE._MOVIES[_url_movie]['ok']} ",
                                f"[nok]:{NakedSwordMovieIE._MOVIES[_url_movie]['nok']}"
                            ])
                    )
                    if not NakedSwordMovieIE._MOVIES[_url_movie]['final']:
                        NakedSwordMovieIE._MOVIES[_url_movie] = {
                            'nok': [], 'ok': [], 'entries': {}, 'final': True}
                        continue
                    else:
                        _entries = list(map(
                            lambda x: x[1],
                            sorted(NakedSwordMovieIE._MOVIES[_url_movie]['entries'].items())))
                        NakedSwordMovieIE._MOVIES.pop(_url_movie)
                        if _force_list:
                            return _entries
                        else:
                            playlist_id = str(details.get('id'))
                            pl_title = sanitize_filename(details.get('title'), restricted=True)
                            return self.playlist_result(
                                _entries,
                                playlist_id=playlist_id,
                                playlist_title=pl_title,
                                webpage_url=_url_movie,
                                original_url=_url_movie)

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
                        self.url_result(
                            f"{_url_movie.strip('/')}/scene/{x['index']}",
                            ie=NakedSwordSceneIE)
                        for x in details.get('scenes')]
                else:
                    playlist_id = str(details.get('id'))
                    pl_title = sanitize_filename(details.get('title'), restricted=True)
                    return self.playlist_from_matches(
                        traverse_obj(details, 'scenes'),
                        getter=lambda x: f"{_url_movie.strip('/')}/scene/{x['index']}",
                        ie=NakedSwordSceneIE,
                        playlist_id=playlist_id,
                        playlist_title=pl_title,
                        webpage_url=_url_movie,
                        original_url=_url_movie)

    @dec_on_reextract_1
    def get_entries_from_full_movie(self, movie_id, **kwargs):

        premsg = f"[get_entries_from_full_movie][{movie_id}]"

        _movie_url = try_get(
            self._send_request(f"https://www.nakedsword.com/movies/{movie_id}/_"),
            lambda x: str(x.url))

        if _movie_url not in NakedSwordMovieIE._MOVIES:
            NakedSwordMovieIE._MOVIES.update({_movie_url: {'on_backoff': False}})

        if NakedSwordMovieIE._MOVIES[_movie_url]['on_backoff']:

            NakedSwordBaseIE.API_LOGOUT(msg=premsg)
            time.sleep(2)

            _timeout = my_jitter(30)

            _simple_counter = self.get_param('_util_classes', {}).get('SimpleCountDown')

            self.logger_info(
                "".join([
                    f'{premsg}[wait] start[{_timeout}] ',
                    f'counter[{try_get(_simple_counter, lambda x: x.__name__)}] ',
                    f'indexdl[{getattr(self, "indexdl", None)}]']))

            with self.create_progress_bar(_timeout, msg=f'[{movie_id}][wait]') as progress_bar:

                if _simple_counter:
                    _counter = _simple_counter(
                        progress_bar, None, self.check_stop,
                        timeout=_timeout, indexdl=getattr(self, 'indexdl', None))
                    _reswait = _counter()
                else:
                    _reswait = _wait_for_either(
                        progress_bar, self.check_stop, timeout=_timeout)

            self.logger_info(f'{premsg}[wait][{_reswait}] end')

            NakedSwordBaseIE.API_LOGIN(msg='[getentries]')
            time.sleep(2)

        details = self._get_api_details(movie_id)
        if not details:
            raise ReExtractInfo(f"{premsg} no details info")
        _pre = f"{NakedSwordBaseIE._API_URLS['streaming']}/aebn/movie/"
        _api_movie_url = f"{_pre}{movie_id}?max_bitrate=50000&format=HLS"

        try:

            m3u8_url = try_get(
                self._send_request(_api_movie_url, headers=NakedSwordBaseIE.API_GET_HTTP_HEADERS()),
                lambda x: x.json().get('data') if x else None)

            m3u8_doc = try_get(
                self._send_request(m3u8_url, headers=NakedSwordBaseIE._HEADERS["MPD"]),
                lambda x: (x.content).decode('utf-8', 'replace'))
            if not m3u8_doc:
                raise ReExtractInfo("couldnt get m3u8 doc")

            _formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                m3u8_doc, m3u8_url, ext='mp4', entry_protocol='m3u8_native', m3u8_id='hls')

        except ReExtractInfo as e:
            logger.info(f"{premsg} reextractinfo {str(e)}")
            NakedSwordMovieIE._MOVIES[_movie_url]['on_backoff'] = True
            raise
        except Exception as e:
            logger.error(f"{premsg} {repr(e)}")
            NakedSwordMovieIE._MOVIES[_movie_url]['on_backoff'] = True
            raise ReExtractInfo(repr(e))

        _entries = []
        for sc in details.get('scenes'):
            _entry = {
                "id": str(sc['id']) + "bm",
                "_id_movie": movie_id,
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

        playlist_id = movie_id
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
            raise ExtractorError(str(e))
        except Exception as e:
            raise ExtractorError(f'{repr(e)}')


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
        msg = kwargs.get('msg')
        premsg = "[get_entries]"
        if msg:
            premsg = f"{msg}{premsg}"

        try:
            info_url = try_get(self._match_valid_url(url), lambda x: x.groupdict())
            assert info_url

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

            def _getter(movie_id, index):
                _movie_url = try_get(
                    self._send_request(f"https://www.nakedsword.com/movies/{movie_id}/_"),
                    lambda x: str(x.url))
                return f'{_movie_url}/scene/{index}'

            if not _scenes:
                raise ExtractorError('no scenes found')

            _scenes = cast(list[dict], _scenes)
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
            raise ExtractorError(str(e))
        except Exception as e:
            raise ExtractorError(f'{repr(e)}')


class NakedSwordMoviesPlaylistIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:movies:playlist'  # type: ignore
    _VALID_URL = r'''(?x)
        https?://(?:www\.)?nakedsword.com/(?:
            ((((studios|stars)/(?P<id>[\d]+)/(?P<name>[^/?#&]+))|
            (tag/(?P<tagname>[^/?#&]+))|most-watched)\?content=Movies(&limit=(?P<limit>\d+))?)|
            playlists/(?P<plid>\d+)/movies/.*|top-10)'''

    def get_entries_from_movies_list(self, url: str, **kwargs):

        msg = kwargs.get('msg')
        premsg = "[get_entries]"
        if msg:
            premsg = f"{msg}{premsg}"

        try:

            info_url = try_get(self._match_valid_url(url), lambda x: x.groupdict())

            assert info_url

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

            if not _movies:
                raise ExtractorError('no movies found')

            _movies = cast(list[dict], _movies)

            _url_movies = list(dict.fromkeys([try_get(
                self._send_request(_url),
                lambda x: str(x.url))
                for _url in [
                    f'https://www.nakedsword.com/movies/{x["id"]}/_'
                    for x in _movies]]))

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
                        list(map(lambda x: x.update({'playlist_url': url})), _res)
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
            raise ExtractorError(str(e))
        except Exception as e:
            raise ExtractorError(f'{repr(e)}')


class NakedSwordJustAddedMoviesPlaylistIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:justaddedmovies:playlist'  # type: ignore
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/just-added(\?(?P<query>.+))?"

    def get_entries_from_justadded_movies_list(self, url, **kwargs):

        premsg = f"[get_entries][{url}]"
        msg = kwargs.get('msg')
        if msg:
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

            _url_movies = list(dict.fromkeys([try_get(
                self._send_request(_url), lambda x: str(x.url))
                for _url in [f'https://www.nakedsword.com/movies/{x["id"]}/_' for x in _movies_filtered]]))

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
                        list(map(lambda x: x.update({'playlist_url': url})), _res)
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
            raise ExtractorError(str(e))
        except Exception as e:
            raise ExtractorError(f'{repr(e)}')
