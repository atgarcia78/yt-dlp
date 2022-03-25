from __future__ import unicode_literals


import re


from backoff import on_exception

from ..utils import (
    ExtractorError,
    try_get)


from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_0_1
)



import traceback
import sys

from backoff import constant, on_exception


class QueroFoderIE(SeleniumInfoExtractor):
    IE_NAME = "querofoder"
    _VALID_URL = r'https?://cdn\.querofoder\.com/player.php\?.*id=(?P<id>[^&$]+)'
    
       
    
    @on_exception(constant, Exception, max_tries=5, interval=0.1)
    @limiter_0_1.ratelimit("querofoder", delay=True)
    def _send_request(self, url):        
        
        self.logger_info(f"[send_request] {url}") 
        res = self._CLIENT.get(url)
        return res
    
    def _real_initialize(self):
        super()._real_initialize()
               
    def _real_extract(self, url):        
        
        def getter(x):
            if len(x) > 1:
                for el in x:
                    if 'dood.' in el: return el
            else: return x[0]
        
        self.report_extraction(url)

        try:

            res = self._send_request(url)
            videourl = try_get(re.findall(r'iframe[^>]*src=[\"\']([^\"\']+)[\"\']', res.text), getter)
                        
            self.to_screen(videourl)
            
            _entry = {
                '_type': 'url_transparent',
                'url': videourl}
            
            
            
            return _entry
                
        
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e))
        