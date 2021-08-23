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
from threading import Lock

class XVidsIE(InfoExtractor):

    _IE_NAME = 'xvids'
    _SITE_URL = "https://xvids.gq"
    _VALID_URL = r'https?://(?:www\.)?xvids\.gq/(?P<title>[^\/$]+)(?:\/|$)'
   
    
    
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
    
    
   

 

    
 

   
                
                

    def _real_extract(self, url):
        
        
        self.report_extraction(url)
        
        try:
        
            client = httpx.Client(timeout=60)
                      
            res = client.get(url, headers=std_headers) 
            webpage = re.sub('[\t\n]', '', html.unescape(res.text))
            mobj = re.findall(r'og:title\" content\=\"([^\"]+)\"', webpage)
            title = mobj[0] if mobj else url.split("/")[-1]
            
            mobj = re.findall(r'postid-(\d+)',webpage)
            mobj2 = re.findall(r"shortlink\' href\=\'https://xvids.gq/\?p\=(\d+)\'",webpage)
            videoid = mobj[0] if mobj else mobj2[0] if mobj2 else "xvids"
            
            mobj = re.findall(r'contentURL\" content="([^\"]+)\"', webpage)
            real_url = mobj[0] if mobj else ""

            
         
            if not real_url:
                raise ExtractError("Can't find real URL")

           


            format_video = {
                'format_id' : 'http-mp4',
                'url' : real_url,
                'filesize' : self._get_filesize(real_url),
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

 
    
