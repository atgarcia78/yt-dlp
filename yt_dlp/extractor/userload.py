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

import time

import traceback
import sys



class UserLoadIE(SeleniumInfoExtractor):

    IE_NAME = 'userload'
    _VALID_URL = r'https?://(?:www\.)?userload\.co/(?:embed|e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    
 
    _LOCK = threading.Lock()


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
            
            _url = url.replace('/e/', '/f/').replace('/embed/', '/f/')
            with UserLoadIE._LOCK: 
                driver.get(_url)
            el = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID,"videooverlay"))) 
            el_video = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID, "olvideo_html5_api")))
            if not el_video: raise ExtractorError("no info")           
            
            if el:
                
                try:
                    el.click()
                    self.wait_until(driver, 5, ec.title_is("DUMMYFORWAIT"))
                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            
                video_url = el_video.get_attribute("src")
                if not video_url: 
                    try:
                        el.click()
                        self.wait_until(driver, 5, ec.title_is("DUMMYFORWAIT"))
                    except Exception as e:
                        lines = traceback.format_exception(*sys.exc_info())
                        self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
                                       
                    
                    video_url = el_video.get_attribute("src")
                    if not video_url: 
                        try:
                            el.click()
                            self.wait_until(driver, 5, ec.title_is("DUMMYFORWAIT"))
                        except Exception as e:
                            lines = traceback.format_exception(*sys.exc_info())
                            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
                                        
                        video_url = el_video.get_attribute("src")
                        if not video_url:  
                            raise ExtractorError("no video url") 
            
                title = driver.title.replace(" | userload","").replace(".mp4","").strip()
                videoid = self._match_id(url)
            
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
        
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e)) from e
        finally:
            try:
                self.rm_driver(driver, tempdir)
            except Exception:
                pass
        
        



       


