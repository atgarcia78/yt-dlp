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

import httpx
import html
import time
import json
import traceback
import sys

class GayMenTubexxxIE(InfoExtractor):

    _IE_NAME = 'gaymentubexxx'    
    _VALID_URL = r'https?://(?:www\.)?gaymentubexxx\.com/(?P<title>[^\/$]+)(?:\/|$)'
   
    
    
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
            mobj = re.findall(r'gallery-data" type="text/json">([^\<]+)<',webpage)
            if mobj:
                _player_info = json.loads(mobj[0])
                _url = _player_info.get('videos', {}).get('mp4', {})
                _info_video = self._get_info_video(_url, client)

                format_video = {
                    'format_id' : 'http-mp4',
                    'url' : _info_video.get('url'),
                    'filesize' : _info_video.get('filesize'),
                    'ext' : 'mp4'
                }
                
                return ({
                    'id' : str(_player_info.get('id')),
                    'title' : sanitize_filename(_player_info.get('title'), restricted=True),
                    'formats' : [format_video],
                    'ext': 'mp4'
                })
            
            else: raise ExtractorError("No video details found")
                
        
        except  ExtractorError as e:
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e)) from e
        finally:
            client.close()
            
     

 
    
