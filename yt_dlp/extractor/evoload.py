# coding: utf-8
from __future__ import unicode_literals

from ..utils import (
    ExtractorError,
    sanitize_filename,
    int_or_none,
    std_headers    
)


import traceback
import sys


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


import httpx

from threading import Lock

from .webdriver import SeleniumInfoExtractor

from ratelimit import (
    sleep_and_retry,
    limits
)

class get_title():
    def __call__(self, driver):
        
        el = driver.find_elements(by=By.CSS_SELECTOR, value="h3")        
        if el:            
            text = el[0].text
            if text:
                return text.replace(".mp4", "").replace("evo", "").replace("-","_")
            else:
                return False
                       
        else:       
            return False

class EvoloadIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://evoload.io"
    
    IE_NAME = 'evoload'
    _VALID_URL = r'https?://(?:www\.)?evoload.io/(?:e|v)/(?P<id>[^\/$]+)(?:\/|$)'

    _LOCK = Lock()

    @sleep_and_retry
    @limits(calls=1, period=10)
    def _get_video_info(self, url):
        
        count = 0
        try:
            
            while (count<5):
                
                try:
                    
                    
                    res = httpx.head(url)
                    if res.status_code >= 400:
                        
                        count += 1
                    else: 
                        _filesize = int_or_none(res.headers.get('content-length'))
                        _url = str(res.url)
                        if _filesize and _url:
                            break
                        else:
                            count += 1
                        
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass

        if count < 5: return ({'url': _url, 'filesize': _filesize}) 
        else: return ({'error': 'max retries'}) 

    @sleep_and_retry
    @limits(calls=1, period=10)
    def _send_request(self, driver, url):

        self.to_screen(f"[send_request] {url}")
        driver.get(url)
        
    def _real_extract(self, url):
        
        self.report_extraction(url)

        driver = self.get_driver()
 
            
        try:            
            
            _url = url.replace('/e/', '/v/')
            
            self._send_request(driver, _url)
           
            el_fr = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "iframe#videoplayer")))
            #self.wait_until(driver, 60, ec.frame_to_be_available_and_switch_to_it("videoplayer"))
            if not el_fr: raise ExtractorError("no videoframe")
            
            _title =  self.wait_until(driver, 60, get_title())
           
            driver.switch_to.frame(el_fr)
                
                
            el_video = self.wait_until(driver, 60, ec.presence_of_element_located((By.TAG_NAME, "video")))
            if not el_video: raise ExtractorError("no info")                        
            video_url = el_video.get_attribute("src")
            if not video_url: raise ExtractorError("no video url") 
            _videoid = self._match_id(url)
            
            _videoinfo = self._get_video_info(video_url)
            if _videoinfo.get('error'): raise ExtractorError("error video info")
            
            _format = {
                    'format_id': 'http-mp4',
                    'url': _videoinfo['url'],
                    'filesize': _videoinfo['filesize'],
                    'ext': 'mp4'
            }
            
            _entry_video = {
                'id' : _videoid,
                'title' : sanitize_filename(_title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
            }
            
            if not _entry_video: raise ExtractorError("no video info")
            else:  return _entry_video   
            
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(repr(e))
        finally:
            try:
                self.rm_driver(driver)
            except Exception:
                pass
        
        
     
               
        

      

