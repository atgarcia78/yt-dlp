from __future__ import unicode_literals


import re
from .common import InfoExtractor
from ..utils import (
    ExtractorError,   
    std_headers,
    sanitize_filename,
    int_or_none,

)

import httpx
import traceback
import sys
import demjson
import time


import random
from urllib.parse import unquote


class Gay0DayIE(InfoExtractor):
    
    IE_NAME = 'gay0day'
    _VALID_URL = r'https?://(www\.)?gay0day\.com/(?:videos|embed)/(?P<id>\d+)/?(?P<title>[^\$]*)$'
    
     
    def get_filesize(self, url, client):
        
        count = 0
        try:
            
            _res = None
            while (count<3):
                
                try:
                    
                    res = client.head(url)
                    if res.status_code > 400:
                        time.sleep(10)
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
            
            client = httpx.Client(headers=std_headers,timeout=60,verify=(not self._downloader.params.get('nocheckcertificate')))
            
            res = client.get(url)
            if res.status_code > 400: raise ExtractorError(f'{url}:{res}')
            else: webpage = res.text
            flashvars = re.findall(r'(?ms)<script.*?>.*?var\s+flashvars\s*=\s*(\{.*?\});.*?</script>', webpage)
            _entry_video = {}
            if flashvars:
                info_video = demjson.decode(flashvars[0])
                if info_video: 
            
                    _url = info_video.get("video_url")
                    _res = info_video.get("postfix").replace("_","").replace(".mp4","")            
                    _format = {
                        'format_id': _res,
                        'resolution': _res,
                        'url': _url,
                        'ext': 'mp4',
                        'filesize': self.get_filesize(_url, client)
                    }
                    _videoid = info_video.get("video_id")
                    if not _videoid: _videoid = self._match_id(url)
                    mobj = re.findall(r"<title>([^<]+)<", webpage)
                    _title = mobj[0] if mobj else "video_gaydgay"
                    _title = _title.replace("Video:","").replace("at Gay0Day","").strip()
                    _entry_video = {
                        'id' : _videoid,
                        'title' : sanitize_filename(_title, restricted=True),
                        'formats' : [_format],
                        'ext': 'mp4'}
        
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))
        finally:
            client.close()
        
        if not _entry_video: raise ExtractorError("no video info")
        else:
            return _entry_video    
            
                        

    
