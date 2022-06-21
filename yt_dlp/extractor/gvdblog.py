from __future__ import unicode_literals

import json
import re
import sys
import traceback
from datetime import datetime
import time

from ..utils import ExtractorError, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_0_1, limiter_0_5, By, ec

from concurrent.futures import ThreadPoolExecutor

class getvideos():
    def __call__(self, driver):
        el_iframes = driver.find_elements(By.TAG_NAME, "iframe")
        videos = []
        _subvideos = []
        if el_iframes:
            for _ifr in el_iframes:
                if _ifr.get_attribute("allowfullscreen"):
                    if _ifr.get_attribute("mozallowfullscreen"):
                        _subvideos.append(_ifr.get_attribute('src'))
                    else:
                        _vid = _ifr.get_attribute('src')
                        if _subvideos:
                            _subvideos.append(_vid)
                            videos.append(_subvideos)
                            _subvideos = []
                        else: videos.append(_vid)
        if _subvideos:
            if len(_subvideos) == 1: _subvideos = _subvideos[0]
            videos.insert(0, _subvideos)        
        if not videos: return False
        return(videos)

class check_consent():
    def __init__(self):
        self.init = True
        self.button = None
    def __call__(self, driver):

        if self.init:
            if (el_ifr:=driver.find_elements(By.ID, "injected-iframe")):

                driver.switch_to.frame(el_ifr[0])
                self.init = False

                if (el_button:=driver.find_elements(By.CSS_SELECTOR, "a.maia-button.maia-button-primary")):
                  
                    self.button = el_button[0]
                    el_button[0].click()
                    driver.switch_to.default_content()
                    return True


            else:
                return True

        if not self.button:
            if (el_button:=driver.find_elements(By.CSS_SELECTOR, "a.maia-button.maia-button-primary")):
                print("button ok")
                self.button = el_button[0]
                el_button[0].click()
                driver.switch_to.default_content()
                return True
                
class get_postdate():
    def __call__(self, driver):
        el_postdate = driver.find_element(By.CSS_SELECTOR, "time.published")
        if (_text:=el_postdate.text):
            return _text
        else: return False
        
                    
                
        

class GVDBlogBaseIE(SeleniumInfoExtractor):
    
    

    def getbestvid(self, x, check=True, msg=None):

        _x = x if isinstance(x, list) else [x]
        _x.sort(reverse=True) #tube prior to dood
        
        if msg: pre = f'{msg} '
        else: pre = ' '
       
        for el in _x:
            ie = self._downloader.get_info_extractor(ie_key:=self._get_ie_key(el))
            ie._real_initialize()
            
            try:
                _entry = ie._get_entry(el, check_active=check, msg=pre)
                if _entry:
                    self.to_screen(f"{pre}OK:{self._get_url_print(el)}")
                    return _entry
                else:
                    self.report_warning(f'{pre}[{self._get_url_print(el)}] WARNING get entry {repr(e)}')
            except Exception as e:
                self.report_warning(f'{pre}[{self._get_url_print(el)}] WARNING get entry {repr(e)}')
                
               
            
    def get_entries(self, url, check=True):
        
        self.report_extraction(url)
        driver = self.get_driver()

        try:
            
            self._send_request(url, driver, msg='[get_entries]')
            
            self.wait_until(driver, 30, check_consent())
            
            postdate = try_get(self.wait_until(driver, 30, get_postdate()), lambda x: datetime.strptime(x.text, '%B %d, %Y'))  

            list_candidate_videos = self.wait_until(driver, 30, getvideos())
            pre = f'{self._get_url_print(url)}: [get_entry]'
            
            entries = []
            if (_len:=len(list_candidate_videos)) > 1:
                with ThreadPoolExecutor(thread_name_prefix="gvdblog_pl", max_workers=min(len(list_candidate_videos), 5)) as exe:
                    futures = {exe.submit(self.getbestvid, _el, check=check, msg=pre): _el for _el in list_candidate_videos}
                
                #entries = [_entry for _el in list_candidate_videos if (_entry:=self.getbestvid(_el, check=check))]
                
                for fut in futures:
                    try:
                        entries.append(fut.result())
                    except Exception as e:
                        self.to_screen(f'[get_entries][{url}] entry [{futures[fut]}] {repr(e)}')
                
            elif _len == 1:
                entries.append(self.getbestvid(list_candidate_videos[0], check=check, msg=pre))
            
            if not entries: raise ExtractorError("no video urls")

            _entryupdate = {'original_url': url}
            
            if postdate: 
                _entryupdate.update({
                    'release_date': postdate.strftime('%Y%m%d'),
                    'release_timestamp': int(postdate.timestamp())})

            for _el in entries:
                _el.update(_entryupdate)
            
            return entries
        
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'[get_entries][{url}] {repr(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e))
        finally:
            self.rm_driver(driver)

    
    @dec_on_exception
    @limiter_0_1.ratelimit("gvdblog", delay=True)
    def _send_request(self, url, driver=None, msg=None):
        
        if msg: pre = f'{msg}[_send_request]'
        else: pre = '[_send_request]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}") 
        if driver:
            driver.get(url)
        else:
            return(self.send_http_request(url))
        


    def _real_initialize(self):
        super()._real_initialize()

class GVDBlogPostIE(GVDBlogBaseIE):
    IE_NAME = "gvdblogpost:playlist"
    _VALID_URL = r'https?://(www\.)?gvdblog\.com/\d{4}/\d+/.+\.html'
    

    def _real_initialize(self):
        super()._real_initialize()
               
    def _real_extract(self, url):
        
        entries = self.get_entries(url)
        if not entries: raise ExtractorError("no videos")
            
        return self.playlist_result(entries, f"gvdblogpost_playlist", f"gvdblogpost_playlist")
                

        
class GVDBlogPlaylistIE(GVDBlogBaseIE):
    IE_NAME = "gvdblog:playlist"
    _VALID_URL = r'https?://(?:www\.)?gvdblog.com/search\?(?P<query>.+)'
    
    
    def _real_initialize(self):
        super()._real_initialize()
               
    def _real_extract(self, url):
        
        def getter(x):

            if not x:
                return []
            if _jsonstr:=x.group("data"):
                return json.loads(_jsonstr).get('feed', {}).get('entry', [])
        
        self.report_extraction(url)
        
        query = re.search(self._VALID_URL, url).group('query')
        
        params = { el.split('=')[0]: el.split('=')[1] for el in query.split('&') if el.count('=') == 1}
        
        urlquery = f"https://www.gvdblog.com/feeds/posts/full?alt=json-in-script&max-results=99999"
        
        if _category:=params.get('label'):
            urlquery += f"&category={_category}"
        _check = True 
        if params.get('check','').lower() == 'no':
            _check = False
        
        res = self._send_request(urlquery)
        if not res: raise ExtractorError("no search results")
        video_entries = try_get(re.search(r"gdata.io.handleScriptLoaded\((?P<data>.*)\);", res.text), getter)
        if not video_entries: raise ExtractorError("no video entries")
        
        self._entries = []
                
        def get_list_entries(_entry, check):
            
            videourlpost = _entry['link'][-1]['href']
            entries = self.get_entries(videourlpost, check=check)

                    
            if entries:
                self._entries += entries
 
            else:
                self.report_warning(f'[{url}][{videourlpost}] couldnt get video from this entry')
        
                
        with ThreadPoolExecutor(thread_name_prefix="gvdpl") as ex:
                
            futures = [ex.submit(get_list_entries, _entry, _check) for _entry in video_entries]       


        if not self._entries: raise ExtractorError("no video list")
        return self.playlist_result(self._entries, f"gvdblog_playlist", f"gvdblog_playlist")
             
        
        