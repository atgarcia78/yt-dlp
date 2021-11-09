from __future__ import unicode_literals
import threading


from ..utils import (
    ExtractorError,
    sanitize_filename,
    int_or_none

)
import httpx

from .seleniuminfoextractor import SeleniumInfoExtractor


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


import traceback
import sys

from ratelimit import (
    sleep_and_retry,
    limits
)

import time

class get_video_url():
    
    def __call__(self, driver):
        
        el = driver.find_elements(by=By.ID, value="videooverlay")        
        if el:            
            try:
                el[0].click()
            except Exception:                
                el_video = driver.find_elements(by=By.ID, value="olvideo_html5_api")
                if el_video:
                    video_url = el_video[0].get_attribute('src')
                    if video_url: return video_url
                    else: return False
                else: return False
        else:
            return False

class UserLoadIE(SeleniumInfoExtractor):

    IE_NAME = 'userload'
    _VALID_URL = r'https?://(?:www\.)?userload\.co/(?:embed|e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    
 
    _LOCK = threading.Lock()

    @sleep_and_retry
    @limits(calls=1, period=10)
    def _get_video_info(self, url):
        
        count = 0
        try:
            
            while (count<5):
                
                try:
                    
                    res = self._req_head(url)
                    
                    if res.status_code >= 400:
                        self.to_screen(f"{res.status_code}:{url}")
                        count += 1
                    else: 
                        _filesize = int_or_none(res.headers.get('content-length'))
                        _url = str(res.url)
                        if _filesize and _url:
                            break
                        else:
                            count += 1
                        
            
                except Exception as e:
                    self.to_screen(repr(e))
                    count += 1
            
        
            
        except Exception as e:
            self.to_screen(repr(e))
            pass

        if count < 5: 
            return ({'url': _url, 'filesize': _filesize}) 
        else: return ({'error': 'max retries'}) 

    @sleep_and_retry
    @limits(calls=1, period=10)
    def _req_head(self, url):
        self.to_screen(f"[req_head] {url}")
        return httpx.head(url)
    
    @sleep_and_retry
    @limits(calls=1, period=10)
    def _send_request(self, driver, url):

        self.to_screen(f"[send_request] {url}")
        driver.get(url)
        
    
    
    def _real_extract(self, url):
        
   
        self.report_extraction(url)
        
        driver = self.get_driver()
        
            
        try:            
            
            _url = url.replace('/e/', '/f/').replace('/embed/', '/f/')
            
            self._send_request(driver, _url)
            
            video_url = self.wait_until(driver, 60, get_video_url())
            if not video_url: raise ExtractorError("no video url")
            
                
            _videoinfo = self._get_video_info(video_url)
            
            self.to_screen(f"info video: {_videoinfo}")
            
            if _videoinfo.get('error'):
                raise ExtractorError("error video info")
            
            _format = {
                'format_id': 'http-mp4',
                'url': _videoinfo['url'],
                'filesize': _videoinfo['filesize'],
                'ext': 'mp4'
            }
            
            title = driver.title.replace(" | userload","").replace(".mp4","").strip().replace("-", "_")
            videoid = self._match_id(url)
            
            _entry_video = {
                'id' : videoid,
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
            } 
        
            
            return _entry_video 
        
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e)) from e
        finally:
            try:
                self.rm_driver(driver)
            except Exception:
                pass