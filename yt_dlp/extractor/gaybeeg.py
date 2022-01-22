from __future__ import unicode_literals

import re

from ..utils import (
    ExtractorError,
    try_get)

from .commonwebdriver import (
    SeleniumInfoExtractor)

from concurrent.futures import ThreadPoolExecutor  

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

import traceback
import sys

from datetime import datetime

from backoff import on_exception, constant
from ratelimit import limits, sleep_and_retry

from urllib.parse import unquote



class visible():
    def __init__(self, logger):
        self.old_len = -1
        self.logger = logger
        
    def __call__(self, driver):
        el_footer = driver.find_element(By.ID, "footer")        
        driver.execute_script("window.scrollTo(arguments[0]['x'], arguments[0]['y']);", el_footer.location)
       
        try:
            el_iter = driver.find_elements(By.CLASS_NAME, "button")            
            el_button_list = [el for el in el_iter if (not el.get_attribute('type') and "//netdna-storage.com" in el.get_attribute('href'))] if el_iter else []
            el_a_list = driver.find_elements(By.XPATH, '//a[contains(@href, "//netdna-storage.com")]')
            el_list = list(set(el_button_list + el_a_list))
            if (new_len:=len(el_list)) != self.old_len:
                self.old_len = new_len
                return False
            else:
                if not el_list: return -2
                
                for el in el_list:
                    if (not (_link:=el.get_attribute("href")) or "javascript:void" in _link):
                        self.logger(f"[get_entries][{driver.current_url}] ERROR {el.get_attribute('outerHTML')}")                        
                        return -1
                    
               
                #el_a_netdna_list = driver.find_elements(By.XPATH, '//a[contains(@href, "//netdna-storage.com")]')
                return el_list
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.logger(f'[get_entries][{driver.current_url}] ERROR {repr(e)}\n{"!!".join(lines)}')
            raise
            

class GayBeegBaseIE(SeleniumInfoExtractor):

    def _get_entries_netdna(self, el_list):
        
        _list_urls_netdna = {}
        _next = None
        for _el in el_list:
            _url = _el.get_attribute('href')
            _tree = _el.find_elements(by=By.XPATH, value="./ancestor-or-self::*")
            _tree.reverse()
            if _next:
                _list_urls_netdna[_url] = {'text': _next}
                _next = None
            else:
                if any((_res:=el.text) for el in _tree):
            
                    _text = _res.splitlines()
                    _list_urls_netdna[_url] = {'text': _text[0]}
                    if len(_text) == 2 and any(_ext in _text[1] for _ext in ('mp4', 'zip')):
                        _next = _text[1]
            if any((_el_date:=el.find_elements(by=By.CLASS_NAME, value='date')) for el in _tree):
                    _date = _el_date[0].text
                    _list_urls_netdna[_url].update({'date': _date})
                    

        entries = []
        ie_netdna = self._downloader.get_info_extractor('NetDNA')
        _num_workers = min(SeleniumInfoExtractor._MAX_NUM_WEBDRIVERS, len(_list_urls_netdna))
        with ThreadPoolExecutor(thread_name_prefix="ent_netdna", max_workers=_num_workers) as ex:
            futures = {ex.submit(ie_netdna.get_video_info_url, _url): _url for _url in list(_list_urls_netdna.keys())}
        
        for fut in futures:
            try:
                res = fut.result()
                if not res:
                    self.to_screen(f'[get_entries_netdna][{futures[fut]}] no entries')
                    _list_urls_netdna[futures[fut]].update({'info_video': {}})
                elif (_errormsg:=res.get('error')):
                    self.to_screen(f'[get_entries_netdna][{futures[fut]}] ERROR {_errormsg}')
                    _list_urls_netdna[futures[fut]].update({'info_video': {}})
                    
                else:
                    _list_urls_netdna[futures[fut]].update({'info_video': res})
                                
            except Exception as e:
                self.to_screen(f'[get_entries_netdna][{futures[fut]}] ERROR ] {repr(e)}') 
                _list_urls_netdna[futures[fut]].update({'info_video': {}})
                
        for _url, _item in _list_urls_netdna.items():
            
            
            try: 
                _info_video = _item.get('info_video')
                if not _info_video: continue
                _info_date = datetime.strptime(_item.get('date'), '%B %d, %Y') if _item.get('date') else None
                _ent = {'_type' : 'url_transparent', 'url' : _url, 'ie_key' : 'NetDNA', 'title': _info_video.get('title'), 'id' : _info_video.get('id'), 'ext': _info_video.get('ext'), 'filesize': _info_video.get('filesize')}                
                if _info_date: _ent.update({'release_date': _info_date.strftime('%Y%m%d'), 'release_timestamp': int(_info_date.timestamp())})
                entries.append(_ent)
            except Exception as e:
                self.to_screen(f'{_url}: {repr(e)}')                
        
                                    
        return entries
    
      
    
   
    @on_exception(constant, Exception, max_tries=5, jitter=None, interval=15)
    @sleep_and_retry
    @limits(calls=1, period=1) 
    def _get_entries(self, url):
        
        
        try:
        
            _driver = self.get_driver(usequeue=True)

            self.to_screen(f'[get_entries] {url}')

            self.send_request(_driver, url)

            el_netdna_list = self.wait_until(_driver, timeout=60, method=visible(self.to_screen))
            
                        
            if el_netdna_list == -1:
                raise Exception("void link found")
            elif el_netdna_list == -2:
                self.to_screen(f"[{url}] no links netdna")
                return []
            else:
                self.to_screen(f"[{url}] list combination links: {len(el_netdna_list)}")
                return self._get_entries_netdna(el_netdna_list)
            
        except Exception as e:
            self.to_screen(f'[get_entries][{url}] {repr(e)}')
            raise
        finally:
            self.put_in_queue(_driver)
           

    @sleep_and_retry
    @limits(calls=1, period=1)  
    def send_request(self, driver, url):
        
        try:        
            driver.execute_script("window.stop();")
        except Exception:
            pass
        driver.get(url)
        
        
    @on_exception(constant, Exception, max_tries=5, interval=5)
    @sleep_and_retry
    @limits(calls=1, period=1)    
    def get_info_pages(self, url):
        res = self._CLIENT.get(url)
        res.raise_for_status()
        num_pages = try_get(re.findall(r'class="pages">Page 1 of ([\d\,]+)', res.text), lambda x: int(x[0].replace(',',''))) or 1
        if num_pages == 1: _href = url
        else: _href = try_get(re.findall(r'class="page" title="\d">\d</a><a href="([^"]+)"', res.text), lambda x: unquote(x[0]))
        return num_pages, _href
        
    def _real_initialize(self):
        super()._real_initialize()
        
class GayBeegPlaylistPageIE(GayBeegBaseIE):
    IE_NAME = "gaybeeg:onepage:playlist"
    _VALID_URL = r'https?://(www\.)?gaybeeg\.info.*/page/.*'
    
    def _real_initialize(self):
        super()._real_initialize()
        
    def _real_extract(self, url):        
        
        try:
                   
            self.report_extraction(url)
            
            entries = self._get_entries(url)
            
            if not entries: raise ExtractorError("No entries")  
                      
            return self.playlist_result(entries, "gaybeeg", "gaybeeg")
            
   
            
        except ExtractorError as e:
            raise
        except Exception as e:
            self.to_screen(repr(e))            
            raise ExtractorError(repr(e))

class GayBeegPlaylistIE(GayBeegBaseIE):
    IE_NAME = "gaybeeg:allpages:playlist"    
    _VALID_URL = r'https?://(www\.)?gaybeeg\.info/(?:((?P<type>(?:site|pornstar|tag))(?:$|(/(?P<name>[^\/$\?]+)))(?:$|/$|/(?P<search1>\?(?:tag|s)=[^$]+)$))|((?P<search2>\?(?:tag|s)=[^$]+)$))'
    
    def _real_initialize(self):
        super()._real_initialize()
        
        
    def _real_extract(self, url):        
        
        try:
                                   
            self.report_extraction(url)

            

            num_pages, _href = self.get_info_pages(url) 

            self.to_screen(f"Pages to check: {num_pages}")                    
                
            list_urls_pages = [re.sub(r'page/\d+', f'page/{i}', _href) for i in range(1, num_pages+1)]
            
            self.to_screen(list_urls_pages)
            
            _num_workers = min(SeleniumInfoExtractor._MAX_NUM_WEBDRIVERS, len(list_urls_pages))
            
            with ThreadPoolExecutor(thread_name_prefix="gybgpages", max_workers=_num_workers) as ex:
                futures = {ex.submit(self._get_entries, _url): _url for _url in list_urls_pages}
                
            entries = []
            for fut in futures:
                try:
                    res = fut.result()
                    entries += res
                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f'[{futures[fut]}] {repr(e)} \n{"!!".join(lines)}')  
                    #raise ExtractorError(repr(e))

            if entries:
                return self.playlist_result(entries, "gaybeegplaylist", "gaybeegplaylist")
            else: raise ExtractorError("No entries")
            
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(repr(e))



class GayBeegIE(GayBeegBaseIE):
    IE_NAME = "gaybeeg:post:playlist"
    _VALID_URL = r'https?://(www\.)?gaybeeg\.info/\d\d\d\d/\d\d/\d\d/.*'
    
    def _real_initialize(self):
        super()._real_initialize()           
    
    def _real_extract(self, url):        
        
        try:
                 
            self.report_extraction(url)
            
            entries = self._get_entries(url)            
                        
            if not entries:
                raise ExtractorError("No video entries")
            else:
                return self.playlist_result(entries, "gaybeegpost", "gaybeegpost")  
            
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(repr(e))