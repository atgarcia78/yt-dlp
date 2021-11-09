# coding: utf-8
from __future__ import unicode_literals


import re


from ..utils import (
    ExtractorError,
    sanitize_filename,
    std_headers
)


import threading
import traceback
import sys

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


import demjson

from .seleniuminfoextractor import SeleniumInfoExtractor

import httpx

class SketchySexBaseIE(SeleniumInfoExtractor):
    _LOGIN_URL = "https://sketchysex.com/sign-in"
    _SITE_URL = "https://sketchysex.com"
    _LOGOUT_URL = "https://sketchysex.com/sign-out"
    _MULT_URL = "https://sketchysex.com/multiple-sessions"
    _ABORT_URL = "https://sketchysex.com/multiple-sessions/abort"
    _AUTH_URL = "https://sketchysex.com/authorize2"
    _BASE_URL_PL = "https://sketchysex.com/episodes/"

    _NETRC_MACHINE = 'sketchysex'

    _LOCK = threading.Lock()
    
    
    _COOKIES = None 


    def _login(self, _driver):
        
        _driver.get(self._SITE_URL)
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

            
            
            if not username or not password:
                self.raise_login_required(
                    'A valid %s account is needed to access this media.'
                    % self._NETRC_MACHINE)
            
            _driver.get(self._LOGIN_URL)
            el_username = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#username")))
            el_password = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#password")))
            el_login = _driver.find_element(by=By.CSS_SELECTOR, value="input#submit1.submit1")
            if not el_username or not el_password or not el_login: raise ExtractorError("couldnt find text elements")
            el_username.send_keys(username)
            self.wait_until(_driver, 3, ec.title_is("DUMMYFORWAIT"))
            el_password.send_keys(password)
            self.wait_until(_driver, 3, ec.title_is("DUMMYFORWAIT"))
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
                    el_enter = _driver.find_element(by=By.CSS_SELECTOR, value="button")
                    if not el_email or not el_lastname or not el_enter: raise ExtractorError("couldnt find text elements")
                    el_email.send_keys("a.tgarc@gmail.com")
                    self.wait_until(_driver, 3, ec.title_is("DUMMYFORWAIT"))
                    el_lastname.send_keys("Torres")
                    self.wait_until(_driver, 3, ec.title_is("DUMMYFORWAIT"))                
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

    def _extract_from_page(self, cl, url):
  
        res = cl.get(url)
        _title = None
        mobj = re.findall(r'<h1>([^\<]+)<', res.text)        
        if mobj:
            _title = mobj[0]
        
        if not _title: _title = url.split('/')[-1].replace("-","_").upper() 
        #self.to_screen(_title)
        mobj = re.findall(r'<iframe src=\"([^\"]+)\"', res.text)
        if mobj:
            embedurl = mobj[0]
        else: raise ExtractorError("not embed url")
        
        try:
            res2 = cl.get(embedurl)
            mobj = re.findall(r'globalSettings\s+\=\s+([^;]*);',res2.text)
        except Exception:
            mobj = None
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
        
        try:
            res3 = cl.get(videourl, headers=headers)
            info = res3.json()
        except Exception:
            info = None
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

            #self.to_screen(url_pl)
            
            _driver.get(url_pl)
            el_listmedia = self.wait_until(_driver, 60, ec.presence_of_all_elements_located((By.CLASS_NAME, "content")))
            if not el_listmedia: raise ExtractorError("no info")
            for media in el_listmedia:
                el_tag = media.find_element(by=By.TAG_NAME, value="a")
                
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

    def _real_initialize(self):
        
        with SketchySexIE._LOCK:
            if SketchySexIE._COOKIES:
                return  

            driver = self.get_driver()

            
            try:
                
                self._login(driver)                
                
                SketchySexIE._COOKIES = driver.get_cookies()
             
            
            except Exception as e:
                self.to_screen("error when login")
                raise
            finally:
                self.rm_driver(driver)
            

    def _real_extract(self, url):
        
        
        data = None
        try:
        
            cl = httpx.Client(headers=std_headers, timeout=httpx.Timeout(15, connect=30), limits=httpx.Limits(max_keepalive_connections=None, max_connections=None))
            for cookie in SketchySexIE._COOKIES:
                cl.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
                
            data = self._extract_from_page(cl, url)
                 
            
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))
        finally:
            cl.close()

        if not data:
            raise ExtractorError("Not any video format found")
        elif "error" in data['id']:
            raise ExtractorError(str(data['cause']))
        else:
            return(data)

class SketchySexOnePagePlaylistIE(SketchySexBaseIE):
    IE_NAME = 'sketchysex:playlist'
    IE_DESC = 'sketchysex:playlist'
    _VALID_URL = r"https?://(?:www\.)?sketchysex\.com/episodes/(?P<id>\d+)"


    def _real_extract(self, url):

        playlistid = re.search(self._VALID_URL, url).group("id")
        
        entries = None
        
        try:              
                        
            driver = self.get_driver()
            

            
            driver.get(self._SITE_URL)
            
            _title = driver.title.lower()
            
            if "warning" in _title:
                el_enter = self.wait_until(driver, 60, ec.presence_of_element_located((By.CLASS_NAME, "enter-btn")))
                if el_enter: el_enter.click()
            
            entries = self._extract_list(driver, playlistid, nextpages=False)  
       
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            self.rm_driver(driver)
            
        if not entries: raise ExtractorError("no video list") 
        
        return self.playlist_result(entries, f"sketchysex:page_{playlistid}", f"sketchysex:page_{playlistid}")
    
class SketchySexAllPagesPlaylistIE(SketchySexBaseIE):
    IE_NAME = 'sketchysex:allpages:playlist'
    IE_DESC = 'sketchysex:allpages:playlist'
    _VALID_URL = r"https?://(?:www\.)?sketchysex\.com/episodes/?$"
   
 
    def _real_extract(self, url):
        
        entries = None
        
        try:              


            driver = self.get_driver()
            
            driver.get(self._SITE_URL)
            _title = driver.title.lower()            
            if "warning" in _title:
                el_enter = self.wait_until(driver, 60, ec.presence_of_element_located((By.CLASS_NAME, "enter-btn")))
                if el_enter: el_enter.click()
                
            entries = self._extract_list(driver, 1, nextpages=True)  
        
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))
        finally:
            self.rm_driver(driver)
            
        if not entries: raise ExtractorError("no video list") 
        
        return self.playlist_result(entries, f"sketchysex:AllPages", f"sketchysex:AllPages")