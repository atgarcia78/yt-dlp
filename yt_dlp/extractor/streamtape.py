# coding: utf-8
from __future__ import unicode_literals

import re
from .common import InfoExtractor
from ..utils import (
    ExtractorError, int_or_none, 
    std_headers,
    sanitize_filename
)


import httpx
import html
import time
from urllib.parse import unquote
import hashlib
import logging
from collections import OrderedDict
import random

logger = logging.getLogger("streamtape")


class StreamtapeIE(InfoExtractor):
    IE_NAME = 'streamtape'
    _VALID_URL = r'https?://(www.)?streamtape\.(?:com|net)/(?:d|e|v)/(?P<id>[a-zA-Z0-9_-]+)(?:$|/)'
    

    def _headers_ordered(self, extra=None):
        _headers = OrderedDict()
        
        if not extra: extra = dict()
        
        for key in ["User-Agent", "Accept", "Accept-Language", "Accept-Encoding", "Content-Type", "X-Requested-With", "Origin", "Connection", "Referer", "Upgrade-Insecure-Requests"]:
        
            value = extra.get(key) if extra.get(key) else std_headers.get(key)
            if value:
                _headers[key.lower()] = value
      
        
        return _headers
    
    
    def _get_info(self, url, client):
        
        count = 0
        try:
            
            _res = None
            while (count<3):
                
                try:
                    
                    res = client.head(url)
                    if res.status_code > 400:
                        time.sleep(1)
                        count += 1
                    else: 
                        _size = int_or_none(res.headers.get('content-length'))
                        _url = unquote(str(res.url))
                        if _size and _url:
                            _res = {'url': _url, 'filesize': _size}                         
                            break
                        else: count += 1
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass
                
        return _res


    
    def _real_extract(self, url):

        
        try:
        
            #_headers = self._headers_ordered({"Upgrade-Insecure-Requests": "1"})
            #client = httpx.Client(headers=_headers, timeout=httpx.Timeout(10, connect=30), limits=httpx.Limits(max_keepalive_connections=None, max_connections=None)) 
            
            client = httpx.Client()
            
            _url = unquote(url.replace("/e/", "/v/").replace("/d/", "/v/"))
            self.report_extraction(_url)       
            count = 0
            
            while( count < 20 ):
                
                try:
                    res = client.get(_url)
                    self.to_screen(res)
                    if res.status_code > 400:
                        
                        count += 1
                        time.sleep(random.random()*random.randint(1,5))
                        continue
                        
                    else:    
                        webpage = re.sub('[\t\n]', '', html.unescape(res.text))
                      
                    
                        if 'Video not found' in webpage:
                            self.to_screen(f"video not found {_url}")
                            raise ExtractorError("Video not found")

                        elif '<title>oopps</title>' in webpage:
                            self.to_screen(f"Ooops, will retry {_url}")
                            count += 1
                            time.sleep(random.random()*random.randint(1,5))
                            continue
                        
                        else: break
                
                except Exception as e:
                    count += 1
                    continue
                        
            if count == 10: 
                
                raise ExtractorError("video not found")
            
                    
            mobj = re.findall(r'id\=[\"\']videoo?link[\"\'].*(//streamtape\.com/get_video\?id=.*token\=).*token\=([^\'\"]+)[\'\"]', webpage)
            video_url = f"https:{mobj[0][0]}{mobj[0][1]}&dl=1" if mobj else None                                   
            info_video = self._get_info(video_url, client) if video_url else None
                
            if not info_video: raise ExtractorError("No info video")
                
            mobj =  re.findall(r'og:title[\"\']\s*content\s*=\s*[\"\']([^\"\']+)[\"\']', webpage)
            mobj2 = re.findall(r'<h2>([^\<]+)<', webpage)
            title = mobj[0] if mobj else mobj2[0] if mobj2 else "video_streamtape"
                
            _id_str = self._match_id(url)
                
            videoid = str(int(hashlib.sha256(_id_str.encode('utf-8')).hexdigest(),16) % 10**8)
                        
            format_video = {
                    
                    'format_id' : 'http',
                    'url' : info_video.get('url'),
                    'filesize' : info_video.get('filesize'),
                    'ext' : 'mp4'
                }
            
        
        
        except Exception as e:
            self.to_screen(e)
            count += 1
        finally:
            client.close()

        return {
            'id': videoid,
            'title': sanitize_filename(title, True),
            'formats': [format_video],
            'ext': 'mp4'
        }



