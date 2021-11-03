# coding: utf-8
from __future__ import unicode_literals

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


import httpx

from threading import Lock

from .seleniuminfoextractor import SeleniumInfoExtractor

class EvoloadIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://evoload.io"
    
    IE_NAME = 'evoload'
    _VALID_URL = r'https?://(?:www\.)?evoload.io/(?:e|v)/(?P<id>[^\/$]+)(?:\/|$)'

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

        driver, tempdir = self.get_driver(prof='/Users/antoniotorres/Library/Application Support/Firefox/Profiles/22jv66x2.selenium0')
 
            
        try:            
            
            _url = url.replace('/e/', '/v/')
            
            with EvoloadIE._LOCK:
                driver.get(_url)
            
            el_title =  self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "h3.kt-subheader__title.ng-binding")))
            _title = el_title.text
            while not _title:
                self.wait_until(driver, 1, ec.title_is("DUMMYFORWAIT"))
                _title = el_title.text
            
            _title = _title.replace(".mp4", "").replace("evo","")            
            self.wait_until(driver, 60, ec.frame_to_be_available_and_switch_to_it("videoplayer"))
            el_video = self.wait_until(driver, 60, ec.presence_of_element_located((By.TAG_NAME, "video")))
            if not el_video: raise ExtractorError("no info")                        
            video_url = el_video.get_attribute("src")
            if not video_url: raise ExtractorError("no video url") 
            _videoid = self._match_id(url)
            
            _format = {
                    'format_id': 'http-mp4',
                    'url': video_url,
                    'filesize': self._get_filesize(video_url),
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
                self.rm_driver(driver, tempdir)
            except Exception:
                pass
        
        
     
               
        

      

