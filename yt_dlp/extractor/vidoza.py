from __future__ import unicode_literals

import re
from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    int_or_none,
    sanitize_filename,
    std_headers
)

import httpx
import time
import demjson



class VidozaIE(InfoExtractor):
    IE_NAME = 'vidoza'
    _VALID_URL = r'https?://(?:www\.)?vidoza\.net/(?P<id>[^.]+).html'
   
   
    def _get_filesize(self, url):
        
        count = 0
        try:
            
            _res = None
            while (count<10):
                
                try:
                    
                    res = httpx.head(url,headers={'Referer': 'https://vidoza.net', 'User-Agent': std_headers['User-Agent']})
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
            mobj = re.findall(r'sourcesCode: (\[\{.*\}\])\,', res.text.replace('\n',''))
            if mobj:
                info_sources = demjson.decode(mobj[0])
                _formats = []
                for source in info_sources:
                    _url_video = source.get('src')
                    _formats.append({
                        'format-id': 'http-mp4',
                        'url' : _url_video,
                        'ext': 'mp4',
                        'filesize': self._get_filesize(_url_video)
                    })
                    
            if not _formats: raise ExtractorError("No formats found")
            
            self._sort_formats(_formats)
                      
            _videoid = self._match_id(url)
            mobj = re.findall(r'<h1>([^\<]+)\<', res.text.replace('\n',''))
            _title = mobj[0] if mobj else "vidoza_video"       
            entry_video = {
                'id' : _videoid,
                'title' : sanitize_filename(_title, restricted=True),
                'formats' : _formats,
                'ext': 'mp4'
            } 
        
        except Exception as e:
            self.to_screen(e)
            raise
        
        return entry_video


