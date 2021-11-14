# coding: utf-8

from __future__ import unicode_literals

import re

from .webdriver import SeleniumInfoExtractor
from ..utils import (
    ExtractorError,
    sanitize_filename,
    std_headers
)

from threading import Lock
import traceback
import sys

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import httpx


from collections import OrderedDict

from concurrent.futures import ThreadPoolExecutor
class NakedSwordBaseIE(SeleniumInfoExtractor):
    IE_NAME = 'nakedsword'
    IE_DESC = 'nakedsword'
    
    _SITE_URL = "https://nakedsword.com/"
    _LOGIN_URL = "https://nakedsword.com/signin"
    _LOGOUT_URL = "https://nakedsword.com/signout"
    _NETRC_MACHINE = 'nakedsword'

    def _headers_ordered(self, extra=None):
        _headers = OrderedDict()
        
        if not extra: extra = dict()
        
        for key in ["User-Agent", "Accept", "Accept-Language", "Accept-Encoding", "Content-Type", "X-Requested-With", "Origin", "Connection", "Referer", "Upgrade-Insecure-Requests"]:
        
            value = extra.get(key) if extra.get(key) else std_headers.get(key)
            if value:
                _headers[key.lower()] = value
      
        
        return _headers
    
    def islogged(self):
        page, urlh = self._download_webpage_handle(
            self._SITE_URL,
            None
        )
        return ("/signout" in page)
    
    def _login(self):
        
        self.report_login()
        username, password = self._get_login_info()
        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)            

        driver = self.get_driver()
        try:
            driver.get(self._SITE_URL)
            driver.get(self._LOGIN_URL)
            
            el_username = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#SignIn_login.SignInFormInput.SignInFormUsername")))
            el_psswd = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#SignIn_password.SignInFormInput.SignInFormPassword")))
            el_submit = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input.button.expanded.SignInBtnSubmit")))
            self.wait_until(driver, 2, ec.title_is("DUMMYFORWAIT"))
            el_username.send_keys(username)
            self.wait_until(driver, 2, ec.title_is("DUMMYFORWAIT"))
            el_psswd.send_keys(password)
            self.wait_until(driver, 2, ec.title_is("DUMMYFORWAIT"))
            el_submit.submit()
            self.wait_until(driver, 60, ec.url_changes(self._LOGIN_URL))
            if driver.current_url == "https://nakedsword.com/members":
                self.to_screen("Login OK")
                return driver.get_cookies()
            else: raise ExtractorError("login nok")
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(f"login nok: {repr(e)}")
        finally:
            self.rm_driver(driver)
                    

        
   
         
        
    def get_entries_scenes(self, url):
        
        entries = []
        webpage = self._download_webpage(url, None, "Downloading web page playlist", fatal=False)
        if webpage:  
                        
            videos_paths = re.findall(
                r"<div class='SRMainTitleDurationLink'><a href='/([^\']+)'>",
                webpage)     
            
            if videos_paths:
                
                for video in videos_paths:
                    _url = self._SITE_URL + video
                    res = NakedSwordSceneIE._get_info(_url)
                    if res:
                        _id = res.get('id')
                        _title = res.get('title')
                    entry = self.url_result(_url, ie=NakedSwordSceneIE.ie_key(), video_id=_id, video_title=_title)
                    entries.append(entry)
 
        return entries
    
    def get_entries_movies(self, url):
        
        entries = []
        webpage = self._download_webpage(url, None, "Downloading web page playlist", fatal=False)
        if webpage:  
                        
            videos_paths = re.findall(
                r"<div class='BoxResultsLink'><a href='/([^\']+)'>",
                webpage)     
            
            if videos_paths:
                
                for video in videos_paths:
                    _url = self._SITE_URL + video                    
                    entry = self.url_result(_url, ie=NakedSwordMovieIE.ie_key())
                    entries.append(entry)
 
        return entries
        
class NakedSwordSceneIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:scene'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<movieid>[\d]+)/(?P<title>[^\/]+)/scene/(?P<id>[\d]+)/?$"

    _LOCK = Lock()
    _COOKIES = {}
    
    @staticmethod
    def _get_info(url, _res=None):       
        
        if not _res:
            count = 0
            while count < 3:
                try:
                    _res = httpx.get(url)
                    if _res.status_code < 400:         
                        res = re.findall(r"class=\'M(?:i|y)MovieTitle\'[^\>]*\>([^\<]*)<[^\>]*>[^\w]+(Scene[^\<]*)\<", _res.text)
                        res2 = re.findall(r"\'SCENEID\'content\=\'([^\']+)\'", _res.text.replace(" ",""))
                        if res and res2: break
                        else: count += 1
                        
                    else: count += 1
                except Exception as e:
                    count += 1 
        else:
            
            res = re.findall(r"class=\'M(?:i|y)MovieTitle\'[^\>]*\>([^\<]*)<[^\>]*>[^\w]+(Scene[^\<]*)\<", _res.text)
            res2 = re.findall(r"\'SCENEID\'content\=\'([^\']+)\'", _res.text.replace(" ",""))
            if res and res2: count = 0
            else: count = 3
                           
        
        return({'id': res2[0], 'title': sanitize_filename(f'{res[0][0]}_{res[0][1].lower().replace(" ","_")}', restricted=True)} if count < 3 else None)
    
    def _get_url(self, client, url, headers):
        count = 0
        while count < 3:
            try:
                _res = client.get(url, headers=headers)
                if _res.status_code < 400: break
                else: count += 1
            except Exception as e:
                count += 1
        return(_res if count < 3 else None)
    
    def _get_formats(self, client, url, stream_url, _type):
        
        _headers_json = self._headers_ordered({"Referer": url, "X-Requested-With": "XMLHttpRequest",  "Content-Type" : "application/json",
                                                "Accept": "application/json, text/javascript, */*; q=0.01"})
        _headers_mpd = self._headers_ordered({"Accept": "*/*", "Origin": "https://nakedsword.com", "Referer": self._SITE_URL})
        
        try:
                    
            res = self._get_url(client, stream_url, _headers_json)
            if not res or not res.content: raise ExtractorError("Cant get stream url info")
            #self.to_screen(f"{res.request} - {res} - {res.request.headers} - {res.headers} - {res.content}")
            info_json = res.json()
            if not info_json: raise ExtractorError("Can't get json")                                                     
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{type(e)}: {str(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f"Cant get json info - {str(e)}")
            
        
                
        #self.to_screen(info_json)
        mpd_url = info_json.get("StreamUrl") 
        if not mpd_url: raise ExtractorError("Can't find url mpd")    
        #self.to_screen(mpd_url) 
        #NakedSwordSceneIE._COOKIES = client.cookies      
        
        try:
            res = self._get_url(client, mpd_url, _headers_mpd)
            #self.to_screen(f"{res.request} - {res} - {res.headers} - {res.request.headers} - {res.content}")
            if not res or not res.content: raise ExtractorError("Cant get mpd info")
            
            mpd_doc = (res.content).decode('utf-8', 'replace')
            if _type == "dash":
                mpd_doc = self._parse_xml(mpd_doc, None)
            #self.to_screen(mpd_doc)
            if not mpd_doc: raise ExtractorError("Cant get mpd doc") 
                
            if _type == "m3u8":
                formats, subtitles = self._parse_m3u8_formats_and_subtitles(mpd_doc, mpd_url, ext="mp4", entry_protocol="m3u8_native", m3u8_id="hls")
            elif _type == "dash":
                formats = self._parse_mpd_formats(mpd_doc, mpd_id="dash", mpd_url=mpd_url, mpd_base_url=(mpd_url.rsplit('/', 1))[0])
                
            if not formats: raise ExtractorError("Cant get formats") 
            
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{type(e)}: {str(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f"Cant get formats {_type} - {str(e)}") 
            
               
        
        return formats               
                
    def _real_extract(self, url):

        try:
            
            _headers = self._headers_ordered({"Upgrade-Insecure-Requests": "1"})
            client = httpx.Client(timeout=60,verify=(not self._downloader.params.get('nocheckcertificate')))
            client.cookies.set("ns_pfm", "True", "nakedsword.com")
        
            with NakedSwordSceneIE._LOCK:
                if not NakedSwordSceneIE._COOKIES:
                    try:
                        
                        NakedSwordSceneIE._COOKIES = self._login()
                        
                    except Exception as e:
                        self.to_screen(f"{repr(e)}")
                        raise
                
                for cookie in NakedSwordSceneIE._COOKIES:
                    if cookie['name'] in ("ns_auth", "ns_pk"):
                        client.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
                
        
        
            res = self._get_url(client, url, _headers)
            info_video = self._get_info(url, res)
            if not info_video: raise ExtractorError("Can't find sceneid")
                          
            scene_id = info_video.get('id')
            if not scene_id: raise ExtractorError("Can't find sceneid")
            
            stream_url = "/".join(["https://nakedsword.com/scriptservices/getstream/scene", str(scene_id)])                                   
            
            with ThreadPoolExecutor(thread_name_prefix="nakedsword", max_workers=2) as ex:
                # futs = [ex.submit(self._get_formats, client, url, "/".join([stream_url, "HLS"]), "m3u8"), 
                #        ex.submit(self._get_formats, client, url, "/".join([stream_url, "DASH"]), "dash")]
                futs = [ex.submit(self._get_formats, client, url, "/".join([stream_url, "HLS"]), "m3u8")]
                
            formats = []
            for _fut in futs:
                try:
                    formats += _fut.result()
                except Exception as e:
                    self.to_screen(f"{repr(e)}")
                   
            
            self._sort_formats(formats) 
            
            return {
                "id": scene_id,
                "title": info_video.get('title'),
                "formats": formats,
                "ext": "mp4"
            }
 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            client.close()

        

class NakedSwordMovieIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:movie:playlist'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<id>[\d]+)/(?P<title>[a-zA-Z\d_-]+)/?$"
    _MOVIES_URL = "https://nakedsword.com/movies/"


    def _real_extract(self, url):

        mobj = re.match(self._VALID_URL, url)
        
        playlist_id = mobj.group('id')
        title = mobj.group('title')

        webpage = self._download_webpage(url, playlist_id, "Downloading web page playlist")

        pl_title = self._html_search_regex(r'(?s)<title>(?P<title>.*?)<', webpage, 'title', group='title').split(" | ")[1]

        scenes_paths = re.findall(rf'{title}/scene/([\d]+)', webpage)

        entries = []
        for scene in scenes_paths:
            _url = self._MOVIES_URL + playlist_id + "/" + title + "/" + "scene" + "/" + scene
            res = NakedSwordSceneIE._get_info(_url)
            if res:
                _id = res.get('id')
                _title = res.get('title')
            entry = self.url_result(_url, ie=NakedSwordSceneIE.ie_key(), video_id=_id, video_title=_title)
            entries.append(entry)

        return {
            '_type': 'playlist',
            'id': playlist_id,
            'title': sanitize_filename(pl_title, True),
            'entries': entries,
        }

class NakedSwordMostWatchedIE(NakedSwordBaseIE):
    IE_NAME = "nakedsword:mostwatched:playlist"
    _VALID_URL = r'https?://(?:www\.)?nakedsword.com/most-watched/?'
    _MOST_WATCHED = 'https://nakedsword.com/most-watched?content=Scenes&page='
    
    def _real_extract(self, url):      
       

        entries = []

        with ThreadPoolExecutor(thread_name_prefix="nakedsword", max_workers=5) as ex:
            
            futures = [ex.submit(self.get_entries_scenes, f"{self._MOST_WATCHED}{i}") for i in range(1, 3)]
        
        for fut in futures:
            try:
                entries += fut.result()
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')  
                raise ExtractorError(repr(e)) from e

        return {
            '_type': 'playlist',
            'id': "NakedSWord mostwatched",
            'title': "NakedSword mostwatched",
            'entries': entries,
        }


class NakedSwordStarsIE(NakedSwordBaseIE):
    IE_NAME = "nakedsword:stars:playlist"
    _VALID_URL = r'https?://(?:www\.)?nakedsword.com/(?P<typepl>(?:stars|studios))/(?P<id>[\d]+)/(?P<name>[a-zA-Z\d_-]+)/?$'
    _MOST_WATCHED = "?content=Scenes&sort=MostWatched&page="
    _NPAGES = {"stars" : 2, "studios" : 3}
    
    def _real_extract(self, url):     
       
        
        data_list = re.search(self._VALID_URL, url).group("typepl", "id", "name")
        
        entries = []

        with ThreadPoolExecutor(max_workers=5) as ex:
            
            futures = [ex.submit(self.get_entries_scenes, f"{url}{self._MOST_WATCHED}{i}") for i in range(1, self._NPAGES[data_list[0]] + 1)]

        for fut in futures:
            try:
                entries += fut.result()
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')  
                raise ExtractorError(repr(e)) from e
        

        return {
            '_type': 'playlist',
            'id': data_list[1],
            'title':  f"NSw{data_list[0].capitalize()}_{''.join(w.capitalize() for w in data_list[2].split('-'))}",
            'entries': entries,
        }
        
class NakedSwordPlaylistIE(NakedSwordBaseIE):
    IE_NAME = "nakedsword:playlist"
    _VALID_URL = r'https?://(?:www\.)?nakedsword.com/(?P<id>.+)$'
    
    
    def _real_extract(self, url):      
       

        entries = []

        webpage = self._download_webpage(url, None, "Downloading web page playlist")
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