# coding: utf-8
from __future__ import unicode_literals

import re

import time
from ..utils import ExtractorError

from .common import InfoExtractor

from concurrent.futures import (
    ThreadPoolExecutor
)

import traceback
import sys
import threading



from selenium.webdriver import Firefox, FirefoxProfile
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


from queue import Queue

from .netdna import NetDNAIE

import logging

logger = logging.getLogger("gaybeeg")

class GayBeegBaseIE(InfoExtractor):
    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/0khfuzdw.selenium0']
    
    
    
    def _get_entries_netdna(self, el_list):
        
        _list_urls_netdna = []
        for _el in el_list:
            for _el_tag in _el.find_elements_by_tag_name("a"):
                if "netdna-storage" in (_url:=_el_tag.get_attribute('href')):
                    _list_urls_netdna.append(_url)
        _final_list = list(set(_list_urls_netdna))
        
        logger.info(_final_list)
        
        entries = []
        
        for _item in _final_list:
            _info_video = NetDNAIE.get_video_info(_item)
            entries.append({'_type' : 'url', 'url' : _item, 'ie' : 'NetDNA', 'title': _info_video.get('title'), 'id' : _info_video.get('id'), 'filesize': _info_video.get('filesize')})
                
  
                                    
        return entries
    
   
    def _get_entries_gaybeeg(self, el_list):
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

class GayBeegPlaylistPageIE(GayBeegBaseIE):
    IE_NAME = "gaybeeg:onepage:playlist"
    _VALID_URL = r'https?://(www\.)?gaybeeg\.info.*/page/.*'
    
    _lock = threading.Lock()
        
    
    def _real_extract(self, url):        
        
        try:
            opts = Options()
            opts.headless = True
            with self._lock:
                prof_ff = self._FF_PROF.pop() 
                self._FF_PROF.insert(0,prof_ff)
            
            driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof_ff))            
            
            driver.set_window_size(1920,575)
            self.to_screen(f"[worker_pl_main] init with ffprof[{prof_ff}]")          
            self.report_extraction(url)
            driver.get(url)
            time.sleep(1) 
            el_list = WebDriverWait(driver, 120).until(ec.presence_of_all_elements_located((By.CLASS_NAME, "hentry-large")))
           
                           
            entries_final = self._get_entries_netdna(el_list) if el_list else None         
   
            
        except Exception as e:
            self.to_screen(str(e))
            logger.error(str(e), exc_info=True)
            raise 
        finally:
            driver.quit()        
        
        return {
            '_type': "playlist",
            'id': "gaybeeg",
            'title': "gaybeeg",
            'entries': entries_final
        } 
    
class GayBeegPlaylistIE(GayBeegBaseIE):
    IE_NAME = "gaybeeg:allpages:playlist"    
    _VALID_URL = r'https?://(www\.)?gaybeeg\.info/(?:((?P<type>(?:site|pornstar|tag))(?:$|(/(?P<name>[^\/$\?]+)))(?:$|/$|/(?P<search1>\?(?:tag|s)=[^$]+)$))|((?P<search2>\?(?:tag|s)=[^$]+)$))'
    
    _lock = threading.Lock()
        
    def _worker_pl(self, i):        
               
        
        try:
            
            opts = Options()
            opts.headless = True
            with self._lock:
                prof_ff = self._FF_PROF.pop() 
                self._FF_PROF.insert(0,prof_ff)
            driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof_ff))            
            
            driver.set_window_size(1920,575)
                    
            
            while not self.queue_in.empty():
                
                info_dict = self.queue_in.get()
                url_p = info_dict['url']
                npage = info_dict['page']
                self.to_screen(f"[worker_pl{i}] page {npage}  {url_p}")
                if url_p == "KILL":
                    
                    self.completed += 1
                    self.to_screen(f"[worker_pl{i}] bye bye, completed {self.completed}")                   
                    break
                elif url_p == "KILLANDCLEAN":
                    while(self.completed < self.workers - 1):
                        time.sleep(1)
                        self.to_screen(f"[worker_pl{i}] completed {self.completed}")
                    pending_pages = list(self.queue_nok.queue)
                    if pending_pages:
                        self.to_screen(f"[worker_pl{i}] retry with pending pages \n {pending_pages}")
                        for info_page in pending_pages:
                            self.queue_in.put(info_page)
                        self.queue_in.put({'url': "KILL", 'page': 0})
                        continue
                    else:
                        self.to_screen(f"[worker_pl{i}] no need to retry pending pages") 
                        break
                        
                else:
                    try:
                        driver.get(url_p)
                        time.sleep(1)                

                        el_list = WebDriverWait(driver, 120).until(ec.presence_of_all_elements_located((By.CLASS_NAME, "hentry-large")))
                        if el_list:
                            
                            _entries = self._get_entries_netdna(el_list)
                            if _entries:
                                for entry in _entries:
                                    if entry.get('id'): self.queue_entries.put(entry)
                            self.to_screen(f"[worker_pl{i}]: entries [{len(_entries)}]\n {_entries}")

                        else:
                            self.queue_nok.put({'url': url_p, 'page': npage})
                    except Exception as e:
                        self.to_screen(f"[worker_pl{i}] {e}")
                        self.queue_nok.put({'url': url_p, 'page': npage})
                    
        except Exception as e:
            self.to_screen(f"[worker_pl{i}] {e}")
            logger.error(str(e), exc_info=True)

        finally:
            driver.quit()
        

        
    
    def _real_extract(self, url):        
        
        try:
            
            self.queue_in = Queue()
            self.queue_entries= Queue()
            self.queue_nok = Queue()
            
            opts = Options()
            opts.headless = True
            with self._lock:
                prof_ff = self._FF_PROF.pop() 
                self._FF_PROF.insert(0,prof_ff)
                
            driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof_ff))            
            
            driver.set_window_size(1920,575)
            
            
            self.to_screen(f"[worker_pl_main] init with ffprof[{prof_ff}]")
            
            driver.get("https://gaybeeg.info") 
            self.wait_until(driver, 30, ec.title_contains("GayBeeg"))
                        
            self.report_extraction(url)
            driver.get(url)
            time.sleep(1)                
            el_list = self.wait_until(driver, 120, ec.presence_of_all_elements_located((By.CLASS_NAME, "hentry-large")))
            if el_list:
                
                _entries = self._get_entries_netdna(el_list)
                if _entries:
                    logger.info(_entries)
                    for entry in _entries:
                        if entry.get('id'): self.queue_entries.put(entry)
            
            
            
            mobj = re.search(self._VALID_URL,url)
            
            _type, _name, _search1, _search2 = mobj.group('type','name','search1','search2')
            
            _search = _search1 or _search2
            
            
            _items_url_fix = [_item for _item in ["https://gaybeeg.info",_type,_name] if _item]
            
            _url_fix = "/".join(_items_url_fix)
            
            el_pagination = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CLASS_NAME, "pagination")))
            
            if el_pagination:
                webpage = el_pagination[0].get_attribute("innerHTML")
                _n_pages = re.search(r'Page 1 of (?P<n_pages>[\d]+)<', webpage)
                if _n_pages:
                    n_pages = int(_n_pages.group("n_pages"))
                else:
                    n_pages = 0
                
                self.to_screen(f"[worker_pl_main] Playlist with {n_pages} pages including this main page. Starting to process the pending {n_pages - 1} pages")
                if n_pages == 2:
                    _items_url = [_item for _item in [_url_fix,"page","2", _search] if _item]
                    _url = "/".join(_items_url)                   
                    driver.get(_url)
                    time.sleep(1) 
                    el_list = self.wait_until(driver, 120, ec.presence_of_all_elements_located((By.CLASS_NAME, "hentry-large")))
                    #self.to_screen([el.text for el in el_list])
                    if el_list:
                        _entries = self._get_entries_netdna(el_list)
                        if _entries:
                            for entry in _entries:
                                if entry.get('id'): self.queue_entries.put(entry)
                        self.to_screen(f"[worker_pl_main]: entries [{len(_entries)}]\n {_entries}")
                elif n_pages > 2:    
                    for num in range(2,n_pages+1):
                        _items_url = [_item for _item in [_url_fix,"page",str(num), _search] if _item]
                        _url = "/".join(_items_url) 
                        
                        self.queue_in.put({'url': _url, 'page': num})
                                                
                    for _ in range(min(16,n_pages-1) - 1):
                        self.queue_in.put({'url': "KILL", 'page': 0})
                        
                    self.queue_in.put({'url': "KILLANDCLEAN", 'page': 0})
                        
                    self.to_screen(list(self.queue_in.queue))
                    
                    
                    self.workers = min(12,n_pages-1)
                    self.total = n_pages - 1
                    self.completed = 0
                    self.to_screen(f"[worker_pl_main] nworkers pool [{self.workers}] total pages to download [{self.total}]")
                    
                
                    with ThreadPoolExecutor(max_workers=self.workers) as ex:
                        for i in range(self.workers):
                            ex.submit(self._worker_pl,i) 
 
                    
            entries_final = list(self.queue_entries.queue)   
            
        except Exception as e:
            self.to_screen(str(e))
            logger.error(str(e), exc_info=True)

        finally:
            driver.quit()        
        
        return {
            '_type': "playlist",
            'id': "gaybeeg",
            'title': "gaybeeg",
            'entries': entries_final
        }       
        
        
class GayBeegIE(GayBeegBaseIE):
    IE_NAME = "gaybeeg:post:playlist"
    _VALID_URL = r'https?://(www\.)?gaybeeg\.info/\d\d\d\d/\d\d/\d\d/.*'
    

    _lock = threading.Lock()
            
    def _real_extract(self, url):        
        
        try:
            entries = None

            opts = Options()
            opts.headless = True
            with self._lock:
                prof_ff = self._FF_PROF.pop() 
                self._FF_PROF.insert(0,prof_ff)
                
            driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof_ff))            
            
            driver.set_window_size(1920,575)            
            
            
            self.to_screen(f"[worker_pl_main] init with ffprof[{prof_ff}]")
         
            self.report_extraction(url)
            driver.get(url)
            time.sleep(1)                
            el_list = WebDriverWait(driver, 120).until(ec.presence_of_all_elements_located((By.CLASS_NAME, "hentry-large")))
            
            
            entries = self._get_entries_netdna(el_list) if el_list else None
            
        except Exception as e:
            logger.error(str(e), exc_info=True)

        finally:
            driver.quit()
            
        if not entries:
            raise ExtractorError(f'no video info: {str(e)}')
        else:
            return{
                '_type': "playlist",
                'id': "gaybeeg",
                'title': "gaybeeg",
                'entries': entries
            }      
        
