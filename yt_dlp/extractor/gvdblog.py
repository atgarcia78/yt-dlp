from __future__ import unicode_literals

import json
import re
import sys
import traceback
from datetime import datetime
import time

from ..utils import ExtractorError, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_1, By, ec

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
        return(videos)            
        

class GVDBlogBaseIE(SeleniumInfoExtractor):
    
    

    def getbestvid(self, x, check=True):

        
        if not check: return x[0] if isinstance(x, list) else x
        _x = x if isinstance(x, list) else [x]
        for el in _x:
            ie = self._downloader.get_info_extractor(self._get_ie_key(el))
            ie._real_initialize()
            if (func:=getattr(ie, '_video_active', None)): #tubeload
                if (_entry:=func(el)): return _entry
                else: continue                    
            else:
                _entry = ie._real_extract(el)
                _entry.update({'webpage_url': el, 'extractor': 'doodstream', 'extractor_key': 'DoodStream'})
                return _entry
            
    def get_entries(self, url, check=True):
        
        self.report_extraction(url)
        driver = self.get_driver(usequeue=True)

        try:
            
            self._send_request(url, driver)
            if (el_ifr:=driver.find_elements(By.ID, "injected-iframe")):
                
                driver.switch_to.frame(el_ifr[0])
                
                el_button = self.wait_until(driver, 1, ec.presence_of_element_located((By.CSS_SELECTOR, "a.maia-button.maia-button-primary")))
                if el_button: 
                    el_button.click()
                    self.wait_until(driver, 5)
                
                driver.switch_to.default_content()
            
            postdate = try_get(self.wait_until(driver, 1, ec.presence_of_all_elements_located((By.CSS_SELECTOR, "time.published"))), lambda x: datetime.strptime(x[0].text, '%B %d, %Y'))
            list_candidate_videos = self.wait_until(driver, 30, getvideos())
            entries = [_entry for _el in list_candidate_videos if (_entry:=self.getbestvid(_el, check=check))]
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
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e))
        finally:
            self.put_in_queue(driver)

    
    @dec_on_exception
    @limiter_1.ratelimit("gvdblog", delay=True)
    def _send_request(self, url, driver=None):
        
        self.logger_debug(f"[_send_request] {self._get_url_print(url)}") 
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
             
        
        