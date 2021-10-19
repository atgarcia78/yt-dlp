from __future__ import unicode_literals


import re
from .common import InfoExtractor
from ..utils import (
    ExtractorError,   
    std_headers,
    sanitize_filename,
    int_or_none,

)

import httpx
import html
import demjson
import time

from concurrent.futures import ThreadPoolExecutor

from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
import os
from urllib.parse import unquote

from threading import Lock


class YourPornGodIE(InfoExtractor):
    
    IE_NAME = 'yourporngod'
    _VALID_URL = r'https?://(?:www\.)?yourporngod\.com/videos/(?P<id>\d+)/(?P<title>[^\/\$]+)'
    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/ultb56bi.selenium0']
    
    def _get_info(self, url):
        
        count = 0
        try:
            
            _res = None
            while (count<5):
                
                try:
                    
                    res = httpx.head(url, headers=std_headers)
                    if res.status_code > 400:
                        time.sleep(1)
                        count += 1
                    else: 
                        _size = int_or_none(res.headers.get('content-length'))
                        _url = unquote(str(res.url))
                        if _size and _url:
                            _res = {'url': _url, 'filesize': _size}                         
                            break
                        else: count += 1
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass
        
        if (count < 5): return _res
        else: return ({'error': 'Max retries'})
    
    def wait_until(self, driver, time, method):        
        
        try:
            el = WebDriverWait(driver, time).until(method)
        except Exception as e:
            el = None
    
        return(el)   
    

    def _real_extract(self, url):
        video_id = self._match_id(url)
       
               
        self.report_extraction(url)
        
        res = httpx.get(url, headers=std_headers)
        
        webpage = re.sub('[\t\n]', '', html.unescape(res.text))
        
        mobj = re.findall(r"<title>([^<]+)<", webpage)
        title = mobj[0] if mobj else re.search(self._VALID_URL, url).group('title')
        
        mobj = re.findall(r'var\s+flashvars\s*=\s*([^;]+);',webpage)
        info_video = demjson.decode(mobj[0]) if mobj else None
        if info_video: 
        
            formats = []
            
            if (_target:=info_video.get("video_url")):
                
                _url = re.findall(r'(https.*)', _target)[0]
                if (_rnd:=info_video.get('rnd')): _url = _url +"?rnd=" + _rnd
                _desc = info_video.get("video_url_text", "")
                formats.append({'format_id': 'http' + _desc, 'url': (_info:=self._get_info(_url)).get('url'), 'filesize': _info.get('filesize'), 'ext': 'mp4', 'resolution': _desc, 'height' : int_or_none(_desc[:-1] if _desc else None)})
                
            if (_urlalt:=info_video.get("video_alt_url")):
                
                _desc = info_video.get("video_alt_url_text", "")
                formats.append({'format_id': 'http' + _desc, 'url': (_info:=self._get_info(_urlalt)).get('url'), 'filesize': _info.get('filesize'), 'ext': 'mp4', 'resolution': _desc, 'height' : int_or_none(_desc[:-1] if _desc else None)})
                
            if not formats: raise ExtractorError("No formats found")
            
            self._sort_formats(formats)
            
        else:
            with YourPornGodIE._LOCK:
                prof = YourPornGodIE._FF_PROF.pop()
                YourPornGodIE._FF_PROF.insert(0, prof)
        
        
            opts = Options()
            opts.add_argument("--headless")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-application-cache")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--profile")
            opts.add_argument(prof)                        
            os.environ['MOZ_HEADLESS_WIDTH'] = '1920'
            os.environ['MOZ_HEADLESS_HEIGHT'] = '1080'                               
                                    
            driver = Firefox(options=opts)
    
            self.to_screen(f"ffprof[{prof}]")

            try:
            
                driver.maximize_window()
            
                self.wait_until(driver, 3, ec.title_is("DUMMYFORWAIT"))
    
                driver.get(url)
                el_frames = self.wait_until(driver, 60, ec.presence_of_all_elements_located(((By.TAG_NAME, "iframe"))))
                for i,el in enumerate(el_frames):
                    if "embed" in el.get_attribute('src'):
                        driver.switch_to.frame(el)
                        break
                
                el_settings = self.wait_until(driver, 60, ec.presence_of_all_elements_located(((By.CSS_SELECTOR, "a.fp-settings"))))
                _url = None
                for el in el_settings:
                    el_tag = el.find_elements(by=By.TAG_NAME, value='a')
                    for tag in el_tag:
                        if "download" in tag.get_attribute('innerHTML').lower():
                            _url = tag.get_attribute('href')
                            break
                    if _url: break
                    
                driver.get(_url)
                el_video = self.wait_until(driver, 60, ec.presence_of_element_located(((By.CSS_SELECTOR, "video.fp-engine"))))
                video_url = el_video.get_attribute('src') if el_video else None
                if not video_url: raise ExtractorError("No video url")
                
                formats = [{'format_id': 'http', 'url': (_info:=self._get_info(video_url)).get('url'), 'filesize': _info.get('filesize'), 'ext': 'mp4'}]
            except Exception as e:
                self.to_screen(e)
                raise
            finally:
                driver.quit()
        
        
        entry = {
                'id' : video_id,
                'title' : sanitize_filename(title, restricted=True),
                'formats' : formats,
                'ext': 'mp4'
            }
        
        return entry
    
class YourPornGodPlayListIE(InfoExtractor):
    
    IE_NAME = 'yourporngod:playlist'
    _VALID_URL = r'https?://(?:www\.)?yourporngod\.com/(?:((?P<type1>playlists)/(?P<id>\d+)/(?P<title>[^\/\$]+))|((?P<type3>models)/(?P<model>[^\/\$]+))|((?P<type2>categories)/(?P<categorie>[^\/\$]+)))'
    _SEARCH_URL = {"playlists" : "?mode=async&function=get_block&block_id=playlist_view_playlist_view&sort_by=added2fav_date&from=",
                   "models" : "?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed&from=",
                   "categories": "?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed&from="}
    _REGEX_ENTRIES = {"playlists": r'data-playlist-item\=[\"\']([^\'\"]+)[\'\"]',
                      "models": r'item  [\"\']><a href=["\']([^\'\"]+)[\'\"]',
                      "categories": r'item  [\"\']><a href=["\']([^\'\"]+)[\'\"]'}
    
    
    def _get_entries(self, url, _type):
        res = httpx.get(url, headers=std_headers)
        webpage = re.sub('[\t\n]', '', html.unescape(res.text))
        entries = re.findall(self._REGEX_ENTRIES[_type],webpage)
        return entries
    
    def _real_extract(self, url):
        
        
        #playlist_id = self._match_id(url)
        _type1, _type2, _type3, _id, _title, _model, _categorie = re.search(self._VALID_URL, url).group('type1','type2','type3','id','title','model','categorie')
        
        _type = _type1 or _type2 or _type3
                      
        self.report_extraction(url)
        
        res = httpx.get(url, headers=std_headers)
        
                
        webpage = re.sub('[\t\n]', '', html.unescape(res.text))
        
        mobj = re.findall(r"<title>([^<]+)<", webpage)
        title = mobj[0] if mobj else _title or _model or _categorie
        
        playlist_id = _id or _model or _categorie
        
        
        mobj = re.findall(r'\:(\d+)[\"\']>Last', webpage)        
        last_page = int(mobj[0]) if mobj else 1
        
        base_url = url + self._SEARCH_URL[_type]
        
        
        
        with ThreadPoolExecutor(max_workers=16) as ex:        
            
            futures = [ex.submit(self._get_entries, base_url + str(i), _type) for i in range(1,last_page+1)]
                
        res = []
        
        for fut in futures:
            try:
                res += fut.result()
            except Exception as e:
                pass
            
        entries = [self.url_result(_url, ie="YourPornGod") for _url in res]
        
        return {
            
            '_type': 'playlist',
            'id': playlist_id,
            'title': sanitize_filename(title,restricted=True),
            'entries': entries,
            
        }   
        
                
 




