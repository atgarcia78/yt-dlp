# coding: utf-8
from __future__ import unicode_literals

import re

import time
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


from queue import Queue

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
    _QUEUE = Queue()
    _DRIVER = 0
    
    @staticmethod
    def _get_entries_netdna(el_list):
        
        _list_urls_netdna = {}
        for _el in el_list:
            _url = _el.get_attribute('href')
            _list_urls_netdna[_url] = _el.text
         
        
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
    
    
    def _get_entries(self, url):
        
        try:
        
            self._launch_driver()
            
            driver = GayBeegBaseIE._QUEUE.get(block=True)
            
            
            driver.get(url)
            
            SCROLL_PAUSE_TIME = 2

            last_height = driver.execute_script("return document.body.scrollHeight")

            while True:
                # Scroll down to bottom
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

                # Wait to load page
                self.wait_until(driver, SCROLL_PAUSE_TIME, ec.title_is("DUMMYFORWAIT"))
                #time.sleep(SCROLL_PAUSE_TIME)                    
                

                # Calculate new scroll height and compare with last scroll height
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
        
            el_list = self.wait_until(driver, 120, ec.visibility_of_all_elements_located((By.CLASS_NAME, "button")))
                
                #el = self.wait_until(driver, 120, ec.element_to_be_clickable((By.CLASS_NAME, "button")))
                
            entries = GayBeegBaseIE._get_entries_netdna(el_list)
            
            return entries
            
        finally:
            GayBeegBaseIE._QUEUE.put_nowait(driver)
            
            
        
                
    def _launch_driver(self):
        
        with GayBeegBaseIE._LOCK:
            
            try:
  
                if GayBeegBaseIE._DRIVER == self._downloader.params.get('winit', 6):
                    return 
                
                prof_ff = GayBeegBaseIE._FF_PROF.pop() 
                GayBeegBaseIE._FF_PROF.insert(0,prof_ff) 
                
                _firefox_prof = FirefoxProfile(prof_ff)              
            
            
                opts = Options()
                opts.headless = True
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-application-cache")
                opts.add_argument("--disable-gpu")
                opts.add_argument("--disable-dev-shm-usage")
                os.environ['MOZ_HEADLESS_WIDTH'] = '1920'
                os.environ['MOZ_HEADLESS_HEIGHT'] = '1080'
                
                driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=_firefox_prof)
                
                 
                driver.maximize_window()
                
                GayBeegBaseIE._DRIVER += 1
                
                GayBeegBaseIE._QUEUE.put_nowait(driver)
                
            except ExtractorError as e:                 
                raise 
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
                raise ExtractorError(str(e)) from e
        
             
        
    
    def _real_initialize(self):
        
        try:
        
            self._launch_driver()
            
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
        finally:                         
            with GayBeegPlaylistPageIE._LOCK:
                
                try:
                    self._downloader.params.get('dict_videos_to_dl', {}).get('GayBeegPlaylistPage',[]).remove(url)
                except ValueError as e:
                    self.to_screen(str(e))
                count = len(self._downloader.params.get('dict_videos_to_dl', {}).get('GayBeegPlayList',[])) + len(self._downloader.params.get('GayBeegPlaylistPageIE', {})) + len(self._downloader.params.get('dict_videos_to_dl', {}).get('GayBeeg',[]))
                
                self.to_screen(f"COUNT: [{count}]")
                if count == 0:
                    self.to_screen("LETS CLOSE DRIVERS")
                    for __driver in list(GayBeegPlaylistIE._QUEUE.queue):
                        try:
                            __driver.quit()                            
                        except Exception as e:
                            self.to_screen(str(e))
        
        
        
    
class GayBeegPlaylistIE(GayBeegBaseIE):
    IE_NAME = "gaybeeg:allpages:playlist"    
    _VALID_URL = r'https?://(www\.)?gaybeeg\.info/(?:((?P<type>(?:site|pornstar|tag))(?:$|(/(?P<name>[^\/$\?]+)))(?:$|/$|/(?P<search1>\?(?:tag|s)=[^$]+)$))|((?P<search2>\?(?:tag|s)=[^$]+)$))'
    
       
    
    def _real_extract(self, url):        
        
        try:
                       

            driver = GayBeegPlaylistIE._QUEUE.get(block=True)
            
                                    
            self.report_extraction(url)
            
            driver.get(url)
            
            SCROLL_PAUSE_TIME = 2

            last_height = driver.execute_script("return document.body.scrollHeight")

            while True:
                # Scroll down to bottom
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

                # Wait to load page
                self.wait_until(driver, SCROLL_PAUSE_TIME, ec.title_is("DUMMYFORWAIT"))
                #time.sleep(SCROLL_PAUSE_TIME)                    
                

                # Calculate new scroll height and compare with last scroll height
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            
            
            
            el_pages = driver.find_elements_by_class_name("pages")
            
            if el_pages:
                
                num_pages = int(el_pages[0].get_attribute('innerHTML').split(' ')[-1])
                self.to_screen(num_pages)
                el_page = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "page")))
                _href = el_page.get_attribute('href')
                list_urls_pages = [re.sub('page/\d+/', f'page/{i}/', _href) for i in range(1, num_pages+1)]
                
                self.to_screen(list_urls_pages)

                _num_workers = min(6, len(list_urls_pages))
                
                with ThreadPoolExecutor(max_workers=_num_workers) as ex:
                    futures = [ex.submit(self._get_entries, _url) for _url in list_urls_pages] 
                
                    done, _ = wait(futures)
                
                entries = []
                for d in done:
                    try:
                        entries += d.result()
                    except Exception as e:
                        lines = traceback.format_exception(*sys.exc_info())
                        self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
                        raise ExtractorError(str(e)) from e
                        
            else: #single page
                entries = self._get_entries(url)
                                       
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
            GayBeegPlaylistIE._QUEUE.put_nowait(driver)
                         
            with GayBeegPlaylistIE._LOCK:
                
                try:
                    self._downloader.params.get('dict_videos_to_dl', {}).get('GayBeegPlayList',[]).remove(url)
                except ValueError as e:
                    self.to_screen(str(e))
                count = len(self._downloader.params.get('dict_videos_to_dl', {}).get('GayBeegPlayList',[])) + len(self._downloader.params.get('GayBeegPlaylistPage', {})) + len(self._downloader.params.get('dict_videos_to_dl', {}).get('GayBeeg',[]))
                
                self.to_screen(f"COUNT: [{count}]")
                if count == 0:
                    self.to_screen("LETS CLOSE DRIVERS")
                    for __driver in list(GayBeegPlaylistIE._QUEUE.queue):
                        try:
                            __driver.quit()                            
                        except Exception as e:
                            self.to_screen(str(e))
                            
        
           
        
        
class GayBeegIE(GayBeegBaseIE):
    IE_NAME = "gaybeeg:post:playlist"
    _VALID_URL = r'https?://(www\.)?gaybeeg\.info/\d\d\d\d/\d\d/\d\d/.*'
    
           
    def _real_extract(self, url):        
        
        try:
            
                 
            self.report_extraction(url)
            
            driver = GayBeegIE._QUEUE.get(block=True)
            
            driver.get(url)
            
            SCROLL_PAUSE_TIME = 2

            last_height = driver.execute_script("return document.body.scrollHeight")

            while True:
                # Scroll down to bottom
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

                # Wait to load page
                self.wait_until(driver, SCROLL_PAUSE_TIME, ec.title_is("DUMMYFORWAIT"))
                #time.sleep(SCROLL_PAUSE_TIME)                    
                

                # Calculate new scroll height and compare with last scroll height
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                         
            el_list = WebDriverWait(driver, 120).until(ec.presence_of_all_elements_located((By.CLASS_NAME, "button")))
            
            
            entries = GayBeegBaseIE._get_entries_netdna(el_list) if el_list else None
            
            if not entries:
                raise ExtractorError("No video entries")
            else:
                return{
                    '_type': "playlist",
                    'id': "gaybeeg",
                    'title': "gaybeeg",
                    'entries': entries
                }      
            
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e)) from e

        finally:
            GayBeegIE._QUEUE.put_nowait(driver) 
            
                         
            with GayBeegIE._LOCK:
                
                try:
                    self._downloader.params.get('dict_videos_to_dl', {}).get('GayBeeg',[]).remove(url)
                except ValueError as e:
                    self.to_screen(str(e))
                count = len(self._downloader.params.get('dict_videos_to_dl', {}).get('GayBeegPlayList',[])) + len(self._downloader.params.get('GayBeegPlaylistPage', {})) + len(self._downloader.params.get('dict_videos_to_dl', {}).get('GayBeeg',[]))
                
                self.to_screen(f"COUNT: [{count}]")
                if count == 0:
                    self.to_screen("LETS CLOSE DRIVERS")
                    for __driver in list(GayBeegPlaylistIE._QUEUE.queue):
                        try:
                            __driver.quit()                            
                        except Exception as e:
                            self.to_screen(str(e))
            
        
        
