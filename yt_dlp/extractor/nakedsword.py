# coding: utf-8

from __future__ import unicode_literals

import re

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    sanitize_filename,
    std_headers
)

from threading import Lock
import traceback
import sys

import httpx
import time

from collections import OrderedDict

from concurrent.futures import ThreadPoolExecutor
class NakedSwordBaseIE(InfoExtractor):
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
    
    def _login(self, client:httpx.Client):
        
        self.report_login()
        username, password = self._get_login_info()
        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)            

        login_form = {
            "SignIn_login": username,
            "SignIn_password": password,
            "SignIn_returnUrl": "/",
            "SignIn_isPostBack": "true",
        }
        
        
        
        _headers = self._headers_ordered({"Upgrade-Insecure-Requests": "1"})         
        _aux = dict()
        _aux.update({"Referer": self._LOGIN_URL,"Origin": "https://nakedsword.com","Content-Type": "application/x-www-form-urlencoded", "Upgrade-Insecure-Requests": "1"})
        _headers_post = self._headers_ordered(_aux)
        
        count = 0
        while (count < 5):
        
            try:
                page = client.get(self._LOGIN_URL, headers=_headers)
                mobj = re.findall(r"\'SignIn_returnUrl\'value=\'([^\']+)\'", page.text.replace(" ",""))
                if mobj: login_form.update({"SignIn_returnUrl": mobj[0]})
                #self.to_screen(f"Count login: [{count}]")
                #self.to_screen(f"{page.request} - {page} - {page.request.headers} - {mobj}")
                time.sleep(2)            
                res = client.post(
                    self._LOGIN_URL,               
                    data=login_form,
                    headers=_headers_post,
                    timeout=60
                )
                #self.to_screen(f"{res.request} - {res} - {res.request.headers}")
                #self.to_screen("URL login: " + str(res.url))

                if str(res.url) != self._SITE_URL + "members":
                    count += 1
                else: break
            except Exception as e:
                self.to_screen(f"{type(e)}:{str(e)}")
                count += 1
                
        if count == 5:
            raise ExtractorError("unable to login")

    def _logout(self,client):
        
        _headers = self._headers_ordered()
        res = client.get(self._LOGOUT_URL, headers=_headers, timeout=120)
       


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
        
        
    
    
    def _real_initialize(self):
        with NakedSwordSceneIE._LOCK:
            #self.to_screen(f"Init of NSwordScene extractor: {NakedSwordSceneIE._COOKIES}")
            if not NakedSwordSceneIE._COOKIES:
                try:
                                        
                    client = httpx.Client()
                    self._login(client)
                    NakedSwordSceneIE._COOKIES = client.cookies
                    
                except Exception as e:
                    raise
                finally:
                    client.close()
                
            
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
        NakedSwordSceneIE._COOKIES = client.cookies      
        
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
                formats = self._parse_m3u8_formats(mpd_doc, mpd_url, ext="mp4", entry_protocol="m3u8_native", m3u8_id="hls")
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
            client = httpx.Client()
        
            with NakedSwordSceneIE._LOCK:
                if not NakedSwordSceneIE._COOKIES:
                    try:
                        self._login(client)
                        NakedSwordSceneIE._COOKIES = client.cookies
                        client.cookies.set("ns_pfm", "True", "nakedsword.com")
                    except Exception as e:
                        self.to_screen(f"{type(e)}: {str(e)}")
                        raise
                else:
                    client.get(self._SITE_URL, headers=_headers)
                    auth = NakedSwordSceneIE._COOKIES.get("ns_auth")
                    if auth:
                        #self.to_screen(f"Load Cookie: [ns_auth] {auth}")
                        client.cookies.set("ns_auth", auth, "nakedsword.com")
                    client.cookies.set("ns_pfm", "True", "nakedsword.com")
                    
                    pk = NakedSwordSceneIE._COOKIES.get("ns_pk")
                    if pk:
                        #self.to_screen(f"Load Cookie: [ns_pk] {pk}")
                        self._set_cookie("nakedsword.com","ns_pk", pk)
        
        
            res = self._get_url(client, url, _headers)
            info_video = self._get_info(url, res)
            if not info_video: raise ExtractorError("Can't find sceneid")
                          
            scene_id = info_video.get('id')
            if not scene_id: raise ExtractorError("Can't find sceneid")
            
            stream_url = "/".join(["https://nakedsword.com/scriptservices/getstream/scene", str(scene_id)])                                   
            
            with ThreadPoolExecutor(max_workers=2) as ex:
                futs = [ex.submit(self._get_formats, client, url, "/".join([stream_url, "HLS"]), "m3u8"), 
                       ex.submit(self._get_formats, client, url, "/".join([stream_url, "DASH"]), "dash")]
                
            formats = []
            for _fut in futs:
                try:
                    formats += _fut.result()
                except Exception as e:
                    self.to_screen(f"{type(e)} - {str(e)}")
                   
            
            self._sort_formats(formats) 
 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{type(e)}: {str(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(str(e))
        finally:
            client.close()

        return {
            "id": scene_id,
            "title": info_video.get('title'),
            "formats": formats,
            "ext": "mp4"
        }

class NakedSwordMovieIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:movie:playlist'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<id>[\d]+)/(?P<title>[a-zA-Z\d_-]+)/?$"
    _MOVIES_URL = "https://nakedsword.com/movies/"


    def _real_extract(self, url):

        mobj = re.match(self._VALID_URL, url)
        
        playlist_id = mobj.group('id')
        title = mobj.group('title')

        webpage = self._download_webpage(url, playlist_id, "Downloading web page playlist")

        #print(webpage)

        pl_title = self._html_search_regex(r'(?s)<title>(?P<title>.*?)<', webpage, 'title', group='title').split(" | ")[1]

        #print(title)

        scenes_paths = re.findall(rf'{title}/scene/([\d]+)', webpage)

        #print(scenes_paths)

        entries = []
        for scene in scenes_paths:
            _url = self._MOVIES_URL + playlist_id + "/" + title + "/" + "scene" + "/" + scene
            res = NakedSwordSceneIE._get_info(_url)
            if res:
                _id = res.get('id')
                _title = res.get('title')
            entry = self.url_result(_url, ie=NakedSwordSceneIE.ie_key(), video_id=_id, video_title=_title)
            entries.append(entry)

        #print(entries)

        

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

        for i in range(1,5):
               
            webpage = self._download_webpage(f"{self._MOST_WATCHED}{i}", None, "Downloading web page playlist")
            if webpage:  
                #print(webpage)          
                videos_paths = re.findall(
                    r"<div class='SRMainTitleDurationLink'><a href='/([^\']+)'>",
                    webpage)     
                
                if videos_paths:

                    for j, video in enumerate(videos_paths):
                        _url = self._SITE_URL + video
                        res = NakedSwordSceneIE._get_info(_url)
                        if res:
                            _id = res.get('id')
                            _title = res.get('title')
                        entry = self.url_result(_url, ie=NakedSwordSceneIE.ie_key(), video_id=_id, video_title=_title)
                        entries.append(entry)
                else:
                    raise ExtractorError("No info")


                
            else:
                raise ExtractorError("No info")

                

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
    _NPAGES = {"stars" : 1, "studios" : 1}
    
    def _real_extract(self, url):     
       
        
        data_list = re.search(self._VALID_URL, url).group("typepl", "id", "name")
        
        entries = []

        for i in range(self._NPAGES[data_list[0]]):


            webpage = self._download_webpage(f"{url}{self._MOST_WATCHED}{i+1}", None, "Downloading web page playlist")
            if webpage:  
                #print(webpage)          
                videos_paths = re.findall(
                    r"<div class='SRMainTitleDurationLink'><a href='/([^\']+)'>",
                    webpage)     
                
                if videos_paths:

                    for j, video in enumerate(videos_paths):
                        
                        _url = self._SITE_URL + video
                        res = NakedSwordSceneIE._get_info(_url)
                        if res:
                            _id = res.get('id')
                            _title = res.get('title')                        
                        entry = self.url_result(_url, ie=NakedSwordSceneIE.ie_key(), video_id=_id, video_title=_title)
                        entries.append(entry)
                else:
                    raise ExtractorError("No info")

                if not "pagination-next" in webpage: break
                
            else:
                raise ExtractorError("No info")

                

        return {
            '_type': 'playlist',
            'id': data_list[1],
            'title':  f"NSw{data_list[0].capitalize()}_{''.join(w.capitalize() for w in data_list[2].split('-'))}",
            'entries': entries,
        }