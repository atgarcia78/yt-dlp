# coding: utf-8
from __future__ import unicode_literals


from .common import InfoExtractor

from ..utils import (
    ExtractorError, 
    int_or_none,
    sanitize_filename,
    str_or_none,
    std_headers    

)


from selenium.webdriver import Firefox, FirefoxProfile
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
import time
import re
import httpx
import html
import traceback
import sys
import hashlib
import subprocess
import threading
import json

import os




class HungYoungBritIE(InfoExtractor):
    
    IE_NAME = "hungyoungbrit"
    _SITE_URL = 'https://www.hungyoungbrit.com'
    _NETRC_MACHINE = 'hungyoungbrit'
    _VALID_URL = r'https?://(www\.)?hungyoungbrit\.com/members/gallery\.php\?id=(?P<id>\d+)&type=vids'
   
    
    
    _LOCK = threading.Lock()
    
    _COOKIES = []
    
    _CLIENT = []
    
   
    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/0khfuzdw.selenium0']


    def kill_geckodriver(self):
        res = subprocess.run(["ps","-o","pid","-o","comm"], encoding='utf-8', capture_output=True).stdout
        mobj = re.findall(r'(\d+) geckodriver', res)
        if mobj:
            for process in mobj:                    
                res = subprocess.run(["kill","-9",process[0]], encoding='utf-8', capture_output=True)
                if res.returncode != 0: self.logger.debug(f"cant kill {process[0]} : {process[1]} : {res.stderr}")
                else: self.logger.info(f"killed {process[0]} : {process[1]}")    
        

    def _get_info_video(self, url):
       
        count = 0
        while (count<5):
                
            try:
                
                res = httpx.head(url, verify=(not self._downloader.params.get('nocheckcertificate')))
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
        else: return   

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
    
    
    def _real_initialize(self):
        
        _home_url = "https://www.hungyoungbrit.com/members/category.php?id=5"
        
        with HungYoungBritIE._LOCK:
        
            if not HungYoungBritIE._CLIENT:        
 
                try:                
                        
                    _timeout = httpx.Timeout(30, connect=30)        
                    _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
                    HungYoungBritIE._CLIENT = httpx.Client(timeout=_timeout, limits=_limits, verify=(not self._downloader.params.get('nocheckcertificate')), headers=std_headers)
                
                    _cookies = None
                    if not HungYoungBritIE._COOKIES:
                        
                        try:
                            with open("/Users/antoniotorres/Projects/common/logs/HYB_cookies.json", "r") as f:
                                _cookies = json.load(f)
                        except Exception as e:
                            self.to_screen(str(e))
                    else: _cookies = HungYoungBritIE._COOKIES
                    
                    if _cookies:
                                
                        for cookie in _cookies:
                            HungYoungBritIE._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
                        
                        res = HungYoungBritIE._CLIENT.get(_home_url)
                        
                        if _home_url in str(res.url):
                            self.to_screen("login OK - 151")
                            HungYoungBritIE._COOKIES = _cookies
                            return
                                    
                                    
                                    
                    self.report_login()                                        
                    prof = HungYoungBritIE._FF_PROF.pop()
                    HungYoungBritIE._FF_PROF.insert(0,prof)
                    self.to_screen(f"[ff] {prof}")
                    opts = Options()
                    opts.headless = False                
                    opts.add_argument("--no-sandbox")
                    opts.add_argument("--disable-application-cache")
                    opts.add_argument("--disable-gpu")
                    opts.add_argument("--disable-dev-shm-usage")
                    os.environ['MOZ_HEADLESS_WIDTH'] = '1920'
                    os.environ['MOZ_HEADLESS_HEIGHT'] = '1080'
                    driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof))
                    
                    self.wait_until(driver, 5, ec.title_is("DUMMYFORWAIT"))
                    
                    driver.uninstall_addon('uBlock0@raymondhill.net')
                    
                    self.wait_until(driver, 2, ec.title_is("DUMMYFORWAIT"))
                    
                    driver.uninstall_addon("{529b261b-df0b-4e3b-bf42-07b462da0ee8}")
                    
                    self.wait_until(driver, 2, ec.title_is("DUMMYFORWAIT"))
                    
                    #driver.set_window_size(1920, 525)
                    driver.maximize_window()                    
                    
                    driver.get(self._SITE_URL)
                    driver.add_cookie({"name": "warn", "value":"1", "domain": "www.hungyoungbrit.com", "secure": False, "httpOnly": False, "sameSite": "Lax"})  
                    driver.get(_home_url)  
                    #self.wait_until(driver, 30, ec.url_changes(""))
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
                    HungYoungBritIE._COOKIES = driver.get_cookies()
                    driver.quit()
                                
                    with open("/Users/antoniotorres/Projects/common/logs/HYB_cookies.json", "w") as f:
                        json.dump(HungYoungBritIE._COOKIES, f)
                        
                    for cookie in HungYoungBritIE._COOKIES:
                        HungYoungBritIE._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
                        
                    res = HungYoungBritIE._CLIENT.get(_home_url)
                        
                    if _home_url in str(res.url):
                        self.to_screen("login OK - 229")
                    else: raise ExtractorError("Error cookies")
                        
                    
                                
                                
                except ExtractorError as e:
                    raise
                except Exception as e:                    
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")                    
                    raise ExtractorError(str(e)) from e
                        
                    
                            
                            
                
                
    
    def _real_extract(self, url):
        
            
        try:  
               
            self.report_extraction(url)
            
 
            res = HungYoungBritIE._CLIENT.get(url)
        
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
        finally:
            with HungYoungBritIE._LOCK:
                
                try:
                    self._downloader.params.get('dict_videos_to_dl', {}).get('HungYoungBrit',[]).remove(url)
                except ValueError as e:
                    self.to_screen(str(e))
                count = len(self._downloader.params.get('dict_videos_to_dl', {}).get('HungYoungBrit',[]))  
                self.to_screen(f"COUNT: [{count}]")
                if count == 0:
                    self.to_screen("CLOSE CLIENT")
                    HungYoungBritIE._CLIENT.close()
                    
       
                    
                    
            
            
            
          
        
