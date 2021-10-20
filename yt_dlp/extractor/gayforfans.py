# coding: utf-8
from __future__ import unicode_literals


from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
import re
import json

from .common import InfoExtractor

from ..utils import (
    ExtractorError,
    int_or_none,
    sanitize_filename,

)

import httpx
import time
from threading import Lock
import os

class GayForFansIE(InfoExtractor):
    IE_NAME = 'gayforfans'
    IE_DESC = 'gayforfans'
    _VALID_URL = r'https://gayforfans\.com/video/(?P<video>[a-zA-Z0-9_-]+)'
    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/22jv66x2.selenium0']
    

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
        try:
            
            with GayForFansIE._LOCK:
                prof_ff = self._FF_PROF.pop() 
                self._FF_PROF.insert(0,prof_ff)
                
            opts = Options()
            opts.add_argument("--headless")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-application-cache")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--profile")
            opts.add_argument(prof_ff)    
            opts.set_preference("network.proxy.type", 0)                    
            
                                           
                                
            driver = Firefox(options=opts)
 
            self.to_screen(f"ffprof[{prof_ff}]")
            
            #driver.set_window_size(1920,575)
            driver.maximize_window()
            
            self.wait_until(driver, 3, ec.title_is("DUMMYFORWAIT"))
            
            driver.get(url)
            
            el_video = WebDriverWait(driver, 30).until(ec.presence_of_all_elements_located((By.TAG_NAME,'video')))
            
            _url = el_video[0].find_element(by=By.TAG_NAME, value='source').get_attribute('src') if el_video else None
            
            
            
            
            _title = driver.title.replace(' – Gay for Fans – gayforfans.com', '')
            
            mobj = re.findall(r'wpdiscuzAjaxObj = (\{[^\;]+)\;',driver.page_source)
            if mobj:
                _info = json.loads(mobj[0])
                _videoid = f"POST{_info.get('wc_post_id')}"
            else: _videoid = "POST"    
            if not _url:
                raise ExtractorError('No url')
            
            filesize = self._get_filesize(_url)
           


        except Exception as e:
            raise 
        finally:
            driver.quit()
            
        format_video = {
            'format_id' : 'http-mp4',
            'url' : _url,
            'filesize' : filesize,
            'ext' : 'mp4'
        }

        return {
            'id': _videoid,
            'title': sanitize_filename(_title, restricted=True),
            'formats': [format_video],
            'ext': 'mp4'
           
        } 
        
class GayForFansPlayListIE(InfoExtractor):
    IE_NAME = 'gayforfans:playlist'
    IE_DESC = 'gayforfans'
    _VALID_URL = r'https?://(www\.)?gayforfans\.com(?:(/(?P<type>(?:popular-videos|performer|categories))(?:/?$|(/(?P<name>[^\/$\?]+))))(?:/?$|/?\?(?P<search>[^$]+)$)|/?\?(?P<search2>[^$]+)$)'
    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/22jv66x2.selenium0']
    

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
        try:
            
            with GayForFansPlayListIE._LOCK:
                prof_ff = self._FF_PROF.pop() 
                self._FF_PROF.insert(0,prof_ff)
                
            opts = Options()
            opts.add_argument("--headless")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-application-cache")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--profile")
            opts.add_argument(prof_ff)
            opts.set_preference("network.proxy.type", 0)                        
            
                                           
                                
            driver = Firefox(options=opts)
 
            self.to_screen(f"ffprof[{prof_ff}]")
            
            #driver.set_window_size(1920,575)
            driver.maximize_window()
            
            self.wait_until(driver, 3, ec.title_is("DUMMYFORWAIT"))
            
            driver.get(url)
            entries = []
            
            while True:
            
                el_videos = WebDriverWait(driver, 30).until(ec.presence_of_all_elements_located((By.TAG_NAME,'article')))
                for _el in el_videos:
                    _url = _el.find_element(by=By.TAG_NAME, value='a').get_attribute('href')
                    if _url: entries.append({'_type': 'url', 'url': _url, 'ie_key': 'GayForFans'})

                el_next = driver.find_elements(by=By.CSS_SELECTOR, value='a.next.page-numbers')
                if el_next:
                    el_next[0].click()
                else:          
                    break
        
            if not entries:
                raise ExtractorError(f'no videos info')
        
        except Exception as e:
            self.to_screen(str(e))
            raise

        finally:
            driver.quit()
            
        
        
        return{
            '_type': "playlist",
            'id': "gayforfans",
            'title': "gayforfans",
            'entries': entries
        }     
               