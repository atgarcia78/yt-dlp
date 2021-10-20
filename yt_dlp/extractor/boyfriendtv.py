# coding: utf-8
from __future__ import unicode_literals
from distutils.log import info

import re
import os


from .common import InfoExtractor


from ..utils import (
    ExtractorError,  
    urljoin,
    int_or_none,
    sanitize_filename,
    std_headers

)

import html
import time
import threading

from selenium.webdriver import Firefox
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


class BoyFriendTVBaseIE(InfoExtractor):
    _LOGIN_URL = 'https://www.boyfriendtv.com/login/'
    _SITE_URL = 'https://www.boyfriendtv.com/'
    _NETRC_MACHINE = 'boyfriendtv'
    _LOGOUT_URL = 'https://www.boyfriendtv.com/logout'
   
    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/22jv66x2.selenium0'
                ]
    
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
    
    def _get_info_video(self, url, client):
       
        count = 0
        while (count<5):
                
            try:
                
                res = client.head(url)
                if res.status_code > 400:
                    
                    count += 1
                else: 
                    
                    _filesize = int_or_none(res.headers.get('content-length')) 
                    _url = str(res.url)
                    #self.to_screen(f"{url}:{_url}:{_res}")
                    if _filesize and _url: 
                        break
                    else:
                        count += 1
        
            except Exception as e:
                count += 1
                
            time.sleep(1)
                
        if count < 5: return ({'url': _url, 'filesize': _filesize}) 
        else: return ({'error': 'max retries'})  
    
   

    
    def _login(self, driver):
        
        
        username, password = self._get_login_info()
        
        #self.to_screen(f'{username}:{password}')
        
        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)
        
        self.report_login()
        driver.get(self._SITE_URL)
        el_login = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a#login-url")))
        if el_login: el_login.click()
        el_username = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "input#login.form-control")))
        el_password = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "input#password.form-control")))
        el_login = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "input.btn.btn-submit")))
        if el_username and el_password and el_login:
            el_username.send_keys(username)
            self.wait_until(driver, 2, ec.presence_of_element_located((By.CSS_SELECTOR, "DUMMYFORWAIT")))
            el_password.send_keys(password)
            self.wait_until(driver, 2, ec.presence_of_element_located((By.CSS_SELECTOR, "DUMMYFORWAIT")))            
            el_login.submit()
            el_menu = self.wait_until(driver, 15, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))
        #self.to_screen(driver.current_url)
        #self.to_screen(driver.current_url == self._SITE_URL)
            if not el_menu: 
                self.raise_login_required("Invalid username/password")
            else:
                self.to_screen("Login OK")


 
class BoyFriendTVIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtv'
    _VALID_URL = r'https?://(?:(?P<prefix>m|www|es|ru|de)\.)?(?P<url>boyfriendtv\.com/videos/(?P<id>[0-9]+)/?(?:([0-9a-zA-z_-]+/?)|$))'

    _LOCK = threading.Lock()
    
    _QUEUE = Queue()
    
    _DRIVER = 0
    
    _COOKIES = {}
    
    def _real_initialize(self):
        
        driver = None
        
        with self._LOCK:
            
            try:
    
                if self._DRIVER == self._downloader.params.get('winit', 5):
                    return 
                

                prof = self._FF_PROF.pop() 
                self._FF_PROF.insert(0,prof)
                self.to_screen(f"ff_prof: {prof}")
                
                opts = Options()
                opts.add_argument("--headless")
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-application-cache")
                opts.add_argument("--disable-gpu")
                opts.add_argument("--disable-dev-shm-usage")
                opts.add_argument("--profile")
                opts.add_argument(prof)
                opts.set_preference("network.proxy.type", 0)                        
                
                                               
                                    
                driver = Firefox(options=opts)
                
                self.wait_until(driver, 5, ec.presence_of_element_located((By.CSS_SELECTOR, "DUMMYFORWAIT")))
                
                driver.uninstall_addon('uBlock0@raymondhill.net')
                
                self.wait_until(driver, 5, ec.presence_of_element_located((By.CSS_SELECTOR, "DUMMYFORWAIT")))
                
                driver.uninstall_addon("{529b261b-df0b-4e3b-bf42-07b462da0ee8}")
                
                driver.set_window_size(1920,575)
                driver.minimize_window()
                #driver.maximize_window()
                    
                driver.get(self._SITE_URL)
                el_menu = self.wait_until(driver, 10, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))
                if not el_menu:
                    if self._COOKIES:
                        for _cookie in self._COOKIE: driver.add_cookie(_cookie)
                        driver.get(self._SITE_URL)
                        el_menu = self.wait_until(driver, 10, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))
                        if el_menu:
                            self.to_screen(f"Driver init ok: {prof}")
                            
                        else:
                            self._login(driver)
                    else:
                        driver.add_cookie({'name': 'rta_terms_accepted', 'value': 'true', 'sameSite': 'Lax', 'secure': True, 'domain': '.boyfriendtv.com'})                
                        self._login(driver)
                
            except Exception as e:
               
                raise 
    
            self._COOKIES = driver.get_cookies()
            
            self._DRIVER += 1
                    
            self._QUEUE.put_nowait(driver)
    
    def _real_extract(self, url):
        
        
        try:
            
            driver = self._QUEUE.get(block=True)
            
            self.report_extraction(url) 
            
            client = None  

                       
            #driver.get(self._SITE_URL)
            #self.wait_until(driver, 10, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))
            driver.get(url)
            el_vplayer = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "video-player")))
            el_title = self.wait_until(driver, 10, ec.presence_of_element_located((By.TAG_NAME, "title")))
            if el_title: _title = el_title.get_attribute("innerHTML")
            if "deleted" in _title or "removed" in _title or "page not found" in _title or not el_vplayer: raise ExtractorError("Page not found")   
            _title_video = _title.replace(" - BoyFriendTV.com", "").strip()            
            el_html = self.wait_until(driver, 60, ec.presence_of_element_located((By.TAG_NAME, "html")))
            webpage = el_html.get_attribute("outerHTML")
                       
            mobj = re.findall(r'sources:\s+(\{.*\})\,\s+poster',re.sub('[\t\n]','', html.unescape(webpage)))
            
            
            if mobj:
                _timeout = httpx.Timeout(10, connect=30)        
                _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
                client = httpx.Client(timeout=_timeout, limits=_limits, headers={'User-Agent': std_headers['User-Agent']}, verify=(not self._downloader.params.get('nocheckcertificate')))
                info_sources = demjson.decode(mobj[0])
                _formats = []
                for _src in info_sources.get('mp4'):
                    _url = unquote(_src.get('src'))
                    _info_video = self._get_info_video(_url, client)
                     
                    if (_error:=_info_video.get('error')): 
                        self.to_screen(_error)
                        raise ExtractorError('Error 404')
                    
                    _formats.append({
                        'url': _info_video.get('url'),
                        'ext': 'mp4',
                        'format_id': f"http-{_src.get('desc')}",
                        'resolution': _src.get('desc'),
                        'height': int_or_none(_src.get('desc').lower().replace('p','')),
                        'filesize': _info_video.get('filesize')
                    })
                    
                self._sort_formats(_formats)
                
                return({
                    'id': self._match_id(url),
                    'title': sanitize_filename(_title_video, restricted=True),
                    'formats': _formats,
                    'ext': 'mp4'
            
                })
                   
        except ExtractorError as e:
            raise     
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e)) from e
        finally:
            self._QUEUE.put_nowait(driver)
            if client: client.close()
           
       
 

class BoyFriendTVEmbedIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtv:embed'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/embed/(?:((?P<id>[0-9]+)/)|embed.php\?)'
    
   
    def _real_extract(self, url):
        
        self.report_extraction(url)
        try:
            if not self._match_id(url):
                _url_embed = httpx.URL(url)
                _params_dict = dict(_url_embed.params.items())
                _url = f"https://{_url_embed.host}/embed/{_params_dict.get('m')}/{_params_dict.get('h')}"
            else: _url = url
            
            _timeout = httpx.Timeout(10, connect=30)        
            _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
            client = httpx.Client(timeout=_timeout, limits=_limits, headers={'User-Agent': std_headers['User-Agent']}, verify=(not self._downloader.params.get('nocheckcertificate')))
            
            res = client.get(_url)            
                
            webpage = re.sub('[\t\n]','', html.unescape(res.text))
            
            #self.to_screen(webpage)
            mobj = re.findall(r'sources:\s+(\{.*\})\,\s+poster', webpage)
            mobj2 = re.findall(r'title:\s+\"([^-\"]*)[-\"]', webpage)        
            
            _title_video = mobj2[0].strip() if mobj2 else "boyfriendtv_video"
          
             
            #self.to_screen(_title_video)    
            #_entry_video = {}
                
            if mobj:
                info_sources = demjson.decode(mobj[0])
                _formats = []
                for _src in info_sources.get('mp4'):
                    _url = unquote(_src.get('src'))
                    _info_video = self._get_info_video(_url, client) 
                    _formats.append({
                        'url': _info_video.get('url'),
                        'ext': 'mp4',
                        'format_id': f"http-{_src.get('desc')}",
                        'resolution': _src.get('desc'),
                        'height': int_or_none(_src.get('desc').lower().replace('p','')),
                        'filesize': _info_video.get('filesize')
                    })
                    
                self._sort_formats(_formats)
                
                return({
                    'id': self._match_id(str(res.url)),
                    'title': sanitize_filename(_title_video, restricted=True),
                    'formats': _formats,
                    'ext': 'mp4'
            
                })
                
            else: raise ExtractorError("Video not found")
                
        except ExtractorError as e:
            raise     
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e)) from e
        
        
       
            
        
       
    

class BoyFriendTVPlayListIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtv:playlist'
    IE_DESC = 'boyfriendtv:playlist'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/playlists/(?P<playlist_id>.*?)(?:(/|$))'

 
    
    def _real_extract(self, url):
        mobj = re.match(self._VALID_URL, url)
        playlist_id = mobj.group('playlist_id')


        try:
            
            prof = self._FF_PROF.pop() 
            self._FF_PROF.insert(0,prof)
            
            
            opts = Options()
            opts.add_argument("--headless")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-application-cache")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--profile")
            opts.add_argument(prof) 
            opts.set_preference("network.proxy.type", 0)                       
            
                                           
                                    
            driver = Firefox(options=opts)

            self.to_screen(f"{url}:ffprof[{prof}]")
            
            driver.set_window_size(1920,575)
                
            driver.get(self._SITE_URL)
            el = self.wait_until(driver, 15, ec.presence_of_element_located((By.CLASS_NAME, "swal2-container")))
            if el:
                driver.add_cookie({'name': 'rta_terms_accepted', 'value': 'true', 'sameSite': 'Lax', 'secure': True, 'domain': '.boyfriendtv.com'})      
                
        
            entries = []
            driver.get(url)
            el_title = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "h1")))
            _title = el_title.text.splitlines()[0]
            
            while True:

                el_sources = self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CSS_SELECTOR, "div.thumb.vidItem")))
                
                if el_sources:                        
                    entries += [self.url_result((el_a:=el.find_element(by=By.TAG_NAME, value='a')).get_attribute('href').rsplit("/", 1)[0], ie=BoyFriendTVIE.ie_key(), video_id=el.get_attribute('data-video-id'), video_title=sanitize_filename(el_a.get_attribute('title'), restricted=True)) for el in el_sources]

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