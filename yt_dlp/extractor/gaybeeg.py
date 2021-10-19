# coding: utf-8
from __future__ import unicode_literals

import re


from ..utils import ExtractorError

from .common import InfoExtractor

from concurrent.futures import (
    ThreadPoolExecutor,
    wait,
    ALL_COMPLETED
)


import threading


from selenium.webdriver import Firefox, FirefoxProfile
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By



from .netdna import NetDNAIE

import logging
import traceback
import sys

import os

logger = logging.getLogger("gaybeeg")

class GayBeegBaseIE(InfoExtractor):
    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/0khfuzdw.selenium0']
    
    _LOCK = threading.Lock()

    
    
    @staticmethod
    def _get_entries_netdna(el_list):
        
        _list_urls_netdna = {}
        _next = None
        for _el in el_list:
            _url = _el.get_attribute('href')
            
            if _next:
                _list_urls_netdna[_url] = _next
                _next = None
            else:
                _tree = _el.find_elements_by_xpath("./ancestor-or-self::*")
                _tree.reverse()
                if any((_res:=el.text) for el in _tree):
            
                    _text = _res.splitlines()
                    _list_urls_netdna[_url] = _text[0]
                    if len(_text) == 2 and any(_ext in _text[1] for _ext in ('mp4', 'zip')):
                        _next = _text[1]
                        
         
        
        entries = []
        
        for _url, _item in _list_urls_netdna.items():
            
            _info_video = NetDNAIE.get_video_info(_item)
            entries.append({'_type' : 'url', 'url' : _url, 'ie' : 'NetDNA', 'title': _info_video.get('title'), 'id' : _info_video.get('id'), 'filesize': _info_video.get('filesize')})
        
                                    
        return entries
    
    @staticmethod
    def _get_entries_gaybeeg(el_list):
        entries = [{'_type' : 'url', 'url' : _url, 'ie' : 'GayBeeg'}
                        for el in el_list
                                    for el_tagh2 in el.find_elements_by_tag_name("h2")
                                        for el_taga in el_tagh2.find_elements_by_tag_name("a")
                                            if "//gaybeeg.info" in (_url:=el_taga.get_attribute('href'))]    
        return entries
    
    def wait_until(self, driver, time, method):        
        
        try:
            el = WebDriverWait(driver, time).until(method)
        except Exception as e:
            el = None
    
        return el   
    
    
    def _get_entries(self, url, driver=None):
        
        try:
        
            if not driver:
                _keep = False
                driver = self._launch_driver()
            else:
                _keep = True
                        
            
            driver.get(url)
            
            SCROLL_PAUSE_TIME = 2

            last_height = driver.execute_script("return document.body.scrollHeight")

            while True:
                # Scroll down to bottom
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

                # Wait to load page
                self.wait_until(driver, SCROLL_PAUSE_TIME, ec.title_is("DUMMYFORWAIT"))
               
                # Calculate new scroll height and compare with last scroll height
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
        
            # el_list = self.wait_until(driver, 120, ec.presence_of_all_elements_located((By.CLASS_NAME, "henry-large")))
            # if el_list:
            
            el_a_list = self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.XPATH, '//a[contains(@href, "//netdna-storage.com")]')))
            if el_a_list:
                
                entries = GayBeegBaseIE._get_entries_netdna(el_a_list)
            
                return entries
            
        finally:
            if not _keep: driver.quit()
            
            
        
                
    def _launch_driver(self):
        
        with GayBeegBaseIE._LOCK:
            
                
            prof = GayBeegBaseIE._FF_PROF.pop() 
            GayBeegBaseIE._FF_PROF.insert(0,prof)
        
        try:
                
            opts = Options()
            opts.headless = True
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-application-cache")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-dev-shm-usage")
            os.environ['MOZ_HEADLESS_WIDTH'] = '1920'
            os.environ['MOZ_HEADLESS_HEIGHT'] = '1080'                            
                        
            driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof))

            self.to_screen(f"ffprof[{prof}]")
        
            #driver.set_window_size(1920,575)
            driver.maximize_window()
            
            return driver
            
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e)) from e
        


class GayBeegPlaylistPageIE(GayBeegBaseIE):
    IE_NAME = "gaybeeg:onepage:playlist"
    _VALID_URL = r'https?://(www\.)?gaybeeg\.info.*/page/.*'
    

    def _real_extract(self, url):        
        
        try:
                   
            self.report_extraction(url)
            
            entries = self._get_entries(url)
            
            if not entries: raise ExtractorError("No entries")  
                      
            return {
                '_type': "playlist",
                'id': "gaybeeg",
                'title': "gaybeeg",
                'entries': entries
            }          
   
            
        except ExtractorError as e:
            raise
        except Exception as e:
            self.to_screen(str(e))
            logger.error(str(e), exc_info=True)
            raise 
        
    
class GayBeegPlaylistIE(GayBeegBaseIE):
    IE_NAME = "gaybeeg:allpages:playlist"    
    _VALID_URL = r'https?://(www\.)?gaybeeg\.info/(?:((?P<type>(?:site|pornstar|tag))(?:$|(/(?P<name>[^\/$\?]+)))(?:$|/$|/(?P<search1>\?(?:tag|s)=[^$]+)$))|((?P<search2>\?(?:tag|s)=[^$]+)$))'
    
    
    def _real_extract(self, url):        
        
        try:
                                   
            self.report_extraction(url)
            
            driver = self._launch_driver()
            driver.get(url)
            
            
            el_pages = self.wait_until(driver, 15, ec.presence_of_all_elements_located((By.CLASS_NAME, "pages")))
            
            if el_pages:
                
                num_pages = int(el_pages[0].get_attribute('innerHTML').split(' ')[-1])
                self.to_screen(f"Pages to check: {num_pages}")
                el_page = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "page")))
                _href = el_page.get_attribute('href')
                list_urls_pages = [re.sub('page/\d+/', f'page/{i}/', _href) for i in range(1, num_pages+1)]
                
                self.to_screen(list_urls_pages)

                _num_workers = min(6, len(list_urls_pages))
                
                with ThreadPoolExecutor(max_workers=_num_workers) as ex:
                    futures = [ex.submit(self._get_entries, _url) for _url in list_urls_pages] 
            
                
                entries = []
                for d in futures:
                    try:
                        entries += d.result()
                    except Exception as e:
                        lines = traceback.format_exception(*sys.exc_info())
                        self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
                        raise ExtractorError(str(e)) from e
                        
            else: #single page
                self.to_screen("Single page, lets get entries")
                entries = self._get_entries(url, driver)
                                       
            if entries:
                return self.playlist_result(entries, "gaybeegplaylist", "gaybeegplaylist")
            else: raise ExtractorError("No entries")
            
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e)) from e

        finally:
            driver.quit()

        
        
class GayBeegIE(GayBeegBaseIE):
    IE_NAME = "gaybeeg:post:playlist"
    _VALID_URL = r'https?://(www\.)?gaybeeg\.info/\d\d\d\d/\d\d/\d\d/.*'
    
               
    def _real_extract(self, url):        
        
        try:
                 
            self.report_extraction(url)
            
            entries = self._get_entries(url)            
                        
            if not entries:
                raise ExtractorError("No video entries")
            else:
                return{
                    '_type': "playlist",
                    'id': "gaybeegpost",
                    'title': "gaybeegpost",
                    'entries': entries
                }      
            
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e)) from e
