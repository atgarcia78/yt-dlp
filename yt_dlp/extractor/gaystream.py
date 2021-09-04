# coding: utf-8
from __future__ import unicode_literals


from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    sanitize_filename,
    int_or_none,
    std_headers   
)



import time
import traceback
import sys
from random import randint

from selenium.webdriver import Firefox, FirefoxProfile
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

from queue import Queue
from threading import Lock



import httpx


class GayStreamIE(InfoExtractor):
    
    _SITE_URL = "https://gaystream.pw"
    
    IE_NAME = 'gaystream'
    _VALID_URL = r'https?://(?:www\.)?gaystream.pw/video/(?P<id>\d+)/?([^$]+)?$'

    
    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/0khfuzdw.selenium0']

    _QUEUE = Queue()   
    
    _DRIVER = 0
    
    _LOCK =  Lock()
    
    


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
                    
                    res = httpx.head(url, headers=std_headers)
                    if res.status_code > 400:
                        time.sleep(10)
                        count += 1
                    else: 
                        _res = int_or_none(res.headers.get('content-length')) 
                        break
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass

        
        return _res
    
    def get_info_video(self, url, url_post, data_post, headers_post, driver):
        
        count = 0
        while count < 5:
            try:
                res = httpx.post(url_post, data=data_post, headers=headers_post)
                self.to_screen(f'{count}:{url}:{url_post}:{res}')
                if res.status_code > 400:
                    count += 1
                    self.wait_until(driver, randint(10,15), ec.title_is("DUMMYFORWAIT"))                                        
                else:
                    info_video = res.json()                    
                    return info_video
            except Exception as e:
                count += 1
                    
                
            
     





    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        
        with self._LOCK: 
                
            if self._DRIVER == self._downloader.params.get('winit'):
                
                driver = self._QUEUE.get(block=True)
                
            else:
                
        
                prof = self._FF_PROF.pop()
                self._FF_PROF.insert(0, prof)
                    
                opts = Options()
                opts.headless = True
                
                driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof))
 
                self.to_screen(f"ffprof[{prof}]")
                
                driver.set_window_size(1920,575)
                
                self._DRIVER += 1
                    
        try:                            
            
            
            driver.get(url)
            
            el_over =  self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "a.boner")))
            if el_over:
                el_over.click()
            
            el_ifr = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID, "ifr")))
            _entry_video = {}
            
            if el_ifr:
                url_ifr = el_ifr.get_attribute("src")
                _url_ifr = httpx.URL(url_ifr)
                url_post = url_ifr.replace('/v/', '/api/source/') 
                data_post = {'r': "https://gaystream.pw/", 'd': _url_ifr.host}
                headers_post = {'Referer': url_ifr, 'Origin': f'{_url_ifr.scheme}://{_url_ifr.host}'}
                self.wait_until(driver, randint(3,5), ec.title_is("DUMMYFORWAIT"))
                info_video = self.get_info_video(url, url_post, data_post, headers_post, driver)
                self.to_screen(f'{url}:{url_post}\n{info_video}')
                _formats = []
                if info_video:
                    for vid in info_video.get('data'):
                        _formats.append({
                                'format_id': vid.get('label'),
                                'url': (_url:=vid.get('file')),
                                'resolution' : vid.get('label'),                                
                                'filesize': self._get_filesize(_url),
                                'ext': "mp4"
                            })
            
                    if _formats: self._sort_formats(_formats)
                    _videoid = self._match_id(url)
                    _title = driver.title.replace("Watch","").replace("on Gaystream.pw","").strip()        
    
                
                
                    _entry_video = {
                        'id' : _videoid,
                        'title' : sanitize_filename(_title, restricted=True),
                        'formats' : _formats,
                        'ext': 'mp4'
                    } 
                    
                    self.to_screen(f'{url}\n{_entry_video}')  
                
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
        

      

