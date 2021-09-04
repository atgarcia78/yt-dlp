from __future__ import unicode_literals



from .common import InfoExtractor, ExtractorError
from ..utils import (
    
    sanitize_filename,
    int_or_none

)
import httpx


from selenium.webdriver import Firefox, FirefoxProfile
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import time

import traceback
import sys
from threading import Lock
from queue import Queue

from random import randint


class StreamtapeIE(InfoExtractor):

    IE_NAME = 'streamtape'
    _VALID_URL = r'https?://(www.)?streamtape\.(?:com|net)/(?:d|e|v)/(?P<id>[a-zA-Z0-9_-]+)(?:$|/)'
    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',                
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',                
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/0khfuzdw.selenium0']

 
    _LOCK = Lock()
    _DRIVER = 0
    _QUEUE = Queue()

    def wait_until(self, _driver, time, method):
        try:
            el = WebDriverWait(_driver, time).until(method)
        except Exception as e:
            el = None
            
        return el  
    
    def _get_infovideo(self, url):
        
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
                        _res = {'filesize' : int_or_none(res.headers.get('content-length')), 'url' : str(res.url)} 
                        break
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass

        
        return _res

    
    def _real_extract(self, url):
        
   
        self.report_extraction(url)
        
        with self._LOCK: 
                
            if self._DRIVER == self._downloader.params.get('winit'):
                
                driver = self._QUEUE.get(block=True)
                driver.execute_script('''location.replace("about:blank");''')
                
            else:
                
        
                prof = self._FF_PROF.pop()
                self._FF_PROF.insert(0, prof)
                driver = None
                self._DRIVER += 1
                
        if not driver:
                    
                opts = Options()
                opts.headless = True
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-application-cache")
                opts.add_argument("--disable-gpu")
                opts.add_argument("--disable-dev-shm-usage")
                
                ff_prof = FirefoxProfile(prof)
                ff_prof.set_preference("dom.webdriver.enabled", False)
                ff_prof.set_preference("useAutomationExtension", False)
                ff_prof.update_preferences()

                
                driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof))
 
                self.to_screen(f"{url}:ffprof[{prof}]")
                
                driver.set_window_size(1920,575)
                
                
            
        try:                            
                            

            _url = url.replace('/e/', '/v/').replace('/d/', '/v/')
            
            self.wait_until(driver, randint(2, 7), ec.title_is("DUMMYFORWAIT"))
            driver.get(_url)
            el_video = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID, "mainvideo")))
            el_overlay = self.wait_until(driver, 60, ec.presence_of_element_located((By.CLASS_NAME,"plyr-overlay")))            
            
            if not el_video: 
                driver.get_screenshot_as_file("/Users/antoniotorres/testing/test.png")
                raise ExtractorError("no info")
            if el_overlay:
                el_overlay.click()
                time.sleep(1)
                if not (el_video.get_attribute("src")):
                    el_overlay.click()
                    time.sleep(1)
                     
                    
            video_url = el_video.get_attribute("src")
            if not video_url: 
                
                raise ExtractorError("no video url")
            
            title = driver.title.replace(" at Streamtape.com","").replace(".mp4","").strip()
            videoid = self._match_id(url)
            
            _entry_video = None
            
            _info_video = self._get_infovideo(video_url)
            
            _format = {
                    'format_id': 'http-mp4',
                    'url': _info_video.get('url'),
                    'filesize': _info_video.get('filesize'),
                    'ext': 'mp4'
            }
            
            _entry_video = {
                'id' : videoid,
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
            }   
            
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))
        finally:
            self._QUEUE.put_nowait(driver)
        
        if not _entry_video: raise ExtractorError("no video info")
        else:
            return _entry_video    



       


