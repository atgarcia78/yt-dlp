from __future__ import unicode_literals

import json


from .webdriver import SeleniumInfoExtractor
from ..utils import (
    ExtractorError,
    int_or_none,
    block_exceptions   
)


import re
import httpx


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
from browsermobproxy import Server

import html


import sys
import traceback
import threading


from datetime import datetime 

from backoff import on_exception, constant
from ratelimit import limits, sleep_and_retry


class error404_or_found():
    
    def __call__(self, driver):
        
        el = driver.find_elements(by=By.CLASS_NAME, value="b-404")        
        if el:            
            return ("error404", el[0])       
        else:
            
            el = driver.find_elements(by=By.CLASS_NAME, value="b-profile__user")
            if el: return ("userfound", el[0])
            else: 
                el = driver.find_elements(by=By.CLASS_NAME, value="video-wrapper")
                if el: return ("postfound", el[0])
                return False
    

class alreadylogin_or_reqtw():
    
    def __call__(self, driver):
        
        el = driver.find_elements(by=By.CSS_SELECTOR, value="nav.l-header__menu")        
        if el:            
            return ("loginok", el[0])       
        else:
            
            el = driver.find_elements(by=By.CSS_SELECTOR, value="a.g-btn.m-rounded.m-twitter.m-lg")

            if el: return ("reqlogin", el[0])
            else: return False
            

class succ_or_twlogin():
    
    def __call__(self, driver):
        
        el = driver.find_elements(by=By.CSS_SELECTOR, value="nav.l-header__menu")        
        if el:            
            return ("loginok", el[0])       
        else:
            
            el_username = driver.find_elements(by=By.CSS_SELECTOR, value="input#username_or_email.text")
            el_password =  driver.find_elements(by=By.CSS_SELECTOR, value="input#password.text") 
            el_login = driver.find_elements(by=By.CSS_SELECTOR, value="input#allow.submit.button.selected")
                        
            if el_username and el_password and el_login:
                return ("twlogin", el_username[0], el_password[0], el_login[0])
            
            else:
                return False
    
    
class succ_or_twrelogin():
    
    def __call__(self, driver):
        
        el = driver.find_elements(by=By.CSS_SELECTOR, value="nav.l-header__menu")        
        if el:            
            return ("loginok", el[0])       
        else:

            el_username = driver.find_elements(by=By.PARTIAL_LINK_TEXT, value="usuario") or driver.find_elements(by=By.PARTIAL_LINK_TEXT, value="user")
            el_password =  driver.find_elements(by=By.PARTIAL_LINK_TEXT, value="Contra") or driver.find_elements(by=By.PARTIAL_LINK_TEXT, value="Pass")              
           
            el_login = driver.find_elements(by=By.PARTIAL_LINK_TEXT, value="Iniciar") or driver.find_elements(by=By.PARTIAL_LINK_TEXT, value="Start")
            
            if el_username and el_password and el_login:
                return ("twrelogin", el_username[0], el_password[0], el_login[0])
            
            else:
                return False

class OnlyFansBaseIE(SeleniumInfoExtractor):

    _SITE_URL = "https://onlyfans.com"
    #log in via twitter
    _NETRC_MACHINE = 'twitter2'

    _LOCK = threading.Lock()
     
    _COUNT = 0
    
    _COOKIES = None
    
    
    @block_exceptions
    @on_exception(constant, Exception, max_tries=5, interval=1)
    def _get_filesize(_vurl):

        res = httpx.head(_vurl, follow_redirects=True)
        res.raise_for_status()
        _fsize = int_or_none(res.headers.get('content-length'))
        if _fsize: return(_fsize)
        else: raise ExtractorError("no video info")
        
    @block_exceptions
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @sleep_and_retry
    @limits(calls=1, period=0.1)    
    def send_request(self, driver, url):
                
        driver.execute_script("window.stop();")
        driver.get(url)

    def scan_for_request(self, _har, _ref, _link):
                          
        self.write_debug(_har)
        
        for entry in _har['log']['entries']:
                            
            if entry['pageref'] == _ref:
                
                if _link in (_url:=entry['request']['url']):
                    
                    self.write_debug(_url)                   
            
                    if ((_res:=entry.get('response')) and (_content:=_res.get('content')) and (_text:=_content.get('text'))):                         
                    
                        _str = html.unescape(_text)
                        _info_str = re.sub('[\t\n]', '', _str)
                        _info_json = json.loads(_info_str)
                        if _info_json:
                            return(_info_json)
                    
    def scan_for_all_requests(self, _har, _ref, _reg):
                          
        _list_info_json = []
        
        self.write_debug(_har)
        
        for entry in _har['log']['entries']:
                            
            if entry['pageref'] == _ref:
                if re.search(_reg, (_url:=entry['request']['url'])):
                    
                    self.write_debug(_url)                   
            
                    if ((_res:=entry.get('response')) and (_content:=_res.get('content')) and (_text:=_content.get('text'))):                         
                    
                        
                        _info_str = re.sub('[\t\n]', '', html.unescape(_text))
                        _info_json = json.loads(_info_str)
                        if _info_json: _list_info_json.append(_info_json)
            
        return _list_info_json
    
    def _logout(self, driver):
              
        push_el = self.wait_until(driver, 30, ec.presence_of_element_located(
                 (By.CSS_SELECTOR, "button.l-header__menu__item.m-size-lg-hover.m-with-round-hover.m-width-fluid-hover") ))
        
        if push_el: push_el.click()
        
        el_menu = self.wait_until(driver, 30, ec.presence_of_all_elements_located(
                 (By.CSS_SELECTOR, "button.l-sidebar__menu__item") ))
        
        if el_menu:
            for _el in el_menu:
                if _el.get_attribute('at-attr') == 'logout':
                    _el.click()
                    return
    
    def _login(self, driver):
        

        username, password = self._get_login_info()
    
        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)

        self.report_login()

        try:

             
            self.send_request(driver, self._SITE_URL)
            self.wait_until(driver, 2, ec.title_is("DUMMYFORWAIT"))        

            
            el_init = self.wait_until(driver, 60, alreadylogin_or_reqtw())
            if not el_init: raise ExtractorError("Error in login")
            if el_init[0] == "loginok": 
                self.to_screen("Login OK")
                return
            else: 
                #el_init[1].click()
                self.send_request(driver, el_init[1].get_attribute('href'))
            
            el = self.wait_until(driver, 60, succ_or_twlogin())            

            if el:
                if el[0] == "loginok":
                    self.to_screen("Login OK")
                    return
                    
                else:
                    username_element, password_element, login_element = el[1], el[2], el[3]
                    username_element.send_keys(username)
                    password_element.send_keys(password)            
                    login_element.submit()
                    
                    el = self.wait_until(driver, 60, succ_or_twrelogin())
                
                    if el:
                        if el[0] == "loginok":
                            self.to_screen("Login OK")
                            return
                        else:
                            username_element, password_element, login_element = el[1], el[2], el[3]
                            username_element.send_keys(username)
                            password_element.send_keys(password)            
                            login_element.submit()
                            el = self.wait_until(driver, 30, ec.presence_of_all_elements_located(
                                (By.CSS_SELECTOR, "nav.l-header__menu") ))
                            if el:
                                self.to_screen("Login OK")
                                return
                            else: raise ExtractorError("login error")
                        
                                            
                    else:
                        raise ExtractorError("Error in relogin via twitter: couldnt find any of the twitter login elements")
         
            else:
                raise ExtractorError("Error in login via twitter: couldnt find any of the twitter login elements")
             

        except Exception as e:            
            self.to_screen(f'{type(e)}')
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')
            raise           
 
    def _extract_from_json(self, data_post, users_dict={}, user_profile=None):

        try:
            self.write_debug(f"[extract_from_json][input] {data_post}")            
            
            account = user_profile or users_dict.get(data_post.get('fromUser', {}).get('id'))
            date_timestamp = int(datetime.fromisoformat((_datevideo:=data_post.get('createdAt','') or data_post.get('postedAt',''))).timestamp())

            _entries = []
            
            for _media in data_post['media']:
                
                if _media['type'] == "video":
                    
                    videoid = _media['id']
                    _formats = []
                    orig_width = orig_height = None
                    
                    if _url:=_media.get('source',{}).get('source'):
                        _filesize = self._get_filesize(_url)
                         
                        _formats.append({
                            'url': _url,
                            'width': (orig_width := _media.get('info',{}).get('source', {}).get('width')),
                            'height': (orig_height := _media.get('info',{}).get('source', {}).get('height')),
                            'format_id': f"{orig_height}p-orig",
                            'filesize': _filesize,
                            'format_note' : "original",
                            'ext': "mp4"
                        })
                        
                    if _url2:=_media.get('videoSources',{}).get('720'):
                            _filesize2 = self._get_filesize(_url2)
                            
                            if orig_width and orig_height and (orig_width > orig_height):
                                height = 720
                                width = 1280
                            else:
                                width = 720
                                height = 1280
                            
                            _formats.append({
                                'format_id': f"{height}p",
                                'url': _url2,
                                'format_note' : "720",
                                'height': height,
                                'width': width,
                                'filesize': _filesize2,
                                'ext': "mp4"
                            })

                    if _url3:=_media.get('videoSources',{}).get('240'):
                            _filesize3 = self._get_filesize(_url3)
                            
                            if orig_width and orig_height and (orig_width > orig_height):
                                height = 240
                                width = 426
                            else:
                                width = 426
                                height = 240
                            
                            _formats.append({
                                'format_id': f"{height}p",
                                'url': _url3,
                                'format_note' : "240",
                                'height': height,
                                'width': width,
                                'filesize': _filesize3,
                                'ext': "mp4"
                            })
                    
                    if _formats: 
                    
                        if orig_width > orig_height:
                            self._sort_formats(_formats, field_preference=('height', 'width'))
                        else:
                            self._sort_formats(_formats, field_preference=('width', 'height'))
                            
                        _entries.append({
                                "id" :  str(videoid),
                                "release_timestamp": date_timestamp,
                                "release_date" :  _datevideo.split("T")[0].replace("-", ""),
                                "title" :  _datevideo.split("T")[0].replace("-", "") + "_from_" + account,
                                "formats" : _formats,
                                "duration" : _media.get('info',{}).get('source', {}).get('duration', 0),
                                "ext" : "mp4"})
        
            self.write_debug(f'[extract_from_json][output] {_entries}')
            return _entries
        
        except Exception as e:            
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'[extract_from_json][output] {type(e)} \n{"!!".join(lines)}')

    def _real_initialize(self):

        with OnlyFansBaseIE._LOCK: 
            
            if OnlyFansBaseIE._COOKIES:
                return           

            driver = self.get_driver()

            try:
                self._login(driver)
                
                OnlyFansBaseIE._COOKIES = driver.get_cookies()
                
            except ExtractorError as e:                 
                raise 
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
                raise ExtractorError(str(e)) from e
            finally:
                self.rm_driver(driver)
                                            


class OnlyFansPostIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:post:playlist'
    IE_DESC = 'onlyfans:post:playlist'
    _VALID_URL =  r"https?://(?:www\.)?onlyfans.com/(?P<post>[\d]+)/(?P<account>[\da-zA-Z]+)"

                
    def _real_extract(self, url):

        try:            
            
            with OnlyFansPostIE._LOCK:
                _server_port = 18080 + 100*OnlyFansPostIE._COUNT
                OnlyFansPostIE._COUNT += 1
                _server = Server(path="/Users/antoniotorres/Projects/async_downloader/browsermob-proxy-2.1.4/bin/browsermob-proxy", options={'port': _server_port})
                _server.start({'log_path': '/dev', 'log_file': 'null'})
                _host = 'localhost'
                _port = _server_port + 1                
                _mitmproxy = _server.create_proxy({'port' : _port})

            driver  = self.get_driver(host=_host, port=_port)
            self.send_request(driver, self._SITE_URL)
            for cookie in OnlyFansPostIE._COOKIES:
                driver.add_cookie(cookie)
            
            self.report_extraction(url)                  

            post, account = re.search(self._VALID_URL, url).group("post", "account")

            self.to_screen("post:" + post + ":" + "account:" + account)
            
            entries = {} 
            
            _mitmproxy.new_har(options={'captureHeaders': False, 'captureContent': True}, ref=f"har_{post}", title=f"har_{post}")
            self.send_request(driver, url) 
            res = self.wait_until(driver, 30, error404_or_found())
            if not res or res[0] == "error404": raise ExtractorError("Post doesnt exists")
            har = _mitmproxy.har            
            data_json = self.scan_for_request(har, f"har_{post}", f"/api2/v2/posts/{post}")
            if data_json:
                self.write_debug(data_json)                
                _entry = self._extract_from_json(data_json, user_profile=account)
                if _entry: 
                    for _video in _entry:
                        if not _video['id'] in entries.keys(): entries[_video['id']] = _video
                        else:
                            if _video['duration'] > entries[_video['id']]['duration']:
                                entries[_video['id']] = _video               
            
            if entries:
                return self.playlist_result(list(entries.values()), "Onlyfans:" + account, "Onlyfans:" + account)
            else:
                raise ExtractorError("No entries")
                 
        
        except ExtractorError as e:
            raise
        except Exception as e:                
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')
            raise                
 
            
        finally:
            _mitmproxy.close()
            _server.stop()
            self.rm_driver(driver)
            
            

        
                                                       

class OnlyFansPlaylistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:playlist'
    IE_DESC = 'onlyfans:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans.com/(?P<account>\w+)/((?P<mode>(?:all|latest|chat|favorites|tips))/?)$"
    _MODE_DICT = {"favorites" : "?order=favorites_count_desc", "tips" : "?order=tips_summ_desc", "all" : "", "latest" : ""}
    
    
           
   
    def _real_extract(self, url):
 
        try:
            self.report_extraction(url)
            
            with OnlyFansPlaylistIE._LOCK:
                _server_port = 18080 + 100*OnlyFansPlaylistIE._COUNT
                OnlyFansPlaylistIE._COUNT += 1            
                _server = Server(path="/Users/antoniotorres/Projects/async_downloader/browsermob-proxy-2.1.4/bin/browsermob-proxy", options={'port': _server_port})
                _server.start({'log_path': '/dev', 'log_file': 'null'})
                _host = 'localhost' 
                _port = _server_port + 1               
                _mitmproxy = _server.create_proxy({'port' : _port})

            driver  = self.get_driver(host=_host, port=_port)
            self.send_request(driver, self._SITE_URL)
            for cookie in OnlyFansPlaylistIE._COOKIES:
                driver.add_cookie(cookie)
            
            account, mode = re.search(self._VALID_URL, url).group("account", "mode")            
            if not mode:
                mode = "latest"
            
            entries = {}
            
            self.send_request(driver, f"{self._SITE_URL}/{account}")
            res = self.wait_until(driver, 30, error404_or_found())
            if not res or res[0] == "error404": raise ExtractorError("User profile doesnt exists")
            
            if mode in ("all", "latest", "favorites","tips"):
                
                _url = f"{self._SITE_URL}/{account}/videos{self._MODE_DICT[mode]}"
                
                driver.add_cookie({'name': 'wallLayout','value': 'grid', 'domain': '.onlyfans.com', 'path' : '/'})
                            
                _mitmproxy.new_har(options={'captureHeaders': False, 'captureContent': True}, ref=f"har_{account}_{mode}", title=f"har_{account}_{mode}")
                
                self.send_request(driver, _url)
                self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "js-posts-container")))
                
                if mode in ("latest"):
                    har = _mitmproxy.har
                    data_json = self.scan_for_request(har, f"har_{account}_{mode}", "posts/videos?")
                    if data_json:
                        self.write_debug(data_json)
                        list_json = data_json.get('list')
                        if list_json:                            
                            for info_json in list_json:                                                  
                                _entry = self._extract_from_json(info_json, user_profile=account)
                                if _entry: 
                                    for _video in _entry:
                                        if not _video['id'] in entries.keys(): entries[_video['id']] = _video
                                        else:
                                            if _video.get('duration', 1) > entries[_video['id']].get('duration', 0):
                                                entries[_video['id']] = _video

                else:            
                    
                    
                    SCROLL_PAUSE_TIME = 2 

                    last_height = driver.execute_script("return document.body.scrollHeight")

                    while True:
                        # Scroll down to bottom
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

                        # Wait to load page
                        self.wait_until(driver, SCROLL_PAUSE_TIME, ec.title_is("DUMMYFORWAIT"))
                        #time.sleep(SCROLL_PAUSE_TIME)                    

                        # Calculate new scroll height and compare with last scroll height
                        new_height = driver.execute_script("return document.body.scrollHeight")
                        if new_height == last_height:
                            break
                        last_height = new_height
                        
                    har = _mitmproxy.har
                    _reg_str = r'/api2/v2/users/\d+/posts/videos\?'
                    data_json = self.scan_for_all_requests(har, f"har_{account}_{mode}", _reg_str)
                    if data_json:
                        self.write_debug(data_json)
                        list_json = []
                        for el in data_json:
                            list_json += el.get('list')
                    
                        self.write_debug(list_json)
                        
                        for info_json in list_json:                                                  
                            _entry = self._extract_from_json(info_json, user_profile=account)
                            if _entry: 
                                for _video in _entry:
                                    if not _video['id'] in entries.keys(): entries[_video['id']] = _video
                                    else:
                                        
                                        if _video.get('duration', 1) > entries[_video['id']].get('duration', 0):
                                            entries[_video['id']] = _video
            
            elif mode in ("chat"):
                
                _url =  f"{self._SITE_URL}/{account}"
                self.send_request(driver, _url)
                el = self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CLASS_NAME, "g-btn.m-rounded.m-border.m-icon.m-icon-only.m-colored.has-tooltip")))
                for _el in el:
                    if (link:=_el.get_attribute('href')): break
                    
                _mitmproxy.new_har(options={'captureHeaders': False, 'captureContent': True}, ref=f"har_{account}_{mode}", title=f"har_{account}_{mode}")
                
                userid = link.split("/")[-1]
                
                self.send_request(driver, f'{link}/gallery')
                
                SCROLL_PAUSE_TIME = 2
                
                last_height = driver.execute_script("return document.body.scrollHeight")

                while True:
                    # Scroll down to bottom
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

                    # Wait to load page
                    self.wait_until(driver, SCROLL_PAUSE_TIME, ec.title_is("DUMMYFORWAIT"))
                    #time.sleep(SCROLL_PAUSE_TIME)                    
                    

                    # Calculate new scroll height and compare with last scroll height
                    new_height = driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height:
                        break
                    last_height = new_height
                
                har = _mitmproxy.har
                _reg_str = r'/api2/v2/chats/\d+/media\?'
                data_json = self.scan_for_all_requests(har, f"har_{account}_{mode}", _reg_str)
                if data_json:
                    self.write_debug(data_json)
                    list_json = []
                    for el in data_json:
                        list_json += el.get('list')
                        
                    for info_json in list_json:
                        
                        _entry = self._extract_from_json(info_json, user_profile=account)
                        if _entry: 
                            for _video in _entry:
                                if not _video['id'] in entries.keys(): entries[_video['id']] = _video
                                else:
                                    if _video.get('duration', 1) > entries[_video['id']].get('duration', 0):
                                        entries[_video['id']] = _video
                
            if entries:
                return self.playlist_result(list(entries.values()), "Onlyfans:" + account, "Onlyfans:" + account)
            else:
                raise ExtractorError("no entries") 
            
        
        except ExtractorError as e:
            raise 
        except Exception as e:            
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e)) from e
        
        finally:
            _mitmproxy.close()
            _server.stop()
            self.rm_driver(driver)
            
            
class OnlyFansPaidlistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfanspaidlist:playlist'
    IE_DESC = 'onlyfanspaidlist:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans\.com/paidlist"
    _PAID_URL = "https://onlyfans.com/purchased"


    def _real_extract(self, url):
 
        try:
            
            
            self.report_extraction(url)
            
            with OnlyFansPaidlistIE._LOCK:
                _server_port = 18080 + 100*OnlyFansPaidlistIE._COUNT
                OnlyFansPaidlistIE._COUNT += 1            
                _server = Server(path="/Users/antoniotorres/Projects/async_downloader/browsermob-proxy-2.1.4/bin/browsermob-proxy", options={'port': _server_port})
                _server.start({'log_path': '/dev', 'log_file': 'null'})
                _host = 'localhost' 
                _port = _server_port + 1   
                _host = 'localhost'                
                _mitmproxy = _server.create_proxy({'port' : _port})
        
            driver  = self.get_driver(host=_host, port=_port)
            self.send_request(driver, self._SITE_URL)
            for cookie in OnlyFansPaidlistIE._COOKIES:
                driver.add_cookie(cookie)
            
            _mitmproxy.new_har(options={'captureHeaders': False, 'captureContent': True}, ref="har_paid", title="har_paid")
            self.send_request(driver, self._SITE_URL)
            list_el = self.wait_until(driver, 60, ec.presence_of_all_elements_located(
                (By.CLASS_NAME, "b-tabs__nav__item") ))
            for el in list_el:
                if re.search(r'(?:purchased|comprado)',el.get_attribute("textContent").lower()):
                    el.click()
                    break
            self.wait_until(driver, 60, ec.presence_of_element_located(
                (By.CLASS_NAME, "user_posts") ))
       
                
            SCROLL_PAUSE_TIME = 2


            last_height = driver.execute_script("return document.body.scrollHeight")

            while True:
                # Scroll down to bottom
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

                # Wait to load page
                self.wait_until(driver, SCROLL_PAUSE_TIME, ec.title_is("DUMMYFORWAIT"))

                # Calculate new scroll height and compare with last scroll height
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                
            
            har = _mitmproxy.har           
            users_json = self.scan_for_all_requests(har, "har_paid", r'/api2/v2/users/list')
            if users_json:
                self.to_screen("users list attempt success")                    
                users_dict = dict()
                for _users in users_json:
                    for user in _users.keys():
                        users_dict.update({_users[user]['id']:_users[user]['username']})
            else:
                    self.to_screen("User-dict loaded manually")
                    users_dict = dict()
                    users_dict.update({127138: 'lucasxfrost',
                    1810078: 'sirpeeter',
                    5442793: 'stallionfabio',
                    7820586: 'mreyesmuriel'})
                
            self.to_screen(users_dict)
            
            entries = {}
            _reg_str = r'/api2/v2/posts/paid\?'
            data_json = self.scan_for_all_requests(har, "har_paid", _reg_str)
            if data_json:
                self.write_debug(data_json)
                list_json = []
                for el in data_json:
                    list_json += el['list']                               
                
                for info_json in list_json:
                    for _video in self._extract_from_json(info_json, users_dict=users_dict):
                        if not _video['id'] in entries.keys(): entries[_video['id']] = _video
                        else:
                            if _video.get('duration', 1) > entries[_video['id']].get('duration', 0):
                                entries[_video['id']] = _video
                         
                
           
            if entries:
                return self.playlist_result(list(entries.values()), "Onlyfans:paid", "Onlyfans:paid")
            else:
                raise ExtractorError("no entries") 
                 
            
        except ExtractorError as e:
            raise 
        except Exception as e:            
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e)) from e
            
            
        finally:
            _mitmproxy.close()
            _server.stop()
            self.rm_driver(driver)