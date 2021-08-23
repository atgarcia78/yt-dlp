from __future__ import unicode_literals

import re
from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    int_or_none,
    sanitize_filename
)

import httpx
import time
import demjson



class ManPornXXXIE(InfoExtractor):
    IE_NAME = 'manpornxxx'
    _VALID_URL = r'https?://(?:www\.)?manporn\.xxx/videos/(?P<id>\d+)/(?P<title>[^\/$]+)/?$'
   
   
    def _get_filesize(self, url):
        
        count = 0
        try:
            
            _res = None
            while (count<10):
                
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
        
            res = httpx.get(url)
            mobj = re.findall(r'ld\+json\"\>([^\<]+)\<', res.text.replace('\n',''))
            
            if mobj:
                for _el in mobj:
                    _info = demjson.decode(_el)
                    if _info.get('@type') == 'VideoObject': 
                        _url_video = _info.get('contentUrl')
                        _title = _info.get('name').replace(" - manporn.xxx", "")
                        break
            
                       
            _format = {
                'format_id': 'http-mp4',
                'url': _url_video,
                'ext': 'mp4',
                'filesize': self._get_filesize(_url_video)
            }
       
            entry_video = {
                'id' : self._match_id(url),
                'title' : sanitize_filename(_title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
            } 
        
        except Exception as e:
            self.to_screen(e)
            raise
        
        return entry_video


