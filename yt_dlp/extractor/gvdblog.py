from __future__ import unicode_literals
import queue

import re

from datetime import datetime

from backoff import on_exception

from ..utils import (
    ExtractorError,
    try_get)


from .commonwebdriver import SeleniumInfoExtractor



from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By



import traceback
import sys

from ratelimit import sleep_and_retry, limits
from backoff import constant, on_exception


class GVDBlogPostIE(SeleniumInfoExtractor):
    IE_NAME = "gvdblogpost"
    _VALID_URL = r'https?://(www\.)?gvdblog\.com/\d{4}/\d+/.+\.html'
    
    @classmethod
    def get_post_time(cls, webpage):
        post_time = try_get(re.findall(r"<span class='post-timestamp'[^>]+><a[^>]+>([^<]+)<", webpage.replace('\n','')), lambda x: x[0])            
            
        if post_time:
            _info_date = datetime.strptime(post_time, '%B %d, %Y')
            
            
            return {
                'release_date': _info_date.strftime('%Y%m%d'),
                'release_timestamp': int(_info_date.timestamp())}
        
    
    @on_exception(constant, Exception, max_tries=5, interval=0.1)
    @sleep_and_retry
    @limits(calls=1, period=0.1)
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
                    if not 'dood.' in el: return el
            else: return x[0]
        
        self.report_extraction(url)

        try:

            res = self._send_request(url)
            videourl = try_get(re.findall(r'iframe[^>]*src=[\"\']([^\"\']+)[\"\']', res.text), getter)
                       
            post_time = try_get(re.findall(r"<span class='post-timestamp'[^>]+><a[^>]+>([^<]+)<", res.text.replace('\n','')), lambda x: x[0])            
            if not videourl: raise ExtractorError("no video url")
            self.to_screen(videourl)
            if post_time:
                _info_date = datetime.strptime(post_time, '%B %d, %Y')
            
            
                return {
                    '_type': 'url_transparent',
                    'url': videourl,
                    'release_date': _info_date.strftime('%Y%m%d'),
                    'release_timestamp': int(_info_date.timestamp())}
            else:
                return {
                    '_type': 'url_transparent',
                    'url': videourl}
                
        
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e)) from e
        