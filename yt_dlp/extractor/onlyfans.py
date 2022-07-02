from __future__ import unicode_literals

import html
import json
import re
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import httpx


from ..utils import ExtractorError, int_or_none, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_0_1, scroll, By, ec, Keys


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
    _NETRC_MACHINE = 'twitter2'
    _LOCK = threading.Lock()     
    _COOKIES = None
    
    

    @dec_on_exception
    @limiter_0_1.ratelimit("onlyfans1", delay=True) 
    def _get_filesize(self, _vurl):

        res = httpx.head(_vurl, follow_redirects=True)
        res.raise_for_status()
        
        return(int_or_none(res.headers.get('content-length')))
        
        

    @dec_on_exception
    @limiter_0_1.ratelimit("onlyfans2", delay=True)
    def send_driver_request(self, driver, url):
                
        driver.execute_script("window.stop();")
        driver.get(url)

    def scan_for_json(self, _driver, _link, _all=False):

        _hints = self.scan_for_request(_driver, _link, _all)
        
        if not _all:
            _info_json = try_get(el, lambda x: json.loads(re.sub('[\t\n]', '', html.unescape(x[1]))))
            return(_info_json)
        else:
            _list_info_json = []           
            
            for el in _hints:
                _info_json = try_get(el, lambda x: json.loads(re.sub('[\t\n]', '', html.unescape(x[1]))))
                if _info_json: 
                    _list_info_json.append(_info_json)
            return(_list_info_json)

    
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

             
            self.send_driver_request(driver, self._SITE_URL)
            self.wait_until(driver, 2)        

            
            el_init = self.wait_until(driver, 60, alreadylogin_or_reqtw())
            if not el_init: raise ExtractorError("Error in login")
            if el_init[0] == "loginok": 
                self.to_screen("Login OK")
                return
            else: 
                #el_init[1].click()
                self.send_driver_request(driver, el_init[1].get_attribute('href'))
            
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
            self.to_screen(f'{repr(e)}')
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise           
 
    def _extract_from_json(self, data_post, users_dict={}, user_profile=None, original_url = None):

        try:
            #self.write_debug(f"[extract_from_json][input] {data_post}")            
            
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
                            
                        
                        _entry = {
                            "id" :  str(videoid),
                            "release_timestamp": date_timestamp,
                            "release_date" :  _datevideo.split("T")[0].replace("-", ""),
                            "title" :  _datevideo.split("T")[0].replace("-", "") + "_from_" + account,
                            "formats" : _formats,
                            "duration" : _media.get('info',{}).get('source', {}).get('duration', 0),
                            "ext" : "mp4"}
                        
                        if original_url: _entry.update({"original_url": original_url})
                        
                        _entries.append(_entry)
                        
        
            #self.write_debug(f'[extract_from_json][output] {_entries}')
            return _entries
        
        except Exception as e:            
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'[extract_from_json][output] {repr(e)} \n{"!!".join(lines)}')

    def _real_initialize(self):

        super()._real_initialize()

class OnlyFansPostIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:post:playlist'
    IE_DESC = 'onlyfans:post:playlist'
    _VALID_URL =  r"https?://(?:www\.)?onlyfans.com/(?P<post>[\d]+)/(?P<account>[\da-zA-Z]+)"

    
    def _real_initialize(self):
        super()._real_initialize()
                
    def _real_extract(self, url):

        try:            
            
            with OnlyFansPostIE._LOCK:
            

                driver = self.get_driver(devtools=True)
                self._login(driver)
                
                self.report_extraction(url)                  

                post, account = re.search(self._VALID_URL, url).group("post", "account")

                self.to_screen("post:" + post + ":" + "account:" + account)
                
                entries = {} 
                
                self.send_driver_request(driver, url) 
                res = self.wait_until(driver, 30, error404_or_found())
                if not res or res[0] == "error404": raise ExtractorError("Error 404: Post doesnt exists")

                data_json = self.scan_for_json(driver, f"/api2/v2/posts/{post}")
                if data_json:
                    #self.write_debug(data_json)                
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
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(repr(e))
        finally:
            self.rm_driver(driver)
            


class OnlyFansPlaylistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:playlist'
    IE_DESC = 'onlyfans:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans.com/(?P<account>\w+)/((?P<mode>(?:all|latest|chat|favorites|tips))/?)$"
    _MODE_DICT = {"favorites" : "?order=favorites_count_desc", "tips" : "?order=tips_summ_desc", "all" : "", "latest" : ""}

    def _real_initialize(self):
        super()._real_initialize()
        
    def _real_extract(self, url):
 
        try:
            self.report_extraction(url)
            
            with OnlyFansPostIE._LOCK:
            
                driver = self.get_driver(devtools=True)
                # self.send_driver_request(driver, self._SITE_URL)
                # for cookie in OnlyFansPlaylistIE._COOKIES:
                #     driver.add_cookie(cookie)
                self._login(driver)
                
                account, mode = re.search(self._VALID_URL, url).group("account", "mode")            
                if not mode:
                    mode = "latest"
                
                entries = {}
                
                if mode in ("all", "latest", "favorites","tips"):

                    self.send_driver_request(driver, f"{self._SITE_URL}/{account}")
                    res = self.wait_until(driver, 60, error404_or_found())
                    if not res or res[0] == "error404": raise ExtractorError("Error 404: User profile doesnt exists")
                    
                    _url = f"{self._SITE_URL}/{account}/videos{self._MODE_DICT[mode]}"
                    
                    #_harproxy.new_har(options={'captureHeaders': False, 'captureContent': True}, ref=f"har_{account}_{mode}", title=f"har_{account}_{mode}")
                    
                    self.send_driver_request(driver, _url)
                    self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CLASS_NAME, "b-photos__item.m-video-item")))
                    if mode in ("latest"):
                        data_json = self.scan_for_json(driver, "posts/videos?")
                        if data_json:
                            #self.write_debug(data_json)
                            list_json = data_json.get('list')
                            if list_json:                            
                                for info_json in list_json:                                                  
                                    _entry = self._extract_from_json(info_json, user_profile=account, original_url=_url)
                                    if _entry: 
                                        for _video in _entry:
                                            if not _video['id'] in entries.keys(): entries[_video['id']] = _video
                                            else:
                                                if _video.get('duration', 1) > entries[_video['id']].get('duration', 0):
                                                    entries[_video['id']] = _video

                    else:            

                        #lets scroll down in the videos pages till the end
                        self.wait_until(driver, 600, scroll(10))                            

                        _reg_str = r'/api2/v2/users/\d+/posts/videos\?'
                        data_json = self.scan_for_json(driver, _reg_str, _all=True)
                        if data_json:
                            #self.write_debug(data_json)
                            list_json = []
                            for el in data_json:
                                list_json += el.get('list')
                        
                            #self.write_debug(list_json)
                            
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
                    self.send_driver_request(driver, _url)
                    res = self.wait_until(driver, 60, error404_or_found())
                    if not res or res[0] == "error404": raise ExtractorError("User profile doesnt exists")
                    
                    data_json = self.scan_for_request(driver, f"users/{account}")
                               
                    userid = try_get(data_json, lambda x: x['id'])
                    if not userid: raise ExtractorError("couldnt get id user for chat room")
                    url_chat = f"https://onlyfans.com/my/chats/chat/{userid}/"

                    self.to_screen(url_chat)
                    self.send_driver_request(driver, url_chat)
                    #init start of chat is to be at the end, with all the previous messages above. Lets scroll
                    # up to the start of the chat
                    el_chat_scroll = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "div.b-chats__scrollbar.m-custom-scrollbar.b-chat__messages.m-native-custom-scrollbar.m-scrollbar-y.m-scroll-behavior-auto")))
                    self.wait_until(driver, 1) 
                    el_chat_scroll.send_keys(Keys.HOME)
                    self.wait_until(driver, 5)                
                    
                    
                    _reg_str = r'/api2/v2/chats/\d+/messages'
                    data_json = self.scan_for_json(driver, _reg_str, _all=True)
                    if data_json:
                        #self.write_debug(data_json)
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
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(repr(e))       
        finally:
            self.rm_driver(driver)
            
class OnlyFansPaidlistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfanspaidlist:playlist'
    IE_DESC = 'onlyfanspaidlist:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans\.com/paid"
    _PAID_URL = "https://onlyfans.com/purchased"

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):
 
        try:

            self.report_extraction(url)
            
            with OnlyFansPaidlistIE._LOCK:
                
               
                
        
                driver = self.get_driver(devtools=True)
                # self.send_driver_request(driver, self._SITE_URL)
                # for cookie in OnlyFansPlaylistIE._COOKIES:
                #     driver.add_cookie(cookie)
                self._login(driver)
                
                
                self.send_driver_request(driver, self._SITE_URL)
                list_el = self.wait_until(driver, 60, ec.presence_of_all_elements_located(
                    (By.CLASS_NAME, "b-tabs__nav__item") ))
                for el in list_el:
                    if re.search(r'(?:purchased|comprado)',el.get_attribute("textContent").lower()):
                        el.click()
                        break
                self.wait_until(driver, 60, ec.presence_of_element_located(
                    (By.CLASS_NAME, "user_posts") ))
        
                self.wait_until(driver, 600, scroll(10))
                    
                          
                users_json = self.scan_for_json(driver, '/api2/v2/users/list', _all=True)
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
                data_json = self.scan_for_json(driver,_reg_str, _all=True)
                if data_json:
                    #self.write_debug(data_json)
                    list_json = []
                    for el in data_json:
                        list_json += el['list']                               
                    
                    for info_json in list_json:
                        for _video in self._extract_from_json(info_json, users_dict=users_dict, original_url="https://onlyfans.com/paid"):
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
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(repr(e))
        finally:
            self.rm_driver(driver)
            
class OnlyFansActSubslistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfansactsubslist:playlist'
    IE_DESC = 'onlyfansactsubslist:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans\.com/actsubs"
    _ACT_SUBS_URL = "https://onlyfans.com/my/subscriptions/active"

    def _get_videos_from_subs(self, url):
        try:
            
            _url_videos = f"{url}/videos"
            self.report_extraction(_url_videos)
            with OnlyFansActSubslistIE._LOCK:
                

                driver = self.get_driver(devtools=True)
                # self.send_driver_request(driver, self._SITE_URL)
                # for cookie in OnlyFansPlaylistIE._COOKIES:
                #     driver.add_cookie(cookie)
                self._login(driver)
                
                self.send_driver_request(driver, url)
                res = self.wait_until(driver, 60, error404_or_found())
                if not res or res[0] == "error404": raise ExtractorError(f"[{_url_videos}] User profile doesnt exists")        
                account = url.split("/")[-1]
                self.send_driver_request(driver, _url_videos)
                self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CLASS_NAME, "b-photos__item.m-video-item")))
 
                data_json = self.scan_for_request(driver, "posts/videos?")
                entries = {}
                if data_json:
                    #self.write_debug(data_json)
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
                
                if not entries: raise ExtractorError(f"[{_url_videos}] no entries")                
                return list(entries.values())
        
        except ExtractorError as e:
            raise 
        except Exception as e:            
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'[{_url_videos}] {repr(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(f'[{_url_videos}] {repr(e)}')        
        finally:
            self.rm_driver(driver)
            
        

    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
 
        try:            
            
            self.report_extraction(url)            
        
            driver = self.get_driver(devtools=True)
            # self.send_driver_request(driver, self._SITE_URL)
            # for cookie in OnlyFansPlaylistIE._COOKIES:
            #     driver.add_cookie(cookie)
            self._login(driver)
            
            
            self.send_driver_request(driver, self._ACT_SUBS_URL)
            el_subs = self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CLASS_NAME, "b-users__item__inner")))
            
            act_subs_urls = [el.find_element(By.TAG_NAME, "a").get_attribute('href') for el in el_subs]
            entries = []
            if act_subs_urls:
                self.to_screen(f"act_subs_urls:\n{act_subs_urls}")
                with ThreadPoolExecutor(thread_name_prefix='OFPlaylist', max_workers=len(act_subs_urls)) as ex:
                    futures = [ex.submit(self._get_videos_from_subs, _url) for _url in act_subs_urls]
                for fut in futures:
                    try:
                        entries = entries + fut.result()
                    except Exception as e:
                        self.to_screen(repr(e))                        

            if entries:
                return self.playlist_result(entries, "Onlyfans:subs", "Onlyfans:subs")
            else:
                raise ExtractorError("no entries") 
            
        except ExtractorError as e:
            raise 
        except Exception as e:            
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(repr(e))        
        finally:
            self.rm_driver(driver)
