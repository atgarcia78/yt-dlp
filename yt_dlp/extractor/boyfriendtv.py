# coding: utf-8
from __future__ import unicode_literals
from distutils.log import info

import re
import json


from .common import InfoExtractor

import requests 


from ..utils import (
    ExtractorError,
    get_element_by_attribute,  
    urljoin,
    int_or_none,
    sanitize_filename,
    std_headers

)

import random
import time
import threading

from selenium.webdriver import Firefox
from selenium.webdriver import FirefoxProfile
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import traceback
import sys

import httpx
import demjson
from urllib.parse import unquote


from queue import Queue


class checkvideo_and_find():
    
    def __call__(self, driver):
        
        el = driver.title       
        if "deleted" in el.lower() or "removed" in el.lower():            
            return "error"        
        else:
            
            el = driver.find_elements_by_class_name("download-item")
            return el if el else False
            
                        
            
class BoyFriendTVBaseIE(InfoExtractor):
    _LOGIN_URL = 'https://www.boyfriendtv.com/login/'
    _SITE_URL = 'https://www.boyfriendtv.com/'
    _NETRC_MACHINE = 'boyfriendtv'
    _LOGOUT_URL = 'https://www.boyfriendtv.com/logout'
   
    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',                
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/0khfuzdw.selenium0',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium']
    
    def wait_until(self, driver, time, method):
        
        
        try:
            el = WebDriverWait(driver, time).until(method)
        except Exception as e:
            el = None
         
        return el 
    
    def wait_until_not(self, driver, time, method):
        
      
        try:
            el = WebDriverWait(driver, time).until_not(method)
        except Exception as e:
            el = None
   
        return el
    
    def _get_info_video(self, url):
       
        count = 0
        while (count<5):
                
            try:
                
                res = httpx.head(url)
                if res.status_code > 400:
                    
                    count += 1
                else: 
                    
                    _res = int_or_none(res.headers.get('content-length')) 
                    _url = str(res.url)
                    #self.to_screen(f"{url}:{_url}:{_res}")
                    if _res and _url: 
                        break
                    else:
                        count += 1
        
            except Exception as e:
                count += 1
                
            time.sleep(1)
                
        if count < 5: return ({'url': _url, 'filesize': _res}) 
        else: return ({'error': 'max retries'})  
    
   

    
    def _login(self, driver):
        
        
        username, password = self._get_login_info()
        
        #self.to_screen(f'{username}:{password}')
        
        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)
        
        self.report_login()
        driver.get(self._LOGIN_URL)
        
        el_username = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#login.form-control")))
        el_password = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#password.form-control")))
        if el_username and el_password:
            el_username.send_keys(username)
            time.sleep(2)
            el_password.send_keys(password)
            time.sleep(2)
        el_login = driver.find_element_by_css_selector("input.btn.btn-submit")
        _current_url = driver.current_url
        el_login.submit()
        self.wait_until(driver, 60, ec.url_changes(_current_url))
        #self.to_screen(driver.current_url)
        #self.to_screen(driver.current_url == self._SITE_URL)
        if driver.current_url != self._SITE_URL: 
            self.raise_login_required("Invalid username/password")
        else:
            self.to_screen("Login OK")


 
class BoyFriendTVIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtv'
    _VALID_URL = r'https?://(?:(?P<prefix>m|www|es|ru|de)\.)?(?P<url>boyfriendtv\.com/videos/(?P<id>[0-9]+)/?(?:([0-9a-zA-z_-]+/?)|$))'

    _LOCK = threading.Lock()
    
    _QUEUE = Queue()
    
    _DRIVER = []
    
    def _real_initialize(self):
        
        driver = None
        
        with self._LOCK:
            
            try:
    
                if len(self._DRIVER) == (self._downloader.params.get('winit', 1)):
                    return 
                opts = Options()
                opts.headless = True
                prof_ff = self._FF_PROF.pop() 
                self._FF_PROF.insert(0,prof_ff)
                _firefox_prof = FirefoxProfile(prof_ff) 
                driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", firefox_profile=_firefox_prof, options=opts)
                driver.set_window_size(1920,575)
                driver.minimize_window()
                    
                driver.get(self._SITE_URL)
                self.wait_until(driver, 60, ec.title_contains("Gay"))
                driver.add_cookie({'name': 'rta_terms_accepted', 'value': 'true', 'domain': '.boyfriendtv.com', 'path': '/'})
                #driver.refresh()
                self._login(driver)
                self._DRIVER.append(driver)
                self._QUEUE.put_nowait(driver)
                
                
            except Exception as e:
                if driver:                
                    self._DRIVER.remove(driver)
                    driver.quit() 
                raise 
    
    
    def _real_extract(self, url):
        
        
        try:
            
            driver = self._QUEUE.get(block=True)
            
            self.report_extraction(url)   

            _titledriver = ""            
            driver.get(url)
            self.wait_until_not(driver, 30, ec.title_is(_titledriver))
            _title = driver.title.lower()
            _title_video = driver.title.replace(" - BoyFriendTV.com", "")
            if "deleted" in _title or "removed" in _title: raise ExtractorError("video removed")   
                        
            webpage = driver.page_source.replace('\n','').replace('\t','')
                       
            mobj = re.findall(r'sources:\s+(\{.*\})\,\s+poster',webpage)
            
            if mobj:
                info_sources = demjson.decode(mobj[0])
                _formats = []
                for _src in info_sources.get('mp4'):
                    _url = unquote(_src.get('src'))
                    _info_video = self._get_info_video(_url) 
                    _formats.append({
                        'url': _info_video.get('url'),
                        'ext': 'mp4',
                        'format_id': 'http-mp4',
                        'resolution': _src.get('desc'),
                        'filesize': _info_video.get('filesize')
                    })
                    
                self._sort_formats(_formats)
                   
             
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))
        finally:
            self._QUEUE.put_nowait(driver)
       
            
            
        return({
                'id': self._match_id(url),
                'title': sanitize_filename(_title_video, restricted=True),
                'formats': _formats,
            
            })       


class BoyFriendTVPlayListIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtvplaylist'
    IE_DESC = 'boyfriendtvplaylist'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/playlists/(?P<playlist_id>.*?)(?:(/|$))'

 
    
    def _real_extract(self, url):
        mobj = re.match(self._VALID_URL, url)
        playlist_id = mobj.group('playlist_id')


        try:
            
            opts = Options()
            opts.headless = True
            prof_ff = self._FF_PROF.pop() 
            self._FF_PROF.insert(0,prof_ff)
            _firefox_prof = FirefoxProfile(prof_ff) 
            driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", firefox_profile=_firefox_prof, options=opts)
            driver.set_window_size(1920,575)
                
            driver.get(self._SITE_URL)
            self.wait_until(driver, 60, ec.title_contains("Gay"))
            driver.add_cookie({'name': 'rta_terms_accepted', 'value': 'true', 'domain': '.boyfriendtv.com', 'path': '/'})
            #driver.refresh()
        
            entries = []
            driver.get(url)
            el_title = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "h1")))
            _title = el_title.text.splitlines()[0]
            
            while True:

                el_sources = self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CSS_SELECTOR, "div.thumb.vidItem")))
                
                if el_sources:                        
                    entries += [self.url_result((el_a:=el.find_element_by_tag_name('a')).get_attribute('href').rsplit("/", 1)[0], ie=BoyFriendTVIE.ie_key(), video_id=el.get_attribute('data-video-id'), video_title=sanitize_filename(el_a.get_attribute('title'), restricted=True)) for el in el_sources]

                el_next = self.wait_until(driver, 60, ec.presence_of_element_located((By.PARTIAL_LINK_TEXT, "Next")))
                if el_next: 
                    driver.get(urljoin(self._SITE_URL, el_next.get_attribute('href')))                    
                else: break
                
            if not entries: raise ExtractorError("cant find any video")
            
            
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))            
        finally:
            driver.quit()

                

        return {
            '_type': 'playlist',
            'id': playlist_id,
            'title': sanitize_filename(_title, restricted=True),
            'entries': entries,
        }