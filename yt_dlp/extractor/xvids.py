from __future__ import unicode_literals


import re
from tarfile import ExtractError
from .common import InfoExtractor
from ..utils import (
    int_or_none,
    sanitize_filename
)

import httpx
import html
import time


class XVidsIE(InfoExtractor):

    _IE_NAME = 'xvids'    
    _VALID_URL = r'https?://(?:www\.)?xvids\.(?:gq|cc)/(?P<title>[^\/$]+)(?:\/|$)'
   
    
    
    def _get_info_video(self, url, client):
       
        count = 0
        while (count<5):
                
            try:
                
                res = client.head(url)
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
                

    def _real_extract(self, url):
        
        
        self.report_extraction(url)
        
        try:
        
            _timeout = httpx.Timeout(15, connect=15)        
            _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
            client = httpx.Client(timeout=_timeout, limits=_limits, headers=self.get_param('http_headers'), follow_redirects=True, verify=(not self.get_param('nocheckcertificate')))
                      
            res = client.get(url) 
            webpage = re.sub('[\t\n]', '', html.unescape(res.text))
            mobj = re.findall(r'og:title\" content\=\"([^\"]+)\"', webpage)
            title = mobj[0] if mobj else url.split("/")[-1]
            
            mobj = re.findall(r'postid-(\d+)',webpage)
            mobj2 = re.findall(r"shortlink\' href\=\'https://(?:xvids\.gq|gay-tubes\.cc)/\?p\=(\d+)\'",webpage)
            videoid = mobj[0] if mobj else mobj2[0] if mobj2 else "video_id"
            
            mobj = re.findall(r'contentURL\" content="([^\"]+)\"', webpage)
            real_url = mobj[0] if mobj else ""

            
         
            if not real_url:
                raise ExtractError("Can't find real URL")

           
            _info_video = self._get_info_video(real_url, client)

            format_video = {
                'format_id' : 'http-mp4',
                'url' : _info_video.get('url'),
                'filesize' : _info_video.get('filesize'),
                'ext' : 'mp4'
            }
                
            entry_video = {
                'id' : videoid,
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [format_video],
                'ext': 'mp4'
            }
                
           
        except Exception as e:
            self.to_screen(e)
            raise
        finally:
            client.close()
            
        return entry_video

 
    
