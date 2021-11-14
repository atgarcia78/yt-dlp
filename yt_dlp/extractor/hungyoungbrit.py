# coding: utf-8
from __future__ import unicode_literals



from ..utils import (
    ExtractorError, 
    int_or_none,
    sanitize_filename,
    std_headers    

)

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
import time
import re
import httpx
import html
import traceback
import sys
import hashlib
import threading
import json
from .webdriver import SeleniumInfoExtractor

import os


class HungYoungBritBaseIE(SeleniumInfoExtractor):
    
    _SITE_URL = 'https://www.hungyoungbrit.com'
    _NETRC_MACHINE = 'hungyoungbrit'
    
    _LOCK = threading.Lock()
    
    _COOKIES = []
    
    _CLIENT = None
    


    def _get_info_video(self, url):
       
        count = 0
        while (count<5):
                
            try:
                
                #res = httpx.head(url, verify=(not self._downloader.params.get('nocheckcertificate')))
                with HungYoungBritBaseIE._LOCK:
                    res = HungYoungBritBaseIE._CLIENT.head(url)
                
                    if res.status_code > 400:
                    
                        count += 1
                    else: 
                    
                        _filesize = int_or_none(res.headers.get('content-length')) 
                        _url = str(res.url)
                    
                        #self.to_screen(f"{url}:{_url}:{_filesize}")
                        if _filesize: 
                            # for key, value in HungYoungBritBaseIE._CLIENT.cookies.jar.__dict__['_cookies']['.xvid.com']['/'].items():
                            #     self._set_cookie(domain='.xvid.com', name=key, value=value.value)
                            res = {'url': _url, 'filesize': _filesize}
                            return res
                        else:
                            count += 1
        
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
                
                count += 1
                
            
                
        


    def _real_initialize(self):
        
        _home_url = "https://www.hungyoungbrit.com/members/category.php?id=5"
        
        with HungYoungBritBaseIE._LOCK:
        
            if not HungYoungBritBaseIE._CLIENT:        
 
                try:                
                        
                    _timeout = httpx.Timeout(30, connect=30)        
                    _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
                    HungYoungBritBaseIE._CLIENT = httpx.Client(timeout=_timeout, limits=_limits, verify=(not self._downloader.params.get('nocheckcertificate')), headers=std_headers)
                
                    _cookies = None
                    if not HungYoungBritBaseIE._COOKIES:
                        
                        try:
                            with open("/Users/antoniotorres/Projects/common/logs/HYB_cookies.json", "r") as f:
                                _cookies = json.load(f)
                        except Exception as e:
                            self.to_screen(str(e))
                    else: _cookies = HungYoungBritBaseIE._COOKIES
                    
                    if _cookies:
                                
                        for cookie in _cookies:
                            HungYoungBritBaseIE._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
                        
                        res = HungYoungBritBaseIE._CLIENT.get(_home_url)
                        
                        if _home_url in str(res.url):
                            self.to_screen("login OK - 112")
                            HungYoungBritBaseIE._COOKIES = _cookies
                            return
                                    
                    self.report_login()                                        
                    
                    
                    
                    
                    driver = self.get_driver(noheadless=True)

                                
                    
                    
                    driver.get(self._SITE_URL)
                    driver.add_cookie({"name": "warn", "value":"1", "domain": "www.hungyoungbrit.com", "secure": False, "httpOnly": False, "sameSite": "Lax"})  
                    
                    driver.get(_home_url)  
                    self.wait_until(driver, 30, ec.url_changes(""))
                    self.to_screen(f"current url: {driver.current_url}")
                    if _home_url not in driver.current_url:
                            
                        
                                
                        el = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a.dropdown-toggle.londrina")))
                        el.click()
                        
                        el_username = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "input#username.form-control")))
                        el_password = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "input#password.form-control")))
                        button_login = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR,"button#btnLogin.btn.btn-primary.btn-sm.btn-block")))                    
                        username, password = self._get_login_info()
                        el_username.send_keys(username)
                        self.wait_until(driver, 2, ec.title_is("JUSTTOWAIT"))
                        el_password.send_keys(password)
                        self.wait_until(driver, 2, ec.title_is("JUSTTOWAIT"))
                        
                        button_login.click()
                        
                        #self.wait_until(driver, 300, ec.url_changes(_url)) 
                        self.wait_until(driver, 300, ec.invisibility_of_element(button_login)) 
                        
                        #if driver.current_url != "https://www.hungyoungbrit.com/members/index.php": raise ExtractError("login error")
                        
                        el = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a.dropdown-toggle.londrina")))
                        
                        if el.text != 'ACCOUNT': raise ExtractorError("log in error")

                                        
                    #self.to_screen("login OK")
                    HungYoungBritBaseIE._COOKIES = driver.get_cookies()
                    self.rm_driver(driver)
                                
                    with open("/Users/antoniotorres/Projects/common/logs/HYB_cookies.json", "w") as f:
                        json.dump(HungYoungBritBaseIE._COOKIES, f)
                        
                    for cookie in HungYoungBritBaseIE._COOKIES:
                        HungYoungBritBaseIE._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
                        
                    res = HungYoungBritBaseIE._CLIENT.get(_home_url)
                        
                    if _home_url in str(res.url):
                        self.to_screen("login OK - 172")
                    else: raise ExtractorError("Error cookies")
                        
                               
                except ExtractorError as e:
                    raise
                except Exception as e:                    
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")                    
                    raise ExtractorError(repr(e)) from e
              
                
    


class HungYoungBritIE(HungYoungBritBaseIE):
    
    IE_NAME = "hungyoungbrit"
    
    _VALID_URL = r'https?://(www\.)?hungyoungbrit\.com/members/gallery\.php\?id=(?P<id>\d+)&type=vids'
    
 
    def _real_extract(self, url):
        
            
        try:  
               
            self.report_extraction(url)
            
            with HungYoungBritBaseIE._LOCK:
                
                res = HungYoungBritBaseIE._CLIENT.get(url)
        
            webpage = re.sub('[\n\t]', '', html.unescape(res.text))
            
            mobj2 = re.findall(r'<title>([^<]+)<', webpage)
            title = mobj2[0] if mobj2 else f'hyb_{self._match_id()}'
            
            mobj = re.findall(r'movie\[\"(?:1080|720|480)p\"\]\[\"([^\"]+)\"\]=\{path:\"([^\"]+)\"[^\}]+movie_width:\'(\d+)\',movie_height:\'(\d+)\'[^\}]+\}', webpage.replace(' ',''))
            if not mobj: 
                self.write_debug(webpage)
                raise ExtractorError("no video formats")
            
            video_id = str(int(hashlib.sha256((mobj[0][0]).encode('utf-8')).hexdigest(),16) % 10**8)
            
            
            formats = []
            
            for el in mobj:
                # std_headers['Accept'] = "video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5"
                # std_headers['Referer'] = "https://www.hungyoungbrit.com/"
                # std_headers['Accept-Language'] = "en,es-ES;q=0.5"
                # std_headers['Accept-Encoding'] = "gzip, deflate, br"

                _info_video = self._get_info_video(el[1])
            
                if _info_video:
                    _url = _info_video['url']                    
                    _filesize = _info_video['filesize']
                else:
                    _url = el[1]
                    _filesize = None
                
                formats.append({'url': _url,
                        'width': int(el[2]),
                        'height': int(el[3]),
                        'filesize': _filesize,
                        'format_id': f'http{el[3]}',                        
                        'ext': 'mp4'})
            
            self._sort_formats(formats)
            
            return({
                'id': video_id,
                'title': sanitize_filename(title, restricted=True).upper(),
                'formats': formats 
            }) 
            #self.to_screen(formats)
            
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e)) from e

                    
       
                    
                    
class HungYoungBritPlaylistIE(HungYoungBritBaseIE):
    
    IE_NAME = "hungyoungbrit:playlist"
    
    _VALID_URL = r'https?://(?:www\.)?hungyoungbrit\.com/members/category\.php\?id=5(?:&page=(?P<page>\d+))?(?:&(?P<search>s=\w))?'
   
    
    # def _real_initialize(self):
        
    #     _home_url = "https://www.hungyoungbrit.com/members/category.php?id=5"
        
    #     with HungYoungBritPlaylistIE._LOCK:
        
    #         if not HungYoungBritPlaylistIE._CLIENT:        
 
    #             try:                
                        
    #                 _timeout = httpx.Timeout(30, connect=30)        
    #                 _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
    #                 HungYoungBritPlaylistIE._CLIENT = httpx.Client(timeout=_timeout, limits=_limits, verify=(not self._downloader.params.get('nocheckcertificate')), headers=std_headers)
                
    #                 _cookies = None
    #                 if not HungYoungBritPlaylistIE._COOKIES:
                        
    #                     try:
    #                         with open("/Users/antoniotorres/Projects/common/logs/HYB_cookies.json", "r") as f:
    #                             _cookies = json.load(f)
    #                     except Exception as e:
    #                         self.to_screen(str(e))
    #                 else: _cookies = HungYoungBritPlaylistIE._COOKIES
                    
    #                 if _cookies:
                                
    #                     for cookie in _cookies:
    #                         HungYoungBritPlaylistIE._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
                        
    #                     res = HungYoungBritPlaylistIE._CLIENT.get(_home_url)
                        
    #                     if _home_url in str(res.url):
    #                         self.to_screen("login OK - 151")
    #                         HungYoungBritPlaylistIE._COOKIES = _cookies
    #                         return
                                    
                                    
                                    
    #                 self.report_login()                                        
    #                 prof = HungYoungBritPlaylistIE._FF_PROF.pop()
    #                 HungYoungBritPlaylistIE._FF_PROF.insert(0,prof)
    #                 opts = Options()
    #                 #opts.add_argument("--headless")
    #                 opts.add_argument("--no-sandbox")
    #                 opts.add_argument("--disable-application-cache")
    #                 opts.add_argument("--disable-gpu")
    #                 opts.add_argument("--disable-dev-shm-usage")
    #                 opts.add_argument("--profile")
    #                 opts.add_argument(prof)
    #                 opts.set_preference("network.proxy.type", 0)                        
                    
                                                   
                                        
                    
    #                 self.to_screen(f"ffprof[{prof}]")
                    
    #                 driver = Firefox(options=opts)
                    
    #                 self.wait_until(driver, 5, ec.title_is("DUMMYFORWAIT"))
                    
    #                 driver.uninstall_addon('uBlock0@raymondhill.net')
                    
    #                 self.wait_until(driver, 2, ec.title_is("DUMMYFORWAIT"))
                    
    #                 driver.uninstall_addon("{529b261b-df0b-4e3b-bf42-07b462da0ee8}")
                    
    #                 self.wait_until(driver, 2, ec.title_is("DUMMYFORWAIT"))
                    
    #                 #driver.set_window_size(1920, 525)
    #                 driver.maximize_window()                    
                    
    #                 driver.get(self._SITE_URL)
    #                 driver.add_cookie({"name": "warn", "value":"1", "domain": "www.hungyoungbrit.com", "secure": False, "httpOnly": False, "sameSite": "Lax"})  
    #                 driver.get(_home_url)  
    #                 #self.wait_until(driver, 30, ec.url_changes(""))
    #                 self.to_screen(f"current url: {driver.current_url}")
    #                 if _home_url not in driver.current_url:
                                
    #                     el = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a.dropdown-toggle.londrina")))
    #                     el.click()
                        
    #                     el_username = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "input#username.form-control")))
    #                     el_password = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "input#password.form-control")))
    #                     button_login = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR,"button#btnLogin.btn.btn-primary.btn-sm.btn-block")))                    
    #                     username, password = self._get_login_info()
    #                     el_username.send_keys(username)
    #                     self.wait_until(driver, 2, ec.title_is("JUSTTOWAIT"))
    #                     el_password.send_keys(password)
    #                     self.wait_until(driver, 2, ec.title_is("JUSTTOWAIT"))
                        
    #                     button_login.click()
                        
    #                     #self.wait_until(driver, 300, ec.url_changes(_url)) 
    #                     self.wait_until(driver, 300, ec.invisibility_of_element(button_login)) 
                        
    #                     #if driver.current_url != "https://www.hungyoungbrit.com/members/index.php": raise ExtractError("login error")
                        
    #                     el = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a.dropdown-toggle.londrina")))
                        
    #                     if el.text != 'ACCOUNT': raise ExtractorError("log in error")

                                        
    #                 #self.to_screen("login OK")
    #                 HungYoungBritPlaylistIE._COOKIES = driver.get_cookies()
    #                 driver.quit()
                                
    #                 with open("/Users/antoniotorres/Projects/common/logs/HYB_cookies.json", "w") as f:
    #                     json.dump(HungYoungBritPlaylistIE._COOKIES, f)
                        
    #                 for cookie in HungYoungBritPlaylistIE._COOKIES:
    #                     HungYoungBritPlaylistIE._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
                        
    #                 res = HungYoungBritPlaylistIE._CLIENT.get(_home_url)
                        
    #                 if _home_url in str(res.url):
    #                     self.to_screen("login OK - 229")
    #                 else: raise ExtractorError("Error cookies")
                        
                    
                                
                                
    #             except ExtractorError as e:
    #                 raise
    #             except Exception as e:                    
    #                 lines = traceback.format_exception(*sys.exc_info())
    #                 self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")                    
    #                 raise ExtractorError(str(e)) from e
                        
    def _real_extract(self, url):
        
            
        try:  
               
            self.report_extraction(url)
            
            with HungYoungBritBaseIE._LOCK:
                res = HungYoungBritBaseIE._CLIENT.get(url)
        
            webpage = re.sub('[\n\t]', '', html.unescape(res.text))
            
            
            
            mobj = re.findall(r'data-setid="(\d+)"', webpage)
            if not mobj: 
                self.write_debug(webpage)
                raise ExtractorError("no video entries")
          
            entries = [self.url_result(f"https://www.hungyoungbrit.com/members/gallery.php?id={_id}&type=vids", ie="HungYoungBrit") for _id in mobj]
            
            
                        
            return self.playlist_result(entries, playlist_id="HYBplaylist", playlist_title="HYBplaylist")
               
            
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e)) from e

                    
       
                    
                   
                            
             
            
            
          
        
