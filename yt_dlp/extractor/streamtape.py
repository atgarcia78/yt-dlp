from __future__ import unicode_literals

import html
import re
import sys
import time
import traceback
from urllib.parse import urlparse

from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, HTTPStatusError, SeleniumInfoExtractor, limiter_5, By

class video_or_error_streamtape():
    
    def __call__(self, driver):
  
        elh1 = driver.find_elements(By.CSS_SELECTOR, "h1")
        if elh1: #error
            errormsg = elh1[0].get_attribute('innerText').strip("!")                    
            return ("error", errormsg)
        
        elover = driver.find_elements(By.CLASS_NAME, "play-overlay")
        if elover:
            for _ in range(5):
                try:
                    elover[0].click()
                    time.sleep(1)
                except Exception as e:
                    break
            
        if (el_vid:=driver.find_elements(By.CSS_SELECTOR, "video")):
            if (_src:=el_vid[0].get_attribute('src')):
                _title = try_get(driver.find_elements(By.CSS_SELECTOR, 'h2'), lambda x: x[0].text)
                return (_src, _title)
        return False

class StreamtapeIE(SeleniumInfoExtractor):

    IE_NAME = 'streamtape'
    _VALID_URL = r'https?://(www.)?(?:streamtape|streamta)\.(?:com|net|pe)/(?:d|e|v)/(?P<id>[a-zA-Z0-9_-]+)/?'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?streamtape\.(?:com|net)/(?:e|v|d)/.+?)\1']
    

    @dec_on_exception3
    @dec_on_exception2
    @limiter_5.ratelimit("streamtape", delay=True)
    def _get_video_info(self, url, headers=None, msg=None):        
        
        if msg: pre = f'{msg}[get_video_info]'
        else: pre = '[get_video_info]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}")
        _headers = {'Range': 'bytes=0-', 'Referer': headers['Referer'],
                        'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
                        'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
        try:
            return self.get_info_for_format(url, headers=_headers)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
    
    @dec_on_exception
    @limiter_5.ratelimit("streamtape", delay=True)
    def _send_request(self, url, driver, msg=None):        
        
        if msg: pre = f'{msg}[send_req]'
        else: pre = '[send_req]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}")
        driver.get(url)
        

    def _get_entry(self, url, check_active=False, msg=None):
        try:
            
            url = url.replace('/e/', '/v/')
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}[get_entry][{self._get_url_print(url)}]'
            driver = self.get_driver()
            self._send_request(url, driver, msg=pre)
            video_url, _title = try_get(self.wait_until(driver, 30, video_or_error_streamtape()), lambda x: x if x else (None, None))
            if ((not video_url) or (video_url == 'error')): 
                raise ExtractorError('Error 404 - video not found')
            
            if not _title:
                _title = self._html_search_meta(('og:title', 'twitter:title'), driver.page_source, None)
                                        
             
            _format = {
                'format_id': 'http-mp4',
                'url': video_url,
                'ext': 'mp4',
                'http_headers': {'Referer': url}
            }
            
            
            if check_active:
                _videoinfo = self._get_video_info(video_url, headers= {'Referer': url}, msg=pre)
                if not _videoinfo: 
                    raise ExtractorError("error 404: no video info")
                _format.update({'url': _videoinfo['url'],'filesize': _videoinfo['filesize'] })
                
            _entry_video = {
                'id' : self._match_id(url),
                'title' : sanitize_filename(_title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4',
                'extractor_key': 'Streamtape',
                'extractor': 'streamtape',
                'webpage_url': url
            }            
            
            return _entry_video
            
        except Exception as e:
            raise
        finally:
            self.rm_driver(driver)
    
    def _real_initialize(self):
        
        super()._real_initialize()
        
    
    def _real_extract(self, url):
        
        self.report_extraction(url)

        try:                            

            if self.get_param('external_downloader'): _check_active = True
            else: _check_active = False

            return self._get_entry(url, check_active=_check_active)  
            
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.report_warning(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))