import functools
import html
import json
import logging
import re
import sys
import traceback
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from queue import Queue
from threading import Lock, Semaphore, Event
from urllib.parse import quote, unquote, urljoin, urlparse
import time

from .commonwebdriver import (
    By,
    ConnectError,
    HTTPStatusError,
    SeleniumInfoExtractor,
    StatusStop,
    dec_on_exception,
    dec_on_exception2,
    dec_on_exception3,
    dec_on_reextract,
    dec_retry,
    ec,
    limiter_0_01,
    limiter_0_005,
    limiter_1,
    limiter_non,
    scroll,
    ReExtractInfo,
    Client,
    my_dec_on_exception,
    TimeoutException,
    WebDriverException
)
from ..utils import (
    ExtractorError,
    sanitize_filename,
    smuggle_url,
    traverse_obj,
    try_get,
    unsmuggle_url,
    int_or_none,
    extract_timezone
)

logger = logging.getLogger('nakedsword')

dec_on_exception_driver = my_dec_on_exception((TimeoutException, WebDriverException), max_tries=3, raise_on_giveup=True, interval=1)

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
                else: return False
            
            else:
                el_loggin = try_get(el_uas.find_elements(By.CLASS_NAME, "UserAction"), lambda x: x[0])
                if el_loggin and el_loggin.text.upper() == "SIGN OUT":
                    el_loggin.click()
                    return "CHECK"
                else: return False
            
        else:
            if not self.ifnot:
                el_loggin.click()
                return "FALSE"
                
            else: return "TRUE"

class selectScenesMostWatched:
    def __call__(self, driver):
        el_sel = driver.find_elements(By.CSS_SELECTOR, "div.Selected")
        if len(el_sel) < 2: return False
        _doreturnfalse = False
        if el_sel[0].text.upper() != "SCENES":
            el_show = driver.find_element(By.CSS_SELECTOR, ".ShowMeSection")
            el_show_but = try_get(el_show.find_elements(By.CLASS_NAME, "Option"), lambda x: x[1])
            if el_show_but:
                try:
                    el_show_but.click()
                except Exception as e:
                    pass

                _doreturnfalse = True

        if el_sel[1].text.upper() != "MOST WATCHED":
            el_sort = driver.find_element(By.CSS_SELECTOR, ".SortSection")
            el_sort_but = try_get(el_sort.find_elements(By.CLASS_NAME, "Option"), lambda x: x[1])
            if el_sort_but:
                try:
                    el_sort_but.click()
                except Exception as e:
                    pass

                _doreturnfalse = True
        
        if _doreturnfalse: 
            return False
        else:
            return(el_sel[0].text.upper(), el_sel[1].text.upper())

class toggleVideo:
    def __call__(self, driver):
        el_pl_click  = try_get(driver.find_element(By.CSS_SELECTOR, "button.vjs-big-play-button"), lambda x: x.click())
        time.sleep(0)
        try:
            click_pause = try_get(driver.find_element(By.CSS_SELECTOR, "button.vjs-play-control.vjs-control.vjs-button.vjs-playing"), lambda x: (x.text, x.click()))
        except Exception as e:
            pass
        return True

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
        el_pl  = driver.find_element(By.CSS_SELECTOR, "button.vjs-big-play-button")
        el_mv = driver.find_element(By.CLASS_NAME, "MovieDetailsPage")
        el_inner = el_mv.find_element(By.CLASS_NAME, "Inner")        
        el_mvsc = try_get(el_inner.find_elements(By.CLASS_NAME, "MovieScenes"), lambda x: x[0] if x else None)
        if el_mvsc:
            if (_scenes:=el_mvsc.find_elements(By.CLASS_NAME, "Scene")):
                return _scenes
            else:
                return False
        else: return "singlescene"
            
class NakedSwordBaseIE(SeleniumInfoExtractor):

    _SITE_URL = "https://www.nakedsword.com/"
    _SIGNIN_URL = "https://www.nakedsword.com/signin"
    _NETRC_MACHINE = 'nakedsword'
    _LOCK = Lock()
    _NLOCKS = {'noproxy': Lock()}
    _SEM = Semaphore(10)
    _TAGS = {}
    _MAXPAGE_SCENES_LIST = 2
    _DRIVERS = {}
    _MAX_DRIVERS = 5
    _USERS = 0

    def wait_until(self, driver, **kwargs):
        kwargs['poll_freq'] = 0.25
        return super().wait_until(driver, **kwargs)

    def _fill_in_queue(self, num):
        _ndrv = self._MAX_DRIVERS
        n = min(_ndrv, num) 
        with NakedSwordBaseIE._LOCK:            
            if NakedSwordBaseIE._DRIVERS.get('queue'):                
                if n <= NakedSwordBaseIE._DRIVERS.get('count'):
                    NakedSwordBaseIE._USERS += 1
                    return
                else:
                    delta = n - NakedSwordBaseIE._DRIVERS.get('count')
            else:
                NakedSwordBaseIE._DRIVERS.update({'count': 0, 'queue': Queue()})
                delta = n
            
            with ThreadPoolExecutor(thread_name_prefix='nsdriv') as ex:
                futures = {ex.submit(self._get_driver_logged, force=True): i for i in range(delta)}

            for fut in futures:
                try:
                    if (_res:=fut.result()):
                        NakedSwordBaseIE._DRIVERS['queue'].put_nowait(_res)
                        NakedSwordBaseIE._DRIVERS['count'] += 1
                except Exception as e:
                    logger.exception(f"[fill_in_queue][{futures[fut]}] {str(e)}")
            
            NakedSwordBaseIE._USERS += 1
                    

    def _remove_queue(self):
        with NakedSwordBaseIE._LOCK:
            if NakedSwordBaseIE._DRIVERS.get('queue'):                
                NakedSwordBaseIE._USERS -= 1
                if (NakedSwordBaseIE._USERS == 0):                    
                    while True:
                        try:
                            _dr = NakedSwordBaseIE._DRIVERS['queue'].get_nowait()
                        except Exception as e:
                            break
                        try:
                            self._logout(_dr)
                        finally:
                            try:                        
                                self.rm_driver(_dr)                        
                            finally:                        
                                NakedSwordBaseIE._SEM.release()
                    NakedSwordBaseIE._DRIVERS = {}

    def _get_formats(self, _types, _info):

        #m3u8_doc = _info.get('m3u8_doc')
        m3u8_url = _info.get('m3u8_url')
        _headers_mpd = self._headers_ordered({"Accept": "*/*", "Origin": "https://www.nakedsword.com", "Referer": self._SITE_URL})
        
        formats = []

        for _type in _types:

            self.check_stop()
            try:
                if _type == "hls":

                    #if not m3u8_doc:
                    m3u8_doc = try_get(self._send_request(m3u8_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace'))
                    if not m3u8_doc:
                        raise ReExtractInfo("couldnt get m3u8 doc")

                    formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                        m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")
                    if formats_m3u8: formats.extend(formats_m3u8)
                
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
                
        if not formats: raise ExtractorError("couldnt find any format")
        else:
            return formats
    
    def _logout(self, driver):
        try:
            logged_out = False
            if not 'nakedsword.com' in driver.current_url:
                self._send_request(self._SITE_URL, driver=driver)
            
            res = self.wait_until(driver, timeout=10, method=checkLogged(ifnot=True))
            if res == "TRUE": logged_out = True
            elif res == "CHECK":
                self.wait_until(driver, timeout=1)
                res = self.wait_until(driver, timeout=10, method=checkLogged(ifnot=True))
                if res == "TRUE": logged_out = True
                else:
                    driver.delete_all_cookies()
                    self.wait_until(driver, timeout=1)
                    res = self.wait_until(driver, timeout=10, method=checkLogged(ifnot=True))
                    if res == "TRUE": logged_out = True
            if logged_out:
                self.logger_debug(f"[logout][{self._key}] Logout OK")
            else:
                self.logger_debug(f"[logout][{self._key}] Logout NOK")
        except Exception as e:
            self.report_warning(f"[logout][{self._key}] Logout NOK {repr(e)}")

    def _headers_ordered(self, extra=None):
        _headers = OrderedDict()
        
        if not extra: extra = dict()
        
        for key in ["User-Agent", "Accept", "Accept-Language", "Accept-Encoding", "Content-Type", "X-Requested-With", "Origin", "Connection", "Referer", "Upgrade-Insecure-Requests"]:
        
            value = extra.get(key) if extra.get(key) else self._CLIENT_CONFIG['headers'].get(key.lower())
            if value:
                _headers[key.lower()] = value      
        
        return _headers
    
    @dec_on_exception_driver
    @dec_on_exception2
    @dec_on_exception3
    @limiter_0_005.ratelimit("nakedsword", delay=True)
    def _send_request(self, url, **kwargs):
        
        driver = kwargs.get('driver', None)

        if not driver:
            try:
                return(self.send_http_request(url, **kwargs))
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
        else:
            driver.execute_script("window.stop();")
            driver.get(url)

    @dec_retry     
    def _get_driver_logged(self, **kwargs):
        
        noheadless = kwargs.get('noheadless', False)
        _driver = kwargs.get('driver', None)
        force = kwargs.get('force', False)
        rem = False
        if not _driver:
            rem = True
            _res_acq = NakedSwordBaseIE._SEM.acquire(timeout=300)
            if not _res_acq: 
                ExtractorError("error timeout acquire driver")

            _driver = self.get_driver(devtools=True, noheadless=noheadless)
            
            if not _driver: raise ExtractorError("error starting firefox")
            
        try:
            _res_login = self._login(_driver)
            if _res_login:
                if force or not force:
                    self._send_request("https://www.nakedsword.com/movies/283060/islas-canarias", driver=_driver)
                    self.wait_until(_driver, timeout=60, method=selectHLS())
                return _driver
            else: raise ExtractorError("error when login")
        except Exception as e:
            if rem:
                NakedSwordBaseIE._SEM.release()
                self.rm_driver(_driver)
            raise ExtractorError({str(e)})
    
    def _get_streaming_info(self, url, **kwargs):
        
        premsg = f"[get_streaming_info][{url}]"
        driver = kwargs.get('driver')

        self._send_request(url, driver=driver)

        el_scenes = self.wait_until(driver, timeout=60, method=getScenes())
        if not el_scenes:
            raise ReExtractInfo(f"{premsg} error auth")
        logger.debug(f"{premsg} {len(el_scenes)} scenes") 
        details = try_get(self.scan_for_json(driver, "details", _all=True), lambda x: x[-1].get('data'))
        if not details:
            raise ReExtractInfo(f"{premsg} no details info")        

        if el_scenes == "singlescene":
            self.wait_until(driver, timeout=30, method=waitVideo())
            m3u8_url = traverse_obj(self.scan_for_json(driver, r'https://ns-api\.nakedsword\.com/frontend/streaming/aebn/movie/.*scenes_id.*format=HLS$'), 'data')
            if not m3u8_url:
                raise ReExtractInfo("no m3u8-url")
            info_scene = {'index': 1, 'url': url, 'm3u8_url': m3u8_url}
            return([info_scene], details)

        else:
            num_scenes = len(el_scenes)
            index_scene = int_or_none(kwargs.get('index'))
            if index_scene:
                _start_ind = index_scene
                _end_ind = _start_ind + 1
            else:
                _start_ind = 1
                _end_ind = num_scenes + 1

            info_scenes = []
            _urls_sc = []
            for ind in range(_start_ind, _end_ind):
                el_scenes = self.wait_until(driver, timeout=60, method=getScenes())
                _link_click = try_get(traverse_obj(el_scenes[ind-1].find_elements(By.TAG_NAME, 'a'), (lambda _, v: 'scene' in v.get_attribute('href'))), lambda x: {'url': x[0].get_attribute('href'), 'ok': x[0].click()} if x else None)
                #logger.info(f"{premsg}[{ind}] scene click {_link_click}")
                if not _link_click: raise ExtractorError(f"{premsg}[{ind}] couldnt click scene")
                _iurl_sc = _link_click.get('url')
                _urls_sc.append(_iurl_sc)
                self.wait_until(driver, timeout=30, method=waitVideo())
            
            m3u8urls_scenes = [_el.get('data') for _el in self.scan_for_json(driver, r'https://ns-api\.nakedsword\.com/frontend/streaming/aebn/movie/.*scenes_id.*format=HLS$', _all=True)]
            if len(m3u8urls_scenes) != len(_urls_sc):
                logger.error(f"{premsg} number of info scenes {len(m3u8urls_scenes)} doesnt match with number of urls sc {len(_urls_sc)}\n{_urls_sc}\n\n{m3u8urls_scenes}")
                raise ReExtractInfo(f"{premsg} number of info scenes {len(m3u8urls_scenes)} doesnt match with number of urls sc {len(_urls_sc)}")
            
            if index_scene:
                info_scene = {'index': index_scene, 'url': _urls_sc[0], 'm3u8_url': m3u8urls_scenes[0]}
                return(info_scene, details)
            
            else:
                for i, (m3u8_url, _url) in enumerate(zip(m3u8urls_scenes, _urls_sc)):

                    if not m3u8_url:
                        raise ReExtractInfo(f"{premsg}[{_url}] couldnt find m3u8 url")

                    info_scenes.append({'index': i+1, 'url': _url, 'm3u8_url': m3u8_url})

                return(info_scenes, details)

    def _is_logged(self, driver):
        
        if not 'nakedsword.com' in driver.current_url:
            self._send_request(self._SITE_URL, driver=driver)
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
                el_username.send_keys(username)
                el_psswd.send_keys(password)
                
                with NakedSwordBaseIE._NLOCKS.get(self._key):
                    el_submit.click()
                    self.wait_until(driver, timeout=5)
                
                if self._is_logged(driver):
                    self.logger_debug(f"[login][{self._key}] Login OK")
                    return True
                else: 
                    self.logger_debug(f"[login][{self._key}] Login NOK")
                    driver.refresh()
                    raise ExtractorError("login nok")
            
            else:
                self.logger_debug(f"[login][{self._key}] Already logged")
                return True
        except Exception as e:
            logger.error(str(e))
            self._logout(driver)
            raise

    def _real_initialize(self):

        try:
            with NakedSwordBaseIE._LOCK:

                super()._real_initialize()
                
                if (_proxy:=self._downloader.params.get('proxy')):
                    self.proxy = _proxy
                    self._key = _proxy.split(':')[-1]
                    self.logged_debug(f"proxy: [{self._key}]")
                    if not NakedSwordBaseIE._NLOCKS.get(self._key):
                        NakedSwordBaseIE._NLOCKS.update({self._key: Lock()})
                else: 
                    self.proxy = None
                    self._key = "noproxy"
                


        except Exception as e:
            logger.error(repr(e))

class NakedSwordSceneIE(NakedSwordBaseIE):
    IE_NAME = 'nakedswordscene'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<movieid>[\d]+)/(?P<title>[^\/]+)/scene/(?P<id>[\d]+)"

    @dec_on_reextract
    def _get_entry(self, url, **kwargs):
        
        _type = kwargs.get('_type', 'all')
        if _type == 'all': _types = ['hls', 'dash', 'ism']
        else: _types = [_type]
        msg = kwargs.get('msg')
        index_scene = try_get(kwargs.get('index') or try_get(self._match_valid_url(url).groupdict(), lambda x: x.get('id')), lambda x: int(x) if x else 1)
        premsg = f"[get_entry][{self._key}][{url}][{index_scene}]"
        if msg: premsg = f"{msg}{premsg}"        
                      
        driver = kwargs.get('driver')
        rem = False
        inqueue = False
        if not driver:            
            if NakedSwordBaseIE._DRIVERS.get('queue'):
                driver = NakedSwordBaseIE._DRIVERS['queue'].get()
                inqueue = True
            else:
                driver = self._get_driver_logged()
                rem = True

        try:

            self.logger_debug(f"{premsg} start to get entry")            
            _url_movie = url.split('/scene/')[0]
            _info, details = self._get_streaming_info(_url_movie, driver=driver, index=index_scene)
            if inqueue:
                NakedSwordBaseIE._DRIVERS['queue'].put_nowait(driver)
                inqueue = False

            #self.logger_debug(f"{premsg} {sceneurl} - {m3u8_url}")
            #_index, sceneurl, m3u8_url, m3u8_doc = list(_info.values())
            #_index, sceneurl, m3u8_url = list(_info.values())
            _title = f"{sanitize_filename(details.get('title'), restricted=True)}_scene_{index_scene}"
            scene_id = traverse_obj(details, ('scenes', int(index_scene) - 1, 'id'))

            formats = self._get_formats(_types, _info)
            
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
            

        except ReExtractInfo as e:
            logger.error(f"[get_entries][{url} {str(e)}")
            raise
        except (StatusStop, ExtractorError) as e: 
            raise       
        except Exception as e:
            logger.exception(repr(e))
            raise ExtractorError(f'{premsg}: error - {repr(e)}')
        finally:
            if rem:
                self._logout(driver)
                NakedSwordBaseIE._SEM.release()
                self.rm_driver(driver)
            elif inqueue:
                NakedSwordBaseIE._DRIVERS['queue'].put_nowait(driver)

    def _real_extract(self, url):

        try:            
            self.report_extraction(url)
            nscene = int(self._match_id(url))           
            return self._get_entry(url, index=nscene, _type="hls")

        except (ExtractorError, StatusStop) as e:
            raise
        except ReExtractInfo as e:
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')

class NakedSwordMovieIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:movie:playlist'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<id>[\d]+)/(?P<title>[^/?#&]+)"
    _MOVIES_URL = "https://www.nakedsword.com/movies/"

    @dec_on_reextract
    def _get_entries(self, url, **kwargs):
        _type = kwargs.get('_type', 'all')
        if _type == 'all': _types = ['hls', 'dash', 'ism']
        else: _types = [_type]
        msg = kwargs.get('msg')
        premsg = f"[get_entries][{self._key}]"
        if msg: premsg = f"{msg}{premsg}"        
        
        driver = kwargs.get('driver')
        rem = False
        inqueue = False
        if not driver:            
            if NakedSwordBaseIE._DRIVERS.get('queue'):
                driver = NakedSwordBaseIE._DRIVERS['queue'].get()
                inqueue = True
            else:
                #driver = self.get_driver(devtools=True)
                driver = self._get_driver_logged()
                rem = True

        _force_list = kwargs.get('force', False)
        _legacy = kwargs.get('legacy', False)
        
        self.report_extraction(url)
        
        try:

            self._send_request(url, driver=driver)
            self.wait_until(driver, timeout=30, method=getScenes())
            details = try_get(self.scan_for_json(driver, "details", _all=True), lambda x: x[-1].get('data'))
            if not details: raise ReExtractInfo("no details info")
            playlist_id = str(details.get('id'))
            pl_title = sanitize_filename(details.get('title'), restricted=True)
            _url_movie = driver.current_url

            if self.get_param('embed') or (self.get_param('extract_flat','') != 'in_playlist'):
                if not _legacy:
                    if inqueue:
                        NakedSwordBaseIE._DRIVERS['queue'].put_nowait(driver)
                        inqueue = False
                    _url_scenes = [f"{_url_movie.strip('/')}/scene/{x['index']}" for x in traverse_obj(details, 'scenes')]
                    self._fill_in_queue(len(_url_scenes))
                    iesc = self._get_extractor('NakedSwordScene')
                    with ThreadPoolExecutor(max_workers=10, thread_name_prefix='nsmov') as ex:
                        futures = {ex.submit(iesc._get_entry, _url, index=i+1, _type="hls"): _url for i,_url in enumerate(_url_scenes)}

                    _entries = [_res for fut in futures if (_res:=fut.result()) and not _res.update({'original_url': _url_movie})]
                    if _force_list:
                        return _entries
                    else:
                        return self.playlist_result(_entries, playlist_id= playlist_id, playlist_title=pl_title)
                else:
                    info_streaming_scenes, details = self._get_streaming_info(_url_movie, driver=driver)
                    if inqueue:
                        NakedSwordBaseIE._DRIVERS['queue'].put_nowait(driver)
                        inqueue = False

                    _entries = []
                    for i, _info in enumerate(info_streaming_scenes):          
                        try:
                            #_index, _url, m3u8_url, m3u8_doc = list(_info.values())

                            self.logger_debug(f"{premsg}[{i}]:\n{_info}")
                    
                            _title = f"{sanitize_filename(details.get('title'), restricted=True)}_scene_{i+1}"
                            scene_id = traverse_obj(details, ('scenes', i, 'id'))
                            formats = self._get_formats(_types, _info)
                            if formats:
                    
                                _entry = {
                                    "id": str(scene_id),
                                    "title": _title,
                                    "formats": formats,
                                    "ext": "mp4",
                                    "webpage_url": _info.get('url'),
                                    "original": url,                   
                                    "extractor_key": 'NakedSwordScene',
                                    "extractor": 'nakedswordscene'
                                }
                            
                                self.logger_debug(f"{premsg}[{_info.get('url')}]: OK got entry")
                                _entries.append(_entry)
                        except ReExtractInfo as e:
                            raise
                        except Exception as e:
                            logger.exception(f"{premsg}[{i}]: info streaming\n{_info} error - {str(e)}") 
                            raise

                    if _force_list:
                        return _entries
                    else:
                        return self.playlist_result(_entries, playlist_id= playlist_id, playlist_title=pl_title)

            else:
                if inqueue:
                    NakedSwordBaseIE._DRIVERS['queue'].put_nowait(driver)
                    inqueue = False

                if _force_list: 
                    return [self.url_result(f"{_url_movie.strip('/')}/scene/{x['index']}", ie=NakedSwordSceneIE) for x in traverse_obj(details, 'scenes')]
                else:
                    return self.playlist_from_matches(
                        traverse_obj(details, 'scenes'), 
                        getter=lambda x: f"{_url_movie.strip('/')}/scene/{x['index']}", 
                        ie=NakedSwordSceneIE, playlist_id= playlist_id, playlist_title=pl_title)
            
        finally:
            # if rem:
            #     self.rm_driver(driver)
            if rem:
                self._logout(driver)
                NakedSwordBaseIE._SEM.release()
                self.rm_driver(driver)
            if inqueue:
                NakedSwordBaseIE._DRIVERS['queue'].put_nowait(driver)
            if not _legacy:
                self._remove_queue()

    def _real_extract(self, url):

        try:
            return self._get_entries(url, legacy=True, _type="hls")
        except (ExtractorError, StatusStop) as e:
            raise
        except ReExtractInfo as e:
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')

class NakedSwordScenesPlaylistIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:scenes:playlist'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/(?:((studios|stars)/(?P<id>[\d]+)/(?P<name>[^/?#&]+))|(tag/(?P<tagname>[^/?#&]+)))"
    _THEMES_URL = "https://www.nakedsword.com/themes"
    _BASE_THEME_URL = "https://www.nakedsword.com/theme/"
    _BASE_SEXACT_URL= "https://www.nakedsword.com/scenes/for/sexact/"

    def _get_tags(self, driver):

        self._send_request(self._THEMES_URL, driver=driver)
        feed = try_get(ie.scan_for_json(driver, r'feed$', _all=True), lambda x: x[-1].get('data'))
        themes = [el['name'].lower().replace(' ','-').replace(',','-') for el in feed['categories']]
        sex_acts  = [el['name'].lower().replace(' ','-').replace(',','-') for el in feed['sex_acts']]
        NakedSwordBaseIE._TAGS.update({'themes': themes, 'sex_acts': sex_acts})

    def _get_streaming_info_from_scenes_list(self, url, **kwargs):
        driver = kwargs.get('driver')
        pages = int(kwargs.get('pages', self._MAXPAGE_SCENES_LIST))
        
        feed = {}

        self._send_request(url, driver=driver)        
        if not "?content=Scenes&sort=MostWatched" in url:
            self.wait_until(driver, timeout=30, method=selectScenesMostWatched())
            pages = 1
        el_scenes = self.wait_until(driver, timeout=30, method=ec.presence_of_all_elements_located((By.CLASS_NAME, "Scene")))
        _feed = try_get(self.scan_for_json(driver, r'feed\?.*sort_by\=most_watched$', _all=True), lambda x: x[-1].get('data'))
        if not _feed:
            raise ExtractorError("couldnt get feed info")
        feed.update({'1': _feed})
        maxpage = min(pages, traverse_obj(_feed, ('pagination', 'last_page')))
        num_scenes_total = min(maxpage*12, traverse_obj(_feed, ('pagination', 'total')))
        info_scenes = []

        def _get_info_scene(_iurl, _dr, ilist):
            
            rem = False
            if not _dr:
                _dr = self._get_driver_logged(force=True)
                rem = True
            _info_scenes = []
            try:
                for i in ilist:
                    _page = i // 12
                    if not _page: iurl = _iurl
                    else: iurl = f"{_iurl}&page={_page+1}"
                    self._send_request(iurl, driver=_dr)        
                    if not "?content=Scenes&sort=MostWatched" in iurl:
                        self.wait_until(_dr, timeout=30, method=selectScenesMostWatched())
                    
                    el_scenes = self.wait_until(_dr, timeout=30, method=ec.presence_of_all_elements_located((By.CLASS_NAME, "Scene")))
                    
                    
                    _get_feed = False
                    with NakedSwordBaseIE._LOCK:
                        if not feed.get(str(_page+1)):
                            feed.update({str(_page+1): 'temp'})
                            _get_feed = True

                    if _get_feed:
                        self.logger_debug(f"[get_streaming_info][{iurl}][{i}] getfeed")
                        _feed_page = try_get(self.scan_for_json(_dr, r'feed\?.*sort_by\=most_watched$', _all=True), lambda x: x[-1].get('data'))
                        if not _feed_page:
                            raise ExtractorError("couldnt get feed info")
                        feed.update({str(_page+1): _feed_page})

                    #_link_click = try_get(el_scenes[i%12].find_elements(By.TAG_NAME, 'a'), lambda x: {'url': x[1].get_attribute('href'), 'ok': x[1].click()} if x else None)
                    #_link_click = try_get(el_scenes[i%12], lambda x: {'ok': x.click(), 'url': driver.current_url} if x else None)                                       
                    _link_click = try_get(traverse_obj(el_scenes[i%12].find_elements(By.TAG_NAME, 'a'), (lambda _, v: 'scene' in v.get_attribute('href'))), lambda x: {'url': x[0].get_attribute('href'), 'ok': x[0].click()} if x else None)
                    if not _link_click: raise ExtractorError(f"[get_streaming_info][{iurl}][{i}] couldnt click scene")
                    _iurl_sc = _link_click.get('url')
                    # if not 'scene' in _iurl_sc:
                    #     _link_click = try_get(traverse_obj(el_scenes[i%12].find_elements(By.TAG_NAME, 'a'), (lambda _, v: 'scene' in v.get_attribute('href'))), lambda x: {'url': x[0].get_attribute('href'), 'ok': x[0].click()} if x else None)
                    #     if not _link_click: raise ExtractorError(f"[get_streaming_info][{iurl}][{i}] couldnt click scene")
                    #     _iurl_sc = _link_click.get('url')

                    self.wait_until(_dr, timeout=30, method=toggleVideo())
                    self.wait_until(_dr, timeout=2)
                    m3u8_url, m3u8_doc, status = self.scan_for_request(_dr, ['playlist.m3u8', r'/[^/]*[a-zA-Z]+[^/]*/playlist.m3u8$'])
                    self.logger_debug(f"[get_streaming_info][{iurl}][{i}][{_iurl_sc}] {status} - {m3u8_url}")
                    details = try_get(self.scan_for_json(_dr, "details", _all=True), lambda x: x[-1].get('data'))

                    if not status or not m3u8_url or int(status) >= 400:
                        raise ReExtractInfo(f"[get_streaming_info][{iurl}][{i}][{_iurl_sc}] {status} - {m3u8_url}")
                    _info_scenes.append((i, _iurl_sc, m3u8_url, m3u8_doc, details))
                
                return _info_scenes
            finally:
                if rem:
                    self._logout(_dr)
                    NakedSwordBaseIE._SEM.release()
                    self.rm_driver(_dr)

        def split(lst, n):
            k, m = divmod(len(lst), n)
            return([lst[i*k+min(i, m):(i+1)*k+min(i+1, m)] for i in range(n)])
        
        if num_scenes_total < 12: _ndrv = 1
        elif num_scenes_total < 24: _ndrv = 2
        else: _ndrv = 3

        _drivers_list = [driver]
        for _ in range(_ndrv):
            _drivers_list.append(None)

        _scenes_lists = split([el for el in range(0,num_scenes_total)], len(_drivers_list))
        self.logger_debug(f"[get_streaming_info] {num_scenes_total} - {_scenes_lists} - {_drivers_list}")
        with ThreadPoolExecutor(thread_name_prefix='getstrinf') as ex:
            futures = [ex.submit(_get_info_scene, url, _driv, _sc_list) for _driv, _sc_list in zip(_drivers_list, _scenes_lists)]
            
        for fut in futures:
            info_scenes.extend(fut.result())
        
        info_scenes = sorted(info_scenes)
        return(info_scenes, feed)

    @dec_on_reextract
    def _get_entries_from_scenes_list(self, url, **kwargs):
        _type = kwargs.get('_type', 'all')
        if _type == 'all': _types = ['hls', 'dash', 'ism']
        else: _types = [_type]
        msg = kwargs.get('msg')
        premsg = f"[get_entries][{self._key}]"
        if msg: premsg = f"{msg}{premsg}"        
        
        driver = kwargs.get('driver')
        rem = False

        if not driver:
            driver = self._get_driver_logged(force=True)
            rem = True

        try:

            info_url = self._match_valid_url(url).groupdict()
            if _tagname:=info_url.get('tagname'):
                with NakedSwordBaseIE._LOCK:
                    if not NakedSwordBaseIE._TAGS:
                        self._get_tags(driver)
                _tagname = _tagname.replace(' ','-').replace(',','-') 
                if _tagname in NakedSwordBaseIE._TAGS['themes']:
                    _url = self._BASE_THEME_URL + _tagname
                elif _tagname in NakedSwordBaseIE._TAGS['sex_acts']:
                    _url = self._BASE_SEXACT_URL + _tagname
            else:
                _url = url.split('?')[0] + "?content=Scenes&sort=MostWatched"

            info_streaming_scenes, feed = self._get_streaming_info_from_scenes_list(_url, driver=driver)

            _str_info = '\n'.join([str(_info) for _info in info_streaming_scenes])
            logger.debug(f"{premsg}[{url}] info streaming scenes {len(info_streaming_scenes)}\n{_str_info}")
            #self.logger_debug(f"{premsg}[{url}] feed\n{feed}")


            _entries = []

            for i, _info in enumerate(info_streaming_scenes):
                _, _url, m3u8_url, m3u8_doc, details = _info
                self.logger_debug(f"{premsg}[{_url}] {m3u8_url}")    
                scene_id = traverse_obj(feed.get(str(i//12 + 1)), ('scenes', i%12, 'id'))
                _nscene = traverse_obj(feed.get(str(i//12 + 1)), ('scenes', i%12, 'index'))
                _titlemovie = traverse_obj(feed.get(str(i//12 + 1)), ('scenes', i%12, 'movie', 'title'))
                _title = f"{sanitize_filename(_titlemovie, restricted=True)}_scene_{_nscene}"

                formats = self._get_formats(_types, m3u8_url, m3u8_doc)

                if formats:
                
                    _entry = {
                        "id": str(scene_id),
                        "title": _title,
                        "formats": formats,
                        "ext": "mp4",
                        "webpage_url": _url,
                        "original": url,                   
                        "extractor_key": 'NakedSwordScene',
                        "extractor": 'nakedswordscene'
                    }
                
                    self.logger_debug(f"{premsg}[{_url}]: OK got entry")
                    _entries.append(_entry)

            playlist_id = info_url.get('name') or info_url.get('tagname')
            return self.playlist_result(_entries, playlist_id=sanitize_filename(playlist_id, restricted=True), playlist_title="MostWatchedScenes")

        except Exception as e:
            logger.exception(f"[get_entries][{url} {str(e)}")
            raise
        finally:
            if rem:
                self._logout(driver)
                NakedSwordBaseIE._SEM.release()
                self.rm_driver(driver)

    def _real_extract(self, url):

        try:
            self.report_extraction(url)            
            return self._get_entries_from_scenes_list(url, _type="hls")
        except (ExtractorError, StatusStop) as e:
            raise
        except ReExtractInfo as e:
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')

class NakedSwordJustAddedMoviesPlaylistIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:justaddedmovies:playlist'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/just-added(\?(?P<query>.+))?"
    _JUSTADDED_URL = "https://www.nakedsword.com/just-added?content=Movies&sort=Newest"

    def _get_entries_from_movies_list(self, url, **kwargs):
        
        premsg = f"[get_entries][{url}]"
        if (msg:=kwargs.get('msg')):
            premsg = f"{msg}{premsg}"        
        
        driver = kwargs.get('driver')
        rem = False

        if not driver:
            #driver = self._get_driver_logged(force=True)
            driver = self.get_driver(devtools=True)
            rem = True

        try:

            self._send_request(self._JUSTADDED_URL, driver=driver)
            el_movies = self.wait_until(driver, timeout=60, method=ec.presence_of_all_elements_located((By.CSS_SELECTOR, "a.BoxCoverInfoDisplay.Movie")))
            driver.execute_script("arguments[0].scrollIntoView(true);", el_movies[-1])
            #self.wait_until(driver, timeout=5)
            _movies = sorted(try_get(self.scan_for_json(driver, r'feed\?.*sort_by\=newest$', _all=True), lambda x: x[-2].get('data').get('movies') + x[-1].get('data').get('movies')), key=lambda x: datetime.fromisoformat(extract_timezone(x.get('publish_start'))[1]))
            
            _query = self._match_valid_url(url).groupdict().get('query')
            if _query:
                _params = {el.split('=')[0]: el.split('=')[1] for el in _query.split('&') if el.count('=') == 1}
            else:
                _params = {}
                _query = "noquery"
            if _f:=_params.get('from'):
                _from = datetime.fromisoformat(f'{_f}T00:00:00.000001')
            else:
                _from = try_get(_movies[0].get('publish_start'), lambda x: datetime.fromisoformat(extract_timezone(x)[1]))
            if _t:= _params.get('to'):
                _to = datetime.fromisoformat(f'{_t}T23:59:59.999999')
            else:
                _to = try_get(_movies[-1].get('publish_start'), lambda x: datetime.fromisoformat(extract_timezone(x)[1]))
           
            self.logger_debug(f"{premsg} from {str(_from)} to {str(_to)}")

            _movies_filtered = [_mov for _mov in _movies if _from <= datetime.fromisoformat(extract_timezone(_mov.get('publish_start'))[1]) <= _to]

            #_url_movies = [try_get(self._send_request(f"https://www.nakedsword.com/movies/{x['id']}/{x['title'].lower().replace(' ','-')}", driver=driver), lambda x: driver.current_url) for x in _movies_filtered]
            _url_movies = list(set(['https://www.nakedsword.com/movies/%s/%s' %(x['id'], re.sub(r"[ :,']", "-", x["title"].lower())) for x in _movies_filtered]))

            self.logger_debug(f"{premsg} url movies [{len(_url_movies)}]\n{_url_movies}")

            self._fill_in_queue(len(_url_movies))

            imov = self._get_extractor('NakedSwordMovie')

            _entries = []
            with ThreadPoolExecutor(thread_name_prefix='nsnewest') as ex:
                futures = {ex.submit(imov._get_entries, _url, _type="hls", force=True, legacy=True): _url for _url in _url_movies}

            for fut in futures:
                if _res:=fut.result():
                    _entries += [_r for _r in _res if not _r.update({'original_url': url})]
                
            return self.playlist_result(_entries, playlist_id=f'{sanitize_filename(_query, restricted=True)}', playlist_title="Search")
            
            # return self.playlist_from_matches(
            #         _movies_filtered, 
            #         getter=lambda x: f"https://www.nakedsword.com/movies/{x['id']}/{sanitize_filename(x['title'].lower(), restricted=True)}", 
            #         ie=NakedSwordMovieIE, playlist_id=f'{sanitize_filename(_query, restricted=True)}', playlist_title="Search")

        except Exception as e:
            logger.exception(f"{premsg} {str(e)}")
            raise
        finally:
            if rem:
                #self._logout(driver)
                #NakedSwordBaseIE._SEM.release()
                self.rm_driver(driver)
            self._remove_queue()

    def _real_extract(self, url):

        try:
            self.report_extraction(url)            
            return self._get_entries_from_movies_list(url)
        except (ExtractorError, StatusStop) as e:
            raise
        except ReExtractInfo as e:
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')
