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

from selenium.webdriver import Firefox, FirefoxProfile
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
from browsermobproxy import Server
#from collections import defaultdict
import html


import sys
import traceback
import subprocess
import threading
from queue import Queue


class alreadylogin_or_reqtw():
    
    def __call__(self, driver):
        
        el = driver.find_elements_by_css_selector("nav.l-header__menu")        
        if el:            
            return ("loginok", el[0])       
        else:
            
            el = driver.find_elements_by_css_selector("a.g-btn.m-rounded.m-twitter")
            if el: return ("reqlogin", el[0])
            else: return False
            

class succ_or_twlogin():
    
    def __call__(self, driver):
        
        el = driver.find_elements_by_css_selector("nav.l-header__menu")        
        if el:            
            return (el[0],)       
        else:
            
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
            return (el[0],)       
        else:

            el_username = driver.find_elements_by_partial_link_text("usuario") + driver.find_elements_by_partial_link_text("user")
            el_password =  driver.find_elements_by_partial_link_text("Contra") + driver.find_elements_by_partial_link_text("Pass")              
           
            el_login = driver.find_elements_by_partial_link_text("Iniciar") + driver.find_elements_by_partial_link_text("Start")
            
            if el_username and el_password and el_login:
                return (el_username[0], el_password[0], el_login[0])
            
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
    
    def wait_until(self, driver, time, method):
        try:
            el = WebDriverWait(driver, time).until(method)
        except Exception as e:
            el = None
            
        return el  
    
     
    
    def scan_for_request(self, _har, _link):
                          
        for entry in _har['log']['entries']:
                            
            if _link in (_url:=entry['request']['url']):
                
                self.to_screen(_url)                   
          
                if ((_res:=entry.get('response')) and (_content:=_res.get('content')) and (_text:=_content.get('text'))):                         
                
                    _str = html.unescape(_text)
                    _info_str = re.sub('[\t\n]', '', _str)
                    _info_json = json.loads(_info_str)
                    if _info_json:
                        return(_info_json)
                    
                    
    def scan_for_all_requests(self, _har, _reg):
                          
        _list_info_json = []
        
        for entry in _har['log']['entries']:
                            
            if re.search(_reg, (_url:=entry['request']['url'])):
                
                self.to_screen(_url)                   
          
                if ((_res:=entry.get('response')) and (_content:=_res.get('content')) and (_text:=_content.get('text'))):                         
                
                    _str = html.unescape(_text)
                    _info_str = re.sub('[\t\n]', '', _str)
                    _info_json = json.loads(_info_str)
                    if _info_json: _list_info_json.append(_info_json)
        
        return _list_info_json
                        
           
            
     
    def kill_java_process(self, port):
        
        res = subprocess.run(["ps","ax","-o","pid","-o","command"], encoding='utf-8', capture_output=True).stdout
        process_id = mobj[0] if (mobj:=re.findall(rf'^\ *(\d+)\ java\ .*browsermob.*port={port}', res, flags=re.MULTILINE)) else None
        if process_id:
            res = subprocess.run(["kill","-9",process_id], encoding='utf-8', capture_output=True)
            if res.returncode != 0: 
                self.to_screen("cant kill java proxy: " + res.stderr.decode())
            else: self.to_screen("java proxy killed")
            
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
            # twitter_element = self.wait_until(driver, 30, ec.presence_of_element_located(
            #      (By.CSS_SELECTOR, "a.g-btn.m-rounded.m-twitter") ))
   
            # if twitter_element:
            #     twitter_element.click()
            #     time.sleep(2)
            # else:
            #     raise ExtractorError("Error in login via twitter: couldnt find twitter oauth button")
            
            el_init = self.wait_until(driver, 60, alreadylogin_or_reqtw())
            if not el_init: raise ExtractorError("Error in login")
            if el_init[0] == "loginok": return
            else: el_init[1].click()
            
            el = self.wait_until(driver, 60, succ_or_twlogin())            
 
            if el:
                if len(el) == 3:
                    username_element, password_element, login_element = el
                    username_element.send_keys(username)
                    password_element.send_keys(password)            
                    login_element.submit()
                    
                    el = self.wait_until(driver, 60, succ_or_twrelogin())
                
                    if el:
                        if (len(el) == 3):
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
 
         
           

    def _extract_from_json(self, data_post, acc=False, users_dict={}, user_profile=None):

        self.to_screen(f"[extract_from_json] {data_post}")
        
        
        
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
            account = user_profile or users_dict.get(data_post.get('fromUser', {}).get('id'))
            if acc:
                #account = users_dict[data_post['fromUser']['id']]
                datevideo = data_post['createdAt'].split("T")[0]
                videoid = data_post['media'][0]['id']
            else:
                #account = data_post['author'].get['username']
                #account = user_profile
                datevideo = data_post['postedAt'].split("T")[0]
                videoid = data_post['id']

            formats = []
            info_dict = []
            
            try:

                filesize = None
                
                
                _url = data_post['media'][index]['source']['source']
                if _url:
                    try:
                        filesize = int_or_none(httpx.head(_url).headers['content-length'])
                    except Exception as e:
                        pass
                    formats.append({
                        'url': _url,
                        'width': (orig_width := data_post['media'][index]['info']['source']['width']),
                        'height': (orig_height := data_post['media'][index]['info']['source']['height']),
                        'format_id': f"{orig_height}p-orig",
                        'filesize': filesize,
                        'format_note' : "original",
                        'ext': "mp4"
                    })  
                    
                    if data_post.get('media',{})[index].get('videoSources',{}).get('720'):
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

            

           
                    if data_post.get('media',{})[index].get('videoSources',{}).get('240'):
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
                
            except Exception as e:            
                self.to_screen(f'{type(e)}')
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f'{type(e)} \n{"!!".join(lines)}')
                           
        
            
    
 
class OnlyFansPostIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:post'
    IE_DESC = 'onlyfans:post'
    _VALID_URL =  r"(?:(onlyfans:post:(?P<post>.*?):(?P<account>[\da-zA-Z]+))|(https?://(?:www\.)?onlyfans.com/(?P<post2>[\d]+)/(?P<account2>[\da-zA-Z]+)))"

    _QUEUE = Queue()   
    
    _DRIVER = []
    
    _SERVER = None
    
    
    def _real_initialize(self):
        
        driver = None
        _mitmproxy = None
  
        
        try:
            
            
            with self._LOCK: 
                

                if len(self._DRIVER) == (self._downloader.params.get('winit', 1)):
                    return  
                
                opts = Options()
                opts.headless = True
                prof_ff = self._FF_PROF.pop() 
                self._FF_PROF.insert(0,prof_ff)
                if not self._SERVER:          
                    self._SERVER = Server(path="/Users/antoniotorres/Projects/async_downloader/venv/lib/python3.9/site-packages/browsermobproxy/browsermob-proxy-2.1.4/bin/browsermob-proxy")
                    self._SERVER.start()
                
                
                _port = 8081 + len(self._DRIVER)
                _host = 'localhost'
                
                _mitmproxy = self._SERVER.create_proxy({'port' : _port})
                
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
                
                _firefox_prof.update_preferences()
                 
                #_firefox_prof.set_proxy(_mitmproxy.selenium_proxy())
                driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", firefox_profile=_firefox_prof, options=opts)
                driver.set_window_size(1920,575)
                #time.sleep(2)   
                            
                #driver.get(self._SITE_URL)
                #self.wait_until(driver, 60, ec.presence_of_element_located(
                #    (By.CSS_SELECTOR, "a.router-link-exact-active.router-link-active") ))
                #driver.delete_all_cookies()
                #driver.execute_script("window.localStorage.clear();") 
                self._login(driver)
                self._DRIVER.append(driver)
                self._QUEUE.put_nowait((driver, _mitmproxy))
            
        except Exception as e:
            if driver:                
                self._DRIVER.remove(driver)
                driver.quit()
            if _mitmproxy: _mitmproxy.close()            
            raise
                
    def _real_extract(self, url):
 
        try:
            
            driver, _mitmproxy = self._QUEUE.get(block=True)
            
            self.report_extraction(url)                  

            (post1, post2, acc1, acc2) = re.search(self._VALID_URL, url).group("post", "post2", "account", "account2")
            post = post1 or post2
            account = acc1 or acc2

            self.to_screen("post:" + post + ":" + "account:" + account)
        

            info_video = None            
        
            
            _mitmproxy.new_har(options={'captureHeaders': False, 'captureContent': True}, title="har1")
            driver.get(url) 
            self.wait_until(driver, 60, ec.presence_of_element_located((By.CLASS_NAME, "video-wrapper")))
            har = _mitmproxy.har            
            data_json = self.scan_for_request(har, f"/api2/v2/posts/{post}")
            if data_json:
                self.to_screen(data_json)                
                info_video = self._extract_from_json(data_json, user_profile=account)
                if not info_video: raise ExtractorError("No info video found")               
                 
        except Exception as e:
                
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')
            raise                
 
            
        finally:
            self._QUEUE.put_nowait((driver, _mitmproxy))            
           
        
        return info_video
                                                       

class OnlyFansPlaylistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:playlist'
    IE_DESC = 'onlyfans:playlist'
    _VALID_URL = r"(?:(onlyfans:account:(?P<account>[^:]+)(?:(:(?P<mode>(?:all|latest10|chat)))?))|(https?://(?:www\.)?onlyfans.com/(?P<account2>\w+)(?:(/(?P<mode2>(?:all|latest10|chat)))?)$))"
    _MODE_DICT = {"favs" : "favorites_count_desc", "tips" : "tips_summ_desc", "all" : "publish_date_desc", "latest10" : "publish_date_desc"}
    
    
        
    def _real_initialize(self):
        
        self._mitmproxy = None
        self._server = None
        self.driver = None
        
        try:
            
            with self._LOCK:     
                prof_ff = self._FF_PROF.pop() 
                self._FF_PROF.insert(0,prof_ff)
                self._server = Server("/Users/antoniotorres/Projects/async_downloader/venv/lib/python3.9/site-packages/browsermobproxy/browsermob-proxy-2.1.4/bin/browsermob-proxy")
                self._server.start()
                self._mitmproxy  = self._server.create_proxy()
                                
                _port = self._mitmproxy.port
                _host = 'localhost'                
                
                
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
                
                _firefox_prof.update_preferences()
                
                opts = Options()
                opts.headless = True
                
                
               #_firefox_prof.set_proxy(self._mitmproxy.selenium_proxy())
                
                self.driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", firefox_profile=_firefox_prof, options=opts)
                self.driver.set_window_size(1920,575)
                #time.sleep(2)   
                
                #self.driver.get(self._SITE_URL)
                #self.wait_until(self.driver, 60, ec.presence_of_element_located(
                #    (By.CSS_SELECTOR, "a.router-link-exact-active.router-link-active") ))
                #self.driver.delete_all_cookies()
                #self.driver.execute_script("window.localStorage.clear();") 
                self._login(self.driver)
            
        except Exception as e:
            if self.driver: self.driver.quit()
            if self._mitmproxy: self._mitmproxy.close()
            if self._server: 
                self._server.stop()
                #self.kill_java_process()
            raise

    def _real_extract(self, url):
 
        try:
            self.report_extraction(url)
            (acc1, acc2, mode1, mode2) = re.search(self._VALID_URL, url).group("account", "account2", "mode", "mode2")
            account = acc1 or acc2
            mode = mode1 or mode2
            if not mode:
                mode = "latest10"

           
            
            entries = []
            
            if mode in ("all", "latest10"):
                
                self.driver.add_cookie( {'name': 'wallLayout', 'value': 'list', 'path': '/',  'domain': '.onlyfans.com', 'secure': False, 'httpOnly': False, 'sameSite': 'None'})
            
                _url = f"{self._SITE_URL}/{account}/videos"
                
                self._mitmproxy.new_har(options={'captureHeaders': False, 'captureContent': True}, title="har2")
                
                self.driver.get(_url)
                self.wait_until(self.driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "video-wrapper")))
                
                
                
                
                
                if mode in ("latest10"):
                    har = self._mitmproxy.har
                    data_json = self.scan_for_request(har, "posts/videos?")
                    if data_json:
                        self.to_screen(data_json)
                        list_json = data_json.get('list')
                        if list_json:
                            entries = [self._extract_from_json(info_json, user_profile=account) for info_json in list_json]
                    

                elif mode in ("all"):            
                    
                    
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
                        
                    har = self._mitmproxy.har
                    _reg_str = r'/api2/v2/users/\d+/posts/videos\?'
                    data_json = self.scan_for_all_requests(har, _reg_str)
                    if data_json:
                        self.to_screen(data_json)
                        list_json = []
                        for el in data_json:
                            list_json += el.get('list')
                    
                    
                        entries = [self._extract_from_json(info_json, user_profile=account) for info_json in list_json]
                
            
            elif mode in ("chat"):
                
                _url =  f"{self._SITE_URL}/{account}"
                self.driver.get(_url)
                el = self.wait_until(self.driver, 60, ec.presence_of_all_elements_located((By.CLASS_NAME, "g-btn.m-rounded.m-border.m-icon.m-icon-only.m-colored.has-tooltip")))
                for _el in el:
                    if (link:=_el.get_attribute('href')): break
                    
                self._mitmproxy.new_har(options={'captureHeaders': False, 'captureContent': True}, title="har2")
                
                userid = link.split("/")[-1]
                
                self.driver.get(f'{link}/gallery')
                
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
                
                har = self._mitmproxy.har
                _reg_str = r'/api2/v2/chats/\d+/media\?'
                data_json = self.scan_for_all_requests(har, _reg_str)
                if data_json:
                    self.to_screen(data_json)
                    list_json = []
                    for el in data_json:
                        list_json += el.get('list')
                        
                    for info_json in list_json:
                        
                        _entry = self._extract_from_json(info_json, acc=True, user_profile=account)
                        if _entry: 
                            entries.append(_entry)
            
            
           
                
                      

            if not entries:
                raise ExtractorError("no entries")            
             
                
            
        except Exception as e:            
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise
        
        finally:
            
            self._logout(self.driver)          
            self.driver.quit()
            self._mitmproxy.close()
            self._server.stop()
            self.kill_java_process(self._server.port)
            
        return self.playlist_result(entries, "Onlyfans:" + account, "Onlyfans:" + account)
            
            
class OnlyFansPaidlistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:playlist:paidlist'
    IE_DESC = 'onlyfans:playlist:paidlist'
    _VALID_URL = r"onlyfans:paidlist"
    _PAID_URL = "https://onlyfans.com/purchased"
    

    
    def _real_initialize(self):
        
        self._mitmproxy = None
        self._server = None
        self.driver = None
        
        try:
                 
            with self._LOCK:     
                prof_ff = self._FF_PROF.pop() 
                self._FF_PROF.insert(0,prof_ff)
                self._server = Server("/Users/antoniotorres/Projects/async_downloader/venv/lib/python3.9/site-packages/browsermobproxy/browsermob-proxy-2.1.4/bin/browsermob-proxy")
                self._server.start()
                self._mitmproxy  = self._server.create_proxy()
                                
                _port = self._mitmproxy.port
                _host = 'localhost'                
                
                
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
                
                _firefox_prof.update_preferences()
                
                opts = Options()
                opts.headless = True
                
                #_firefox_prof.set_proxy(self._mitmproxy.selenium_proxy())
                
                self.driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", firefox_profile=_firefox_prof, options=opts)
                self.driver.set_window_size(1920,575)
                # time.sleep(2)   
                
                # self.driver.get(self._SITE_URL)
                # self.wait_until(self.driver, 60, ec.presence_of_element_located(
                #     (By.CSS_SELECTOR, "a.router-link-exact-active.router-link-active") ))
                # self.driver.delete_all_cookies()
                # self.driver.execute_script("window.localStorage.clear();") 
                self._login(self.driver)
            
        except Exception as e:
            if self.driver: self.driver.quit()
            if self._mitmproxy: self._mitmproxy.close()
            if self._server: 
                self._server.stop()
                self.kill_java_process(self._server.port)
            raise

    def _real_extract(self, url):
 
        try:
            
            self.report_extraction(url)
            self._mitmproxy.new_har(options={'captureHeaders': False, 'captureContent': True}, title="paid")
            self.driver.get(self._SITE_URL)
            list_el = self.wait_until(self.driver, 60, ec.presence_of_all_elements_located(
                (By.CLASS_NAME, "b-tabs__nav__item") ))
            for el in list_el:
                if re.search(r'purchased|comprado',el.get_attribute("textContent").lower()):
                    el.click()
                    break
            self.wait_until(self.driver, 60, ec.presence_of_element_located(
                (By.CLASS_NAME, "user_posts") ))
       
                
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
                
            
            har = self._mitmproxy.har           
            users_json = self.scan_for_all_requests(har, r'/api2/v2/users/list')
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
            data_json = self.scan_for_all_requests(har, _reg_str)
            if data_json:
                #self.to_screen(data_json)
                list_json = []
                for el in data_json:
                    list_json += el['list']                               
          
                entries = [self._extract_from_json(info_json, acc=True, users_dict=users_dict) for info_json in list_json]
           
            if not entries:
                raise ExtractorError("no entries")
                 
            
        except Exception as e:            
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}') 
            raise
            
            
        finally:
            self._logout(self.driver)           
            self.driver.quit()
            self._mitmproxy.close()
            self._server.stop()
            self.kill_java_process(self._server.port)
        
        return self.playlist_result(entries, "Onlyfans:paidlist", "Onlyfans:paidlist")
            