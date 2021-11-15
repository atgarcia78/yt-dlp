from __future__ import unicode_literals


import re

from ..utils import (
    ExtractorError,   
    std_headers,
    sanitize_filename,
    int_or_none

)

import httpx
import html
import demjson
import time

from concurrent.futures import ThreadPoolExecutor
from .common import InfoExtractor


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
import os
from urllib.parse import unquote

from threading import Lock

from .webdriver import SeleniumInfoExtractor
class YourPornGodIE(SeleniumInfoExtractor):
    
    IE_NAME = 'yourporngod'
    _VALID_URL = r'https?://(?:www\.)?yourporngod\.com/videos/(?P<id>\d+)/(?P<title>[^\/\$]+)'
    
    _LOCK = Lock()
        
   
    def _real_extract(self, url):
        video_id = self._match_id(url)
              
        self.report_extraction(url)
        _timeout = httpx.Timeout(15, connect=15)        
        _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
        client = httpx.Client(timeout=_timeout, limits=_limits, headers=std_headers, verify=(not self._downloader.params.get('nocheckcertificate')))
        try:
            
            with YourPornGodIE._LOCK:
                res = client.get(url)
            
            webpage = re.sub('[\t\n]', '', html.unescape(res.text))
            
            mobj = re.findall(r"<title>([^<]+)<", webpage)
            title = mobj[0] if mobj else re.search(self._VALID_URL, url).group('title')
            
            mobj = re.findall(r'var\s+flashvars\s*=\s*([^;]+);',webpage)
            data = demjson.decode(mobj[0]) if mobj else None
            if data: 
            
                formats = []
                
                if (_target:=data.get("video_url")):
                    
                    _url = re.findall(r'(https.*)', _target)[0]
                    if (_rnd:=data.get('rnd')): _url = _url +"?rnd=" + _rnd
                    _desc = data.get("video_url_text", "")
                    info_video = self.get_info_for_format(_url, client)
                    if (error_msg:=info_video.get('error')): raise InfoExtractor(f"error video info - {error_msg}")
                    formats.append({'format_id': 'http' + _desc, 'url': info_video.get('url'), 'filesize': info_video.get('filesize'), 'ext': 'mp4', 'resolution': _desc, 'height' : int_or_none(_desc[:-1] if _desc else None)})
                    
                if (_urlalt:=data.get("video_alt_url")):
                    
                    _desc = data.get("video_alt_url_text", "")
                    info_video = self.get_info_for_format(_urlalt, client)
                    if (error_msg:=info_video.get('error')): raise InfoExtractor(f"error video info - {error_msg}")
                    formats.append({'format_id': 'http' + _desc, 'url': info_video.get('url'), 'filesize': info_video.get('filesize'), 'ext': 'mp4', 'resolution': _desc, 'height' : int_or_none(_desc[:-1] if _desc else None)})
                    
                #if not formats: raise ExtractorError("No formats found")
                
                
                
            else:
                try:
                    driver = self.get_driver()
                    with YourPornGodIE._LOCK:
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
                    info_video = self.get_info_for_format(video_url, client)
                    if (error_msg:=info_video.get('error')): raise InfoExtractor(f"error video info - {error_msg}")
                    
                    formats = [{'format_id': 'http', 'url': info_video.get('url'), 'filesize': info_video.get('filesize'), 'ext': 'mp4'}]
                
                except Exception as e:
                    self.to_screen(e)
                    raise
                finally:
                    try:
                        self.rm_driver(driver)
                    except Exception:
                        pass
            
            if not formats: raise ExtractorError("No formats found")
            else:
                self._sort_formats(formats)        
                entry = {
                        'id' : video_id,
                        'title' : sanitize_filename(title, restricted=True),
                        'formats' : formats,
                        'ext': 'mp4'
                    }            
                return entry
        finally:
            try:
                client.close()
            except Exception:
                pass
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
        
                
 




