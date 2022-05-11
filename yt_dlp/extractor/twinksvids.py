from __future__ import unicode_literals

import re
import sys
import traceback

from backoff import constant, on_exception
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import SeleniumInfoExtractor, limiter_1


class TwinksVidsIE(SeleniumInfoExtractor):
    IE_NAME = "twinksvids"
    _VALID_URL = r'https?://(www\.)?twinksvids\.com/[^\?]+$'
    
            
    
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @limiter_1.ratelimit("twinksvids", delay=True)
    def _send_request(self, url):        
        
        if len(url) > 150:
            _url_str = f'{url[:140]}...{url[-10:]}'
        else: _url_str = url
        self.logger_info(f"[send_request] {_url_str}") 
        res = self._CLIENT.get(url)
        return res
    
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @limiter_1.ratelimit("twinksvids", delay=True)  
    def _get_info_video(self, url):
        
        return super().get_info_for_format(url, headers={'Referer': 'https://twinksvids.com/'})
    
    
    def _real_initialize(self):
        super()._real_initialize()
               
    def _real_extract(self, url):        
        
        
        self.report_extraction(url)

        try:

            webpage = try_get(self._send_request(url), lambda x: x.text.replace("\n", ""))
            if not webpage: raise ExtractorError("couldnt download webpage")
           
            title, videoid, videourl = try_get(re.search(r'og:title" content="([^"]+)".*twinksvids\.com/\?p=([^"\']+)["\'].*contentURL["\'] content=["\']([^"\']+)["\']', webpage), lambda x: x.groups()) or ("", "", "")
            
            if not videourl: raise ExtractorError("no video url")
            
            self.to_screen(videourl)
            
            _entry = {
                'id': videoid,
                'title': sanitize_filename(title.split(' - TwinksVids')[0], restricted=True),                
                'url': videourl,
                'http_headers': {'Referer': 'https://twinksvids.com/'},
                'ext': 'mp4'}
            
            if (_video_info:=self._get_info_video(videourl)):
                _entry.update({'url': _video_info['url'], 'filesize': _video_info['filesize']})                       

                        
            return _entry
                
        
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e))
        