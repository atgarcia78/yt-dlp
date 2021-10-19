# coding: utf-8
from __future__ import unicode_literals



from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    sanitize_filename,
    int_or_none    
)



import time
import traceback
import sys
import os

from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


import httpx

from queue import (
    Queue,
    Empty)

from threading import Lock


class EvoloadIE(InfoExtractor):
    
    _SITE_URL = "https://evoload.io"
    
    IE_NAME = 'evoload'
    _VALID_URL = r'https?://(?:www\.)?evoload.io/(?:e|v)/(?P<id>[^\/$]+)(?:\/|$)'

    
    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/ultb56bi.selenium0']

 
    _LOCK = Lock()
    _DRIVER = 0
    _QUEUE = Queue()


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
        
        
        with self._LOCK: 
                
            if self._DRIVER == self._downloader.params.get('winit', 5):
                
                driver = self._QUEUE.get(block=True)
                driver.execute_script('''location.replace("about:blank");''')
                
            else:
                
                try:
                
                    driver = self._QUEUE.get(block=False)
                    driver.execute_script('''location.replace("about:blank");''')
                    
                except Empty:
                    
                    driver = None
                    prof = self._FF_PROF.pop()
                    self._FF_PROF.insert(0, prof)
                    self._DRIVER += 1
        
                
        
        if not driver:
                
            opts = Options()
            opts.add_argument("--headless")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-application-cache")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--profile")
            opts.add_argument(prof)                        
            os.environ['MOZ_HEADLESS_WIDTH'] = '1920'
            os.environ['MOZ_HEADLESS_HEIGHT'] = '1080'                               
                                
            driver = Firefox(options=opts)

            self.to_screen(f"{url}:ffprof[{prof}]")
            
            #elf.wait_until(driver, 5, ec.title_is("DUMMYFORWAIT"))
            
            #driver.uninstall_addon('uBlock0@raymondhill.net')
            
            #self.wait_until(driver, 5, ec.title_is("DUMMYFORWAIT"))
            
            #driver.uninstall_addon("{529b261b-df0b-4e3b-bf42-07b462da0ee8}")
                   
            driver.set_window_size(1920,575)        
            
        try:            
            
            _url = url.replace('/e/', '/v/')
            
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
            
            _entry_video = None
            
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
            
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))
        finally:
            driver.quit()
        
        if not _entry_video: raise ExtractorError("no video info")
        else:
            return _entry_video    
        

      

