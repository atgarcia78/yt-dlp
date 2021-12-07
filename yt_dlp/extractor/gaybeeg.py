from __future__ import unicode_literals

import re


from ..utils import ExtractorError

from .webdriver import SeleniumInfoExtractor

from concurrent.futures import (
    ThreadPoolExecutor   
)


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


from .netdna import NetDNAIE

import logging
import traceback
import sys

from datetime import datetime


class GayBeegBaseIE(SeleniumInfoExtractor):
    
    
    @staticmethod
    def _get_entries_netdna(el_list):
        
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
        
        for _url, _item in _list_urls_netdna.items():
            
            _info_video = NetDNAIE.get_video_info(_item.get('text'))
            _info_date = datetime.strptime(_item.get('date'), '%B %d, %Y')
            entries.append({'_type' : 'url_transparent', 'url' : _url, 'ie' : 'NetDNA', 'title': _info_video.get('title'), 'id' : _info_video.get('id'), 'ext': _info_video.get('ext'), 'filesize': _info_video.get('filesize'), 'release_date': _info_date.strftime('%Y%m%d'), 'release_timestamp': int(_info_date.timestamp())})
        
                                    
        return entries
    
    @staticmethod
    def _get_entries_gaybeeg(el_list):
        entries = [{'_type' : 'url', 'url' : _url, 'ie' : 'GayBeeg'}
                        for el in el_list
                                    for el_tagh2 in el.find_elements(by=By.TAG_NAME, value="h2")
                                        for el_taga in el_tagh2.find_elements(by=By.TAG_NAME, value="a")
                                            if "//gaybeeg.info" in (_url:=el_taga.get_attribute('href'))]    
        return entries
    
 
    
    
    def _get_entries(self, url, driver=None):
        
        try:
        
            if not driver:
                _keep = False
                driver = self.get_driver()
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
        
            
            
            el_a_list = self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.XPATH, '//a[contains(@href, "//netdna-storage.com")]')))
            
            if el_a_list:
                
                entries = GayBeegBaseIE._get_entries_netdna(el_a_list)
            
                return entries
            
        finally:
            if not _keep: 
                try:
                    self.rm_driver(driver)
                except Exception:
                    pass
            
            
        
                


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
            self.to_screen(repr(e))            
            raise 

class GayBeegPlaylistIE(GayBeegBaseIE):
    IE_NAME = "gaybeeg:allpages:playlist"    
    _VALID_URL = r'https?://(www\.)?gaybeeg\.info/(?:((?P<type>(?:site|pornstar|tag))(?:$|(/(?P<name>[^\/$\?]+)))(?:$|/$|/(?P<search1>\?(?:tag|s)=[^$]+)$))|((?P<search2>\?(?:tag|s)=[^$]+)$))'
    
    
    def _real_extract(self, url):        
        
        try:
                                   
            self.report_extraction(url)
            
            driver = self.get_driver()
            driver.get(url)
            
            
            el_pages = self.wait_until(driver, 15, ec.presence_of_all_elements_located((By.CLASS_NAME, "pages")))
            
            if el_pages:
                
                num_pages = int(el_pages[0].get_attribute('innerHTML').split(' ')[-1])
                self.to_screen(f"Pages to check: {num_pages}")
                el_page = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "page")))
                _href = el_page.get_attribute('href')
                list_urls_pages = [re.sub(r'page/\d+', f'page/{i}', _href) for i in range(1, num_pages+1)]
                
                self.to_screen(list_urls_pages)
                
                self.rm_driver(driver)

                _num_workers = min(4, len(list_urls_pages))
                
                with ThreadPoolExecutor(thread_name_prefix="gaybeeg", max_workers=_num_workers) as ex:
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
            try:
                self.rm_driver(driver)
            except Exception:
                pass

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