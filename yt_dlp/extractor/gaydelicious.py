from __future__ import unicode_literals


import re
from .common import InfoExtractor
from ..utils import (
    ExtractorError,   
    std_headers  

)

import httpx
import traceback
import sys
import html


from urllib.parse import unquote


class GayDeliciousIE(InfoExtractor):
    
    IE_NAME = 'gaydelicious'
    _VALID_URL = r'https?://(www\.)?gaydelicious\.com/(?P<title>[^\$]*)$'
    
   
    def _real_extract(self, url):
        
                       
        self.report_extraction(url)
        
        try:
            
            client = httpx.Client(headers=std_headers,timeout=60,verify=(not self._downloader.params.get('nocheckcertificate')))
            
            res = client.get(url)
            if res.status_code > 400: raise ExtractorError(f'{url}:{res}')
            else: webpage = re.sub('[\t\n]','', html.unescape(res.text))
            _embed_url = re.findall(r'class=[\"\']embed-video[\"\']><p><iframe[\w\s\=\_\-\"\']+src=[\"\']([^\"\']+)[\"\']', webpage)
            if _embed_url:
                return({
                    '_type' : 'url_transparent',
                    'url' : unquote(_embed_url[0])
                })
                   
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e)) from e
        finally:
            client.close()
        
       
            
                        

    
