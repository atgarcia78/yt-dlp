from __future__ import unicode_literals
import threading


from .common import InfoExtractor, ExtractorError
from ..utils import (
    
    sanitize_filename,
    int_or_none

)
import httpx

from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import time

import traceback
import sys
import os


class UserLoadIE(InfoExtractor):

    IE_NAME = 'userload'
    _VALID_URL = r'https?://(?:www\.)?userload\.co/(?:embed|e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/22jv66x2.selenium0']

 
    _LOCK = threading.Lock()


    def wait_until(self, _driver, time, method):
        try:
            el = WebDriverWait(_driver, time).until(method)
        except Exception as e:
            el = None
            
        return el  
    
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
        
        with UserLoadIE._LOCK: 
            
            prof = UserLoadIE._FF_PROF.pop()
            UserLoadIE._FF_PROF.insert(0, prof)
            
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-application-cache")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--profile")
        opts.add_argument(prof)
        opts.set_preference("network.proxy.type", 0)                        
        
                                       
                                
        driver = Firefox(options=opts)
 
        self.to_screen(f"ffprof[{prof}]")

        
            
        try:
            
            driver.maximize_window()
            
            _url = url.replace('/e/', '/f/').replace('/embed/', '/f/')
            
            self.wait_until(driver, 3, ec.title_is("DUMMYFORWAIT"))
            
            driver.get(_url)
            el = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID,"videooverlay"))) 
            el_video = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID, "olvideo_html5_api")))
            if not el_video: raise ExtractorError("no info")           
            
            if el:
                try:
                    el.click()
                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
                time.sleep(5)
                
            
                video_url = el_video.get_attribute("src")
                if not video_url: 
                    try:
                        el.click()
                    except Exception as e:
                        lines = traceback.format_exception(*sys.exc_info())
                        self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
                    time.sleep(5)
                    
                    
                    video_url = el_video.get_attribute("src")
                    if not video_url: 
                        try:
                            el.click()
                        except Exception as e:
                            lines = traceback.format_exception(*sys.exc_info())
                            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
                        
                        time.sleep(5)
                                        
                        video_url = el_video.get_attribute("src")
                        if not video_url:                     
                        
                            raise ExtractorError("no video url") 
            
            title = driver.title.replace(" | userload","").replace(".mp4","").strip()
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
            
            if not _entry_video: raise ExtractorError("no video info")
            else:
                return _entry_video      
            
        
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e)) from e
        finally:
            driver.quit()
        
        



       


