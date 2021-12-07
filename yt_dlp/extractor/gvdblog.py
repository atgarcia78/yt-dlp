from __future__ import unicode_literals

import re

from datetime import datetime

from ..utils import ExtractorError

from .webdriver import SeleniumInfoExtractor



from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By



import traceback
import sys

from ratelimit import sleep_and_retry, limits


class GVDBlogPostIE(SeleniumInfoExtractor):
    IE_NAME = "gvdblogpost"
    _VALID_URL = r'https?://(www\.)?gvdblog\.com/\d{4}/\d+/.+\.html'
    
    @sleep_and_retry
    @limits(calls=1, period=0.1)
    def _send_request(self, driver, url):        
        
        self.logger_info(f"[send_request] {url}") 
        driver.get(url)
               
    def _real_extract(self, url):        
        
        self.report_extraction(url)
        
        driver = self.get_driver()
        
        try:
                    
            self._send_request(driver, url)            
            
            eliframe = self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "iframe")))
            videourl = eliframe.get_attribute('src')
            post_time = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "post-timestamp")))
            if post_time:
                _info_date = datetime.strptime(post_time.text, '%B %d, %Y')
                
            if 'dood.ws' in videourl:             
                return {
                    '_type': 'url_transparent',
                    'url': videourl,
                    'ie': 'Dood',
                    'release_date': _info_date.strftime('%Y%m%d'),
                    'release_timestamp': int(_info_date.timestamp())}    
            
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e)) from e