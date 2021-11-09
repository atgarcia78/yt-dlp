from __future__ import unicode_literals

import re

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    int_or_none,
    std_headers,
    sanitize_filename
)

import httpx
import html
import time
import traceback
import sys

class GayMaleTubesIE(InfoExtractor):

    _IE_NAME = 'gaymaletubes'    
    _VALID_URL = r'https?://(?:www\.)?gaymaletubes\.cc/(?P<title>[^\/$]+)(?:\/|$)'
   
    
    
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
        
            client = httpx.Client(timeout=60, headers=std_headers, verify=(not self._downloader.params.get('nocheckcertificate')))
                      
            res = client.get(url)
            if res.status_code >= 400: raise ExtractorError("Page not found")
            webpage = re.sub('[\t\n]', '', html.unescape(res.text))
            title = re.search(r'<title>(?P<title>[^\<]+)<', webpage).group('title').replace(" - GayMaleTubes.cc", "")
            videoid = re.search(f'data-post_id=\"(?P<id>[^\"]+)\"', webpage).group('id')
            mobj = re.findall(r'<iframe src=\"(https://[^\"]+)\"', webpage)
            if mobj:
                frame_url = mobj[0]
                res = client.get(frame_url)
                if res.status_code >= 400: raise ExtractorError("Page not found")
                webpage_fr = re.sub('[\t\n]', '', html.unescape(res.text))
                mobj = re.findall(r'<source src=\"(https://[^\"]+)\"',webpage_fr)
                if mobj:
                    video_url = mobj[0]
                
                _info_video = self._get_info_video(video_url, client)

                format_video = {
                    'format_id' : 'http-mp4',
                    'url' : _info_video.get('url'),
                    'filesize' : _info_video.get('filesize'),
                    'ext' : 'mp4'
                }
                
                return ({
                    'id' : videoid,
                    'title' : sanitize_filename(title, restricted=True),
                    'formats' : [format_video],
                    'ext': 'mp4'
                })
            
            else: raise ExtractorError("No video details found")
                
        
        except  ExtractorError as e:
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e)) from e
        finally:
            client.close()
            
     

 
    
