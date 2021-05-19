from __future__ import unicode_literals

import json
import requests

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    std_headers
)


import re
import time
import hashlib
import random
import httpx

from seleniumwire import webdriver
#from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options
from selenium.webdriver import FirefoxProfile
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
from selenium.webdriver import FirefoxProfile
from selenium.common.exceptions import TimeoutException
# import Action chains 
from selenium.webdriver.common.action_chains import ActionChains
  
# import KEYS
from selenium.webdriver.common.keys import Keys


from urllib.parse import urlparse

from pathlib import Path

from rclone import RClone
import sys
import traceback

import logging



class succ_or_twlogin():
    
    def __call__(self, driver):
        
        el = driver.find_elements_by_css_selector("nav.l-header__menu")        
        if el:            
            return (el[0],)       
        else:
            
             # username_element = self.wait_until(driver, 120, ec.presence_of_element_located(                
            #     (By.CSS_SELECTOR, "input#username_or_email") ))
            # password_element = self.wait_until(driver, 120, ec.presence_of_element_located(                
            #     (By.CSS_SELECTOR, "input#password") ))
            # login_element = self.wait_until(driver, 120, ec.presence_of_element_located(                
            #     (By.CSS_SELECTOR, "input#allow.submit") ))
            el_username = driver.find_elements_by_css_selector("input#username_or_email")
            el_password =  driver.find_elements_by_css_selector("input#password")                
           
            el_login = driver.find_elements_by_css_selector("input#allow.submit")
            
            
            if el_username and el_password and el_login:
                return (el_username[0], el_password[0], el_login[0])
            
            else:
                return False
    
    
class succ_or_twrelogin():
    
    def __call__(self, driver):
        
        el = driver.find_elements_by_css_selector("nav.l-header__menu")        
        if el:            
            return (el[0])       
        else:
            
           # el_username = ec.presence_of_element_located(
           #     (By.PARTIAL_LINK_TEXT, 'usuario') )(driver)
        #    el_password =  ec.presence_of_element_located(
        #         (By.PARTIAL_LINK_TEXT, 'Contraseña') )(driver)
        # el_login = ec.presence_of_element_located(
        #         (By.PARTIAL_LINK_TEXT, 'Iniciar') )(driver)
            el_username = driver.find_elements_by_partial_link_text("usuario")
            el_password =  driver.find_elements_by_partial_link_text("Contra")               
           
            el_login = driver.find_elements_by_partial_link_text("Iniciar")
            
            if el_username and el_password and el_login:
                return (el_username[0], el_password[0], el_login[0])
            
            else:
                return False

class OnlyFansBaseIE(InfoExtractor):

    _SITE_URL = "https://onlyfans.com"
    

    _APP_TOKEN = "33d57ade8c02dbc5a333db99ff9ae26a" 

    #log in via twitter
    _NETRC_MACHINE = 'twitter2'
    
    _USER_ID = "4090129"
    
    _FF_PROF = [        
            "/Users/antoniotorres/Library/Application Support/Firefox/Profiles/0khfuzdw.selenium0","/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium","/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2","/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3","/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4","/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy", "/Users/antoniotorres/Library/Application Support/Firefox/Profiles/f7zfxja0.selenium_noproxy"
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
   
    
    def _login(self, driver):

        username, password = self._get_login_info()
    
        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)

        self.report_login()

        try:


            driver.get(self._SITE_URL)
            time.sleep(2)          
            twitter_element = self.wait_until(driver, 30, ec.presence_of_element_located(
                 (By.CSS_SELECTOR, "a.g-btn.m-rounded.m-twitter") ))
   
            if twitter_element:
                twitter_element.click()
                time.sleep(2)
            else:
                raise ExtractorError("Error in login via twitter: couldnt find twitter oauth button")
            
            el = self.wait_until(driver, 60, succ_or_twlogin())            
 
            if el:
                if len(el) == 3:
                    username_element, password_element, login_element = el
                    username_element.send_keys(username)
                    password_element.send_keys(password)            
                    login_element.submit()
                    
                    el = self.wait_until(driver, 60, succ_or_twrelogin())
                
                    if el:
                        if len(el) == 3:
                            username_element, password_element, login_element = el
                            username_element.send_keys(username)
                            password_element.send_keys(password)            
                            login_element.submit()
                            el = self.wait_until(driver, 30, ec.presence_of_all_elements_located(
                                (By.CSS_SELECTOR, "nav.l-header__menu") ))
                            if not el: raise ExtractorError("login error")               
                    else:
                        raise ExtractorError("Error in relogin via twitter: couldnt find any of the twitter login elements")
         
            else:
                raise ExtractorError("Error in login via twitter: couldnt find any of the twitter login elements")
             

        except Exception as e:            
            self.to_screen(f'{type(e)}')
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')
            raise           
 
         
           

    def _extract_from_json(self, data_post, acc=False, users_dict=None, user_profile=None):

        #self.to_screen(f"[extract_from_json] {data_post}")
        
        info_dict = []
        
        index = -1
        
        if data_post['media'][0]['type'] == 'video':
            index = 0
        else:
            if len(data_post['media']) > 1:
                for j, data in enumerate(data_post['media'][1:]):
                    if data['type'] == 'video':
                        index = j + 1
                        break
            
        if index != -1:
            if acc:
                account = users_dict[data_post['fromUser']['id']]
                datevideo = data_post['createdAt'].split("T")[0]
                videoid = data_post['media'][0]['id']
            else:
                #account = data_post['author'].get['username']
                account = user_profile
                datevideo = data_post['postedAt'].split("T")[0]
                videoid = str(data_post['id'])
            
            
            

            formats = []
            
            try:

                filesize = None
                
                if acc:
                    try:
                        filesize = int(httpx.head(data_post['media'][index]['source']['source']).headers['content-length'])
                    except Exception as e:
                        pass
                    formats.append({
                        'url': data_post['media'][index]['source']['source'],
                        'width': (orig_width := data_post['media'][index]['info']['source']['width']),
                        'height': (orig_height := data_post['media'][index]['info']['source']['height']),
                        'format_id': f"{orig_height}p-orig",
                        'filesize': filesize,
                        'format_note' : "original",
                        'ext': "mp4"
                    })
                
                
                else:
                    try:
                        filesize = int(httpx.head(data_post['media'][index]['source']['source']).headers['content-length'])
                    except Exception as e:
                        pass
                    formats.append({
                        'width': (orig_width := data_post['media'][index]['info']['source']['width']),
                        'height': (orig_height := data_post['media'][index]['info']['source']['height']),
                        'format_id': f"{orig_height}p-orig",
                        'url': data_post['media'][index]['source']['source'],                        
                        'filesize': filesize,
                        'format_note' : "original",
                        'ext': "mp4"
                    })
            except Exception as e:
                    self.to_screen(str(e))
                    self.to_screen("No source video format")

            try:
                    
                if data_post['media'][index]['videoSources']['720']:
                    filesize = None
                    try:
                        filesize = int(httpx.head(data_post['media'][index]['videoSources']['720']).headers['content-length'])
                    except Exception as e:
                        pass
                    
                    if orig_width > orig_height:
                        height = 720
                        width = 1280
                    else:
                        width = 720
                        height = 1280
                    formats.append({
                        'format_id': f"{height}p",
                        'url': data_post['media'][index]['videoSources']['720'],
                        'format_note' : "720",
                        'height': height,
                        'width': width,
                        'filesize': filesize,
                        'ext': "mp4"
                    })

            except Exception as e:
                    self.to_screen(str(e))
                    self.to_screen("No info for 720p format")

            try:
                if data_post['media'][index]['videoSources']['240']:
                    filesize = None
                    try:
                        filesize = int(httpx.head(data_post['media'][index]['videoSources']['240']).headers['content-length'])
                    except Exception as e:
                        pass
                    
                    if orig_width > orig_height:
                        height = 240
                        width = 426
                    else:
                        width = 426
                        height = 240
                        
                    formats.append({
                        'format_id': f"{height}p",
                        'url': data_post['media'][index]['videoSources']['240'],
                        'format_note' : "240",
                        'height' : height,
                        'width' : width,
                        'filesize': filesize,
                        'ext': "mp4"
                    })

            except Exception as e:
                self.to_screen(str(e))
                self.to_screen("No info for 240p format")
            
           # self._check_formats(formats, videoid)
            if formats:
                if orig_width > orig_height:
                    self._sort_formats(formats, field_preference=('height', 'width', 'format_id'))
                else:
                    self._sort_formats(formats, field_preference=('width', 'height', 'format_id'))
                
                info_dict = {
                    "id" :  str(videoid),
                    "title" :  datevideo.replace("-", "") + "_from_" + account,
                    "formats" : formats,
                    "ext" : "mp4"
                }

        return info_dict
    

    
  
  
    def wait_until_json(self, driver, link, timeout):
        count = timeout
        list_requests = set()
        while (count > 0):
            
            list_requests.update(driver.requests)
            for request in list_requests:
                    
                    if link in request.url:
                        if request.response:
                            self.to_screen(f"{request.method}:{request.url}:{request.response.status_code}")
                            data_post = json.loads(request.response.body.decode())
                            return data_post
                        #return self._extract_from_json(data_post, user_profile=account)      
                   
            count -= 1
            time.sleep(1)
    
    def print_requests(self, driver, text=None):
        
        res = []
        for request in driver.requests:
            if text:
                if text in request.url:
                    self.to_screen(f"{request.method}:{request.url}:{request.response.status_code if request.response else 'NoResponse'}")
                    res.append(request)
            else:
                self.to_screen(f"{request.method}:{request.url}:{request.response.status_code if request.response else 'NoResponse'}")
        
        return res
                
            
        

# class OnlyFansResetIE(OnlyFansBaseIE):
#     IE_NAME = 'onlyfans:reset'
#     IE_DESC = 'onlyfans:reset'
#     _VALID_URL = r"onlyfans:reset"

#     def _real_initialize(self):

#         self.cookies = None
#         opts = Options()
#         opts.headless = False            
#         #prof_id = random.randint(0,5) 
#         prof_id = 0          
#         prof_ff = FirefoxProfile(self._FF_PROF[prof_id])
#         self.driver = webdriver.Firefox(options=opts, firefox_profile=prof_ff)
#         #self.driver.maximize_window()
#         time.sleep(2)   
#         try:
#             #self.driver.install_addon("/Users/antoniotorres/projects/comic_getter/myaddon/web-ext-artifacts/myaddon-1.0.zip", temporary=True)
#             self.driver.uninstall_addon('@VPNetworksLLC')
#         except Exception as e:
#             lines = traceback.format_exception(*sys.exc_info())
#             self.to.screen(f"Error: \n{'!!'.join(lines)}")
    
#         del self.driver.requests
#         self.driver.delete_all_cookies()
#         self.driver.refresh()
#         self._login(self.driver)
#         self.driver.quit()
            

class OnlyFansPostIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:post'
    IE_DESC = 'onlyfans:post'
    _VALID_URL =  r"(?:(onlyfans:post:(?P<post>.*?):(?P<account>[\da-zA-Z]+))|(https?://(?:www\.)?onlyfans.com/(?P<post2>[\d]+)/(?P<account2>[\da-zA-Z]+)))"

    driver = None
    
    def _real_initialize(self):
        
        opts = Options()
        opts.headless = False 
        opts.add_argument('--no-sandbox')
        opts.add_argument('--ignore-certificate-errors-spki-list')
        opts.add_argument('--ignore-ssl-errors')           
        #prof_id = random.randint(0,5) 
        prof_id = 0          
        prof_ff = FirefoxProfile(self._FF_PROF[prof_id])
        self.driver = webdriver.Firefox(options=opts, firefox_profile=prof_ff)
        time.sleep(2)   
        try:           

            self.driver.uninstall_addon('@VPNetworksLLC')
            #self.driver.install_addon("/Users/antoniotorres/Projects/common/addons/fire_clear_cache-1.0.0/web-ext-artifacts/fire_clear_cache-1.0.0.zip", temporary=True)
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to.screen(f"Error: \n{'!!'.join(lines)}")
    
        del self.driver.requests
        self.print_requests(self.driver)
        
        #action = ActionChains(self.driver)
  
        # perform the oepration
        #action.send_keys('F9').perform()
        
        #time.sleep(5)
        
        self.driver.get(self._SITE_URL)
        self.wait_until(self.driver, 60, ec.presence_of_element_located(
            (By.CSS_SELECTOR, "a.router-link-exact-active.router-link-active") ))
        self.driver.delete_all_cookies()
        self.driver.execute_script("window.localStorage.clear();")        
        #time.sleep(5)        
        self._login(self.driver)

    def _real_extract(self, url):
 
        try:
            self.report_extraction(url)                  

            (post1, post2, acc1, acc2) = re.search(self._VALID_URL, url).group("post", "post2", "account", "account2")
            post = post1 or post2
            account = acc1 or acc2

            self.to_screen("post:" + post + ":" + "account:" + account)
        

            info_video = None
            
            try:
                data_json = None
                del self.driver.requests
                self.driver.get(url)                
                request = self.driver.wait_for_request("/api2/v2/posts/" + post, timeout=60)
                self.to_screen(f"{request.method}:{request.url}:{request.response.status_code if request.response else 'NoResponse'}")
                self.print_requests(self.driver, "onlyfans")
                data_json = json.loads(request.response.body.decode())
            except Exception as e:
                self.to_screen(f"Exception {type(e)}")
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f'{type(e)} \n{"!!".join(lines)}')
                self.print_requests(self.driver)
                
            if data_json:
                self.to_screen(data_json)                
                info_video = self._extract_from_json(data_json, user_profile=account)
            else:
                self.to_screen("No data video")  
           
        except Exception as e:# create action chain object

            self.to_screen(f"Exception {type(e)}")
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')
            
        self.driver.quit()
        return info_video
                                                       

class OnlyFansPlaylistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:playlist'
    IE_DESC = 'onlyfans:playlist'
    _VALID_URL = r"(?:(onlyfans:account:(?P<account>[^:]+)(?:(:(?P<mode>(?:date|favs|tips|latest10)))?))|(https?://(?:www\.)?onlyfans.com/(?P<account2>\w+)(?:(/(?P<mode2>(?:date|favs|tips|latest10)))?)$))"
    _MODE_DICT = {"favs" : "favorites_count_desc", "tips" : "tips_summ_desc", "date" : "publish_date_desc", "latest10" : "publish_date_desc"}
    
    
    driver = None       
   
    def _real_initialize(self):
        opts = Options()
        opts.headless = False            
        #prof_id = random.randint(0,5) 
        prof_id = 0          
        prof_ff = FirefoxProfile(self._FF_PROF[prof_id])
        opts.add_argument('--no-sandbox')
        opts.add_argument('--ignore-certificate-errors-spki-list')
        opts.add_argument('--ignore-ssl-errors')  
        self.driver = webdriver.Firefox(options=opts, firefox_profile=prof_ff)
        
        #self.driver.maximize_window()
        time.sleep(2)   
        try:           

            self.driver.uninstall_addon('@VPNetworksLLC')
            #self.driver.install_addon("/Users/antoniotorres/Projects/common/addons/fire_clear_cache-1.0.0/web-ext-artifacts/fire_clear_cache-1.0.0.zip", temporary=True)
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to.screen(f"Error: \n{'!!'.join(lines)}")
    
        del self.driver.requests
        self.print_requests(self.driver)
        
        #action = ActionChains(self.driver)
  
        # perform the oepration
        #action.send_keys('F9').perform()
        
        #time.sleep(5)
        
        self.driver.get(self._SITE_URL)
        self.wait_until(self.driver, 60, ec.presence_of_element_located(
            (By.CSS_SELECTOR, "a.router-link-exact-active.router-link-active") ))
        self.driver.delete_all_cookies()
        self.driver.execute_script("window.localStorage.clear();")        
        #time.sleep(5)        
        self._login(self.driver)
 
                      

    def _real_extract(self, url):
 
        try:
            self.report_extraction(url)
            (acc1, acc2, mode1, mode2) = re.search(self._VALID_URL, url).group("account", "account2", "mode", "mode2")
            account = acc1 or acc2
            mode = mode1 or mode2
            if not mode:
                mode = "latest10"

            del self.driver.requests
            self.driver.add_cookie( {'name': 'wallLayout', 'value': 'list', 'path': '/',  'domain': '.onlyfans.com', 'secure': False, 'httpOnly': False, 'sameSite': 'None'})
            _url = f"{self._SITE_URL}/{account}/videos"
            self.driver.get(_url)
            data_json = self.wait_until_json(self.driver, "posts/videos?", 30 )
            
            entries = []
            list_json = []
            
            if data_json:
                list_json.extend(data_json['list']) 
            
            del self.driver.requests
            
            if mode in ("latest10"):
                if list_json:
                    entries = [self._extract_from_json(info_json, user_profile=account) for info_json in list_json]
                

            elif mode in ("date"):

            
                SCROLL_PAUSE_TIME = 2


                last_height = self.driver.execute_script("return document.body.scrollHeight")

                while True:
                    # Scroll down to bottom
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

                    # Wait to load page
                    time.sleep(SCROLL_PAUSE_TIME)                    
                    

                    # Calculate new scroll height and compare with last scroll height
                    new_height = self.driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height:
                        break
                    last_height = new_height
                    
                
                #self.print_requests(self.driver)
                list_api_requests = [_request for _request in self.driver.requests if re.search(r'/api2/v2/users/\d+/posts/videos\?', _request.url) and _request.response]
                
       
                
                
                for request in list_api_requests:
                    data_json = json.loads(request.response.body.decode())
                    self.to_screen(f"{request.url}:{request.response.status_code}\n{data_json['list']}")
                    list_json.extend(data_json['list'])
                    

                
                entries = [self._extract_from_json(info_json, user_profile=account) for info_json in list_json]
                
                
                        
                            

            elif mode in ("favs", "tips"):   
                pass             

            self.driver.quit()

            return self.playlist_result(entries, "Onlyfans:" + account, "Onlyfans:" + account)

        except Exception as e:
            self.to_screen(f"Exception {type(e)}")
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')
            self.driver.quit()
            
class OnlyFansPaidlistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:paidlist'
    IE_DESC = 'onlyfans:paidlist'
    _VALID_URL = r"onlyfans:paidlist"
    _PAID_URL = "https://onlyfans.com/purchased"
    
    driver = None
   
    def _real_initialize(self):
         
        opts = Options()
        opts.headless = False            
        #prof_id = random.randint(0,5) 
        prof_id = 0         
        prof_ff = FirefoxProfile(self._FF_PROF[prof_id])
        #prof_ff.accept_untrusted_certs = True
        #prof_ff.update_preferences()
        # prof_ff.assume_untrusted_cert_issuer = True
        opts.add_argument('--no-sandbox')
        opts.add_argument('--ignore-certificate-errors-spki-list')
        opts.add_argument('--ignore-ssl-errors') 
        self.driver = webdriver.Firefox(options=opts, firefox_profile=prof_ff)
        time.sleep(2)   
        try:           

            self.driver.uninstall_addon('@VPNetworksLLC')
            #self.driver.install_addon("/Users/antoniotorres/Projects/common/addons/fire_clear_cache-1.0.0/web-ext-artifacts/fire_clear_cache-1.0.0.zip", temporary=True)
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to.screen(f"Error: \n{'!!'.join(lines)}")
    
        del self.driver.requests
        self.print_requests(self.driver)
        
        #action = ActionChains(self.driver)
  
        # perform the oepration
        #action.send_keys('F9').perform()
        
        #time.sleep(5)
       
        
        self.driver.get(self._SITE_URL)
        self.wait_until(self.driver, 60, ec.presence_of_element_located(
            (By.CSS_SELECTOR, "a.router-link-exact-active.router-link-active") ))
        self.driver.delete_all_cookies()
        self.driver.execute_script("window.localStorage.clear();")        
        #time.sleep(5)        
        self._login(self.driver)

        
                    

    def _real_extract(self, url):
 
        try:
            
            del self.driver.requests
            self.driver.get(self._PAID_URL)
            time.sleep(1)
            users_json = self.wait_until_json(self.driver, "users/list", 30)
            if not users_json: self.to_screen("1st attempt not found")
            else:
                self.to_screen("1st attempt success")
                self.to_screen(users_json)
                users_dict = dict()
                for user in users_json.keys():
                    users_dict.update({users_json[user]['id']:users_json[user]['username']})
            
            # users_json = None
            # try:
            #     _req = self.driver.wait_for_request("/api2/v2/users/list", timeout=30)
            #     users_json = json.loads(_req.response.body.decode())
            #     self.to_screen(users_json)
            # except TimeoutException as e:
            #     self.to_screen("No users requests")
                
            SCROLL_PAUSE_TIME = 2


            last_height = self.driver.execute_script("return document.body.scrollHeight")

            while True:
                # Scroll down to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

                # Wait to load page
                time.sleep(SCROLL_PAUSE_TIME)

                # Calculate new scroll height and compare with last scroll height
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                
            if not users_json:
                users_json = self.wait_until_json(self.driver, "users/list", 10)
                self.print_requests(self.driver)
                
                if users_json:
                    self.to_screen("2nd attempt success")                    
                    users_dict = dict()
                    for user in users_json.keys():
                        users_dict.update({users_json[user]['id']:users_json[user]['username']})
                else:
                    self.to_screen("2nd attempt failed. User-dict loaded manually")
                    users_dict = dict()
                    users_dict.update({127138: 'lucasxfrost',
                    1810078: 'sirpeeter',
                    5442793: 'stallionfabio',
                    7820586: 'mreyesmuriel'})
                    
            list_api_requests = [_request for _request in self.driver.requests if (("/api2/v2/posts/paid" in _request.url) and _request.response)]
            
           
                
                       
            self.to_screen(users_dict)
            
            list_json = []
            for request in list_api_requests:
                data_json = json.loads(request.response.body.decode())
                self.to_screen(f"{request.url}:{request.response.status_code}\n{data_json}")
                list_json.extend(data_json['list'])
            
                      
            entries = [self._extract_from_json(info_json, acc=True, users_dict=users_dict) for info_json in list_json]
            #self.to_screen(data)
            
            
            return self.playlist_result(entries, "Onlyfans:paidlist", "Onlyfans:paidlist")
            
        except Exception as e:
            self.to_screen(str(e))
            lines = traceback.format_exception(*sys.exc_info())                
            self.to_screen(f"error\n{'!!'.join(lines)}")