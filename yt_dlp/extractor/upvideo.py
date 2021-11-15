# coding: utf-8
from __future__ import unicode_literals


from .webdriver import SeleniumInfoExtractor
from ..utils import (
    ExtractorError,
    sanitize_filename,
    int_or_none,
    std_headers  
)


import time
import traceback
import sys

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


import httpx

from threading import Lock

class UpVideoIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://upvideo.to"
    
    IE_NAME = 'upvideo'
    _VALID_URL = r'https?://(?:www\.)?upvideo.to/v/(?P<id>[^\/$]+)(?:\/|$)'

    

    _LOCK = Lock()


    def _real_extract(self, url):
        
        self.report_extraction(url)

        driver = self.get_driver()

        try:                            

            
            with UpVideoIE._LOCK:
                driver.get(url)
            
            el = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID,"overlay")))
            if el: 
                try:
                    el.click()
                except Exception:
                    pass
            
            res = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID, "vplayer_html5_api")))
            if not res: raise ExtractorError("no info")
            video_url = res.get_attribute("src")
            if not video_url: raise ExtractorError("no video url") 
            
            title = driver.title.replace(" | upvideo","").replace(".mp4","")
            videoid = self._match_id(url)
            info_video = self.get_info_for_format(video_url)
            if (error_msg:=info_video.get('error')): raise ExtractorError(f"cant get info video - {error_msg}")
            
            _format = {
                    'format_id': 'http-mp4',
                    'url': info_video.get('url', video_url),
                    'filesize': info_video.get('filesize'),
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
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(repr(e))
        finally:
            try:
                self.rm_drive(driver)
            except Exception:
                pass 
        
        
        

      

