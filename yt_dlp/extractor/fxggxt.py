from __future__ import unicode_literals

import re
import sys
import traceback



from ..utils import ExtractorError, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_0_1, By, ec


class FxggxtIE(SeleniumInfoExtractor):
    IE_NAME = "fxggxt"
    _VALID_URL = r'https?://(www\.)?fxggxt\.com/.+'
    
            
    
    @dec_on_exception
    @limiter_0_1.ratelimit("fxggxt", delay=True)
    def _send_request(self, url):        
        
        self.logger_info(f"[send_request] {url}") 
        res = self._CLIENT.get(url)
        return res
    
    def _real_initialize(self):
        super()._real_initialize()
               
    def _real_extract(self, url):        
        
        
        self.report_extraction(url)

        try:

            res = self._send_request(url)
            if not res: raise ExtractorError("couldnt download webpage")
            webpage = re.sub(r'[\t\n]', '', res.text)
            videourl = try_get(re.findall(r'iframe[^>]*src=[\"\']([^\"\']+)[\"\']', webpage), lambda x: x[0])

            if not videourl: raise ExtractorError("no video url")
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
        