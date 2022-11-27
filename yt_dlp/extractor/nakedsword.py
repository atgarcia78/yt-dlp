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
from threading import Lock, Semaphore
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
    ec,
    limiter_0_01,
    limiter_1,
    limiter_non,
    scroll,
    ReExtractInfo,
    Client
)
from ..utils import (
    ExtractorError,
    sanitize_filename,
    smuggle_url,
    traverse_obj,
    try_get,
    unsmuggle_url,
)

logger = logging.getLogger('nakedsword')


class checkLogged:

    def __init__(self, ifnot=False):
        self.ifnot = ifnot

    def __call__(self, driver):

        el_uas = driver.find_element(By.CSS_SELECTOR, "div.UserActions")
        if not self.ifnot:
            el_loggin = try_get(el_uas.find_elements(By.CLASS_NAME, "LoginWrapper"), lambda x: x[0])
            if not el_loggin:
                el_loggin = try_get(el_uas.find_elements(By.CLASS_NAME, "UserAction"), lambda x: x[1])
                if el_loggin and el_loggin.text.upper() == "MY ACCOUNT": 
                    return "TRUE"
                else: return False
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
                else: return False
            else: return "TRUE"



class selectHLS:
    def __call__(self, driver):
        el_pl = driver.find_element(By.CSS_SELECTOR, "button.vjs-big-play-button")
        el_pl.click()
        time.sleep(0.5)
        try:
            click_pause = try_get(driver.find_element(By.CSS_SELECTOR, "button.vjs-play-control.vjs-control.vjs-button.vjs-playing"), lambda x: (x.text, x.click()))
        except Exception as e:
            pass
        el_menu, el_menu_click = try_get(driver.find_element(By.CSS_SELECTOR, "button.vjs-control.vjs-button.fas.fa-cog"), lambda x: (x, x.click()))
        time.sleep(0.5)
        menu_hls = try_get(driver.find_elements(By.CLASS_NAME, "BaseVideoPlayerSettingsMenu-item-inner"), lambda x: x[1])
        
        if not "checked=" in menu_hls.get_attribute('outerHTML'):
            menu_hls.click()            
            time.sleep(0.5)            
            el_conf_click = try_get(driver.find_elements(By.CSS_SELECTOR, "div.Button"), lambda x: (x[1].text, x[1].click()))
            time.sleep(0.5)
            el_menu.click()
            return "TRUE"
        else:                       
            el_menu.click()
            return "FALSE"
        
        


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
                    #time.sleep(2)
                except Exception as e:
                    pass

                _doreturnfalse = True

        if el_sel[1].text.upper() != "MOST WATCHED":
            el_sort = driver.find_element(By.CSS_SELECTOR, ".SortSection")
            el_sort_but = try_get(el_sort.find_elements(By.CLASS_NAME, "Option"), lambda x: x[1])
            if el_sort_but:
                try:
                    el_sort_but.click()
                    #time.sleep(2)
                except Exception as e:
                    pass

                _doreturnfalse = True
        if _doreturnfalse: return False
        else:
            return(el_sel[0].text.upper(), el_sel[1].text.upper())


class toggleVideo:
    def __call__(self, driver):
        el_pl_click  = try_get(driver.find_element(By.CSS_SELECTOR, "button.vjs-big-play-button"), lambda x: x.click())
        time.sleep(0.5)
        try:
            click_pause = try_get(driver.find_element(By.CSS_SELECTOR, "button.vjs-play-control.vjs-control.vjs-button.vjs-playing"), lambda x: (x.text, x.click()))
            
        except Exception as e:
            pass
        return True




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
    _SEM = Semaphore(5)
    _TAGS = {}

    
    def _logout(self, driver):
        try:
            
            logged_out = False
            if not 'nakedsword.com' in driver.current_url:
                self._send_request(self._SITE_URL, driver=driver)
            
            res = self.wait_until(driver, 10, checkLogged(ifnot=True))
            if res == "TRUE": logged_out = True
            elif res == "CHECK":
                self.wait_until(driver, 2)
                res = self.wait_until(driver, 10, checkLogged(ifnot=True))
                if res == "TRUE": logged_out = True
                else:
                    driver.delete_all_cookies()
                    self.wait_until(driver, 2)
                    res = self.wait_until(driver, 10, checkLogged(ifnot=True))
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
    
    
    @dec_on_exception2
    @dec_on_exception3
    @limiter_0_01.ratelimit("nakedsword", delay=True)
    def _send_request(self, url, **kwargs):
        
        if ((_stop:=self.get_param('stop')) and _stop.is_set()):
            self.logger_debug(f"{self._get_url_print(url)}: stop")
            raise StatusStop(f"{self._get_url_print(url)}")
        
        driver = kwargs.get('driver', None)

        if not driver:
            try:
                return(self.send_http_request(url, **kwargs))
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
        else:
            #driver.execute_script("window.stop();")
            driver.get(url)
         
    def _get_driver_logged(self, **kwargs):
        
        noheadless = kwargs.get('noheadless', False)
        _driver = kwargs.get('driver', None)
        force = kwargs.get('force', False)
        rem = False
        if not _driver:
            rem = True
            _res_acq = NakedSwordBaseIE._SEM.acquire(timeout=60)
            if not _res_acq: 
                ExtractorError("error timeout acquire driver")
            
            if self._key == 'noproxy':
                host, port = None, None
            else:
                host, port = (urlparse(self.proxy).netloc).split(':')

            _driver = self.get_driver(devtools=True, noheadless=noheadless, host=host, port=port)
            

           
        try:
            #with NakedSwordBaseIE._NLOCKS.get(self._key):
            
            _res_login = self._login(_driver)
            if _res_login:
                if force:
                    self._send_request("https://www.nakedsword.com/movies/283060/islas-canarias", driver=_driver)
                    self.wait_until(_driver, 60, selectHLS())
                    #self._send_request(self._SITE_URL, driver=_driver)
                return _driver
            else: raise ExtractorError("error when login")
        except Exception as e:
            if rem:
                NakedSwordBaseIE._SEM.release()
                self.rm_driver(_driver)
            raise 
    
    

    
    def _get_streaming_info(self, url, **kwargs):
        
        driver = kwargs.get('driver')
        
        self._send_request(url, driver=driver)

        refresh = self.wait_until(driver, 30, selectHLS())

        self.logger_debug(f"[get_streaming_info][{url}] refresh {refresh}")

        if refresh == "TRUE":
            self._send_request(url, driver=driver)

        el_scenes = self.wait_until(driver, 60, getScenes())

        if not el_scenes:
            self._logout(driver)
            self._get_driver_logged(driver=driver)
            self._send_request(url.split('/scene/')[0], driver=driver)
            el_scenes = self.wait_until(driver, 60, getScenes()) 
            if not el_scenes: raise ExtractorError("error auth")
            
        self.wait_until(driver, 10, toggleVideo())
        res_movie =  self.scan_for_request(driver, ['playlist.m3u8', r'/[^/]*[a-zA-Z]+[^/]*/playlist.m3u8$'], _all=True)
        details = try_get(self.scan_for_json(driver, "details", _all=True), lambda x: x[-1].get('data'))

        self.logger_debug(f"[get_streaming_info] movie req playlist m3u8:\n%no%{res_movie}")

        if not details:
            raise ReExtractInfo("no details info")

        index_scene = try_get(kwargs.get('index') or try_get(re.search(NakedSwordSceneIE._VALID_URL, url), lambda x: x.group('id')), lambda x: int(x) if x else None)
        
        if isinstance(el_scenes, list):
            if not index_scene: _index = 1
            else: _index = int(index_scene)
            _link_click = try_get(el_scenes[_index - 1].find_element(By.TAG_NAME, 'a'), lambda x: {'url': x.get_attribute('href'), 'ok': x.click()} if x else None)
            self.logger_debug(f"[get_streaming_info][{url}] scene click")
            if not _link_click: raise ExtractorError("couldnt click scene")
            
            self.wait_until(driver, 10, toggleVideo())

            res = self.scan_for_request(driver, ['playlist.m3u8', r'/[^/]*[a-zA-Z]+[^/]*/playlist.m3u8$'], _all=True)
            self.logger_debug(f"[get_streaming_info] scene req playlist m3u8:\n%no%{res}")
            for el in res_movie:
                try:
                    res.remove(el)
                except Exception as e:
                    pass
            self.logger_debug(f"[get_streaming_info] after cleaning playlist movie:\n%no%{res}")
            
        
        else:#singlescene
            res = res_movie
           
        for el in res:            
            m3u8_url, m3u8_doc, status = el
            if int(status) >= 400:
                raise ReExtractInfo(str(status))
          
        if el_scenes == "singlescene":
            return([(url, m3u8_url, m3u8_doc, status)], details)
        elif index_scene:
            return((_link_click.get('url'), m3u8_url, m3u8_doc, status), details)
        else:
            info_scenes = []
            _urls_sc = []
            num_scenes = len(el_scenes)
            info_scenes.append((_link_click.get('url'), m3u8_url, m3u8_doc, status))
            for i in range(1, num_scenes):
                el_scenes = self.wait_until(driver, 60, getScenes())
                _link_click = try_get(el_scenes[i].find_element(By.TAG_NAME, 'a'), lambda x: {'url': x.get_attribute('href'), 'ok': x.click()} if x else None)
                if not _link_click: raise ExtractorError("couldnt click scene")
                _urls_sc.append(_link_click.get('url'))
                
                self.wait_until(driver, 10, toggleVideo())

                info_streaming_scenes = self.scan_for_request(driver, ['playlist.m3u8', r'/[^/]*[a-zA-Z]+[^/]*/playlist.m3u8$'], _all=True)

                for (i, (m3u8_url, m3u8_doc, status)), _url in zip(enumerate(info_streaming_scenes), _urls_sc):

                    if int(status) >= 400:
                        raise ReExtractInfo(f"[get_streaming_info][{_url}] {str(status)}")
                    info_scenes.append((_url, m3u8_url, m3u8_doc, status))

            return(info_scenes, details)

    @dec_on_reextract
    def _get_entry(self, url, **kwargs):        
        
        _headers_mpd = self._headers_ordered({"Accept": "*/*", "Origin": "https://www.nakedsword.com", "Referer": self._SITE_URL})        
        _type = kwargs.get('_type', 'all')
        if _type == 'all': _types = ['hls', 'dash', 'ism']
        else: _types = [_type]
        msg = kwargs.get('msg')
        premsg = f"[get_entry][{self._key}][{url}]"
        if msg: premsg = f"{msg}{premsg}"        

        index_scene = try_get(kwargs.get('index') or try_get(re.search(NakedSwordSceneIE._VALID_URL, url), lambda x: x.group('id')), lambda x: int(x) if x else 1)
               
        driver = kwargs.get('driver')
        rem = False

        if not driver:
            driver = self._get_driver_logged()
            rem = True

        try:

            self.logger_debug(f"{premsg} start to get entry")            
            _url_movie = url.split('/scene/')[0]
            (sceneurl, m3u8_url, m3u8_doc, status), details = self._get_streaming_info(_url_movie, driver=driver, index=index_scene)

            self.logger_debug(f"{sceneurl} - {m3u8_url} - {status}")

            if not m3u8_url or status >= 400:
                raise ExtractorError("couldnt get streaming info")
            
            if not details:
                details = try_get(self.scan_for_json(driver, "details", _all=True), lambda x: x[-1].get('data'))


            _title = f"{sanitize_filename(details.get('title'), restricted=True)}_scene_{index_scene}"
            scene_id = traverse_obj(details, ('scenes', int(index_scene) - 1, 'id'))

            formats = []

            for _type in _types:

                self.check_stop()
                try:
                    if _type == "dash":

                        mpd_url = m3u8_url.replace('playlist.m3u8', 'manifest.mpd')
                        _doc = try_get(self._send_request(mpd_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace'))
                        if not _doc:
                            raise ExtractorError("couldnt get mpd doc")
                        mpd_doc = self._parse_xml(_doc, None)

                        formats_dash = self._parse_mpd_formats(mpd_doc, mpd_id="dash", mpd_url=mpd_url, mpd_base_url=(mpd_url.rsplit('/', 1))[0])

                        if formats_dash:
                            #self._sort_formats(formats_dash)
                            formats.extend(formats_dash)
                    
                    elif _type == "hls":

                        if not m3u8_doc:
                            m3u8_doc = try_get(self._send_request(m3u8_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace'))
                            if not m3u8_doc:
                                raise ExtractorError("couldnt get m3u8 doc")
                        
                        #self.cache.store("nakedswordscene", str(scene_id), m3u8_doc)

                        formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                            m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")
                        
                        #self.to_screen(formats_m3u8)
                        
                        if formats_m3u8: 
                            formats.extend(formats_m3u8)

                    elif _type == "ism":

                        ism_url = m3u8_url.replace('playlist.m3u8', 'Manifest')
                        _doc = try_get(self._send_request(ism_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace'))
                        if _doc:       
                            ism_doc = self._parse_xml(_doc, None)                                                         
                            formats_ism, _ = self._parse_ism_formats_and_subtitles(ism_doc, ism_url)
                            if formats_ism:
                                #self._sort_formats(formats_ism)
                                formats.extend(formats_ism) 

                except ReExtractInfo as e:
                    raise
                except Exception as e:
                    logger.error(f"[{_type}] {repr(e)}")


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
            logger.exception(f"[get_entries][{url} {str(e)}")
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

    

    @dec_on_reextract
    def _get_entries(self, url, **kwargs):
        _headers_mpd = self._headers_ordered({"Accept": "*/*", "Origin": "https://www.nakedsword.com", "Referer": self._SITE_URL})        
        _type = kwargs.get('_type', 'all')
        if _type == 'all': _types = ['hls', 'dash', 'ism']
        else: _types = [_type]
        msg = kwargs.get('msg')
        premsg = f"[get_entries][{self._key}]"
        if msg: premsg = f"{msg}{premsg}"        
        
        driver = kwargs.get('driver')
        rem = False

        if not driver:
            driver = self._get_driver_logged()
            rem = True

        try:
        
            info_streaming_scenes, details = self._get_streaming_info(url, driver=driver)

            _entries = []

            for i, _info in enumerate(info_streaming_scenes):          

                _url, m3u8_url, m3u8_doc, status = _info
                
                _title = f"{sanitize_filename(details.get('title'), restricted=True)}_scene_{i+1}"
                scene_id = traverse_obj(details, ('scenes', i, 'id'))

                formats = []

                for _type in _types:

                    self.check_stop()
                    try:
                        if _type == "dash":

                            mpd_url = m3u8_url.replace('playlist.m3u8', 'manifest.mpd')
                            _doc = try_get(self._send_request(mpd_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace'))
                            if not _doc:
                                raise ExtractorError("couldnt get mpd doc")
                            mpd_doc = self._parse_xml(_doc, None)

                            formats_dash = self._parse_mpd_formats(mpd_doc, mpd_id="dash", mpd_url=mpd_url, mpd_base_url=(mpd_url.rsplit('/', 1))[0])
                            if formats_dash:
                                formats.extend(dash)
                        
                        elif _type == "hls":

                            if not m3u8_doc:
                                m3u8_doc = try_get(self._send_request(m3u8_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace'))
                                if not m3u8_doc:
                                    raise ExtractorError("couldnt get m3u8 doc")

                            #self.cache.store("nakedswordscene", str(scene_id), m3u8_doc)
                            
                            formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                                m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")
                            if formats_m3u8: formats.extend(formats_m3u8)


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
                        logger.error(f"[{_type}] {str(e)}")

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

            playlist_id = str(details.get('id'))
            pl_title = sanitize_filename(details.get('title'), restricted=True)
            return self.playlist_result(_entries, playlist_id= playlist_id, playlist_title=pl_title)

        except ReExtractInfo as e:
            logger.exception(f"[get_entries][{url} {str(e)}")
            raise
        except Exception as e:
            logger.exception(f"[get_entries][{url} {str(e)}")
        finally:
            if rem:
                self._logout(driver)
                NakedSwordBaseIE._SEM.release()
                self.rm_driver(driver)

                    
    
    def _is_logged(self, driver):
        
        if not 'nakedsword.com' in driver.current_url:
            self._send_request(self._SITE_URL, driver=driver)
        logged_ok = (self.wait_until(driver, 10, checkLogged()) == "TRUE")
        self.logger_debug(f"[is_logged][{self._key}] {logged_ok}")
        
        return logged_ok
        
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
                el_username.send_keys(username)
                el_psswd.send_keys(password)
                el_submit.click()

                self.wait_until(driver, 2)
                
                logged_ok = (self.wait_until(driver, 10, checkLogged()) == "TRUE")
                if logged_ok:
                    self.logger_debug(f"[login][{self._key}] Login OK")
                    return True
                else: raise ExtractorError("login nok")
            
            else:
                self.logger_debug(f"[login][{self._key}] Already logged")
                return True
        except Exception as e:
            logger.exception(repr(e))
            self._logout(driver)
            raise

    def _real_initialize(self):

        try:
            with NakedSwordBaseIE._LOCK:

                super()._real_initialize()
                
                if (_proxy:=self._downloader.params.get('proxy')):
                    self.proxy = _proxy
                    self._key = _proxy.split(':')[-1]
                    self.to_screen(f"proxy: [{self._key}]")
                    if not NakedSwordBaseIE._NLOCKS.get(self._key):
                        NakedSwordBaseIE._NLOCKS.update({self._key: Lock()})
                else: 
                    self.proxy = None
                    self._key = "noproxy"
                
                

        except Exception as e:
            logger.error(repr(e))


class NakedSwordSceneIE(NakedSwordBaseIE):
    IE_NAME = 'nakedswordscene'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<movieid>[\d]+)/(?P<title>[^\/]+)/scene/(?P<id>[\d]+)/?(?:#.+|$)"
 
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
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<id>[\d]+)/(?P<title>[^\/]+)/?(?:#.+|$)"
    _MOVIES_URL = "https://www.nakedsword.com/movies/"

 
    def _real_extract(self, url):

        try:
            self.report_extraction(url)            
            return self._get_entries(url, _type="hls")
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
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/(?:((studios|stars)/(?P<id>[\d]+)/(?P<name>[^\/\?]+))|(tag/(?P<tagname>[^\/\?]+)))"
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
        pages = int(kwargs.get('pages', 2))


        self._send_request(url, driver=driver)        
        if not "?content=Scenes&sort=MostWatched" in url:
            self.wait_until(driver, 30, selectScenesMostWatched())
            pages = 1
        el_scenes = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CLASS_NAME, "Scene")))
        feed = try_get(self.scan_for_json(driver, r'feed\?.*sort_by\=most_watched$', _all=True), lambda x: x[-1].get('data'))
        if not feed:
            raise ExtractorError("couldnt get feed info")
        maxpage = min(pages, traverse_obj(feed, ('pagination', 'last_page')))
        num_scenes_total = min(maxpage*12, traverse_obj(feed, ('pagination', 'total')))
        info_scenes = []
        #num_scenes = len(el_scenes)
                
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
                        self.wait_until(_dr, 30, selectScenesMostWatched())
                    
                    el_scenes = self.wait_until(_dr, 30, ec.presence_of_all_elements_located((By.CLASS_NAME, "Scene")))
                    _link_click = try_get(el_scenes[i%12].find_elements(By.TAG_NAME, 'a'), lambda x: {'url': x[1].get_attribute('href'), 'ok': x[1].click()} if x else None)
                    
                    if not _link_click: raise ExtractorError(f"[get_streaming_info][{iurl}][{i}] couldnt click scene")
                    _iurl_sc = _link_click.get('url')              
                    self.wait_until(_dr, 10, toggleVideo())

                    m3u8_url, m3u8_doc, status = self.scan_for_request(_dr, ['playlist.m3u8', r'/[^/]*[a-zA-Z]+[^/]*/playlist.m3u8$'])
                    self.logger_debug(f"[get_streaming_info][{iurl}][{i}][{_iurl_sc}] {status} - {m3u8_url}")

                    if not status or not m3u8_url or int(status) >= 400:
                        raise ReExtractInfo(f"[get_streaming_info][{iurl}][{i}][{_iurl_sc}] {status} - {m3u8_url}")
                    _info_scenes.append((i, _iurl_sc, m3u8_url, m3u8_doc, status))
                
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
        _headers_mpd = self._headers_ordered({"Accept": "*/*", "Origin": "https://www.nakedsword.com", "Referer": self._SITE_URL})        
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

            _entries = []

            for i, _info in enumerate(info_streaming_scenes):
                _i, _url, m3u8_url, m3u8_doc, status = _info
                    
                scene_id = traverse_obj(feed, ('scenes', i, 'id'))
                _nscene = traverse_obj(feed, ('scenes', i, 'index'))
                _titlemovie = traverse_obj(feed, ('scenes', i, 'movie', 'title'))
                _title = f"{sanitize_filename(_titlemovie, restricted=True)}_scene_{_nscene}"
                formats = []

                for _type in _types:

                    self.check_stop()
                    try:
                        if _type == "dash":

                            mpd_url = m3u8_url.replace('playlist.m3u8', 'manifest.mpd')
                            _doc = try_get(self._send_request(mpd_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace'))
                            if not _doc:
                                raise ExtractorError("couldnt get mpd doc")
                            mpd_doc = self._parse_xml(_doc, None)

                            formats_dash = self._parse_mpd_formats(mpd_doc, mpd_id="dash", mpd_url=mpd_url, mpd_base_url=(mpd_url.rsplit('/', 1))[0])
                            if formats_dash:
                                formats.extend(dash)
                        
                        elif _type == "hls":

                            if not m3u8_doc:
                                m3u8_doc = try_get(self._send_request(m3u8_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace'))
                                if not m3u8_doc:
                                    raise ExtractorError("couldnt get m3u8 doc")

                            #self.cache.store("nakedswordscene", str(scene_id), m3u8_doc)
                            
                            formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                                m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")
                            if formats_m3u8: formats.extend(formats_m3u8)


                        elif _type == "ism":

                            ism_url = m3u8_url.replace('playlist.m3u8', 'Manifest')
                            _doc = try_get(self._send_request(ism_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace'))
                            if _doc:       
                                ism_doc = self._parse_xml(_doc, None)                                                         
                                formats_ism, _ = self._parse_ism_formats_and_subtitles(ism_doc, ism_url)
                                if formats_ism:
                                    formats.extend(formats_ism) 


                    except Exception as e:
                        logger.error(f"[get_entries][{url}][{_url}][{_type}] {str(e)}")

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
