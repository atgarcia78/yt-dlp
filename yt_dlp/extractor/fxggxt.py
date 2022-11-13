import re
import sys
import traceback

from .commonwebdriver import (
    SeleniumInfoExtractor,
    dec_on_exception2,
    dec_on_exception3,
    limiter_0_1,
)
from ..utils import ExtractorError, try_get


class FxggxtIE(SeleniumInfoExtractor):
    IE_NAME = "fxggxt"
    _VALID_URL = r'https?://(www\.)?fxggxt\.com/.+'
    
            
    
    @dec_on_exception3
    @dec_on_exception2
    @limiter_0_1.ratelimit("fxggxt", delay=True)
    def _send_request(self, url, **kwargs):        
            
        try:
            self.logger_debug(f"[send_req] {self._get_url_print(url)}") 
            return(self.send_http_request(url, **kwargs))
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[send_request] {self._get_url_print(url)}: error - {repr(e)}")
    
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
            #self.to_screen(videourl)
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
        