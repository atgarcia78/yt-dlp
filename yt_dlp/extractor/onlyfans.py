from __future__ import unicode_literals

import json


from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    int_or_none   
)


import re
import time
import httpx
import os

from selenium.webdriver import Firefox, FirefoxProfile
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
from browsermobproxy import Server

import html


import sys
import traceback
import subprocess
import threading
from queue import Queue


class error404_or_found():
    
    def __call__(self, driver):
        
        el = driver.find_elements_by_class_name("b-404")        
        if el:            
            return ("error404", el[0])       
        else:
            
            el = driver.find_elements_by_class_name("b-profile__user")
            if el: return ("userfound", el[0])
            else: 
                el = driver.find_elements_by_class_name("video-wrapper")
                if el: return ("postfound", el[0])
                return False
    

class alreadylogin_or_reqtw():
    
    def __call__(self, driver):
        
        el = driver.find_elements_by_css_selector("nav.l-header__menu")        
        if el:            
            return ("loginok", el[0])       
        else:
            
            el = driver.find_elements_by_css_selector("a.g-btn.m-rounded.m-twitter.m-lg")
            #el = driver.find_elements_by_class_name("g-btn.m-rounded.m-twitter.m-lg")
            #el = driver.find_elements_by_link_text("SIGN IN WITH TWITTER")
            if el: return ("reqlogin", el[0])
            else: return False
            

class succ_or_twlogin():
    
    def __call__(self, driver):
        
        el = driver.find_elements_by_css_selector("nav.l-header__menu")        
        if el:            
            return ("loginok", el[0])       
        else:
            
            el_username = driver.find_elements_by_css_selector("input#username_or_email")
            el_password =  driver.find_elements_by_css_selector("input#password") 
            el_login = driver.find_elements_by_css_selector("input#allow.submit")
                        
            if el_username and el_password and el_login:
                return ("twlogin", el_username[0], el_password[0], el_login[0])
            
            else:
                return False
    
    
class succ_or_twrelogin():
    
    def __call__(self, driver):
        
        el = driver.find_elements_by_css_selector("nav.l-header__menu")        
        if el:            
            return ("loginok", el[0])       
        else:

            el_username = driver.find_elements_by_partial_link_text("usuario") or driver.find_elements_by_partial_link_text("user")
            el_password =  driver.find_elements_by_partial_link_text("Contra") or driver.find_elements_by_partial_link_text("Pass")              
           
            el_login = driver.find_elements_by_partial_link_text("Iniciar") or driver.find_elements_by_partial_link_text("Start")
            
            if el_username and el_password and el_login:
                return ("twrelogin", el_username[0], el_password[0], el_login[0])
            
            else:
                return False

class OnlyFansBaseIE(InfoExtractor):

    _SITE_URL = "https://onlyfans.com"   

    #log in via twitter
    _NETRC_MACHINE = 'twitter2'
    
       
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/0khfuzdw.selenium0']
    
      
    _LOCK = threading.Lock()
    
    _SERVER = None
    
    _QUEUE = Queue() 
    
    _DRIVER = 0
    
    _COUNT = 0
    
    
    def __init__(self, *args, **kwargs):
        super(OnlyFansBaseIE, self).__init__(*args, **kwargs)
        
        with OnlyFansBaseIE._LOCK:
            OnlyFansBaseIE._COUNT += 1
        
            
    
      
  
    
    def wait_until(self, driver, time, method):
        try:
            el = WebDriverWait(driver, time).until(method)
        except Exception as e:
            el = None
            
        return el  

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
    
    @staticmethod                    
    def kill_java_process(port):
        
        res = subprocess.run(["ps","ax","-o","pid","-o","command"], encoding='utf-8', capture_output=True).stdout
        _pid_list = re.findall(rf'^\ *(\d+)\ java\ .*browsermob.*port={port}', res, flags=re.MULTILINE)
        for process_id in _pid_list:
            res = subprocess.run(["kill","-9",process_id], encoding='utf-8', capture_output=True)
            # if res.returncode != 0: 
            #     self.to_screen("cant kill java proxy: " + res.stderr.decode())
            # else: self.to_screen("java proxy killed")
            
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

            driver.get(self._SITE_URL)
            time.sleep(2)          

            
            el_init = self.wait_until(driver, 60, alreadylogin_or_reqtw())
            if not el_init: raise ExtractorError("Error in login")
            if el_init[0] == "loginok": 
                self.to_screen("Login OK")
                return
            else: 
                #el_init[1].click()
                driver.get(el_init[1].get_attribute('href'))
            
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
 
    def _extract_from_json(self, data_post, acc=False, users_dict={}, user_profile=None):

        
        try:
            self.write_debug(f"[extract_from_json][input] {data_post}")
            
            
            account = user_profile or users_dict.get(data_post.get('fromUser', {}).get('id'))
            datevideo = data_post.get('createdAt','').split('T')[0] or data_post.get('postedAt','').split('T')[0]
            
            _entries = []
            
            for _media in data_post['media']:
                
                if _media['type'] == "video":
                    
                    videoid = _media['id']
                    _formats = []
                    
                    if _url:=_media.get('source',{}).get('source'):
                        _filesize = None 
                        try:
                            _filesize = int_or_none(httpx.head(_url).headers['content-length'])
                        except Exception as e:
                            pass
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
                            _filesize2 = None
                            try:
                                _filesize2 = int_or_none(httpx.head(_url2).headers['content-length'])
                            except Exception as e:
                                pass
                            
                            if orig_width > orig_height:
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
                            _filesize3 = None
                            try:
                                _filesize3 = int_or_none(httpx.head(_url2).headers['content-length'])
                            except Exception as e:
                                pass
                            
                            if orig_width > orig_height:
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
                            self._sort_formats(_formats, field_preference=('height', 'width', 'format_id'))
                        else:
                            self._sort_formats(_formats, field_preference=('width', 'height', 'format_id'))
                            
                        _entries.append({
                                "id" :  str(videoid),
                                #"id" :  str(data_post['id']),
                                "title" :  datevideo.replace("-", "") + "_from_" + account,
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
        
            try:  

                if OnlyFansBaseIE._DRIVER == self._downloader.params.get('winit', 5):
                    return  
                
                driver = None
                _mitmproxy = None
                
                prof_ff = OnlyFansBaseIE._FF_PROF.pop() 
                OnlyFansBaseIE._FF_PROF.insert(0,prof_ff)
                if not OnlyFansBaseIE._SERVER:
                              
                    OnlyFansBaseIE._SERVER = Server(path="/Users/antoniotorres/Projects/async_downloader/venv/lib/python3.9/site-packages/browsermobproxy/browsermob-proxy-2.1.4/bin/browsermob-proxy", options={'port': 18080})
                    OnlyFansBaseIE._SERVER.start()
                
                
                _port = 18081 + OnlyFansBaseIE._DRIVER
                _host = 'localhost'
                
                _mitmproxy = OnlyFansBaseIE._SERVER.create_proxy({'port' : _port})
                
                _firefox_prof = FirefoxProfile(prof_ff)
                
                _firefox_prof.set_preference("network.proxy.type", 1)
                _firefox_prof.set_preference("network.proxy.http",_host)
                _firefox_prof.set_preference("network.proxy.http_port",int(_port))
                _firefox_prof.set_preference("network.proxy.https",_host)
                _firefox_prof.set_preference("network.proxy.https_port",int(_port))
                _firefox_prof.set_preference("network.proxy.ssl",_host)
                _firefox_prof.set_preference("network.proxy.ssl_port",int(_port))
                _firefox_prof.set_preference("network.proxy.ftp",_host)
                _firefox_prof.set_preference("network.proxy.ftp_port",int(_port))
                _firefox_prof.set_preference("network.proxy.socks",_host)
                _firefox_prof.set_preference("network.proxy.socks_port",int(_port))
                _firefox_prof.set_preference("dom.webdriver.enabled", False)
                _firefox_prof.set_preference("useAutomationExtension", False)
                
                _firefox_prof.update_preferences()
                 
                #_firefox_prof.set_proxy(_mitmproxy.selenium_proxy())
                opts = Options()
                opts.headless = True
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-application-cache")
                opts.add_argument("--disable-gpu")
                opts.add_argument("--disable-dev-shm-usage")
                os.environ['MOZ_HEADLESS_WIDTH'] = '1920'
                os.environ['MOZ_HEADLESS_HEIGHT'] = '1080'
                
                driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=_firefox_prof)
                
                 
                driver.maximize_window()
      
                self._login(driver) 
                
                OnlyFansBaseIE._DRIVER += 1
                
                OnlyFansBaseIE._QUEUE.put_nowait((driver, _mitmproxy))
                
            except ExtractorError as e:                 
                raise 
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
                raise ExtractorError(str(e)) from e
                                            
                
            
    def __del__(self):
       
        with OnlyFansBaseIE._LOCK: 
            
            OnlyFansBaseIE._COUNT -= 1
            if OnlyFansBaseIE._COUNT == 0:
                #self.to_screen("LETS CLOSE DRIVERS AND PROXIES")
                for __driver, __mitmproxy in list(OnlyFansBaseIE._QUEUE.queue):
                    try:
                        __driver.quit()
                        __mitmproxy.close()
                    except Exception as e:
                        pass
                        #self.to_screen(str(e))
                #self.to_screen("ALL DRIVERS AND PROXIES CLOSED")
                if OnlyFansBaseIE._SERVER:
                    OnlyFansBaseIE._SERVER.stop()
                #self.to_screen("SERVER STOPPED")
                OnlyFansBaseIE.kill_java_process(OnlyFansBaseIE._SERVER.port) 

class OnlyFansPostIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:post:playlist'
    IE_DESC = 'onlyfans:post:playlist'
    _VALID_URL =  r"https?://(?:www\.)?onlyfans.com/(?P<post>[\d]+)/(?P<account>[\da-zA-Z]+)"

                
    def _real_extract(self, url):
 
        try:
            
            driver, _mitmproxy = OnlyFansPostIE._QUEUE.get(block=True)
            
            self.report_extraction(url)                  

            post, account = re.search(self._VALID_URL, url).group("post", "account")
            

            self.to_screen("post:" + post + ":" + "account:" + account)
        

            entries = {}            
        
            
            _mitmproxy.new_har(options={'captureHeaders': False, 'captureContent': True}, ref=f"har_{post}", title=f"har_{post}")
            driver.get(url) 
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
            OnlyFansPostIE._QUEUE.put_nowait((driver, _mitmproxy)) 
            # with OnlyFansPostIE._LOCK:
                
            #     try:
            #         self._downloader.params.get('dict_videos_to_dl', {}).get('OnlyFansPost',[]).remove(url)
            #     except ValueError as e:
            #         self.to_screen(str(e))
            #     count = len(self._downloader.params.get('dict_videos_to_dl', {}).get('OnlyFansPost',[])) + len(self._downloader.params.get('dict_videos_to_dl', {}).get('OnlyFansPlaylist',[])) + len(self._downloader.params.get('dict_videos_to_dl', {}).get('OnlyFansPaidlist',[]))
                
            #     self.to_screen(f"COUNT: [{count}]")
            #     if count == 0:
            #         self.to_screen("LETS CLOSE DRIVERS AND PROXIES")
            #         for __driver, __mitmproxy in list(OnlyFansPostIE._QUEUE.queue):
            #             try:
            #                 __driver.quit()
            #                 __mitmproxy.close()
            #             except Exception as e:
            #                 self.to_screen(str(e))
            #         self.to_screen("ALL DRIVERS AND PROXIES CLOSED")
            #         OnlyFansPostIE._SERVER.stop()
            #         self.to_screen("SERVER STOPPED")
            #         self.kill_java_process(OnlyFansPostIE._SERVER.port)
                    
                            
          
        
        
                                                       

class OnlyFansPlaylistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:playlist'
    IE_DESC = 'onlyfans:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans.com/(?P<account>\w+)/((?P<mode>(?:all|latest|chat|favorites|tips))/?)$"
    _MODE_DICT = {"favorites" : "?order=favorites_count_desc", "tips" : "?order=tips_summ_desc", "all" : "", "latest" : ""}
    
    
           
   
    def _real_extract(self, url):
 
        try:
            self.report_extraction(url)
            
            driver, _mitmproxy = OnlyFansPlaylistIE._QUEUE.get(block=True)
            
            account, mode = re.search(self._VALID_URL, url).group("account", "mode")            
            if not mode:
                mode = "latest"
            
            entries = {}
            
            driver.get(f"{self._SITE_URL}/{account}")
            res = self.wait_until(driver, 30, error404_or_found())
            if not res or res[0] == "error404": raise ExtractorError("User profile doesnt exists")
            
            
            
            if mode in ("all", "latest", "favorites","tips"):
                
                _url = f"{self._SITE_URL}/{account}/videos{self._MODE_DICT[mode]}"
                
                self.to_screen(f"URL: {_url}")
                
                driver.add_cookie({'name': 'wallLayout','value': 'grid', 'domain': '.onlyfans.com', 'path' : '/'})
                            
                _mitmproxy.new_har(options={'captureHeaders': False, 'captureContent': True}, ref=f"har_{account}_{mode}", title=f"har_{account}_{mode}")
                
                driver.get(_url)
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
                driver.get(_url)
                el = self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CLASS_NAME, "g-btn.m-rounded.m-border.m-icon.m-icon-only.m-colored.has-tooltip")))
                for _el in el:
                    if (link:=_el.get_attribute('href')): break
                    
                _mitmproxy.new_har(options={'captureHeaders': False, 'captureContent': True}, ref=f"har_{account}_{mode}", title=f"har_{account}_{mode}")
                
                userid = link.split("/")[-1]
                
                driver.get(f'{link}/gallery')
                
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
                        
                        _entry = self._extract_from_json(info_json, acc=True, user_profile=account)
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
            OnlyFansPlaylistIE._QUEUE.put_nowait((driver, _mitmproxy)) 
            # with OnlyFansPlaylistIE._LOCK:
                
            #     try:
            #         self._downloader.params.get('dict_videos_to_dl', {}).get('OnlyFansPlaylist',[]).remove(url)
            #     except ValueError as e:
            #         self.to_screen(str(e))
            #     count = len(self._downloader.params.get('dict_videos_to_dl', {}).get('OnlyFansPost',[])) + len(self._downloader.params.get('dict_videos_to_dl', {}).get('OnlyFansPlaylist',[])) + len(self._downloader.params.get('dict_videos_to_dl', {}).get('OnlyFansPaidlist',[]))
                
            #     self.to_screen(f"COUNT: [{count}]")
            #     if count == 0:
            #         self.to_screen("LETS CLOSE DRIVERS AND PROXIES")
            #         for __driver, __mitmproxy in list(OnlyFansPlaylistIE._QUEUE.queue):
            #             try:
            #                 __driver.quit()
            #                 __mitmproxy.close()
            #             except Exception as e:
            #                 self.to_screen(str(e))
            #         self.to_screen("ALL DRIVERS AND PROXIES CLOSED")
            #         OnlyFansPlaylistIE._SERVER.stop()
            #         self.to_screen("SERVER STOPPED")
            #         self.kill_java_process(OnlyFansPlaylistIE._SERVER.port)
           
            
        
            
            
class OnlyFansPaidlistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfanspaidlist:playlist'
    IE_DESC = 'onlyfanspaidlist:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans\.com/paidlist"
    _PAID_URL = "https://onlyfans.com/purchased"
    
    

    def _real_extract(self, url):
 
        try:
            
            
            self.report_extraction(url)
            
            driver, _mitmproxy = OnlyFansPaidlistIE._QUEUE.get(block=True)
            
            _mitmproxy.new_har(options={'captureHeaders': False, 'captureContent': True}, ref="har_paid", title="har_paid")
            driver.get(self._SITE_URL)
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
            
            entries = []
            _reg_str = r'/api2/v2/posts/paid\?'
            data_json = self.scan_for_all_requests(har, "har_paid", _reg_str)
            if data_json:
                self.write_debug(data_json)
                list_json = []
                for el in data_json:
                    list_json += el['list']                               
          
                entries = [self._extract_from_json(info_json, acc=True, users_dict=users_dict)[0] for info_json in list_json]
           
            if entries:
                self.write_debug(entries)
                return self.playlist_result(entries, "Onlyfanspaidlist", "Onlyfanspaidlist")
            else: raise ExtractorError("no entries")
                 
            
        except ExtractorError as e:
            raise 
        except Exception as e:            
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e)) from e
            
            
        finally:
            OnlyFansPaidlistIE._QUEUE.put_nowait((driver, _mitmproxy)) 
            # with OnlyFansPaidlistIE._LOCK:
                
            #     try:
            #         self._downloader.params.get('dict_videos_to_dl', {}).get('OnlyFansPaidlist',[]).remove(url)
            #     except ValueError as e:
            #         self.to_screen(str(e))
            #     count = len(self._downloader.params.get('dict_videos_to_dl', {}).get('OnlyFansPost',[])) + len(self._downloader.params.get('dict_videos_to_dl', {}).get('OnlyFansPlaylist',[])) + len(self._downloader.params.get('dict_videos_to_dl', {}).get('OnlyFansPaidlist',[]))
                
            #     self.to_screen(f"COUNT: [{count}]")
            #     if count == 0:
            #         self.to_screen("LETS CLOSE DRIVERS AND PROXIES")
            #         for __driver, __mitmproxy in list(OnlyFansPaidlistIE._QUEUE.queue):
            #             try:
            #                 __driver.quit()
            #                 __mitmproxy.close()
            #             except Exception as e:
            #                 self.to_screen(str(e))
            #         self.to_screen("ALL DRIVERS AND PROXIES CLOSED")
            #         OnlyFansPaidlistIE._SERVER.stop()
            #         self.to_screen("SERVER STOPPED")
            #         self.kill_java_process(OnlyFansPaidlistIE._SERVER.port)
        
        
        
            