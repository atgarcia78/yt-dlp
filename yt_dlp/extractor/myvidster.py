from __future__ import unicode_literals


import re

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    int_or_none,
    std_headers,
    sanitize_filename,
    
    
)
from urllib.parse import unquote
from collections import OrderedDict
import httpx
import html
import time
from threading import Lock
from ratelimit import (
    sleep_and_retry,
    limits
)

class MyVidsterBaseIE(InfoExtractor):

    _LOGIN_URL = "https://www.myvidster.com/user/"
    _SITE_URL = "https://www.myvidster.com"
    _NETRC_MACHINE = "myvidster"
    
    _LOCK = Lock()
    _COOKIES = {}
    
    def _get_info_video(self, url, client):
       
        count = 0
        while (count<5):
                
            try:
                
                res = client.head(url, headers={'Referer': f'{self._SITE_URL}/'})
                if res.status_code > 400:
                    
                    count += 1
                else: 
                    
                    _filesize = int_or_none(res.headers.get('content-length')) 
                    _url = str(res.url)
                    #self.to_screen(f"{url}:{_url}:{_res}")
                    if _filesize and _url: 
                        break
                    else:
                        count += 1
        
            except Exception as e:
                count += 1
                
            time.sleep(1)
                
        if count < 5: return ({'url': _url, 'filesize': _filesize}) 
        else: return ({'error': 'max retries'})  
    
    def _is_valid(self, url, client):
        
        try:
            
            res = client.get(url)
        
        except Exception as e:
            self.to_screen(e)
            return False
        
        webpage = res.text.lower()
        valid = (res.status_code <= 400) and not any(_ in str(res.url) for _ in ['status=not_found', 'status=broken']) and not any(_ in webpage for _ in ['has been deleted', 'has been removed', 'was deleted', 'was removed', 'video unavailable', 'video is unavailable', 'video disabled', 'not allowed to watch', 'invalid', 'video not found'])
        self.to_screen(f'valid:{url}:{valid}')
        return valid
    
    def _headers_ordered(self, extra=None):
        _headers = OrderedDict()
        
        if not extra: extra = dict()
        
        for key in ["User-Agent", "Accept", "Accept-Language", "Accept-Encoding", "Content-Type", "X-Requested-With", "Origin", "Connection", "Referer", "Upgrade-Insecure-Requests"]:
        
            value = extra.get(key) if extra.get(key) else std_headers.get(key)
            if value:
                _headers[key.lower()] = value
      
        
        return _headers

    def _login(self):
        
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
                "Content-Type": "application/x-www-form-urlencoded",
                "Upgrade-Insecure-Requests": "1"
        }
        _headers_post = self._headers_ordered(_aux)
        
        _timeout = httpx.Timeout(30, connect=60)        
        _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
        client = httpx.Client(timeout=_timeout, limits=_limits, verify=(not self._downloader.params.get('nocheckcertificate')))
        
        try:
            
            client.get(self._LOGIN_URL, headers=_headers)
            client.cookies.set(name="auto_refresh", value="0", domain="www.myvidster.com")
            
            res = client.post(
                        self._LOGIN_URL,               
                        data=data,
                        headers=_headers_post,
                        timeout=60
                    )
            
            if res.status_code == 302 and "www.myvidster.com/user/home.php" in res.headers.get("location", ""):
                self.to_screen("LOGIN OK")
                return client.cookies
                
            else:
                raise ExtractorError(f"Login failed: {res} : {res.url}")

           
        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(repr(e))
        finally:
            try:
                client.close()
            except Exception:
                pass
            

    def islogged(self, client):
        
        res = client.get(self._LOGIN_URL)
        return("action=log_out" in res.text)
    
    def is_generic(self, url):
    
        extractor = None
        ies = self._downloader._ies
        for ie_key, ie in ies.items():
            if ie.suitable(url):
                extractor = ie_key
                break
        return (extractor == 'Generic', extractor)
    
    @sleep_and_retry
    @limits(calls=1, period=1)
    def _send_request(self, client, url, _type, _headers=None):
        
        self.to_screen(f'[send_request] {_type}:{url}')
        if _type == 'GET': 
            return client.get(url, headers=_headers)
        elif _type == 'HEAD':
            return client.head(url, headers=_headers)

class MyVidsterIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster'
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/(?:video|vsearch)/(?P<id>\d+)/?(?:.*|$)'
    _NETRC_MACHINE = "myvidster"
    
    

    def _real_initialize(self):
        with MyVidsterIE._LOCK:
            if not MyVidsterIE._COOKIES:
                       
                try:
                    MyVidsterIE._COOKIES  = self._login()                                        
        
                except Exception as e:
                    self.to_screen(repr(e))
                    raise
                
                
                

    def _real_extract(self, url):
        video_id = self._match_id(url)
        url = url.replace("vsearch", "video")
        _headers = self._headers_ordered({"Upgrade-Insecure-Requests": "1"}) 
        
        self.report_extraction(url)
        
        try:
        
            _timeout = httpx.Timeout(30, connect=60)        
            _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
            client = httpx.Client(timeout=_timeout, limits=_limits, verify=(not self._downloader.params.get('nocheckcertificate')))
            
            
            
            #client.get(self._SITE_URL, headers=_headers)
            self._send_request(client, self._SITE_URL, "GET", _headers)
            
            for cookie in MyVidsterIE._COOKIES.jar:
                client.cookies.set(name=cookie.name, value=cookie.value, domain=cookie.domain)
                    
            #res = client.get(url, headers=_headers)
            res = self._send_request(client, url, "GET", _headers)
            
            if str(res.url.params) in ('status=not_found', 'status=broken'): raise ExtractorError("Page not found or Page broken") 
            webpage = re.sub('[\t\n]', '', html.unescape(res.text))
            mobj = re.findall(r"<title>([^<]+)<", webpage)
            title = mobj[0] if mobj else url.split("/")[-1]    
            
            mobj = re.findall(r'rel=[\'\"]videolink[\'\"] href=[\'\"]([^\'\"]+)[\'\"]', webpage)
            videolink = ""
            if mobj:
                if self._is_valid(mobj[0], client): videolink = mobj[0]
                
            
            
            mobj2 = re.findall(r"reload_video\([\'\"]([^\'\"]+)[\'\"]", webpage)
            embedlink = ""
            if mobj2:
                if self._is_valid(mobj2[0], client): embedlink = mobj2[0]
                
            mobj3 = re.findall(r'source src=[\'\"]([^\'\"]+)[\'\"] type=[\'\"]video', webpage)
            source_url = ""
            if mobj3:
                if self._is_valid(mobj3[0], client): source_url = mobj3[0]
            
           
            
            if source_url:
                
                
                self.to_screen(f"video found: {source_url}")
                
                
                _info_video = self._get_info_video(source_url, client)
                
                if (_error:=_info_video.get('error')): 
                    self.to_screen(_error)
                    raise ExtractorError('Error 404')
                    
                _format_video = {
                    'format_id' : 'http-mp4',
                    'url': _info_video.get('url'),
                    'filesize': _info_video.get('filesize'),
                    'ext' : 'mp4'
                }
                
                return({
                    'id' : video_id,
                    'title' : sanitize_filename(title, restricted=True),
                    'formats' : [_format_video],
                    'ext': 'mp4'
                })
            
            
            else:
                
                if videolink and embedlink:
                    _videolink = "" if self.is_generic(videolink)[0] else videolink
                    _embedlink = "" if self.is_generic(embedlink)[0] else embedlink
            
                    real_url = _videolink or _embedlink
                
                    if not real_url: real_url = videolink
                
                else: real_url = videolink or embedlink
                
                self.to_screen(f"url found: {real_url}")
                
                if real_url:
                    return({
                        '_type' : 'url_transparent',
                        'id' : video_id,
                        'url' : unquote(real_url),
                        'ie_key': self.is_generic(real_url)[1]                     
                    })
                    
                else: raise ExtractorError("Page not found")
                    
                
       
            

        except ExtractorError as e:
            raise 
        except Exception as e:
            raise ExtractorError("No video info") from e
        finally:
            client.close()
            # with MyVidsterIE._LOCK:
                
            #     try:
            #         self._downloader.params.get('dict_videos_to_dl', {}).get('MyVidster',[]).remove(url)
            #     except ValueError as e:
            #         self.to_screen(str(e))
            #     self.to_screen(f"COUNT: [{len(self._downloader.params.get('dict_videos_to_dl', {}).get('MyVidster',[]))}]")
                    
            
            
        

class MyVidsterChannelPlaylistIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:channel:playlist'   
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/channel/(?P<id>\d+)/?(?P<title>\w+)?'
    _POST_URL = "https://www.myvidster.com/processor.php"
 
    


    def _real_extract(self, url):
        channelid = self._match_id(url)
        
        self.report_extraction(url)
        _headers = self._headers_ordered({"Upgrade-Insecure-Requests": "1"}) 
        
        try:
        
            _timeout = httpx.Timeout(10, connect=30)
        
            _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
            client = httpx.Client(timeout=_timeout, limits=_limits, verify=(not self._downloader.params.get('nocheckcertificate')))
                    
            #res = client.get(url, headers=_headers)
            res = self._send_request(client, url, "GET", _headers)
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

            entries = []
            
            if list_videos:
                
                entries = [{'_type':'url', 'url': f'{self._SITE_URL}{video}', 'ie_key': 'MyVidster'} for video in list_videos]
            
            return {
                '_type': 'playlist',
                'id': channelid,
                'title': sanitize_filename(title, True),
                'entries': entries,
            }
            
        except Exception as e:
            self.to_screen(e)
            raise ExtractorError from e
        finally:
            client.close()
            # with MyVidsterChannelPlaylistIE._LOCK:
                
            #     try:
            #         self._downloader.params.get('dict_videos_to_dl', {}).get('MyVidsterChannelPlaylist',[]).remove(url)
            #     except ValueError as e:
            #         self.to_screen(str(e))
            #     self.to_screen(f"COUNT: [{len(self._downloader.params.get('dict_videos_to_dl', {}).get('MyVidsterChannelPlaylist',[]))}]")
                    
            
            


        


