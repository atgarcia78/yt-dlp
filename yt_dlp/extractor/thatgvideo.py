# coding: utf-8
from __future__ import unicode_literals

from .webdriver import SeleniumInfoExtractor
from ..utils import (
    ExtractorError,
    std_headers,
    sanitize_filename,
    int_or_none
)

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import httpx
import time


import traceback
import sys
from threading import Lock
import os



class ThatGVideoIE(SeleniumInfoExtractor):
    IE_NAME = 'thatgvideo'
    _VALID_URL = r'https?://thatgvideo\.com/videos/(?P<id>\d+).*'

    _LOCK = Lock()

    
    def _get_infovideo(self, url):
        
        count = 0
        try:
            
            _res = None
            while (count<5):
                
                try:
                    
                    res = httpx.head(url)
                    if res.status_code > 400:
                        time.sleep(1)
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
 
     
    
  

    def _real_extract(self, url):

        
        self.report_extraction(url)
        
        driver = self.get_driver()
 
        try:
            
  
            with ThatGVideoIE._LOCK: 
                driver.get(url)      

            el_video = self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "video")))
            video_url = el_video.get_attribute('src') if el_video else ""
            _format_video = {}
            
            _entry_video = {}
            
            if video_url:
                self.to_screen(video_url)
                std_headers['Referer'] = url
                std_headers['Accept'] = "*/*" 
                _info = self._get_infovideo(video_url)


                _format_video = {
                        'format_id' : "http-mp4",
                        'url' : _info.get('url'),
                        'filesize' : _info.get('filesize'),
                        'ext': "mp4"
                    }
                
                _entry_video = {
                    'id' : self._match_id(url),
                    'title' : sanitize_filename(driver.title,restricted=True),
                    'formats' : [_format_video],
                    'ext': "mp4"
                }
                
                return _entry_video
                    
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e)) from e
        finally:
            try:
                self.rm_driver(driver)
            except Exception:
                pass
    

            

              

