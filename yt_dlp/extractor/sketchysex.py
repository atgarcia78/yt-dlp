# coding: utf-8
from __future__ import unicode_literals


import re
import random


from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    sanitize_filename    
)


import threading
import time
import traceback
import sys

from selenium.webdriver import Firefox, FirefoxProfile
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

from queue import Queue
import html
import demjson
import time


class SketchySexBaseIE(InfoExtractor):
    _LOGIN_URL = "https://sketchysex.com/sign-in"
    _SITE_URL = "https://sketchysex.com"
    _LOGOUT_URL = "https://sketchysex.com/sign-out"
    _MULT_URL = "https://sketchysex.com/multiple-sessions"
    _ABORT_URL = "https://sketchysex.com/multiple-sessions/abort"
    _AUTH_URL = "https://sketchysex.com/authorize2"
    _BASE_URL_PL = "https://sketchysex.com/episodes/"
    
    _NETRC_MACHINE = 'sketchysex'
    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/0khfuzdw.selenium0']

 


    def wait_until(self, _driver, time, method):
        try:
            el = WebDriverWait(_driver, time).until(method)
        except Exception as e:
            el = None
            
        return el  
    
    def wait_until_not(self, _driver, time, method):
        try:
            el = WebDriverWait(_driver, time).until_not(method)
        except Exception as e:
            el = None
            
        return el 

    def _login(self, _driver):
        
        
        
             
        # _driver.get(self._SITE_URL)
        
        # self.wait_until_not(_driver, 60, ec.url_changes(self._SITE_URL))
        
        _title = _driver.title.upper()
        #self.to_screen(_title)
        if "WARNING" in _title:
            self.to_screen("Adult consent")
            el_enter = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CLASS_NAME, "enter-btn")))
            if not el_enter: raise ExtractorError("couldnt find adult consent button")
            _current_url = _driver.current_url
            el_enter.click()
            self.wait_until(_driver, 60, ec.url_changes(_current_url))
        
        el_top = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "ul.inline-list.top-navbar")))
        if "MEMBERS" in el_top.get_attribute('innerText').upper():
            self.report_login()
            username, password = self._get_login_info()

            self.to_screen(f"{username}#{password}#")
            
            if not username or not password:
                self.raise_login_required(
                    'A valid %s account is needed to access this media.'
                    % self._NETRC_MACHINE)
            
            _driver.get(self._LOGIN_URL)
            el_username = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#username")))
            
            el_password = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#password")))            
            
            el_login = _driver.find_element_by_css_selector("input#submit1.submit1")
            if not el_username or not el_password or not el_login: raise ExtractorError("couldnt find text elements")
            el_username.send_keys(username)
            time.sleep(3)
            el_password.send_keys(password)
            time.sleep(3)
            #_title = _driver.title
            _current_url = _driver.current_url
            #self.to_screen(f"{_title}#{driver.current_url}")
            el_login.click()
            self.wait_until(_driver, 60, ec.url_changes(_current_url))
            count = 3
            while count > 0:
            
                if "episodes" in _driver.current_url:
                    el_top = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "ul.inline-list.top-navbar")))
                    if not "LOG OUT" in el_top.get_attribute('innerText').upper():
                        raise ExtractorError("Login failed")
                    else: break
                if "authorize2" in _driver.current_url:
                    el_email = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#email")))
                    el_lastname = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#last-name")))
                    el_enter = _driver.find_element_by_css_selector("button")
                    if not el_email or not el_lastname or not el_enter: raise ExtractorError("couldnt find text elements")
                    el_email.send_keys("a.tgarc@gmail.com")
                    el_lastname.send_keys("Torres")                
                    _current_url = _driver.current_url
                    el_enter.click()
                    self.wait_until(_driver, 60, ec.url_changes(_current_url))
                if "multiple-sessions" in _driver.current_url:                
                    self.to_screen("Abort existent session")
                    el_abort = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR,"button.std-button")))
                    if not el_abort: raise ExtractorError("couldnt find button to abort sessions")
                    _current_url = _driver.current_url
                    el_abort.click()
                    self.wait_until(_driver, 60, ec.url_changes(_current_url))
                
                count -= 1
                
            if count == 0: raise ExtractorError("couldnt log in")
        
        self.to_screen("Login OK")    
            
    def _logout(self, _driver):
        _driver.get(self._LOGOUT_URL)

    def _extract_from_page(self, _driver, url):
        
                
  
        _driver.get(url)
        _title = None
        el_title = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "h1")))
        if el_title:
            _title = el_title.text
        else: 
            mobj = re.findall(r'(.*) ::', _driver.title)
            if mobj: _title = mobj[0]             
        if not _title:
            el_title = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "title")))
            if el_title:
                mobj = re.findall(r'(.*) ::', el_title.get_attribute('innerText'))
                if mobj: _title = mobj[0]
        
        if not _title: _title = 'sketchysex_video'    
        #self.to_screen(_title)
        el_iframe = _driver.find_elements_by_tag_name("iframe")
        if not el_iframe: raise ExtractorError("no iframe")
        embedurl = el_iframe[0].get_attribute('src')
        #self.to_screen(f"embedurl:{embedurl}")
        if not embedurl: raise ExtractorError("not embed url")
        res = self.wait_until(_driver, 30, ec.frame_to_be_available_and_switch_to_it((By.TAG_NAME,"iframe")))
        mobj = []
        if res:      
            mobj = re.findall(f'globalSettings\s+\=\s+([^;]*);',html.unescape(_driver.page_source))
        if not mobj: raise ExtractorError("no token")
        _data_dict = demjson.decode(mobj[0])
        tokenid = _data_dict.get('token')
        if not tokenid: raise ExtractorError("no token")            
        #self.to_screen(f"tokenid:{tokenid}") 
        videourl = "https://videostreamingsolutions.net/api:ov-embed/parseToken?token=" + tokenid
        #self.to_screen(videourl)
        headers = dict()
        headers.update({
            "Referer" : embedurl,
            "Accept" : "*/*",
            "X-Requested-With" : "XMLHttpRequest"})
        info = self._download_json(videourl, None, headers=headers)
        #self.to_screen(info)
        if not info: raise ExtractorError("Can't find any JSON info")

        #print(info)
        videoid = str(info.get('xdo',{}).get('video', {}).get('id', {}))
        manifestid = str(info.get('xdo',{}).get('video', {}).get('manifest_id', {}))
        manifesturl = "https://videostreamingsolutions.net/api:ov-embed/manifest/" + manifestid + "/manifest.m3u8"
        
        formats_m3u8 = self._extract_m3u8_formats(
            manifesturl, videoid, m3u8_id="hls", ext="mp4", entry_protocol='m3u8_native', fatal=False
        )

        if not formats_m3u8:
            raise ExtractorError("Can't find any M3U8 format")

        self._sort_formats(formats_m3u8)
    
                    
        return ({
            "id": videoid,
            "title": _title,
            "formats": formats_m3u8
        })
        
        
       
  
    def _extract_list(self, _driver, playlistid, nextpages):
        
        entries = []

        i = 0

        while True:

            url_pl = f"{self._BASE_URL_PL}{int(playlistid) + i}"

            self.to_screen(url_pl)
            
            _driver.get(url_pl)
            el_listmedia = self.wait_until(_driver, 60, ec.presence_of_all_elements_located((By.CLASS_NAME, "content")))
            if not el_listmedia: raise ExtractorError("no info")
            for media in el_listmedia:
                el_tag = media.find_element_by_tag_name("a")
                _title = el_tag.get_attribute("innerText").replace(" ","_")
                _title = sanitize_filename(_title, restricted=True)
                entries.append(self.url_result(el_tag.get_attribute("href"), ie=SketchySexIE.ie_key(), video_title=_title))      

            
            
            if not nextpages: break
            
            if "NEXT" in _driver.page_source:
                i += 1
            else:
                break
            
        if not entries: raise ExtractorError("no videos found")
        
        return entries        



class SketchySexIE(SketchySexBaseIE):
    IE_NAME = 'sketchysex'
    IE_DESC = 'sketchysex'
    _VALID_URL = r'https?://(?:www\.)?sketchysex.com/episode/.*'
    
    
    _LOCK = threading.Lock()
    
    _QUEUE = Queue()   
    
    _DRIVER = []
    
    _COOKIES = None    
    
    def _real_initialize(self):
        
        with self._LOCK:
            if len(self._DRIVER) == (self._downloader.params.get('winit', 1)):
                return  
            
            prof = self._FF_PROF.pop()
            self._FF_PROF.insert(0, prof)
            
            opts = Options()
            opts.headless = True                            
                            
            driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof))
 
            self.to_screen(f"ffprof[{prof}]")
            
            driver.set_window_size(1920,575)
            
            driver.get(self._SITE_URL)
            self.wait_until(driver, 30, ec.url_changes(self._SITE_URL))
            
            if self._COOKIES:
            
                driver.delete_all_cookies()
                for cookie in self._COOKIES:
                    driver.add_cookie(cookie)
                        
                driver.get(self._SITE_URL)
                self.wait_until(driver, 30, ec.url_changes(self._SITE_URL))               
            
            try:
                self._login(driver)
            
            except Exception as e:
                self.to_screen("error when login")
                raise
            
            self._COOKIES = driver.get_cookies()
            self._DRIVER.append(driver)
            self._QUEUE.put_nowait(driver)
         
        

    def _real_extract(self, url):
        
        
        data = None
        try:
        
            driver = self._QUEUE.get(block=True) 
            data = self._extract_from_page(driver, url)
                 
            
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))
        finally:
            self._QUEUE.put_nowait(driver)
            
        if not data:
            raise ExtractorError("Not any video format found")
        elif "error" in data['id']:
            raise ExtractorError(str(data['cause']))
        else:
            return(data)
            
        

class SketchySexOnePagePlayListIE(SketchySexBaseIE):
    IE_NAME = 'sketchysex:playlist'
    IE_DESC = 'sketchysex:playlist'
    _VALID_URL = r"https?://(?:www\.)?sketchysex\.com/episodes/(?P<id>\d+)"
   
           
    
    def _real_extract(self, url):

        playlistid = re.search(self._VALID_URL, url).group("id")
        
        entries = None
        
        try:              
                        
            prof = self._FF_PROF.pop()
            
            opts = Options()
            opts.headless = True                            
                            
            driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof))
 
            self.to_screen(f"ffprof[{prof}]")            
            
            driver.get(self._SITE_URL)
            self.wait_until(driver, 30, ec.url_changes(self._SITE_URL))
            
            _title = driver.title.lower()
            
            if "warning" in _title:
                el_enter = self.wait_until(driver, 60, ec.presence_of_element_located((By.CLASS_NAME, "enter-btn")))
                if el_enter: el_enter.click()
            self.wait_until(driver, 60, ec.title_contains("Episodes"))
            entries = self._extract_list(driver, playlistid, nextpages=False)  
       
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))
        finally:
            driver.quit()
            
        if not entries: raise ExtractorError("no video list") 
        
        return self.playlist_result(entries, f"sketchysex:page_{playlistid}", f"sketchysex:page_{playlistid}")
    
class SketchySexAllPagesPlayListIE(SketchySexBaseIE):
    IE_NAME = 'sketchysex:allpages:playlist'
    IE_DESC = 'sketchysex:allpages:playlist'
    _VALID_URL = r"https?://(?:www\.)?sketchysex\.com/episodes/?$"
   
 
    def _real_extract(self, url):
        
        entries = None
        
        try:              
                        
            prof = self._FF_PROF.pop()
            
            opts = Options()
            opts.headless = True                            
                            
            driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof))
 
            self.to_screen(f"ffprof[{prof}]")            
            
            driver.get(self._SITE_URL)
            self.wait_until(driver, 30, ec.url_changes(self._SITE_URL))
            
            _title = driver.title.lower()
            
            if "warning" in _title:
                el_enter = self.wait_until(driver, 60, ec.presence_of_element_located((By.CLASS_NAME, "enter-btn")))
                if el_enter: el_enter.click()
            self.wait_until(driver, 60, ec.title_contains("Episodes"))       
        
            entries = self._extract_list(driver, 1, nextpages=True)  
        
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))
        finally:
            driver.quit()
            
        if not entries: raise ExtractorError("no video list") 
        
        return self.playlist_result(entries, f"sketchysex:AllPages", f"sketchysex:AllPages")


        

