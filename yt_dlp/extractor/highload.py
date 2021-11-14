# coding: utf-8
from __future__ import unicode_literals

from .seleniuminfoextractor import SeleniumInfoExtractor
from ..utils import (
    ExtractorError,
    sanitize_filename,
    int_or_none    
)


import time
import traceback
import sys


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


import time
import httpx

from threading import Lock

class HighloadIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://highload.to"
    
    IE_NAME = 'highload'
    _VALID_URL = r'https?://(?:www\.)?highload.to/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'

    

    _LOCK = Lock()

    
    def _get_filesize(self, url):
        
        count = 0
        try:
            
            _res = None
            while (count<3):
                
                try:
                    
                    res = httpx.head(url)
                    if res.status_code > 400:
                        time.sleep(1)
                        count += 1
                    else: 
                        _res = int_or_none(res.headers.get('content-length')) 
                        break
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass

        
        return _res



    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        driver = self.get_driver() 
           
            
        try:                            

            _url = url.replace('/e/', '/f/')
            with HighloadIE._LOCK:
                driver.get(_url)
            
            el = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID,"videerlay")))
            res = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID, "faststream_html5_api")))
            
            if not res: raise ExtractorError("no info")
            if el:
                try:
                    el.click()
                    self.wait_until(driver, 3, ec.title_is("DUMMYFORWAIT"))
                except Exception:
                    pass
            video_url = res.get_attribute("src")
            if not video_url: raise ExtractorError("no video url") 
            
            title = driver.title.replace(" - Highload.to","").replace(".mp4","").strip()
            videoid = self._match_id(url)
            
            _entry_video = None
            
            _format = {
                    'format_id': 'http-mp4',
                    'url': video_url,
                    'filesize': self._get_filesize(video_url),
                    'ext': 'mp4'
            }
            
            _entry_video = {
                'id' : videoid,
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
            } 
            
            return _entry_video  
            
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))
        finally:
            try:
                self.rm_driver(driver)
            except Exception:
                pass
        
   
        

      

