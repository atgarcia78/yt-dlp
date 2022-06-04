from __future__ import unicode_literals

import html
import json
import re
import sys
import threading
import traceback
from urllib.parse import unquote, urlparse

import httpx


from ..utils import (ExtractorError, int_or_none, js_to_json,
                     sanitize_filename, try_get, urljoin)
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_5, By, ec


class BoyFriendTVBaseIE(SeleniumInfoExtractor):
    _LOGIN_URL = 'https://www.boyfriendtv.com/login/'
    _SITE_URL = 'https://www.boyfriendtv.com/'
    _NETRC_MACHINE = 'boyfriendtv'
    _LOGOUT_URL = 'https://www.boyfriendtv.com/logout'

    _LOCK = threading.Lock()    
    _COOKIES = {}
    
    @dec_on_exception
    @limiter_5.ratelimit("boyfriendtv", delay=True)   
    def _get_info_for_format(self, *args, **kwargs):
        return super().get_info_for_format(*args, **kwargs)
    
    def _login(self, driver):
        
        
        username, password = self._get_login_info()
        
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
            el_title = self.wait_until(driver, 10, ec.presence_of_element_located((By.TAG_NAME, "title")))
            if el_title: _title = el_title.get_attribute("innerText")
            if "deleted" in _title or "removed" in _title or "page not found" in _title or not el_vplayer:
                raise ExtractorError("Page not found 404")   
            el_vplayer.click()
            _title_video = _title.replace(" - BoyFriendTV.com", "").strip()
            _rating = try_get(driver.find_elements(By.CSS_SELECTOR, "div.progress-big.js-rating-title"), lambda x: try_get(x[0].get_attribute('title').strip('%'), lambda y: int(y)))           
            el_html = self.wait_until(driver, 60, ec.presence_of_element_located((By.TAG_NAME, "html")))
            webpage = el_html.get_attribute("outerHTML") 
            jsonstr = try_get(re.findall(r'sources:\s+(\{.*\})\,\s+poster',re.sub('[\t\n]','', html.unescape(webpage))), lambda x: x[0])                    
            info_sources = json.loads(js_to_json(jsonstr)) if jsonstr else None
            el_vplayer.click()
            if info_sources:
                
                try:
                    
                    _formats = []
                    for _src in info_sources.get('mp4'):
                        _url = unquote(_src.get('src'))
                        _info_video = self._get_info_for_format(_url)
                            
                        if not _info_video:
                            self.to_screen("no info video")
                            raise ExtractorError('Error 404')
                        
                        _formats.append({
                            'url': _info_video.get('url'),
                            'ext': 'mp4',
                            'format_id': f"http-{_src.get('desc')}",
                            'resolution': _src.get('desc'),
                            'height': int_or_none(_src.get('desc').lower().replace('p','')),
                            'filesize': _info_video.get('filesize'),
                            'http_headers': {'Referer': (urlp:=urlparse(url)).scheme + "//" + urlp.netloc + "/"}
                        })
                        
                    self._sort_formats(_formats)
                    
                    return({
                        'id': self._match_id(url),
                        'title': sanitize_filename(_title_video, restricted=True),
                        'formats': _formats,
                        'ext': 'mp4',
                        #'original_url': url,
                        'average_rating': _rating
                
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
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/embed/(?:(?P<id>[0-9]+)/|embed.php\?)'
    
    def get_formats_single_video(self, webpage):
        
        jsonstr = try_get(re.findall(r'sources:\s+(\{.*\})\,\s+poster', webpage), lambda x: x[0])      
        info_sources = json.loads(js_to_json(jsonstr)) if jsonstr else None
        
        if info_sources:
            
            _formats = []
            
            for _src in info_sources.get('mp4'):
                _url = unquote(_src.get('src'))
                _info_video = self._get_info_for_format(_url) 
                _formats.append({
                    'url': _info_video.get('url'),
                    'ext': 'mp4',
                    'format_id': f"http-{_src.get('desc')}",
                    'resolution': _src.get('desc'),
                    'height': int_or_none(_src.get('desc').lower().replace('p','')),
                    'filesize': _info_video.get('filesize'),
                    
                })
                
            if _formats:
                self._sort_formats(_formats)
                return _formats
            

    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        try:
            if not (videoid:=self._match_id(url)):
                _url_embed = httpx.URL(url)
                _params_dict = dict(_url_embed.params.items())
                _url = f"https://{_url_embed.host}/embed/{_params_dict.get('m')}/{_params_dict.get('h')}"
            else: _url = url
            
                        
            res = self._CLIENT.get(_url)            
            
            if not videoid:   
                videoid = self._match_id(str(res.url))
            
            webpage = re.sub('[\t\n]','', html.unescape(res.text))
            
            if 'class="video-container"' in webpage:
                
                _title_video = try_get(re.findall(r'<title>([^<]*)</title>', webpage), lambda x: x[0].replace(" - ", "").replace("BoyFriendTv.com", "")) or ""
                _formats = self.get_formats_single_video(webpage)
                if _formats:
                    
                    for el in _formats: 
                        el.update({'http_headers': {'Referer': (urlp:=urlparse(url)).scheme + "//" + urlp.netloc + "/"}})
                    
                    _res = {
                        'id': videoid,
                        'title': sanitize_filename(_title_video, restricted=True),                     
                        'formats': _formats,
                        'ext': 'mp4'}
                    
                                                    
                    return _res
            
           

        except ExtractorError as e:
            raise     
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}  \n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))


        


class BoyFriendTVPlayListIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtv:playlist'
    IE_DESC = 'boyfriendtv:playlist'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/playlists/(?P<playlist_id>\d*)/?(\?(?P<query>.+))?'

 
    def _real_initialize(self):
        super()._real_initialize()
        
    def _real_extract(self, url):
        mobj = re.match(self._VALID_URL, url)
        playlist_id = mobj.group('playlist_id')
        query = mobj.group('query')
        if query:
            params =  { (_key:=el.split('=')[0]): el.split('=')[1] if _key not in ('raiting') else int(el.split('=')[1]) for el in mobj.group('query').split('&')}
        else: params = {}
        driver = self._init_driver()
        try:
        
            entries = []
            driver.get(url)
            el_title = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "h1")))
            _title = el_title.text.splitlines()[0]
            _min_rating = params.get('raiting', 0)
            _q = try_get(params.get('q'), lambda x: x.split(','))
            
            while True:

                #el_videos = self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CSS_SELECTOR, "div.playlist-thumb-info")))
                el_videos = self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CSS_SELECTOR, "li.playlist-video-thumb.thumb-item.videospot")))
                if el_videos:
                    for el in el_videos:
                        (_thumb, _title, _url) = try_get(el.find_elements(By.CSS_SELECTOR, 'a'), lambda x: (try_get(x[0].find_elements(By.TAG_NAME, 'img'), lambda y: y[0].get_attribute('src')),x[0].get_attribute('title'), x[0].get_attribute('href').rsplit("/", 1)[0])) or ("", "", "")
                        if 'img/removed-video' in _thumb or not _url: 
                            continue
                        #(_title, _url) = try_get(el.find_elements(By.CSS_SELECTOR, 'a'), lambda x: (x[0].get_attribute('title'), x[0].get_attribute('href').rsplit("/", 1)[0])) or ("", "")
                        _rating = try_get(el.find_elements(By.CSS_SELECTOR, 'div.progress-small.js-rating-title.green'), lambda x: try_get(x[0].get_attribute('title').strip('%'), lambda y: int(y)))                      
                        if _rating and (_rating < _min_rating): 
                            continue
                        if _title and _q:
                            if not any(_.lower() in _title.lower() for _ in _q):
                                continue
                                
                                
                        entries += [self.url_result(_url, ie=BoyFriendTVIE.ie_key(), video_id=try_get(re.search(BoyFriendTVIE._VALID_URL, _url), lambda x: x.group('id')), video_title=sanitize_filename(_title, restricted=True), average_rating=_rating, original_url=url)]

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
