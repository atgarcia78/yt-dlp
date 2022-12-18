import functools
import html
import json
import logging
import re
import sys
import time
import traceback
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from queue import Queue
from threading import Event, Lock, Semaphore
from urllib.parse import quote, unquote, urljoin, urlparse
import base64

from .commonwebdriver import (
    By,
    Client,
    ConnectError,
    HTTPStatusError,
    ProgressTimer,
    ReExtractInfo,
    SeleniumInfoExtractor,
    StatusStop,
    TimeoutException,
    WebDriverException,
    dec_on_exception,
    dec_on_exception2,
    dec_on_exception3,
    dec_on_reextract,
    dec_retry,
    ec,
    limiter_0_01,
    limiter_0_005,
    limiter_0_1,
    limiter_1,
    limiter_2,
    limiter_5,
    limiter_non,
    long_operation_in_thread,
    my_dec_on_exception,
    scroll,
)
from ..utils import (
    ExtractorError,
    extract_timezone,
    int_or_none,
    sanitize_filename,
    smuggle_url,
    traverse_obj,
    try_get,
    unsmuggle_url,
)

logger = logging.getLogger('nakedsword')

dec_on_exception_driver = my_dec_on_exception(TimeoutException, max_tries=3, myjitter=True, raise_on_giveup=True, interval=5)


class checkLogged:

    def __init__(self, ifnot=False):
        self.ifnot = ifnot

    def __call__(self, driver):

        el_uas = driver.find_element(By.CSS_SELECTOR, "div.UserActions")
        el_loggin = try_get(el_uas.find_elements(By.CLASS_NAME, "LoginWrapper"), lambda x: x[0])
        if not el_loggin:

            if not self.ifnot:
                el_loggin = try_get(el_uas.find_elements(By.CLASS_NAME, "UserAction"), lambda x: x[1])
                if el_loggin and el_loggin.text.upper() == "MY ACCOUNT":
                    return "TRUE"
                else:
                    return False

            else:
                el_loggin = try_get(el_uas.find_elements(By.CLASS_NAME, "UserAction"), lambda x: x[0])
                if el_loggin and el_loggin.text.upper() == "SIGN OUT":
                    el_loggin.click()
                    return "CHECK"
                else:
                    return False

        else:
            if not self.ifnot:
                el_loggin.click()
                return "FALSE"

            else:
                return "TRUE"


class waitVideo:
    def __call__(self, driver):
        driver.find_element(By.CSS_SELECTOR, "button.vjs-big-play-button")
        time.sleep(0.5)
        return True


class selectHLS:
    def __init__(self, delay=0):
        self._pl_click = False
        self._menu = None
        self._delay = delay

    def __call__(self, driver):
        if not self._pl_click:
            el_pl_click = try_get(driver.find_element(By.CSS_SELECTOR, "button.vjs-big-play-button"), lambda x: x.click())
            time.sleep(self._delay)
            self._pl_click = True
            try:
                click_pause = try_get(driver.find_element(By.CSS_SELECTOR, "button.vjs-play-control.vjs-control.vjs-button.vjs-playing"), lambda x: (x.text, x.click()))
            except Exception as e:
                pass
        if not self._menu:
            self._menu, el_menu_click = try_get(driver.find_element(By.CSS_SELECTOR, "button.vjs-control.vjs-button.fas.fa-cog"), lambda x: (x, x.click()))
            time.sleep(self._delay)

        menu_hls = try_get(driver.find_elements(By.CLASS_NAME, "BaseVideoPlayerSettingsMenu-item-inner"), lambda x: x[1])
        if not "checked=" in menu_hls.get_attribute('outerHTML'):
            menu_hls.click()
            time.sleep(self._delay)
            el_conf_click = try_get(driver.find_elements(By.CSS_SELECTOR, "div.Button"), lambda x: (x[1].text, x[1].click()))
            time.sleep(self._delay)
            self._menu.click()
            return "TRUE"
        else:
            self._menu.click()
            return "FALSE"


class getScenes:

    def __call__(self, driver):
        el_pl = driver.find_element(By.CSS_SELECTOR, "button.vjs-big-play-button")
        el_mv = driver.find_element(By.CLASS_NAME, "MovieDetailsPage")
        el_inner = el_mv.find_element(By.CLASS_NAME, "Inner")
        el_mvsc = try_get(el_inner.find_elements(By.CLASS_NAME, "MovieScenes"), lambda x: x[0] if x else None)
        if el_mvsc:
            if (_scenes := el_mvsc.find_elements(By.CLASS_NAME, "Scene")):
                return _scenes
            else:
                return False
        else:
            return "singlescene"


class NakedSwordBaseIE(SeleniumInfoExtractor):

    _SITE_URL = "https://www.nakedsword.com/"
    _SIGNIN_URL = "https://www.nakedsword.com/signin"
    _NETRC_MACHINE = 'nakedsword'
    _LOCK = Lock()
    _NLOCKS = {'noproxy': Lock()}
    _TAGS = {}
    _MAXPAGE_SCENES_LIST = 2
    _API = None
    _USERS = 0
    _INIT_URL = 'https://www.nakedsword.com/movies/285963/physical-evaluations-scene-1'
    _STATUS = 'NORMAL'
    _LIMITERS = {'403': limiter_5.ratelimit("nakedswordscene", delay=True), 'NORMAL': limiter_0_1.ratelimit("nakedswordscene", delay=True)}

    def check_close_nsapi(self):
        with NakedSwordBaseIE._LOCK:
            NakedSwordBaseIE._USERS -= 1
            if NakedSwordBaseIE._USERS <= 0 and not self.get_param('embed'):
                if NakedSwordBaseIE._API:
                    NakedSwordBaseIE._API.stop_event()
                    NakedSwordBaseIE._API.close_event.wait()
                    NakedSwordBaseIE._API = None
                    NakedSwordBaseIE._USERS = 0

    def close(self):
        if NakedSwordBaseIE._API:
            NakedSwordBaseIE._API.stop_event()
            NakedSwordBaseIE._API.close_event.wait()
            NakedSwordBaseIE._API = None
            NakedSwordBaseIE._USERS = 0
        super().close()

    def wait_until(self, driver, **kwargs):
        kwargs['poll_freq'] = 0.25
        return super().wait_until(driver, **kwargs)

    
    def get_formats(self, _types, _info):

        if self.IE_NAME == 'NakedSwordMovie' and NakedSwordBaeIE._STATUS == '403':
            _limiter = NakedSwordBaseIE._LIMITERS['403']
        else:
            _limiter = NakedSwordBaseIE._LIMITERS['NORMAL']

        @_limiter
        def _get_formats():
            logger.info(f"[get_formats] {_info}")

            m3u8_url = _info.get('m3u8_url')

            _headers_mpd = {
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
                'TE': 'trailers'
            }

            formats = []

            for _type in _types:

                self.check_stop()
                try:
                    if _type == "hls":

                        m3u8_doc = try_get(self._send_request(m3u8_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace'))
                        if not m3u8_doc:
                            raise ReExtractInfo("couldnt get m3u8 doc")

                        formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                            m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")
                        if formats_m3u8:
                            formats.extend(formats_m3u8)

                    elif _type == "dash":

                        mpd_url = m3u8_url.replace('playlist.m3u8', 'manifest.mpd')
                        _doc = try_get(self._send_request(mpd_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace'))
                        if not _doc:
                            raise ExtractorError("couldnt get mpd doc")
                        mpd_doc = self._parse_xml(_doc, None)

                        formats_dash = self._parse_mpd_formats(mpd_doc, mpd_id="dash", mpd_url=mpd_url, mpd_base_url=(mpd_url.rsplit('/', 1))[0])
                        if formats_dash:
                            formats.extend(formats_dash)

                    elif _type == "ism":

                        ism_url = m3u8_url.replace('playlist.m3u8', 'Manifest')
                        _doc = try_get(self._send_request(ism_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace'))
                        if _doc:
                            ism_doc = self._parse_xml(_doc, None)
                            formats_ism, _ = self._parse_ism_formats_and_subtitles(ism_doc, ism_url)
                            if formats_ism:
                                formats.extend(formats_ism)

                except ReExtractInfo as e:                    
                    raise
                except Exception as e:
                    logger.error(f"[get_formats][{_type}][{_info.get('url')}] {str(e)}")

            if not formats:
                raise ExtractorError("couldnt find any format")
            else:
                return formats

        return _get_formats()
    
    
    def _logout(self, driver):
        try:
            logged_out = False
            self._send_request(self._SITE_URL, driver=driver)
            self.to_screen(f"[logout][{self._key}] Logout start")
            res = self.wait_until(driver, timeout=10, method=checkLogged(ifnot=True))
            if res == "TRUE":
                logged_out = True
            elif res == "CHECK":
                self.wait_until(driver, timeout=1)
                res = self.wait_until(driver, timeout=10, method=checkLogged(ifnot=True))
                if res == "TRUE":
                    logged_out = True
                else:
                    driver.delete_all_cookies()
                    self.wait_until(driver, timeout=1)
                    res = self.wait_until(driver, timeout=10, method=checkLogged(ifnot=True))
                    if res == "TRUE":
                        logged_out = True
            if logged_out:
                self.to_screen(f"[logout][{self._key}] Logout OK")
            else:
                self.to_screen(f"[logout][{self._key}] Logout NOK")
        except Exception as e:
            self.report_warning(f"[logout][{self._key}] Logout NOK {repr(e)}")

    @dec_on_exception_driver
    @dec_on_exception2
    @dec_on_exception3
    @limiter_0_01.ratelimit("nakedsword", delay=True)
    def _send_request(self, url, **kwargs):

        driver = kwargs.get('driver', None)

        if not driver:
            try:
                return (self.send_http_request(url, **kwargs))
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"[send_request_http] {self._get_url_print(url)}: error - {repr(e)} - {str(e)}")
        else:
            try:
                if url == "REFRESH":
                    driver.refresh()
                else:
                    driver.get(url)
            except Exception as e:
                self.report_warning(f"[send_request_driver] {self._get_url_print(url)}: error - {repr(e)} - {str(e)}")
                raise

    @dec_retry
    def get_driver_logged(self, **kwargs):

        noheadless = kwargs.get('noheadless', False)
        driver = kwargs.get('driver')
        if not driver:
            driver = self.get_driver(noheadless=noheadless, devtools=True)

            if not driver:
                raise ExtractorError("error starting firefox")

        try:
            _res_login = self._login(driver)
            if _res_login:
                #self._send_request(self._INIT_URL, driver=driver)
                self.wait_until(driver, timeout=30, method=selectHLS())
                return driver
            else:
                raise ExtractorError("error when login")
        except Exception as e:
            self.rm_driver(driver)
            raise ExtractorError({str(e)})

    def get_api_basic_auth(self, username, pwd):
        
        return "Basic " + base64.urlsafe_b64encode(f"{username}:{pwd}".encode()).decode('utf-8')
    
    def get_api_http_headers(self):
        return NakedSwordBaseIE._API()

    def get_api_details(self, movieid):
        return try_get(self._send_request(f"https://ns-api.nakedsword.com/frontend/movies/{movieid}/details", headers=self.get_api_http_headers()), lambda x: x.json().get('data') if x else None)

    def get_api_newest_movies(self, pages=2):
        _list_urls = [f"https://ns-api.nakedsword.com/frontend/movies/feed?subset_sort_by=newest&subset_limit=480&page={i}&sort_by=newest" for i in range(1, pages + 1)]
        _movies_info = []
        for _url in _list_urls:
            _movies_info.extend(try_get(self._send_request(_url, headers=self.get_api_http_headers()), lambda x: traverse_obj(x.json(), ('data', 'movies'), default=[]) if x else []))

        return _movies_info

    def get_api_tags(self):

        feed = try_get(self._send_request("https://ns-api.nakedsword.com/frontend/tags/feed", headers=self.get_api_http_headers()), lambda x: x.json().get('data'))
        themes = [el['name'].lower().replace(' ', '-').replace(',', '-') for el in feed['categories']]
        sex_acts = [el['name'].lower().replace(' ', '-').replace(',', '-') for el in feed['sex_acts']]
        NakedSwordBaseIE._TAGS.update({'themes': themes, 'sex_acts': sex_acts})

    def get_api_most_watched_scenes(self, query, pages=2):
        _list_urls = [f"https://ns-api.nakedsword.com/frontend/scenes/feed?{query}&page={i}&sort_by=most_watched" for i in range(1, pages + 1)]
        _scenes_info = []
        for _url in _list_urls:
            _scenes_info.extend(try_get(self._send_request(_url, headers=self.get_api_http_headers()), lambda x: traverse_obj(x.json(), ('data', 'scenes'), default=[]) if x else []))

        return _scenes_info

    def get_api_scene_urls(self, details=None):

        movie_id = details.get('id')
        return [f"https://ns-api.nakedsword.com/frontend/streaming/aebn/movie/{movie_id}?max_bitrate=10500&scenes_id={sc['id']}&start_time={sc['startTimeSeconds']}&duration={sc['endTimeSeconds']-sc['startTimeSeconds']}&format=HLS" for sc in details.get('scenes')]

    def get_streaming_info(self, url, **kwargs):

        premsg = f"[get_streaming_info][{url}]"
        index_scene = int_or_none(kwargs.get('index'))

        try:

            _url_movie = try_get(self._send_request(url.split('/scene/')[0]), lambda x: str(x.url))
            movieid = NakedSwordMovieIE._match_id(_url_movie)
            

            details = None
            headers_api = None

            details = self.get_api_details(movieid)

            if not details:
                raise ReExtractInfo(f"{premsg} no details info")

            _urls_api = self.get_api_scene_urls(details)

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
                if (_info_scene := try_get(self._send_request(_urls_api[ind - 1], headers=headers_api or self.get_api_http_headers()), lambda x: x.json().get('data') if x else None)):
                    m3u8urls_scenes.append(_info_scene)

            if len(m3u8urls_scenes) != len(_urls_sc):
                logger.error(f"{premsg} number of info scenes {len(m3u8urls_scenes)} doesnt match with number of urls sc {len(_urls_sc)}\n{_urls_sc}\n\n{m3u8urls_scenes}")
                raise ReExtractInfo(f"{premsg} number of info scenes {len(m3u8urls_scenes)} doesnt match with number of urls sc {len(_urls_sc)}")

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

    def _is_logged(self, driver, initurl=False):

        if not initurl:
            _init_url  = self._SITE_URL

        else: 
            _init_url = self._INIT_URL

        self._send_request(_init_url, driver=driver)
        logged_ok = (self.wait_until(driver, timeout=10, method=checkLogged()) == "TRUE")
        self.logger_debug(f"[is_logged][{self._key}] {logged_ok}")
        return logged_ok

    @dec_retry
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

                el_username = self.wait_until(driver, timeout=60, method=ec.presence_of_element_located((By.CSS_SELECTOR, "input.Input")))
                el_psswd = self.wait_until(driver, timeout=60, method=ec.presence_of_element_located((By.CSS_SELECTOR, "input.Input.Password")))
                el_submit = self.wait_until(driver, timeout=60, method=ec.presence_of_element_located((By.CSS_SELECTOR, "button.SignInButton")))

                if any([not el_username, not el_psswd, not el_submit]):
                    raise ExtractorError("login nok")

                el_username.send_keys(username)
                el_psswd.send_keys(password)
               # with NakedSwordBaseIE._NLOCKS.get(self._key):
                el_submit.click()
                self.wait_until(driver, timeout=1)

                if self._is_logged(driver, initurl=True):
                    self.logger_debug(f"[login][{self._key}] Login OK")
                    return True
                else:
                    self.logger_debug(f"[login][{self._key}] Login NOK")
                    self._send_request(self._SITE_URL, driver=driver)
                    raise ExtractorError("login nok")

            else:
                self.logger_debug(f"[login][{self._key}] Already logged")
                return True
        except Exception as e:
            logger.error(str(e))
            # self._logout(driver)
            raise

    def _real_initialize(self):

        try:

            super()._real_initialize()

            if (_proxy := self._downloader.params.get('proxy')):
                self.proxy = _proxy
                self._key = _proxy.split(':')[-1]
                self.logged_debug(f"proxy: [{self._key}]")
                if not NakedSwordBaseIE._NLOCKS.get(self._key):
                    NakedSwordBaseIE._NLOCKS.update({self._key: Lock()})
            else:
                self.proxy = None
                self._key = "noproxy"

            if self.IE_NAME != 'nakedswordapi':
                with NakedSwordBaseIE._LOCK:
                    NakedSwordBaseIE._USERS += 1
                    if not NakedSwordBaseIE._API:
                        NakedSwordBaseIE._API = self._get_extractor("NakedSwordAPI")

        except Exception as e:
            logger.error(repr(e))


class NakedSwordAPIIE(NakedSwordBaseIE):
    IE_NAME = 'nakedswordapi'
    _VALID_URL = r'__dummynakedswordapi__'

    def _real_initialize(self):

        super()._real_initialize()

        self.logger = logging.getLogger("NSAPI")

        self.timer = ProgressTimer()

        self.call_lock = Lock()
        self.driver_lock = Lock()
        self.close_event = Event()

        self.driver = None
        self.headers_api = {}
        self.start_driver()

    @dec_on_reextract
    def start_driver(self):

        try:
            if self.driver:
                try:
                    self._logout(self.driver)
                    self.rm_driver(self.driver)
                except Exception as e:
                    pass
            self.driver = self.get_driver_logged()
            status, _headers = try_get(self.scan_for_request(self.driver, r'details$', _mimetype="json", inclheaders=True), lambda x: (x.get('status'), x.get('headers')) if x else (None, None))
            if any([not status, status and int(status) == 403, not _headers]):
                raise Exception("start driver error")
            self.headers_api = _headers
            self.timer.has_elapsed(0.1)
        except Exception as e:
            self.logger.error(f"[start_driver] {str(e)}")
            raise ReExtractInfo("error start driver")

    def check_if_token_refreshed(self):

        self.logger.debug(f"[token_refresh] init refresh")
        try:
            with self.driver_lock:
                self._send_request(self._INIT_URL, driver=self.driver)
                self.wait_until(self.driver, timeout=30, method=waitVideo())
                status, _headers = try_get(self.scan_for_request(self.driver,  r'details$', _mimetype="json", inclheaders=True), lambda x: (x.get('status'), x.get('headers')) if x else (None, None))

            if any([not status, status and int(status) == 403, not _headers]):
                self.logger.error("fails token refresh")
                raise Exception("fails token refresh")

            self.headers_api = _headers
            self.logger.debug(f"[token_refresh] ok refresh")
            self.timer.has_elapsed(0.1)
        except Exception as e:
            self.logger.error(f"fails token refresh - {str(e)}")
            with self.driver_lock:
                self.start_driver()
            self.logger.info(f"[token_refresh] ok refresh after error")

    def stop_event(self):
        try:
            self.logger.info(f"[stop_event]")
            if self.driver:
                self._logout(self.driver)
                self.rm_driver(self.driver)

        finally:
            self.close_event.set()
            self.driver = None

    def __call__(self):
        with self.call_lock:
            if self.timer.elapsed_seconds() < 40:
                return self.headers_api
            else:
                self.logger.info(f"[call] timeout to token refresh")
                self.check_if_token_refreshed()
                self.timer.has_elapsed(0.1)
                return self.headers_api


class NakedSwordSceneIE(NakedSwordBaseIE):
    IE_NAME = 'nakedswordscene'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<movieid>[\d]+)/(?P<title>[^\/]+)/scene/(?P<id>[\d]+)"

    @dec_on_reextract
    def get_entry(self, url, **kwargs):

        _type = kwargs.get('_type', 'all')
        if _type == 'all':
            _types = ['hls', 'dash', 'ism']
        else:
            _types = [_type]
        msg = kwargs.get('msg')
        index_scene = try_get(kwargs.get('index') or try_get(self._match_valid_url(url).groupdict(), lambda x: x.get('id')), lambda x: int(x) if x else 1)
        premsg = f"[get_entry][{self._key}][{url}][{index_scene}]"
        if msg:
            premsg = f"{msg}{premsg}"

        try:

            self.logger_debug(f"{premsg} start to get entry")
            _url_movie = try_get(self._send_request(url.split('/scene/')[0]), lambda x: str(x.url))
            _info, details = self.get_streaming_info(_url_movie, index=index_scene)

            _title = f"{sanitize_filename(details.get('title'), restricted=True)}_scene_{index_scene}"
            scene_id = traverse_obj(details, ('scenes', int(index_scene) - 1, 'id'))

            formats = self.get_formats(_types, _info)

            if formats:

                _entry = {
                    "id": str(scene_id),
                    "title": _title,
                    "formats": formats,
                    "ext": "mp4",
                    "webpage_url": url,
                    "extractor_key": 'NakedSwordScene',
                    "extractor": 'nakedswordscene'
                }

                self.logger_debug(f"{premsg}: OK got entr {_entry}")
                return _entry

            else:
                raise ExtractorError(f'{premsg}: error - no formats')

        except ReExtractInfo as e:
            logger.error(f"[get_entries][{url} {str(e)} - start driver")

            raise
        except (StatusStop, ExtractorError) as e:
            raise
        except Exception as e:
            logger.exception(repr(e))
            raise ExtractorError(f'{premsg}: error - {repr(e)}')

    def _real_extract(self, url):

        try:
            self.report_extraction(url)
            nscene = int(self._match_id(url))
            return self.get_entry(url, index=nscene, _type="hls")

        except (ExtractorError, StatusStop) as e:
            raise
        except ReExtractInfo as e:
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')
        finally:
            self.check_close_nsapi()


class NakedSwordMovieIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:movie:playlist'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<id>[\d]+)/(?P<title>[^/?#&]+)"
    _MOVIES_URL = "https://www.nakedsword.com/movies/"

    @dec_on_reextract
    def get_entries(self, url, **kwargs):
        _type = kwargs.get('_type', 'all')
        if _type == 'all':
            _types = ['hls', 'dash', 'ism']
        else:
            _types = [_type]
        msg = kwargs.get('msg')
        premsg = f"[get_entries][{self._key}]"
        if msg:
            premsg = f"{msg}{premsg}"

        _force_list = kwargs.get('force', False)
        _legacy = kwargs.get('legacy', False)

        self.report_extraction(url)

        _url_movie = try_get(self._send_request(url), lambda x: str(x.url))

        if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

            info_streaming_scenes, details = self.get_streaming_info(_url_movie)

            _entries = []

            sublist = traverse_obj(self.args_ie, ('nakedswordmovie', 'listreset'))

            logger.info(f"{premsg} sublist of movie scenes: {sublist}")

            for _info in info_streaming_scenes:

                try:
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
                        "original": url,
                        "extractor_key": 'NakedSwordScene',
                        "extractor": 'nakedswordscene'
                    }

                    if not sublist or i in sublist:

                        formats = self.get_formats(_types, _info)
                        if formats:
                            _entry.update({'formats': formats})
                            self.logger_debug(f"{premsg}[{_info.get('url')}]: OK got entry")
                            _entries.append(_entry)

                    else:
                        _entries.append(_entry)

                except ReExtractInfo as e:
                    
                    if NakedSwordBaseIE._STATUS == 'NORMAL':
                        NakedSwordBaseIE._STATUS == '403'
                    raise
                except Exception as e:
                    logger.exception(f"{premsg}[{i}]: info streaming\n{_info} error - {str(e)}")
                    raise

            
            
            if NakedSwordBaseIE._STATUS == '403':
                NakedSwordBaseIE._STATUS == 'NORMAL'
            
            if _force_list:
                return _entries
            else:
                playlist_id = str(details.get('id'))
                pl_title = sanitize_filename(details.get('title'), restricted=True)
                return self.playlist_result(_entries, playlist_id=playlist_id, playlist_title=pl_title)

        else:
            details = self.get_api_details(self._match_id(_url_movie))
            if _force_list:
                return [self.url_result(f"{_url_movie.strip('/')}/scene/{x['index']}", ie=NakedSwordSceneIE) for x in traverse_obj(details, 'scenes')]
            else:
                playlist_id = str(details.get('id'))
                pl_title = sanitize_filename(details.get('title'), restricted=True)
                return self.playlist_from_matches(
                    traverse_obj(details, 'scenes'),
                    getter=lambda x: f"{_url_movie.strip('/')}/scene/{x['index']}",
                    ie=NakedSwordSceneIE, playlist_id=playlist_id, playlist_title=pl_title)

    def _real_extract(self, url):

        try:
            return self.get_entries(url, _type="hls")
        except (ExtractorError, StatusStop) as e:
            raise
        except ReExtractInfo as e:
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')
        finally:
            self.check_close_nsapi()


class NakedSwordScenesPlaylistIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:scenes:playlist'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/(?:((studios|stars)/(?P<id>[\d]+)/(?P<name>[^/?#&]+))|(tag/(?P<tagname>[^/?#&]+)))"

    @dec_on_reextract
    def get_entries_from_scenes_list(self, url, **kwargs):
        _type = kwargs.get('_type', 'all')
        if _type == 'all':
            _types = ['hls', 'dash', 'ism']
        else:
            _types = [_type]
        msg = kwargs.get('msg')
        premsg = f"[get_entries][{self._key}]"
        if msg:
            premsg = f"{msg}{premsg}"

        try:

            info_url = self._match_valid_url(url).groupdict()

            if _tagname := info_url.get('tagname'):
                with NakedSwordBaseIE._LOCK:
                    if not NakedSwordBaseIE._TAGS:
                        self._get_tags(driver)
                _tagname = _tagname.lower().replace(' ', '-').replace(',', '-')
                if _tagname in (NakedSwordBaseIE._TAGS['themes'] + NakedSwordBaseIE._TAGS['sex_acts']):
                    query = f'tags_name={_tagname}'

            else:
                _id = info_url.get('id')
                if '/stars/' in url:
                    query = f'stars_id={_id}'
                elif '/studios/' in url:
                    query = f'studios_id={_id}'

            _scenes = self.get_api_most_watched_scenes(query)

            def _getter(movie_id, index):
                _movie_url = try_get(self._send_request(f"https://www.nakedsword.com/movies/{movie_id}/_"), lambda x: str(x.url))
                return f'{_movie_url}/scene/{index}'

            _info_scenes = [(_getter(sc['movie']['id'], sc['index']), int(sc['index'])) for sc in _scenes]

            self.logger_debug(f"{premsg} url scenes [{len(_info_scenes)}]\n{_info_scenes}")

            if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

                isc = self._get_extractor('NakedSwordScene')

                _entries = []
                with ThreadPoolExecutor(thread_name_prefix='nsmostwatch') as ex:
                    futures = {ex.submit(isc.get_entry, _info[0], index=_info[1], _type="hls"): _info[0] for _info in _info_scenes}

                with NakedSwordBaseIE._LOCK:
                    NakedSwordBaseIE._USERS -= 1

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

    def _real_extract(self, url):

        try:
            self.report_extraction(url)
            return self.get_entries_from_scenes_list(url, _type="hls")
        except (ExtractorError, StatusStop) as e:
            raise
        except ReExtractInfo as e:
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')
        finally:
            self.check_close_nsapi()


class NakedSwordJustAddedMoviesPlaylistIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:justaddedmovies:playlist'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/just-added(\?(?P<query>.+))?"

    def get_entries_from_movies_list(self, url, **kwargs):

        premsg = f"[get_entries][{url}]"
        if (msg := kwargs.get('msg')):
            premsg = f"{msg}{premsg}"

        try:

            _movies = sorted(self.get_api_newest_movies(), key=lambda x: datetime.fromisoformat(extract_timezone(x.get('publish_start'))[1]))

            _query = self._match_valid_url(url).groupdict().get('query')
            if _query:
                _params = {el.split('=')[0]: el.split('=')[1] for el in _query.split('&') if el.count('=') == 1}
            else:
                _params = {}
                _query = "noquery"
            if _f := _params.get('from'):
                _from = datetime.fromisoformat(f'{_f}T00:00:00.000001')
            else:
                _from = try_get(_movies[0].get('publish_start'), lambda x: datetime.fromisoformat(extract_timezone(x)[1]))
            if _t := _params.get('to'):
                _to = datetime.fromisoformat(f'{_t}T23:59:59.999999')
            else:
                _to = try_get(_movies[-1].get('publish_start'), lambda x: datetime.fromisoformat(extract_timezone(x)[1]))

            self.logger_debug(f"{premsg} from {str(_from)} to {str(_to)}")

            _movies_filtered = [_mov for _mov in _movies if _from <= datetime.fromisoformat(extract_timezone(_mov.get('publish_start'))[1]) <= _to]

            _url_movies = list(set([try_get(self._send_request(_url), lambda x: str(x.url)) for _url in [f'https://www.nakedsword.com/movies/{x["id"]}/_' for x in _movies_filtered]]))

            self.logger_debug(f"{premsg} url movies [{len(_url_movies)}]\n{_url_movies}")

            if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

                imov = self._get_extractor('NakedSwordMovie')

                _entries = []
                with ThreadPoolExecutor(thread_name_prefix='nsnewest') as ex:
                    futures = {ex.submit(imov.get_entries, _url, _type="hls", force=True): _url for _url in _url_movies}

                with NakedSwordBaseIE._LOCK:
                    NakedSwordBaseIE._USERS -= 1

                for fut in futures:
                    if _res := fut.result():
                        _entries += [_r for _r in _res if not _r.update({'original_url': url})]

                return self.playlist_result(_entries, playlist_id=f'{sanitize_filename(_query, restricted=True)}', playlist_title="Search")

            else:
                return self.playlist_from_matches(
                    _url_movies,
                    getter=lambda x: x,
                    ie=NakedSwordMovieIE, playlist_id=f'{sanitize_filename(_query, restricted=True)}', playlist_title="Search")

        except Exception as e:
            logger.exception(f"{premsg} {str(e)}")
            raise

    def _real_extract(self, url):

        try:
            self.report_extraction(url)
            return self.get_entries_from_movies_list(url)
        except (ExtractorError, StatusStop) as e:
            raise
        except ReExtractInfo as e:
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')
        finally:
            self.check_close_nsapi()
