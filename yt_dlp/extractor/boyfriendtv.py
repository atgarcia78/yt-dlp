from __future__ import unicode_literals

import re

from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_5
)

from ..utils import (
    ExtractorError,
    js_to_json,
    int_or_none,
    sanitize_filename,
    urljoin,
    try_get 

)

import html
import threading


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import traceback
import sys

import httpx
import json
from urllib.parse import unquote


from backoff import constant, on_exception


class BoyFriendTVBaseIE(SeleniumInfoExtractor):
    _LOGIN_URL = 'https://www.boyfriendtv.com/login/'
    _SITE_URL = 'https://www.boyfriendtv.com/'
    _NETRC_MACHINE = 'boyfriendtv'
    _LOGOUT_URL = 'https://www.boyfriendtv.com/logout'

    _LOCK = threading.Lock()    
    _COOKIES = {}
    
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @limiter_5.ratelimit("boyfriendtv", delay=True)   
    def get_info_for_format(self, *args, **kwargs):
        return super().get_info_for_format(*args, **kwargs)
    
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
            self.wait_until(driver, 2)
            el_password.send_keys(password)
            self.wait_until(driver, 2)            
            el_login.submit()
            el_menu = self.wait_until(driver, 15, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))
        #self.to_screen(driver.current_url)
        #self.to_screen(driver.current_url == self._SITE_URL)
            if not el_menu: 
                self.raise_login_required("Invalid username/password")
            else:
                self.to_screen("Login OK")


    def _init_driver(self):        
        
        driver = self.get_driver(usequeue=True)
        try:
            driver.get(self._SITE_URL)
            el_menu = self.wait_until(driver, 10, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))            
            if not el_menu:
                
                with BoyFriendTVBaseIE._LOCK:
                    
                    for cookie in BoyFriendTVBaseIE._COOKIES:
                        driver.add_cookie(cookie)
                
                    driver.get(self._SITE_URL)
                    el_menu = self.wait_until(driver, 10, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))
                    if not el_menu:
                        self._login(driver)
                        BoyFriendTVBaseIE._COOKIES = driver.get_cookies()
                        return driver
                        
                    else:
                        self.to_screen(f"Already logged")
                        return driver                        
                
            else:
                self.to_screen(f"Already logged")
                return driver
            
        except Exception as e:
            self.to_screen("error when init driver")
            self.put_in_queue(driver)
            raise            
            

    def _real_initialize(self):
        super()._real_initialize()
        
        with BoyFriendTVBaseIE._LOCK:
            
            if not BoyFriendTVBaseIE._COOKIES:
                
                driver = self.get_driver(usequeue=True)
                try:                                        
                    driver.get(self._SITE_URL)
                    driver.add_cookie({'name': 'rta_terms_accepted', 'value': 'true', 'domain': 'boyfriendtv.com'})
                    self._login(driver)
                    BoyFriendTVBaseIE._COOKIES = driver.get_cookies()
                    
                
                except Exception as e:
                    self.to_screen("error when login")                    
                    raise
                finally:
                    self.put_in_queue(driver)
        
        

class BoyFriendTVIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtv'
    _VALID_URL = r'https?://(?:(?P<prefix>m|www|es|ru|de)\.)?(?P<url>boyfriendtv\.com/videos/(?P<id>[0-9]+)/?(?:([0-9a-zA-z_-]+/?)|$))'

    def get_video_entry(self, url):
        
        self.report_extraction(url)
        
        driver = self._init_driver()        
        
        try:
        
            driver.get(url)
            
            el_vplayer = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "video-player")))
            el_vplayer.click()
            el_title = self.wait_until(driver, 10, ec.presence_of_element_located((By.TAG_NAME, "title")))
            if el_title: _title = el_title.get_attribute("innerHTML")
            if "deleted" in _title or "removed" in _title or "page not found" in _title or not el_vplayer:
                raise ExtractorError("Page not found 404")   
            _title_video = _title.replace(" - BoyFriendTV.com", "").strip()            
            el_html = self.wait_until(driver, 60, ec.presence_of_element_located((By.TAG_NAME, "html")))
            webpage = el_html.get_attribute("outerHTML") 
            jsonstr = try_get(re.findall(r'sources:\s+(\{.*\})\,\s+poster',re.sub('[\t\n]','', html.unescape(webpage))), lambda x: x[0])                    
            info_sources = json.loads(js_to_json(jsonstr)) if jsonstr else None
            
            if info_sources:
                
                try:
                    
                    _formats = []
                    for _src in info_sources.get('mp4'):
                        _url = unquote(_src.get('src'))
                        _info_video = self.get_info_for_format(_url)
                            
                        if not _info_video:
                            self.to_screen("no info video")
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
                        'ext': 'mp4',
                        'original_url': url
                
                    })
                  
                   
                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
                    raise ExtractorError(repr(e))
                
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            self.put_in_queue(driver)
        
        

    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
                
        return self.get_video_entry(url)

class BoyFriendTVEmbedIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtv:embed'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/embed/(?:((?P<id>[0-9]+)/)|embed.php\?)'
    
    def get_formats_single_video(self, webpage):
        
        jsonstr = try_get(re.findall(r'sources:\s+(\{.*\})\,\s+poster', webpage), lambda x: x[0])      
        info_sources = json.loads(js_to_json(jsonstr)) if jsonstr else None
        
        if info_sources:
            
            _formats = []
            
            for _src in info_sources.get('mp4'):
                _url = unquote(_src.get('src'))
                _info_video = self.get_info_for_format(_url) 
                _formats.append({
                    'url': _info_video.get('url'),
                    'ext': 'mp4',
                    'format_id': f"http-{_src.get('desc')}",
                    'resolution': _src.get('desc'),
                    'height': int_or_none(_src.get('desc').lower().replace('p','')),
                    'filesize': _info_video.get('filesize')
                })
                
            if _formats:
                self._sort_formats(_formats)
                return _formats
            

    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        try:
            if not self._match_id(url):
                _url_embed = httpx.URL(url)
                _params_dict = dict(_url_embed.params.items())
                _url = f"https://{_url_embed.host}/embed/{_params_dict.get('m')}/{_params_dict.get('h')}"
            else: _url = url
            
                        
            res = self._CLIENT.get(_url)            
                
            webpage = re.sub('[\t\n]','', html.unescape(res.text))
            
            if 'class="video-container"' in webpage:
                
                _formats = self.get_formats_single_video(webpage)
                if _formats:
                    _title_video = _title.strip() if (_title:=try_get(re.findall(r'title:\s+\"([^-\"]*)[-\"]', webpage), lambda x: x[0])) else None
                    
                    _res = {
                        'id': self._match_id(str(res.url)),                        
                        'formats': _formats,
                        'ext': 'mp4'}
                    
                    if _title_video: _res['title'] = sanitize_filename(_title_video, restricted=True),
                                
                    return _res
            
            # elif 'class="grid"' in webpage:
                
            #     info_videos = json.loads(js_to_json(jsonstr)) if  (jsonstr:=try_get(re.findall(r'"videos":(\[[^\]]+\])', webpage), lambda x: x[0])) else None
            #     if info_videos:
            #         with ThreadPoolExecutor(thread_name_prefix='BoyFriendTV', max_workers=min(len(info_videos), self._downloader.params.get('winit', 5))) as ex:
            #             futures = [ex.submit(BoyFriendTVIE.get_video_entry, urljoin(self._SITE_URL, link)) for el in info_videos if (link:=el.get('videoLink'))]           
                    
            #         _entries = []
            #         for fut in futures:
            #             try:
            #                 _entries.append(fut.result())
            #             except Exception as e:
            #                 self.to_screen(repr(e))                        
                    
            #         #_entries = [self.url_result(urljoin(self._SITE_URL, link), ie=BoyFriendTVIE.ie_key(), title=title) for el in info_videos if (link:=el.get('videoLink')) and (title:=el.get('videoName'))]
                   
            #         if _entries:
                    
            #             return {
            #                 '_type': 'playlist',
            #                 'id': self._match_id(str(res.url)),                        
            #                 'entries': _entries}
                    

        except ExtractorError as e:
            raise     
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}  \n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))


        


class BoyFriendTVPlayListIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtv:playlist'
    IE_DESC = 'boyfriendtv:playlist'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/playlists/(?P<playlist_id>.*?)(?:(/|$))'

 
    def _real_initialize(self):
        super()._real_initialize()
        
    def _real_extract(self, url):
        mobj = re.match(self._VALID_URL, url)
        playlist_id = mobj.group('playlist_id')

        driver = self._init_driver()
        try:
        
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
            
            return {
                '_type': 'playlist',
                'id': playlist_id,
                'title': sanitize_filename(_title, restricted=True),
                'entries': entries,
            }
            
        except ExtractorError:
            raise    
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}  \n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))            
        finally:
            self.put_in_queue(driver)
