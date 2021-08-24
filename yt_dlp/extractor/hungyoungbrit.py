# coding: utf-8
from __future__ import unicode_literals
from tarfile import ExtractError

from .common import InfoExtractor

from ..utils import (
    ExtractorError, 
    int_or_none,
    sanitize_filename,
    str_or_none    

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
from queue import Queue
import json

import os


class warnage_or_():
    
    def __call__(self, driver):
        
        el = driver.find_elements_by_css_selector("nav.l-header__menu")        
        if el:            
            return ("loginok", el[0])       
        else:
            
            el = driver.find_elements_by_css_selector("a.g-btn.m-rounded.m-twitter")
            if el: return ("reqlogin", el[0])
            else: return False

class HungYoungBritIE(InfoExtractor):
    
    IE_NAME = "hungyoungbrit"
    _SITE_URL = 'https://www.hungyoungbrit.com'
    _NETRC_MACHINE = 'hungyoungbrit'
    _VALID_URL = r'https?://(www\.)?hungyoungbrit\.com/members/gallery\.php\?id=(?P<id>\d+)&type=vids'
   
    _QUEUE = Queue()    
    
    _LOCK = threading.Lock()
    
    _DRIVER = 0
  
    
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
        
                 
        with self._LOCK:
            
            if self._DRIVER == self._downloader.params.get('winit'):
                return   

            try:
                prof = self._FF_PROF.pop()
                self._FF_PROF.insert(0,prof)
                self.to_screen(f"[ff] {prof}")
                opts = Options()
                opts.headless = True                
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-application-cache")
                opts.add_argument("--disable-gpu")
                opts.add_argument("--disable-dev-shm-usage")
                os.environ['MOZ_HEADLESS_WIDTH'] = '1920'
                os.environ['MOZ_HEADLESS_HEIGHT'] = '1080'
                driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof))
                
                self.wait_until(driver, 5, ec.title_is("DUMMYFORWAIT"))
                
                driver.uninstall_addon('uBlock0@raymondhill.net')
                
                self.wait_until(driver, 5, ec.title_is("DUMMYFORWAIT"))
                
                driver.uninstall_addon("{529b261b-df0b-4e3b-bf42-07b462da0ee8}")
                
                driver.set_window_size(1920, 525)
                
                                           
                driver.get("https://www.hungyoungbrit.com/members/category.php?id=5")
                self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "html")))
                #el = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a.dropdown-toggle.londrina")))
                                            
                _cookies = None
                try:                            
                    with open("/Users/antoniotorres/Projects/common/logs/HYB_cookies.json", "r") as f:
                            _cookies = json.load(f)
                except Exception as e:
                    pass                            
                    
                if _cookies:
                    driver.delete_all_cookies()
                    for cookie in _cookies:
                        driver.add_cookie(cookie)
                        
                    driver.get("https://www.hungyoungbrit.com/members/category.php?id=5")
                    self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "html")))
                    

                el = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a.dropdown-toggle.londrina")))
                if not el: raise ExtractorError("not info")
                #el_warn = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a.close")))
                el_warn = driver.find_elements_by_css_selector("a.close")
                if el_warn:
                    el_warn[0].click()
                if str_or_none(el.get_attribute('text'), default="").upper().strip() == 'LOG IN':
                
                    self.report_login()
                    
                                        
                    driver.quit()
                    #self.kill_geckodriver()
                    #del driver
                    opts.headless = False
                    driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, 
                                    firefox_profile=FirefoxProfile(prof))
                    
                    self.wait_until(driver, 5, ec.title_is("DUMMYFORWAIT"))
                
                    driver.uninstall_addon('uBlock0@raymondhill.net')
                
                    self.wait_until(driver, 5, ec.title_is("DUMMYFORWAIT"))
                
                    driver.uninstall_addon("{529b261b-df0b-4e3b-bf42-07b462da0ee8}")
                
                    driver.set_window_size(1920, 525)
                    
                    #driver.maximize_window() 
                                            
                    driver.get("https://www.hungyoungbrit.com/members/category.php?id=5")                    
                    el = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a.dropdown-toggle.londrina")))
                    if not el: raise ExtractorError("not info") 
                    #el_warn = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a.close")))
                    el_warn = driver.find_elements_by_css_selector("a.close")
                    if el_warn:
                        el_warn[0].click()
                    
                    #time.sleep(1) 
                    
                    
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
                    
                    self.wait_until(driver, 300, ec.url_changes("https://www.hungyoungbrit.com/tour/pages.php?id=members-only")) 
                    
                    if driver.current_url != "https://www.hungyoungbrit.com/members/index.php": raise ExtractError("login error")
                    
                    
                    
                    #self.wait_until(driver, 300, ec.url_to_be("https://www.hungyoungbrit.com/members/index.php"))
                    _cookies = driver.get_cookies()
                    driver.quit()
                    #del driver
                    #self.kill_geckodriver()
                    opts.headless = True
                    driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, 
                                    firefox_profile=FirefoxProfile(prof))
                    
                    self.wait_until(driver, 5, ec.title_is("DUMMYFORWAIT"))
                
                    driver.uninstall_addon('uBlock0@raymondhill.net')
                
                    self.wait_until(driver, 5, ec.title_is("DUMMYFORWAIT"))
                
                    driver.uninstall_addon("{529b261b-df0b-4e3b-bf42-07b462da0ee8}")
                
                    driver.set_window_size(1920, 525)
                    #driver.maximize_window()                           
                    driver.get("https://www.hungyoungbrit.com/members/category.php?id=5")
                    self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "html")))
                    driver.delete_all_cookies()
                    for cookie in _cookies:
                        driver.add_cookie(cookie)                        
                    driver.get("https://www.hungyoungbrit.com/members/category.php?id=5")
                    el = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a.dropdown-toggle.londrina")))
                    if not el: raise ExtractorError("not info")
                    if str_or_none(el.get_attribute('text'), default="").upper().strip() != 'ACCOUNT': raise ExtractorError("not info")
                    
                    
                self.to_screen("login OK")         
                 
                _cookies = driver.get_cookies()
                
                driver.minimize_window()
                  
                with open("/Users/antoniotorres/Projects/common/logs/HYB_cookies.json", "w") as f:
                    json.dump(_cookies, f)
                    
                
            
            except Exception as e:                    
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
                if "ExtractorError" in str(e.__class__): raise
                else: raise ExtractorError(str(e))
                
            self._DRIVER += 1
                    
            self._QUEUE.put_nowait(driver)
                
    
    def _real_extract(self, url):
        
            
        try:
            
           
            
            _driver = self._QUEUE.get(block=True)
               
            self.report_extraction(url)
            
            _driver.get(url)
            
            el = self.wait_until(_driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "button#dropdownMenu2.btn.btn-default.btn-lg.btn-block.btn-bar.dropdown-toggle")))
            if not el: raise ExtractorError("not video info")
            
            webpage = html.unescape(_driver.page_source).replace('\n', '').replace('\t','')
            mobj = re.findall(r'movie\[\"(?:1080|720|480)p\"\]\[\"([^\"]+)\"\]=\{path:\"([^\"]+)\"[^\}]+movie_width:\'(\d+)\',movie_height:\'(\d+)\'[^\}]+\}',webpage.replace(' ',''))
            if not mobj: 
                self.to_screen(webpage)
                raise ExtractorError("no video info")
            
            video_id = str(int(hashlib.sha256((mobj[0][0]).encode('utf-8')).hexdigest(),16) % 10**8)
            #self.to_screen(mobj)
            title = sanitize_filename(_driver.title, True).upper()
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
            #self.to_screen(formats)
            
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))
        finally:
            self._QUEUE.put_nowait(_driver)
            
        return({
                'id': video_id,
                'title': title,
                'formats': formats 
            })   
        
