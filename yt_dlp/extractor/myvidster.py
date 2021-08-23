from __future__ import unicode_literals


import re
from tarfile import ExtractError
from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    int_or_none,
    std_headers,
    sanitize_filename
)
from urllib.parse import unquote
from collections import OrderedDict
import httpx
import html
import time
from threading import Lock
class MyVidsterBaseIE(InfoExtractor):

    _LOGIN_URL = "https://www.myvidster.com/user/"
    _SITE_URL = "https://www.myvidster.com"
    _NETRC_MACHINE = "myvidster"
    
    
    def _get_filesize(self, url):
        
        count = 0
        try:
            
            _res = None
            while (count<3):
                
                try:
                    
                    res = httpx.head(url)
                    if res.status_code > 400:
                        time.sleep(1)
                        count += 1
                    else: 
                        _res = int_or_none(res.headers.get('content-length')) 
                        break
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass

        
        return _res
    
    def _is_valid(self, url, client):
        
        try:
            
            res = client.head(url)
        
        except Exception as e:
            self.to_screen(e)
            return False
        
        return (res.status_code <= 200)
    
    def _headers_ordered(self, extra=None):
        _headers = OrderedDict()
        
        if not extra: extra = dict()
        
        for key in ["User-Agent", "Accept", "Accept-Language", "Accept-Encoding", "Content-Type", "X-Requested-With", "Origin", "Connection", "Referer", "Upgrade-Insecure-Requests"]:
        
            value = extra.get(key) if extra.get(key) else std_headers.get(key)
            if value:
                _headers[key.lower()] = value
      
        
        return _headers

    def _log_in(self, client):
        
        username, password = self._get_login_info()
        

        self.report_login()
        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)
        
               

        data = {
            "user_id": username,
            "password": password,
            "save_login" : "on",
            "submit" : "Log+In",
            "action" : "log_in"
        }

        _headers = self._headers_ordered({"Upgrade-Insecure-Requests": "1"})         
        
        _aux = {
                "Referer": self._LOGIN_URL,
                "Origin": self._SITE_URL,
                "Content-Type": "application/x-www-form-urlencoded"
        }
        _headers_post = self._headers_ordered(_aux)
        
        client.get(self._LOGIN_URL, headers=_headers)
        
        res = client.post(
                    self._LOGIN_URL,               
                    data=data,
                    headers=_headers_post,
                    timeout=60
                )

        if str(res.url) != "https://www.myvidster.com/user/home.php":
            raise ExtractorError("Login failed")


    def islogged(self, client):
        
        res = client.get(self._LOGIN_URL)
        return("action=log_out" in res.text)

class MyVidsterIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster'
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/(?:video|vsearch)/(?P<id>\d+)/?(?:.*|$)'
    _NETRC_MACHINE = "myvidster"
    
    _LOCK = Lock()
    _COOKIES = {}
    
 

    def _real_initialize(self):
        with MyVidsterIE._LOCK:
            if not MyVidsterIE._COOKIES:
                
                client = httpx.Client(timeout=60)   
                       
                try:
                    self._log_in(client)
                    MyVidsterIE._COOKIES = client.cookies                    
        
                except Exception as e:
                    self.to_screen(e)
                    raise
                finally:
                    client.close()
                
                

    def _real_extract(self, url):
        video_id = self._match_id(url)
        url = url.replace("vsearch", "video")
        _headers = self._headers_ordered({"Upgrade-Insecure-Requests": "1"}) 
        
        self.report_extraction(url)
        
        try:
        
            client = httpx.Client(timeout=60)
            
            client.get(self._SITE_URL, headers=_headers)
            
            for cookie in MyVidsterIE._COOKIES.jar:
                client.cookies.set(name=cookie.name, value=cookie.value, domain=cookie.domain)
                    
            res = client.get(url, headers=_headers) 
            webpage = re.sub('[\t\n]', '', html.unescape(res.text))
            mobj = re.findall(r"<title>([^<]+)<", webpage)
            title = mobj[0] if mobj else url.split("/")[-1]    
            
            mobj = re.findall(r'rel=[\'\"]videolink[\'\"] href=[\'\"]([^\'\"]+)[\'\"]', webpage)
            videolink = mobj[0] if mobj else ""
            
            
            mobj2 = re.findall(r"reload_video\([\'\"]([^\'\"]+)[\'\"]", webpage)
            embedlink = mobj2[0] if mobj2 else ""
            
            real_url = videolink or embedlink      
                
            if not real_url:
                raise ExtractError("Can't find real URL")

            #self.to_screen(f"{real_url}")   

            if 'myvidster.com' in real_url:
                
                res = client.get(real_url,headers=_headers)
                webpage = re.sub('[\t\n]', '', html.unescape(res.text))
                mobj = re.findall(r'source src="(?P<video_url>.*)" type="video', webpage)
                video_url = mobj[0] if mobj else ""
                if not video_url: raise ExtractError("Can't find real URL")           
                filesize = self._get_filesize(video_url)


                format_video = {
                    'format_id' : 'http-mp4',
                    'url' : video_url,
                    'filesize' : filesize,
                    'ext' : 'mp4'
                }
                
                entry_video = {
                    'id' : video_id,
                    'title' : sanitize_filename(title, restricted=True),
                    'formats' : [format_video],
                    'ext': 'mp4'
                }
                
            else:

                entry_video = {
                    '_type' : 'url_transparent',
                    'url' : unquote(real_url),
                    'id' : video_id,
                    'title' : sanitize_filename(title, restricted=True)
                }
        
        except Exception as e:
            self.to_screen(e)
            raise
        finally:
            client.close()
            
        return entry_video


class MyVidsterChannelPlaylistIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:channel:playlist'   
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/channel/(?P<id>\d+)/?(?P<title>\w+)?'
    _POST_URL = "https://www.myvidster.com/processor.php"
 
    


    def _real_extract(self, url):
        channelid = self._match_id(url)
        
        self.report_extraction(url)
        _headers = self._headers_ordered({"Upgrade-Insecure-Requests": "1"}) 
        
        try:
        
            client = httpx.Client(timeout=60)
                    
            res = client.get(url, headers=_headers)
            webpage = re.sub('[\t\n]', '', html.unescape(res.text))
            
            title = self._search_regex(r'<title>([\w\s]+)</title>', webpage, 'title', default=f"MyVidsterChannel_{channelid}", fatal=False)
            
            mobj = re.findall(r"display_channel\(.*,[\'\"](\d+)[\'\"]\)", webpage)
            num_videos = mobj[0] if mobj else 100000

            info = {
                'action' : 'display_channel',
                'channel_id': channelid,
                'page' : '1',
                'thumb_num' : num_videos,
                'count' : num_videos
            }
            
            _aux = {
                    "Referer": url,                
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "x-requested-with" : "XMLHttpRequest",
                    "Accept": "*/*"
            }
            
            _headers_post = self._headers_ordered(_aux)
            
                    
            res = client.post(
                        self._POST_URL,               
                        data=info,
                        headers=_headers_post,
                        
                    )

            webpage = re.sub('[\t\n]', '', html.unescape(res.text))

            list_videos = re.findall(r'<a href=\"(/video/[^\"]+)\" class', webpage)

            entries = [{'_type':'url', 'url': f'{self._SITE_URL}{video}', 'ie_key': 'MyVidster'} for video in list_videos]
            
        except Exception as e:
            self.to_screen(e)
            raise
        finally:
            client.close()


        return {
            '_type': 'playlist',
            'id': channelid,
            'title': sanitize_filename(title, True),
            'entries': entries,
        }
