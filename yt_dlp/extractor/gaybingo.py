from __future__ import unicode_literals

from ..utils import (
    ExtractorError,
    sanitize_filename,
    int_or_none,
    try_get,
    std_headers

    
)

import traceback
import sys
import re

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

from .commonwebdriver import SeleniumInfoExtractor

from ratelimit import (
    sleep_and_retry,
    limits
)

import httpx

from backoff import constant, on_exception

class get_videourl():
    def __call__(self, driver):
        elvideo = driver.find_elements(By.CSS_SELECTOR, "video#player")
        if not elvideo: return False
        elsrc = elvideo[0].find_elements(By.TAG_NAME, "source")
        if not elsrc: return False
        videourl = elsrc[0].get_attribute('src')
        if videourl: return videourl
        else: return False
        

class GayBingoIE(SeleniumInfoExtractor):
    
    _SITE_URL = 'https://gay.bingo'    
    IE_NAME = 'gaybingo'
    _VALID_URL = r'https?://(?:www\.)?gay.bingo/video/(?P<id>\d+)(?:\?|$)'


    @on_exception(constant, Exception, max_tries=5, interval=1)  
    @sleep_and_retry
    @limits(calls=1, period=1)
    def url_request(self, driver, url):        
        
        self.logger_info(f"[send_request] {url}") 
        driver.get(url)
        
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @sleep_and_retry
    @limits(calls=1, period=1)
    def _send_request(self, url, headers=None):
        
        try:
            res = httpx.get(url, follow_redirects=True, headers=headers)
            res.raise_for_status()
            return res
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise            
         

    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        
        driver = self.get_driver()
 
            
        try: 
            self.url_request(driver, url)
            
            m3u8_url = self.wait_until(driver, 60, get_videourl())
            
            if m3u8_url:
                self.to_screen(m3u8_url)
                uagent = driver.execute_script("return navigator.userAgent")
                _headers = {'Origin': self._SITE_URL, 'Referer': f"{self._SITE_URL}/", 'User-Agent': uagent}
                _videoid = self._match_id(url)           
                height =  int_or_none(try_get(re.findall(r'stream/(\d+)p?/', m3u8_url), lambda x: x[0]))
                _title = driver.title.replace(" - Gay.Bingo", "").strip()

                formats = self._extract_m3u8_formats(m3u8_url, _videoid, 'mp4', entry_protocol='m3u8_native', m3u8_id='hls', headers=_headers, fatal=False)
                if formats: 
                    if height and len(formats) == 1:
                        if not formats[0].get('height'): formats[0].update({'height': height})            
                    for f in formats:
                        
                        _httpheaders = std_headers.copy()                        
                        _httpheaders.update(_headers)                        
                        f.update({'http_headers': _httpheaders})                        
                        
                
                    self._sort_formats(formats)
                
        
                    _entry_video = {
                        'id' : _videoid,
                        'title' : sanitize_filename(re.sub(r' - ', r'_', _title.replace("'","").replace("&","and")), restricted=True),
                        'formats' : formats,
                        'ext': 'mp4'
                    }
        
                
                    return _entry_video
                else: raise ExtractorError("no formats")
                
            else: raise ExtractorError("couldnt find any video")   
            
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")            
            raise ExtractorError(repr(e))
        finally:
            try:
                self.rm_driver(driver)
            except Exception:
                pass
