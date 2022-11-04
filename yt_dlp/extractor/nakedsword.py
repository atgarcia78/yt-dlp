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
from threading import Lock
from urllib.parse import quote, unquote, urljoin

from .commonwebdriver import (
    By,
    ConnectError,
    HTTPStatusError,
    SeleniumInfoExtractor,
    dec_on_exception,
    dec_on_exception2,
    dec_on_exception3,
    ec,
    limiter_0_1,
    limiter_1,
    limiter_non,
    scroll,
)
from ..utils import ExtractorError, sanitize_filename, traverse_obj, try_get

logger = logging.getLogger('nakedsword')

class getScenes:

    def __init__(self, logger):
        self.logger = logger
    def __call__(self, driver):
        el_mv = driver.find_element(By.CLASS_NAME, "MovieDetailsPage")
        el_inner = el_mv.find_element(By.CLASS_NAME, "Inner")
        #self.logger(f"[getscenes] {el_inner.get_attribute('outerHTML')}")
        el_mvsc = try_get(el_inner.find_elements(By.CLASS_NAME, "MovieScenes"), lambda x: x[0])
        #self.logger(f"[getscenes] {el_mvsc}")
        if el_mvsc:
            if (_scenes:=el_mvsc.find_elements(By.CLASS_NAME, "Scene")):
                return _scenes
            else:
                return False
        else: raise ExtractorError("no entries")
            

class NakedSwordBaseIE(SeleniumInfoExtractor):

    
    _SITE_URL = "https://www.nakedsword.com/"
    
    _NETRC_MACHINE = 'nakedsword'
    
    _LOCK = Lock()

    _NLOCKS = {'noproxy': Lock()}

    def _logout(self, driver):
        try:
            if driver:
                self._send_request(self._SITE_URL, driver=driver)
                if not self._is_logged(driver=driver):
                    self.to_screen(f"[close][{self._proxy}] Logout OK")
                    
                else:
                    try_get(self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CSS_SELECTOR, "div.UserAction"))), lambda x: x[0].click())
                    self.wait_until(driver, 2)
                    if not self._is_logged(driver=driver):
                        self.to_screen(f"[close][{self._proxy}] Logout OK")
                    else:
                        self.report_warning(f"[close][{self._proxy}] Logout NOK")
        except Exception as e:
            self.report_warning(f"[close][{self._proxy}] NOK {repr(e)}")

    def _headers_ordered(self, extra=None):
        _headers = OrderedDict()
        
        if not extra: extra = dict()
        
        for key in ["User-Agent", "Accept", "Accept-Language", "Accept-Encoding", "Content-Type", "X-Requested-With", "Origin", "Connection", "Referer", "Upgrade-Insecure-Requests"]:
        
            value = extra.get(key) if extra.get(key) else self._CLIENT_CONFIG['headers'].get(key.lower())
            if value:
                _headers[key.lower()] = value      
        
        return _headers
    
    @dec_on_exception
    @dec_on_exception2
    @dec_on_exception3
    @limiter_0_1.ratelimit("nakedsword", delay=True)
    def _send_request(self, url, driver=None, **kwargs):
        
        if not driver:

            try:
                return(self.send_http_request(url, **kwargs))
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
        else:
            driver.execute_script("window.stop();")
            driver.get(url)

    def _get_last_page(self, _urlqbase):
        i = 1
        while(True):
            webpage = try_get(self._send_request(f"{_urlqbase}{i}"), lambda x: html.unescape(x.text))
            if "Next Page" in webpage:
                i += 1
            else:
                break
        return i
                
    def get_entries_scenes(self, url, page=None, func=None):
        
        entries = []
        
        try:
            premsg = f"[get_entries_scenes]"
            if page: premsg = f"{premsg}[page {page}]"
            self.report_extraction(f"{premsg} {url}")
            webpage = try_get(self._send_request(url), lambda x: re.sub('[\t\n]','', html.unescape(x.text)) if x else None)
            
            if webpage:  
                            
                videos_paths = re.findall(
                    r"<div class='SRMainTitleDurationLink'><a href='/([^\']+)'>",
                    webpage)     
                
                if videos_paths:
                    
                    list_urlscenes = [f"{self._SITE_URL}{video}" for video in videos_paths]
                    if func:
                        list_urlscenes = list(filter(func, list_urlscenes))
                    
                    self.logger_debug(f"{premsg} scenes found [{len(list_urlscenes)}]: \n{list_urlscenes}")
                    
                    if list_urlscenes:               
                        with ThreadPoolExecutor(thread_name_prefix="nsgetscenes", max_workers=min(len(list_urlscenes), 10)) as exe:                                     
                            
                            futures = {exe.submit(self._get_entry, _urlscene, _type="hls", msg=premsg): _urlscene for _urlscene in list_urlscenes}

                        for fut in futures:
                            try:
                                _entry = fut.result()
                                if not _entry: raise ExtractorError("no entry")
                                _entry.update({'original_url': url})
                                entries.append(_entry)
                            except Exception as e:
                                self.report_warning(f"[get_entries_scenes] {url} - {futures[fut]} error - {repr(e)}")                                             
    
            return entries
        except Exception as e:
            self.report_warning(f"[get_entries_scenes] {url} error - {repr(e)}")
    
    def get_entries_movies(self, url):
        
        entries = []
        webpage = try_get(self._send_request(url), lambda x: re.sub('[\t\n]','', html.unescape(x.text)) if x else None)
        if webpage:  
                        
            videos_paths = re.findall(
                r"<div class='BoxResultsLink'><a href='/([^\']+)'>",
                webpage)     
            
            if videos_paths:
                
                for video in videos_paths:
                    _urlmovie = self._SITE_URL + video                    
                    entry = self.url_result(_urlmovie, ie=NakedSwordMovieIE.ie_key())
                    entries.append(entry)
 
        return entries
    
    def _get_driver_logged(self):
        
        with NakedSwordBaseIE._NLOCKS.get(self._proxy):
            _driver = self.get_driver(devtools=True)
            if self._login(driver=_driver):
                return _driver

    def _get_entry(self, url, **kwargs):        
        
        _headers_mpd = self._headers_ordered({"Accept": "*/*", "Origin": "https://www.nakedsword.com", "Referer": self._SITE_URL})        
        
        _type = kwargs.get('_type', 'all')
        if _type == 'all': _types = ['hls', 'dash', 'ism']
        else: _types = [_type]
        msg = kwargs.get('msg')
        premsg = f"[get_entry][{url}]"
        if msg: premsg = f"{msg}{premsg}"
        
        details = kwargs.get('details')
        index_scene = try_get(kwargs.get('index') or try_get(re.search(NakedSwordSceneIE._VALID_URL, url), lambda x: x.group('id')), lambda x: int(x) if x else None)
        if not index_scene: raise ExtractorError("no index scene")

        try:

            self.logger_debug(f"{premsg} start to get entry")
            driver = kwargs.get('driver')
            rem = False

            if not driver:

                driver = self._get_driver_logged()
                rem = True
                self.logger_debug(f"{premsg} start to get entry")
                
                self._send_request(url.split('/scene/')[0], driver=driver)
                self.wait_until(driver, 60, scroll())
                el_scenes = self.wait_until(driver, 60, getScenes(self.to_screen))
                if el_scenes:
                    scene_click = try_get(el_scenes, lambda x: {'ok': x[index_scene-1].find_element(By.TAG_NAME, 'a').click()} if x else None)
                    if not scene_click: raise ExtractorError("couldnt select scene")
                
            play = try_get(self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "button.vjs-big-play-button"))), lambda x: {'ok': x.click()} if x else None)
            if play:
                try:
                    pause = try_get(self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "button.vjs-play-control.vjs-control.vjs-button.vjs-playing"))), lambda x: {'ok': x.click()} if x else None)
                except Exception as e:
                    pause = try_get(self.wait_until(driver, 60, ec.presence_of_element_located((By.ID, "vjs_video_3_html5_api"))), lambda x: {'ok': x.click()} if x else None)

            else: raise ExtractorError("couldnt play video")

            mpd_url, _doc = try_get(self.scan_for_request(driver, f"manifest.mpd", _all=True), lambda x: x[-1])
            if not mpd_url: raise ExtractorError("couldnt find mpd url")
            if not details:
                details = try_get(self.scan_for_json(driver, "details"), lambda x: x.get('data'))
                self.logger_debug(f"{premsg}\n%no%{details}")

            if index_scene:
                _title = f"{sanitize_filename(details.get('title'), restricted=True)}_scene_{index_scene}"
            
                scene_id = traverse_obj(details, ('scenes', int(index_scene) - 1, 'id'))

            formats = []

            for _type in _types:

                try:

                    if _type == "dash":

                        if not _doc:
                            _doc = try_get(self._send_request(mpd_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace'))                      
                            if not _doc:
                                raise ExtractorError("couldnt get mpd doc")
                        
                        mpd_doc = self._parse_xml(_doc, None)

                        formats_dash = self._parse_mpd_formats(mpd_doc, mpd_id="dash", mpd_url=mpd_url, mpd_base_url=(mpd_url.rsplit('/', 1))[0])

                        if formats_dash:
                            self._sort_formats(formats_dash)
                            formats.extend(formats_dash)
                    
                    elif _type == "hls":

                        m3u8_url = mpd_url.replace('manifest.mpd', 'playlist.m3u8')
                        m3u8_doc = try_get(self._send_request(m3u8_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace'))
                        if m3u8_doc:                                                                
                            formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                                m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")
                            if formats_m3u8:
                                self._sort_formats(formats_m3u8)
                                formats.extend(formats_m3u8)

                    elif _type == "ism":

                        ism_url = mpd_url.replace('manifest.mpd', 'Manifest')
                        _doc = try_get(self._send_request(ism_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace'))
                        if _doc:       
                            ism_doc = self._parse_xml(_doc, None)                                                         
                            formats_ism, _ = self._parse_ism_formats_and_subtitles(ism_doc, ism_url)
                            if formats_ism:
                                self._sort_formats(formats_ism)
                                formats.extend(formats_ism) 


                except Exception as e:
                    logger.exception(f"[{_type}] {repr(e)}")


            if formats:
                self._sort_formats(formats)
            
                _entry = {
                    "id": str(scene_id),
                    "title": _title,
                    "formats": formats,
                    "ext": "mp4",
                    "webpage_url": url,
                    "extractor_key": 'NakedSwordScene',
                    "extractor": 'nakedswordscene'
                }
            
                self.logger_debug(f"{premsg}: OK got entry")
                return _entry
            
        except ExtractorError as e:
            logger.exception(repr(e))
            raise
        except Exception as e:
            logger.exception(repr(e))
            raise ExtractorError(f'{premsg}: error - {repr(e)}')
        finally:
            if rem:
                self._logout(driver=driver)
                self.rm_driver(driver)

    def _is_logged(self, driver=None):
        
        self._send_request(self._SITE_URL, driver=driver)
        self.wait_until(driver, 2)
        el_ua = try_get(self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CSS_SELECTOR, "div.UserAction"))), lambda x: x[1].text)
        logged_ok = (el_ua == "MY ACCOUNT")

        self.to_screen(f"[is_logged] {logged_ok}")
        return logged_ok
        
    def _login(self, driver=None):
        
        rem = False
        if not driver:
            driver = self.get_driver(devtools=True)
            rem = True
        try:
            
            if not self._is_logged(driver=driver):

                self.report_login()
                username, password = self._get_login_info()
                if not username or not password:
                    self.raise_login_required(
                        'A valid %s account is needed to access this media.'
                        % self._NETRC_MACHINE)        
                
                ua_click = try_get(self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CSS_SELECTOR, "div.UserAction"))), lambda x: {'ok': x[1].click()} if x else None)
                if not ua_click: raise ExtractorError("couldnt rollout login option")
                el_username = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input.Input")))
                el_psswd = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input.Input.Password")))
                el_submit = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "button.SignInButton")))
                self.wait_until(driver, 0.1)
                el_username.send_keys(username)
                self.wait_until(driver, 0.1)
                el_psswd.send_keys(password)
                self.wait_until(driver, 0.1)                
                el_submit.click() 
                self.wait_until(driver, 1)
                self._send_request(self._SITE_URL, driver=driver)
                self.wait_until(driver, 1)               
                el_ua = try_get(self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CSS_SELECTOR, "div.UserAction"))), lambda x: x[1].text)
                if el_ua == "MY ACCOUNT":
                    self.to_screen(f"[login][{self._proxy}] Login OK")
                    return True
                else: raise ExtractorError("login nok")
            
            else:
                self.to_screen(f"[login] Already logged")
                
                return True
        except Exception as e:
            logger.exception(repr(e))
            if rem: self.rm_driver(driver)
            raise

    def _real_initialize(self):

        try:
            with NakedSwordBaseIE._LOCK:

                super()._real_initialize()

                if self._downloader.params.get('proxy'):
                    
                    self._proxy = try_get(self._downloader.params.get('proxy'), lambda x: x.split(':')[-1])
                    self.to_screen(f"proxy: [{self._proxy}]")
                    if not NakedSwordBaseIE._NLOCKS.get(self._proxy):
                        NakedSwordBaseIE._NLOCKS.update({self._proxy: Lock()})

                else: self._proxy = "noproxy"


        except Exception as e:
            logger.exception(repr(e))


class NakedSwordSceneIE(NakedSwordBaseIE):
    IE_NAME = 'nakedswordscene'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<movieid>[\d]+)/(?P<title>[^\/]+)/scene/(?P<id>[\d]+)/?$"

    def _get_video_entry(self, url, index=1, **kwargs):
        
        driver = self._get_driver_logged()
        _type = kwargs.get('_type', 'all')

        try:

            self._send_request(url, driver=driver)
            self.wait_until(driver, 60, scroll())
            el_scenes = self.wait_until(driver, 60, getScenes(self.to_screen))
            details = try_get(self.scan_for_json(driver, "details"), lambda x: x.get('data'))
            if not el_scenes:
                return self._get_entry(url, driver=driver, details=details, _type=_type, index=1)
            else:
                _link_click = try_get(el_scenes[index - 1].find_element(By.TAG_NAME, 'a'), lambda x: {'url': x.get_attribute('href'), 'ok': x.click()} if x else None)
                if not _link_click: raise ExtractorError("couldnt click scene")
                return self._get_entry(_link_click.get('url'), driver=driver, details=details, _type=_type, index=index)
        except Exception as e:
            self.report_warning(f"[get_video_entry] {url} - error - {repr(e)}")
            raise
        finally:
            self._logout(driver=driver)
            self.rm_driver(driver)

    def _real_extract(self, url):

        try:            
            self.report_extraction(url)
            index = int(self._match_id(url))
            return self._get_video_entry(url.split('/scene/')[0], index=index, _type='all')
 
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')

            
class NakedSwordMovieIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:movie:playlist'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<id>[\d]+)/(?P<title>[a-zA-Z\d_-]+)/?$"
    _MOVIES_URL = "https://www.nakedsword.com/movies/"


    def _get_playlist_movie(self, url, **kwargs):


        driver = self._get_driver_logged()
        _type = kwargs.get('_type', 'all')
        
        try:
            self._send_request(url, driver=driver)

            self.wait_until(driver, 60, scroll())
            el_scenes = self.wait_until(driver, 60, getScenes(self.to_screen))

            details = try_get(self.scan_for_json(driver, "details"), lambda x: x.get('data'))
            if details:
                playlist_id = str(details.get('id'))
                pl_title = details.get('title')
            else:
                playlist_id, pl_title = try_get(re.search(NakedSwordMovieIE._VALID_URL, url), lambda x: x.group('id', 'title'))

            entries = []
            
            if not el_scenes:
                _entry = self._get_entry(url, driver=driver, details=details, _type=_type, index=1)
                if _entry: entries.append(_entry)
            else:
                
                num_scenes = len(el_scenes)
                for i in range(num_scenes):
                    try:                
                        el = driver.find_elements(By.CLASS_NAME, "Scene")
                        _link_click = try_get(el[i].find_element(By.TAG_NAME, 'a'), lambda x: {'url': x.get_attribute('href'), 'ok': x.click()} if x else None)
                        if not _link_click: raise ExtractorError("couldnt click scene")
                        _entry = self._get_entry(_link_click.get('url'), driver=driver, details=details, _type=_type, index=i+1)
                        if _entry: entries.append(_entry)

                    except Exception as e:
                        self.report_warning(f"[get_playlist_movie][{url}] scene {i+1} - error - {repr(e)}")


            if entries:
                self.logger_debug(f"[get_entries_list][{url}] OK got entries list")
                return self.playlist_result(entries, playlist_id=playlist_id, playlist_title=sanitize_filename(pl_title, True))
            else:        
                raise ExtractorError("no entries")
        
        except Exception as e:
            self.report_warning(f"[get_playlist_movie] {url} - error - {repr(e)}")
            raise
        finally:
            self._logout(driver=driver)
            self.rm_driver(driver)

 
    def _real_extract(self, url):

        try:            
            self.report_extraction(url)            
            return self._get_playlist_movie(url, _type="all")
 
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')


class NakedSwordMostWatchedIE(NakedSwordBaseIE):
    IE_NAME = "nakedsword:mostwatched:playlist"
    _VALID_URL = r'https?://(?:www\.)?nakedsword.com/most-watched(\?pages=(?P<pages>\d+))?'
    _MOST_WATCHED = 'https://www.nakedsword.com/most-watched?content=Scenes&page='
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):      
       
        pages = try_get(re.search(self._VALID_URL, url), lambda x: x.group('pages')) or "1"
        entries = []
        list_pages = [(i, f"{self._MOST_WATCHED}{i}") for i in range(1, int(pages) + 1)]
        with ThreadPoolExecutor(thread_name_prefix="nakedsword", max_workers=10) as ex:            
            futures = {ex.submit(self.get_entries_scenes, el[1], el[0]): f"page={el[0]}"  for el in list_pages}
        
        for fut in futures:
            try:
                _res = fut.result()
                if _res:
                    entries += _res
                else: raise ExtractorError("no entries")
            except Exception as e:
                self.report_warning(f'[{url}][{futures[fut]}] {repr(e)}')  
        
        if entries:
            return {
                '_type': 'playlist',
                'id': f'{datetime.now().strftime("%Y%m%d")}',
                'title': f"Scenes",
                'entries': entries,
            }
        
        else: 
            raise ExtractorError("no entries")

class NakedSwordStarsStudiosIE(NakedSwordBaseIE):
    IE_NAME = "nakedsword:starsstudios:playlist"
    _VALID_URL = r'https?://(?:www\.)?nakedsword.com/(?P<typepl>(?:stars|studios))/(?P<id>[\d]+)/(?P<name>[a-zA-Z\d_-]+)(/\?(?P<query>.+))?'
    _MOST_WATCHED = "?content=Scenes&sort=MostWatched&page="
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):     
       
        data = try_get(re.search(self._VALID_URL, url), lambda x: x.groupdict())
        query = data.get('query')        
        if query:
            params = { el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
        else:
            params = {}
     
        base_url = url.split("?")[0]
        base_url_search = f'{base_url}{self._MOST_WATCHED}'
        last_page = self._get_last_page(base_url_search)

        npages = params.get('pages', '1')

        if npages == 'all': 
            npages = last_page
        elif npages.isdecimal():
            _npages = int(npages)
            if _npages > last_page:
                npages = last_page
            else:
                npages = _npages or 1

      
        filter_by = params.get('filter_by')
        if filter_by:
            tokens_filter = filter_by.split(',')
            if tokens_filter[0] == 'not':
                func = lambda x: not(re.search(r'%s' % tokens_filter[1].replace(' ','-'), x, re.IGNORECASE) != None)
            else:
                func = lambda x: re.search(r'%s' % tokens_filter[0].replace(' ','-'), x, re.IGNORECASE)
        else: func = None    
                
        entries = []

        with ThreadPoolExecutor(max_workers=10) as ex:
            
            futures = {ex.submit(self.get_entries_scenes, f"{base_url}{self._MOST_WATCHED}{i}", i, func) : f"page={i}" for i in range(1, npages + 1)}

        for fut in futures:
            try:
                _res = fut.result()
                if _res:
                    entries += _res
                else: raise ExtractorError("no entries")
            except Exception as e:
                self.report_warning(f'[{url}][{futures[fut]}] {repr(e)}')  
                #raise ExtractorError(repr(e))
        
        if entries:
            return {
                '_type': 'playlist',
                'id': data['id'],
                'title': f"MWScenes{''.join(w.capitalize() for w in data['name'].split('-'))}",
                'entries': entries,
            }
        else: raise ExtractorError("no entries")
        
class NakedSwordPlaylistIE(NakedSwordBaseIE):
    IE_NAME = "nakedsword:playlist"
    _VALID_URL = r'https?://(?:www\.)?nakedsword.com/(?P<id>[^?&]+)$'
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):      
       

        entries = []

        webpage = try_get(self._send_request(url), lambda x: re.sub('[\t\n]','', html.unescape(x.text)) if x else None)
        if webpage: 

            if 'SCENE LIST GRID WRAPPER' in webpage:
                
                entries = self.get_entries_scenes(url)
                
            else:
                
                entries = self.get_entries_movies(url)
                       
        if entries:
            return {
                '_type': 'playlist',
                'id': "NakedSword_Playlist",
                'title': sanitize_filename(self._match_id(url), restricted=True).upper(),
                'entries': entries,
            }
        
        else: raise ExtractorError("No entries")
        
class NakedSwordSearchIE(NakedSwordBaseIE):
    IE_NAME = "nakedsword:searchresult:playlist"
    _VALID_URL = r'https?://(?:www\.)?nakedsword.com/search\?(?P<query>.+)'
    _SEARCH_SITE_URL = 'https://vod.nakedsword.com'
    
    _CATEGORIES = {
        'alt': '687',
        'amateur': '501',
        'anal': '582',
        'asian': '502',
        'auto-fellatio': '621',
        'bareback': '567',
        'bdsm': '511',
        'bear': '561',
        'big-dick': '515',
        'bisexual': '516',
        'black': '503',
        'blowjob': '510',
        'blue-collar': '683',
        'body-builders': '574',
        'boyfriends': '648',
        'brazilian': '651',
        'british': '693',
        'bubble-butt': '653',
        'chubs': '571',
        'classic': '556',
        'compilation': '594',
        'cops': '581',
        'cowboy': '563',
        'cream-pies': '672',
        'creator-content': '710',
        'cumshot': '512',
        'czech': '647',
        'daddy': '681',
        'dildo': '584',
        'double-penetration': '673',
        'euro': '521',
        'exclusive': '709',
        'extreme-penetration': '611',
        'feature': '523',
        'fetish': '505',
        'foot': '524',
        'fratboys': '579',
        'french-speaking': '695',
        'gangbang': '506',
        'gender-queer': '674',
        'gloryhole': '624',
        'hardcore': '596',
        'hidden-camera': '592',
        'high-definition': '685',
        'instructional': '554',
        'international': '559',
        'interracial': '528',
        'japanese-unmosaic': '664',
        'jocks': '562',
        'latin': '514',
        'leather': '555',
        'massage': '686',
        'masturbation': '532',
        'mature': '536',
        'military': '593',
        'model': '646',
        'muscles': '557',
        'new-release': '513',
        'orgies': '537',
        'outdoors': '580',
        'parody': '684',
        'pigs': '649',
        'pissing': '540',
        'pre-condom': '661',
        'prison-sex': '688',
        'punishment': '620',
        'russian': '583',
        'safe-sex': '657',
        'sale-downloads': '698',
        'sale-rentals': '700',
        'sale-streaming': '703',
        'shaving': '542',
        'softcore': '585',
        'spanish-speaking': '544',
        'spanking': '545',
        'str8-bait': '606',
        'straight-for-gay': '659',
        'taboo': '702',
        'threeway': '644',
        'twink': '566',
        'ultra-high-definition': '707',
        'uncut': '604',
        'uniform': '558',
        'vintage': '569',
        'voyeur': '551',
        'vr-3d-360': '706',
        'white-collar': '682',
        'wrestling': '608'}
    _SETTINGS = {
        'abandonedbuilding': '48146',
        'airplane': '48001',
        'alley': '48002',
        'altar': '48003',
        'arcade': '48098',
        'arena': '48004',
        'artgallery': '48121',
        'athleticcourt': '48125',
        'attic': '48148',
        'balcony': '48005',
        'balletstudio': '48006',
        'bar': '48007',
        'barbershop-salon': '48135',
        'barn': '48008',
        'barracks': '48122',
        'basement': '48009',
        'bathroom': '48010',
        'bathtub': '48011',
        'beach': '48012',
        'bedroom': '48013',
        'boat': '48014',
        'bowlingalley': '48015',
        'boxingring': '48016',
        'bus': '48017',
        'business': '48144',
        'cabin': '48018',
        'cafeteria': '48147',
        'cage': '48019',
        'casino': '48021',
        'cave': '48139',
        'church': '48022',
        'circus': '48100',
        'classroom': '48023',
        'closet': '48024',
        'compilation': '48132',
        'conferenceroom': '48094',
        'constructionsite': '48112',
        'conventioncenter': '48123',
        'couch': '48110',
        'courtroom': '48025',
        'courtyard': '48145',
        'crypt': '48026',
        'diningroom': '48027',
        'doctoroffice': '48028',
        'dojo': '48029',
        'dormroom': '48105',
        'dressingroom': '48030',
        'dungeon': '48031',
        'elevator': '48032',
        'fantasy': '48113',
        'farm': '48114',
        'firestation': '48033',
        'forest': '48108',
        'funeralhome': '48142',
        'gameroom': '48128',
        'garage': '48034',
        'gazebo': '48107',
        'genericroom': '48035',
        'gloryhole': '48136',
        'graveyard': '48117',
        'gym': '48036',
        'hairsalon': '48037',
        'hallway': '48038',
        'hangar': '48131',
        'hardwarestore': '48099',
        'helicopter': '48039',
        'hospitalroom': '48040',
        'hotelroom': '48041',
        'icecreamparlor': '48109',
        'invehicle': '48020',
        'interrogationroom': '48134',
        'jacuzzi': '48042',
        'jailcell': '48043',
        'junkyard': '48111',
        'kitchen': '48044',
        'laboratory': '48045',
        'lake': '48140',
        'laundryroom': '48046',
        'library': '48106',
        'limousine': '48047',
        'liquorstore': '48091',
        'livingroom': '48048',
        'lobby': '48049',
        'lockerroom': '48050',
        'lounge': '48051',
        'massageparlor': '48052',
        'militarybase': '48129',
        'motorhome': '48053',
        'movieset': '48054',
        'nightclub': '48141',
        'office': '48055',
        'onvehicle': '48126',
        'outdoors': '48056',
        'paddedcell': '48057',
        'parkinglot': '48095',
        'patio': '48127',
        'photostudio': '48058',
        'playground': '48104',
        'pool': '48130',
        'poolhall': '48059',
        'pooltable': '48138',
        'poolside': '48060',
        'porch': '48103',
        'pornshop': '48101',
        'publicplace': '48061',
        'radiostudio': '48062',
        'restaurant': '48063',
        'rooftop': '48064',
        'sauna-steamroom': '48065',
        'school': '48066',
        'securityoffice': '48124',
        'sewer': '48096',
        'sexclub': '48067',
        'sexswing': '48115',
        'shed': '48068',
        'shed-shack': '48133',
        'shipcabin': '48069',
        'shootingrange': '48137',
        'shower': '48070',
        'spaceship': '48071',
        'stable': '48072',
        'stage': '48073',
        'staircase': '48102',
        'stairs': '48074',
        'store': '48075',
        'stripclub': '48076',
        'swimmingpool': '48077',
        'tattooparlor': '48078',
        'televisionstudio': '48119',
        'tenniscourt': '48079',
        'tent': '48080',
        'theater': '48081',
        'trailer': '48082',
        'train': '48083',
        'trainstation': '48084',
        'underwater': '48085',
        'van': '48116',
        'waitingroom': '48120',
        'warehouse': '48086',
        'waterfall': '48087',
        'whorehouse': '48088',
        'winecellar': '48089',
        'woods-jungle': '48090',
        'workshop': '48118'}
    _SEX_ACTS = {
        '3-way': '32001',
        'analdaisychain': '32002',
        'analsex': '32005',
        'asstomouth': '32006',
        'asstoothermouth': '32007',
        'blowjob': '32010',
        'bondage': '32012',
        'bootlicking': '32025',
        'breastplay': '32125',
        'bukkake': '32015',
        'casting': '32153',
        'choking': '32017',
        'circlejerk': '32140',
        'clubbing': '32018',
        'cock&ballstorture': '32064',
        'collar&lead-leash': '32026',
        'creampie': '32019',
        'cumswallowing': '32021',
        'cumswap': '32023',
        'deepthroating': '32024',
        'docking': '32102',
        'domination': '32112',
        'doublepenetration': '32028',
        'enema': '32107',
        'exhibitionism': '32108',
        'extremepenetration': '32158',
        'faceslapping': '32034',
        'facesitting': '32035',
        'felching': '32037',
        'fetish': '32138',
        'fingercuffing-anal': '32038',
        'fingercuffing-dp': '32039',
        'fingercuffing-vaginal': '32040',
        'fishhooking': '32101',
        'fisting': '32110',
        'fondling': '32145',
        'foodplay': '32120',
        'footjob': '32044',
        'footplay': '32041',
        'gagging': '32045',
        'gangbang': '32047',
        'gapes': '32048',
        'girlongirlaction': '32049',
        'grinding': '32050',
        'grooming': '32131',
        'hairpulling': '32051',
        'handjob': '32052',
        'humiliation': '32123',
        'jousting': '32054',
        'lactation': '32111',
        'maleonmaleaction': '32149',
        'massage': '32104',
        'masturbation': '32055',
        'modeling': '32105',
        'multiplepops': '32056',
        'nippleplay': '32156',
        'oralsex': '32011',
        'orgy': '32063',
        'pissing': '32066',
        'ponyplay': '32124',
        'punishment': '32067',
        'reversegangbang': '32069',
        'rimjob': '32070',
        'rustytrombone': '32071',
        'self-bondage': '32113',
        'self-fucking': '32143',
        'self-torture': '32154',
        'shaving': '32072',
        'showering-bathing': '32116',
        'sloppyseconds,anal': '32073',
        'smoking': '32118',
        'snowballing': '32075',
        'spanking-paddling': '32076',
        'spitting': '32078',
        'squirting': '32079',
        'straight-to-anal': '32080',
        'strap-on': '32081',
        'stripping': '32126',
        'teabagging': '32083',
        'throatfucking': '32139',
        'tickling': '32084',
        'tittiefucking': '32086',
        'toesucking': '32087',
        'torture': '32115',
        'toyplay-anal': '32089',
        'toyplay-cockandball': '32144',
        'toyplay-doubleanal': '32090',
        'toyplay-doublepenetration': '32091',
        'toyplay-doublevaginal': '32092',
        'toyplay-oral': '32088',
        'toyplay-vaginal': '32093',
        'trampling': '32122',
        'urethraplay': '32142',
        'vaginalsex': '32097',
        'vomiting': '32098',
        'voyeurism': '32109',
        'wet-messy': '32132',
        'whipping': '32099',
        'worship': '32114',
        'wrestling': '32100'}
    _SORTBY = {'scenes': ['Popularity', 'Trending', 'Newest', 'Relevance'], 'movies': ['MostWatched', 'Trending', 'Newest', 'Released', 'Relevance']}
    _CONTENTS = ['movies', 'scenes']    
    _PARAMS = {'movies': ['content', 'pages', 'tag', 'star', 'studio', 'videoquality', 'director', 'releasedate'],
               'scenes': ['content', 'pages', 'tag', 'star', 'studio', 'videoquality', 'setting', 'sexact', 'position']}
    _STUDIOS = {}
    _STARS = {}
    
    @staticmethod
    def get_info_conf():
        with open("/Users/antoniotorres/Projects/common/logs/nakedsword_conf.json", 'r') as file:
            conf = json.load(file)
        return conf
    
    @staticmethod
    def upt_info_conf():
        conf_str = '{"studios": ' + json.dumps(NakedSwordSearchIE._STUDIOS) + ', ' + '"stars": ' + json.dumps(NakedSwordSearchIE._STARS) + '}' 
        with open("/Users/antoniotorres/Projects/common/logs/nakedsword_conf.json", 'w') as file:
            file.write(conf_str)
 
    def get_starid(self, starname):
         
        query = starname.replace(' ', '+')
        url = f"https://vod-classic.nakedsword.com/dispatcher/fts?targetSearchMode=basic&isAdvancedSearch=false&isFlushAdvancedSearchCriteria=false&userQuery={query}d&sortType=Relevance&theaterId=22299&genreId=102&locale=en"
        
        driver = self.get_driver()
        
        try:
            
            self._send_request(url, driver=driver)
            
            elstar = self.wait_until(driver, 60, ec.presence_of_element_located((By.CLASS_NAME, "exactMatchStar")))
            if elstar:
                ela = try_get(elstar.find_elements(By.TAG_NAME, "a"), lambda x: x[0])
                if ela:
                    starid = try_get(re.findall(r'starId=(\d+)', ela.get_attribute('href')), lambda x: x[0])
                    if starid: 
                        NakedSwordSearchIE._STARS[starname.lower().replace(' ', '').replace("/", "-")] = starid
                        NakedSwordSearchIE._STARS = {_key: NakedSwordSearchIE._STARS[_key] for _key in sorted(NakedSwordSearchIE._STARS)}
                        self.logger_debug(NakedSwordSearchIE._STARS)
                        NakedSwordSearchIE.upt_info_conf()
                        return starid
        except Exception as e:
            self.report_warning(f'[get_starid] {repr(e)}')
        finally:
            self.rm_driver(driver)        
    
    def get_studioid(self, studioname):
         
        query = studioname.replace(' ', '+')
        url = f"https://vod-classic.nakedsword.com/dispatcher/fts?targetSearchMode=basic&isAdvancedSearch=false&isFlushAdvancedSearchCriteria=false&userQuery={query}&sortType=Relevance&theaterId=22299&genreId=102&locale=en"
        
        driver = self.get_driver()
        
        try:
            
            self._send_request(url, driver=driver)
            
            class getstudioid():
                def __call__(self,driver):
                    elstudio = driver.find_elements(By.CLASS_NAME, "exactMatchStudio")
                    if not elstudio:
                        elres = driver.find_element(By.CLASS_NAME, "searchDetails")
                        return "NotFound"
                    else:
                        if (ela:=try_get(elstudio[0].find_elements(By.TAG_NAME, "a"), lambda x: x[0])):
                            if (studioid:=try_get(re.findall(r'studioId=(\d+)', ela.get_attribute('href')), lambda x: x[0])):
                                return studioid
                        return "NotFound"
                        
                            
            
            
            # elstudio = self.wait_until(driver, 60, ec.presence_of_element_located((By.CLASS_NAME, "exactMatchStudio")))
            # if elstudio:
            #     ela = try_get(elstudio.find_elements(By.TAG_NAME, "a"), lambda x: x[0])
            #     if ela:
            #         studioid = try_get(re.findall(r'studioId=(\d+)', ela.get_attribute('href')), lambda x: x[0])
            #         if studioid: 
            #             NakedSwordSearchIE._STUDIOS[studioname.lower().replace(' ', '').replace('-', '')] = studioid
            #             NakedSwordSearchIE._STUDIOS = {_key: NakedSwordSearchIE._STUDIOS[_key] for _key in sorted(NakedSwordSearchIE._STUDIOS)}
            #             self.to_screen(NakedSwordSearchIE._STUDIOS)
            #             NakedSwordSearchIE.upt_info_conf()
            #             return studioid
            
            studioid = self.wait_until(driver, 60, getstudioid())
            if studioid and studioid != 'NotFound':
                NakedSwordSearchIE._STUDIOS[studioname.lower().replace(' ', '').replace('-', '')] = studioid
                NakedSwordSearchIE._STUDIOS = {_key: NakedSwordSearchIE._STUDIOS[_key] for _key in sorted(NakedSwordSearchIE._STUDIOS)}
                self.logger_debug(NakedSwordSearchIE._STUDIOS)
                NakedSwordSearchIE.upt_info_conf()                
                return studioid
                
        except Exception as e:
            self.report_warning(f'[get_studioid] {repr(e)}')
        finally:
            self.rm_driver(driver)

    def get_scenes_ns(self, urls):
        

        def _get_scenes_url(j):
            _driver = self.get_driver()
                        
            try:                
                while True:
                    _pos, _uq = self._urlqueriesqueue.get()
                    if _uq == "KILL": break
                    self.logger_debug(f'[get_scenes][{j}][{_pos}/{self._num}] {_uq}')
                    try:
                        self._send_request(_uq[0], driver=_driver)
                        el_title = self.wait_until(_driver, 2, ec.presence_of_element_located((By.TAG_NAME, "title")))
                        if not el_title: continue
                        elscenes = self.wait_until(_driver, 2, ec.presence_of_all_elements_located((By.CLASS_NAME, "dts-panel ")))
                        if not elscenes: continue
                        _list_scenes_urls = []
                        for el in elscenes:

                            elinfo = try_get(el.find_elements(By.TAG_NAME, "a"), lambda x: x[0])
                            if not elinfo: continue
                            num_scene = elinfo.text.split(" ")[-1]
                            movie = try_get(re.findall(r'gay/movies/(.+)#', elinfo.get_attribute('href')), lambda x: x[0])
                            if movie and num_scene:
                                _urlscene = f"https://www.nakedsword.com/movies/{movie}/scene/{num_scene}" 
                                _list_scenes_urls.append((_urlscene, _uq[1], _uq[2]))
                        
                        if not _list_scenes_urls: continue
                        _nw = min((_size:=len(_list_scenes_urls)), 12)
                        
                        def _check_url(_urlsc, _n):
                            try:
                                

                                res = try_get(self._send_request(_urlsc[0]), lambda x: html.unescape(x.text))
                                if res:  
                                    self.logger_debug(f'[get_scenes][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] {_urlsc[0]} OK is available')
                                    self._urlscenesqueue.put_nowait((_urlsc[0], _urlsc[1], _urlsc[2], _n))
                                else:
                                    self.logger_debug(f'[get_scenes][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] {_urlsc[0]} ERROR not available')
                               
                        
                            except Exception as e:
                                self.logger_debug(f'[get_scenes][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] {_urlsc[0]} ERROR {repr(e)}')
                        
                        with ThreadPoolExecutor(max_workers=_nw) as _ex:               
                            for _k, _elurl in enumerate(_list_scenes_urls):
                                _ex.submit(_check_url, _elurl, _k+1)
                    
                    except Exception as e:
                        lines = traceback.format_exception(*sys.exc_info())
                        self.logger_debug(f"[get_scenes][{j}][{_pos}/{self._num}]  {repr(e)}\n{'!!'.join(lines)}")
                
            
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.logger_debug(f"[get_scenes][{j}] {repr(e)}\n{'!!'.join(lines)}")
            finally:
                self.rm_driver(_driver)
                self.logger_debug(f'[get_scenes][{j}] bye') 

        try:
            
            self._num = len(urls)
            self._urlqueriesqueue = Queue()
            self._urlscenesqueue = Queue()
            for _i, _urlquery in enumerate(urls):
                self._urlqueriesqueue.put_nowait((_i+1, _urlquery))
            n_workers = min(self._num, 5)
            for _ in range(n_workers):
                self._urlqueriesqueue.put_nowait((-1, "KILL"))
            with ThreadPoolExecutor(max_workers=n_workers) as exe:
                for _j in range(n_workers):
                    exe.submit(_get_scenes_url, _j)
                
            return list(self._urlscenesqueue.queue)
        except ExtractorError:
            raise
        except Exception as e:
            self.logger_debug(f'[get_scenes] {repr(e)}')
            raise ExtractorError(f"{repr(e)}")

    def get_movies_ns(self, urls):

        def _get_movies_url(j):
            _driver = self.get_driver()
                        
            try:                
                while True:
                    _pos, _uq = self._urlqueriesqueue.get()
                    if _uq == "KILL": break
                    self.logger_debug(f'[get_movies][{j}][{_pos}/{self._num}] {_uq}')
                    try:
                        self._send_request(_uq[0], driver=_driver)
                        el_title = self.wait_until(_driver, 2, ec.presence_of_element_located((By.TAG_NAME, "title")))
                        if not el_title: continue
                        elmovies = self.wait_until(_driver, 2, ec.presence_of_all_elements_located((By.CLASS_NAME, "dts-image-overlay-container")))
                        if not elmovies: continue
                        _list_movies_urls = []
                        for el in elmovies:

                            elinfo = try_get(el.find_elements(By.TAG_NAME, "a"), lambda x: x[0])
                            if not elinfo: continue
                            movie = try_get(re.findall(r'gay/movies/(.+)', elinfo.get_attribute('href')), lambda x: x[0])
                            if movie:
                                _urlmovie = f"https://www.nakedsword.com/movies/{movie}"
                                 
                                _list_movies_urls.append((_urlmovie, _uq[1], _uq[2]))
                        
                        if not _list_movies_urls: continue
                        _nw = min((_size:=len(_list_movies_urls)), 5)
                        
                        def _check_url(_urlmv, _n):
                            try:
                                
                                res = try_get(self._send_request(_urlmv[0]), lambda x: html.unescape(x.text))                                
                                if res and not 'NakedSword.com | Untitled Page' in res: 
                                    self.logger_debug(f'[get_movies][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] {_urlmv[0]} OK is available')
                                    self._urlmoviesqueue.put_nowait((_urlmv[0], _urlmv[1], _urlmv[2], _n))
                                else:
                                    self.logger_debug(f'[get_movies][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] {_urlmv[0]} ERROR not available')
                                    
                        
                            except Exception as e:
                                self.logger_debug(f'[get_movies][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] {_urlmv[0]} ERROR {repr(e)}')
                        
                        with ThreadPoolExecutor(max_workers=_nw) as _ex:               
                            futures = [_ex.submit(_check_url, _elurl, _k+1) for _k, _elurl in enumerate(_list_movies_urls)]
                    
                    except Exception as e:
                        lines = traceback.format_exception(*sys.exc_info())
                        self.logger_debug(f"[get_movies][{j}][{_pos}/{self._num}]  {repr(e)}\n{'!!'.join(lines)}")
                
            
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.logger_debug(f"[get_movies][{j}] {repr(e)}\n{'!!'.join(lines)}")
            finally:
                self.rm_driver(_driver)
                self.logger_debug(f'[get_movies][{j}] bye') 

        try:
            
            self._num = len(urls)
            self._urlqueriesqueue = Queue()
            self._urlmoviesqueue = Queue()
            for _i, _urlquery in enumerate(urls):
                self._urlqueriesqueue.put_nowait((_i+1, _urlquery))
            n_workers = min(self._num, 5)
            for _ in range(n_workers):
                self._urlqueriesqueue.put_nowait((-1, "KILL"))
            with ThreadPoolExecutor(max_workers=n_workers) as exe:
                for _j in range(n_workers):
                    exe.submit(_get_movies_url, _j)
                
            return list(self._urlmoviesqueue.queue)
        except ExtractorError:
            raise
        except Exception as e:
            self.logger_debug(f'[get_movies] {repr(e)}')
            raise ExtractorError(f"{repr(e)}")

    def _real_initialize(self):
        super()._real_initialize()
        conf = NakedSwordSearchIE.get_info_conf()
        NakedSwordSearchIE._STUDIOS = conf['studios']
        NakedSwordSearchIE._STARS = conf['stars']
    
    def _real_extract(self, url):

        query = re.search(self._VALID_URL, url).group('query')
        
        params = { el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
        
        if (_s:=params.get('s', None)):
            stext = f"sysQuery={_s}&"
        else:
            stext = "sysQuery=&"
            

        content = params.get('content', 'scenes')
        
        
        if (_sortby:=params.get('sort')):
            _sortby = _sortby.replace(' ','').lower()
            if _sortby == 'mostwatched':
                if content == 'scenes': _sby = 'Popularity'
                else: _sby = 'MostWatched'
            elif _sortby == 'released':
                if content == 'scenes': _sby = 'Newest'
                else: _sby = 'Released'                
            elif _sortby in ['trending', 'newest', 'relevance']: 
                _sby = _sortby.capitalize()
            else:
                _sby = 'Relevance'
            criteria = {'sort': _sby}
        else:
            #criteria_list = [{'sort': _sort} for _sort in self._SORTBY[content]]
            criteria = {'sort': 'Relevance'}
            
        if (_studio:=params.get('studio')):
            if not (_studioid:=NakedSwordSearchIE._STUDIOS.get(_studio.lower().replace(' ', '').replace('-', ''))):
                _studioid = self.get_studioid(_studio)
        if (_star:=params.get('star')):
            if not (_starid:=NakedSwordSearchIE._STAR.get(_star.lower().replace(' ', '').replace('/', '-'))):
                _starid = self.get_starid(_star)
        if (_tag:=params.get('tag')):
            _tagid = [int(_id) for el in _tag.split(',') if (_id:=NakedSwordSearchIE._CATEGORIES.get(el))]
        if (_setting:=params.get('setting')):
            _settingid = [int(_id) for el in _setting.split(',') if (_id:=NakedSwordSearchIE._SETTINGS.get(el))]
        if (_sexact:=params.get('sexact')):
            _sexactid = [int(_id) for el in _sexact.split(',') if (_id:=NakedSwordSearchIE._SEX_ACTS.get(el))]
        
        if _tag and _tagid: criteria.update({'tagFilters': _tagid})
        if _setting and _settingid and content == 'scenes': criteria.update({'settingFilters': _settingid})
        if _sexact and _sexactid and content == 'scenes': criteria.update({'sexActFilters': _sexactid})
        if _studio and _studioid: criteria.update({'studioFilters': [int(_studioid)]})
        if _star and _starid: criteria.update({'starFilters': [int(_starid)]})
            
        
        criteria_str = json.dumps(criteria).replace(" ", "")       
        
        url_query_base = f'https://vod.nakedsword.com/gay/search/{content}/page/1?{stext}criteria={quote(criteria_str)}&viewMode=List'
        pages = int(params.get('pages', '5'))        
        maxpages = min(try_get(self._send_request(url_query_base), lambda x: try_get(re.findall(r'<a class="dts-paginator-tagging" href="/gay/search/(?:scenes|movies)/page/(\d+)\?', x.text), lambda y: int(y[-1]) if y else 1)), pages)
        

        url_query = [(f'https://vod.nakedsword.com/gay/search/{content}/page/{page+1}?{stext}criteria={quote(criteria_str)}&viewMode=List', criteria['sort'], page+1) for page in range(maxpages)]
        self.logger_debug(f"url query list[{len(url_query)}]: \n{url_query}")
        url_query_str = '\n'.join([f'{unquote(_el[0])}, {_el[0].split("?")[-1]}' for _el in url_query])
        self.logger_debug(f"url query list[{len(url_query)}]: \n{url_query_str}")
        

        try:
            entries = []
            if content == 'scenes':
                list_res = self.get_scenes_ns(url_query)
                self.logger_debug(list_res)
                if list_res:
                    list_res_sorted = sorted(list_res, key=lambda x: (NakedSwordSearchIE._SORTBY['scenes'].index(x[1]),x[2], x[3]))
                    self.logger_debug(list_res_sorted)
                    list_res_final = []
                    for el in list_res_sorted:
                        if el[0] not in list_res_final: list_res_final.append(el[0])
                    entries = [self.url_result(_urlscene, ie=NakedSwordSceneIE.ie_key()) for _urlscene in list_res_final]
                
            elif content == 'movies':
                #list_res = list(set(self.get_movies_ns(url_query)))
                list_res = self.get_movies_ns(url_query)
                self.logger_debug(list_res)
                if list_res:
                    list_res_sorted = sorted(list_res, key=lambda x: (NakedSwordSearchIE._SORTBY['movies'].index(x[1]),x[2], x[3]))
                    self.logger_debug(list_res_sorted)
                    list_res_final = []
                    for el in list_res_sorted:
                        if el[0] not in list_res_final: list_res_final.append(el[0])
                    entries = [self.url_result(_urlmovie, ie=NakedSwordMovieIE.ie_key()) for _urlmovie in list_res_final]
                
            if entries:
                return {
                    '_type': 'playlist',
                    'id': "NakedSword_Search_Playlist",
                    'title': "NakedSword_Search_Playlist",
                    'entries': entries,
                }
            
            else: raise ExtractorError("No entries")
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"error {repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f"{repr(e)}")

