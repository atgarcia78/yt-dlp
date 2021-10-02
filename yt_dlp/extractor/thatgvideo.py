# coding: utf-8
from __future__ import unicode_literals

from .common import InfoExtractor
from ..utils import (
    ExtractorError, 
    std_headers,
    sanitize_filename,
    int_or_none
)

from selenium.webdriver import Firefox, FirefoxProfile
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import httpx
import time


import traceback
import sys
from queue import Queue, Empty
from threading import Lock



class ThatGVideoIE(InfoExtractor):
    IE_NAME = 'thatgvideo'
    _VALID_URL = r'https?://thatgvideo\.com/videos/(?P<id>\d+).*'

    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/0khfuzdw.selenium0']
    
    
    _LOCK = Lock()
    _DRIVER = 0
    _QUEUE = Queue()
    
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
 
     
    
    def wait_until(self, driver, time, method):
        try:
            el = WebDriverWait(driver, time).until(method)
        except Exception as e:
            el = None
            
        return el     

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
            opts.headless = True
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-application-cache")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-dev-shm-usage")
            
                            
            driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof))

            self.to_screen(f"{url}:ffprof[{prof}]")
            
            #elf.wait_until(driver, 5, ec.title_is("DUMMYFORWAIT"))
            
            #driver.uninstall_addon('uBlock0@raymondhill.net')
            
            #self.wait_until(driver, 5, ec.title_is("DUMMYFORWAIT"))
            
            #driver.uninstall_addon("{529b261b-df0b-4e3b-bf42-07b462da0ee8}")
                   
            driver.set_window_size(1920,575)         
        try:
                        
                        
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
                    
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e)) from e
        finally:
            self._QUEUE.put_nowait(driver)
    
        if _entry_video:
            return _entry_video
            

              

