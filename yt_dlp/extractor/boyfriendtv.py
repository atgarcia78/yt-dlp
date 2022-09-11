import html
import json
import re
import sys
import threading
import traceback
from urllib.parse import unquote, urlparse

import httpx

from concurrent.futures import ThreadPoolExecutor

from ..utils import (ExtractorError, int_or_none, js_to_json,
                     sanitize_filename, try_get, urljoin, get_domain, traverse_obj)
from .commonwebdriver import dec_on_exception2, dec_on_exception3, dec_on_exception, HTTPStatusError, ConnectError, SeleniumInfoExtractor, limiter_2,limiter_5, By, ec

import logging
logger = logging.getLogger('bftv')

class BoyFriendTVBaseIE(SeleniumInfoExtractor):
    _LOGIN_URL = 'https://www.boyfriendtv.com/login/'
    _SITE_URL = 'https://www.boyfriendtv.com/'
    _NETRC_MACHINE = 'boyfriendtv'
    _LOGOUT_URL = 'https://www.boyfriendtv.com/logout'

    _LOCK = threading.Lock()    
    _COOKIES = {}
    
    @dec_on_exception3
    @dec_on_exception2
    @limiter_2.ratelimit("boyfriendtv", delay=True)   
    def _get_info_for_format(self, url, **kwargs):
        
        try:
        
            _headers = kwargs.get('headers', None)        

            self.logger_debug(f"[get_video_info] {url}")
            _host = get_domain(url)
                    
            with self.get_param('lock'):
                if not (_sem:=traverse_obj(self.get_param('sem'), _host)): 
                    _sem = threading.Lock()
                    self.get_param('sem').update({_host: _sem})
                        
                                
            with _sem:            
                return self.get_info_for_format(url, headers={'Range': 'bytes=0-', 'Referer': _headers['Referer'], 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'})
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
    
    
    
    @dec_on_exception
    @dec_on_exception3
    @dec_on_exception2
    @limiter_2.ratelimit("boyfriendtv2", delay=True)
    def _send_request(self, url, driver=None, **kwargs):
        
        if driver:
            driver.get(url)
        else:
            try:
                return self.send_http_request(url, **kwargs)
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"[send_request] {self._get_url_print(url)}: error - {repr(e)}")
    
    
    
    def _login(self, driver):        
        
        username, password = self._get_login_info()
        
        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)
        
        self.report_login()
        
        self._send_request(self._SITE_URL, driver)
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

            if not el_menu: 
                self.raise_login_required("Invalid username/password")
            else:
                self.logger_debug("Login OK")

    def _init_client(self):
        self._CLIENT.cookies.set(name='rta_terms_accepted', value='true', domain='.boyfriendtv.com')
        res = self._send_request(self._LOGIN_URL)
        if not res:
            self.logger_debug(f"couldnt get login page")
            self._init_driver()            
        elif 'login' in str(res.url):
            self._init_driver()
        else:
            self.logger_debug(f"Already logged")
            

    def _init_driver(self):        
        
        driver = self.get_driver()
        self._send_request(self._SITE_URL, driver)
        driver.add_cookie({'name': 'rta_terms_accepted', 'value': 'true', 'domain': '.boyfriendtv.com'})
        driver.add_cookie({'name': 'videosPerRow', 'value': '5', 'domain': '.boyfriendtv.com'})
        try:
            self._send_request(self._LOGIN_URL, driver)
            if 'login' in driver.current_url:
                
                with BoyFriendTVBaseIE._LOCK:
                    
                    for cookie in BoyFriendTVBaseIE._COOKIES:
                        driver.add_cookie(cookie)
                
                    self._send_request(self._LOGIN_URL, driver)
                    if 'login' in driver.current_url:
                        self._login(driver)
                        
                        
                    else:
                        self.logger_debug(f"Already logged")
                                            
                
            else:
                self.logger_debug(f"Already logged")
            
            BoyFriendTVBaseIE._COOKIES = driver.get_cookies()
            for cookie in BoyFriendTVBaseIE._COOKIES:
            
                self._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
            return driver
            
        except Exception as e:
            #self.to_screen("error when init driver")
            self.rm_driver(driver)
            raise            
            

    def _real_initialize(self):
        
        super()._real_initialize()
        
        with BoyFriendTVBaseIE._LOCK:
            
            if not BoyFriendTVBaseIE._COOKIES:
                
                driver = self.get_driver()
                try:                                        
                    self._send_request(self._SITE_URL, driver)
                    driver.add_cookie({'name': 'rta_terms_accepted', 'value': 'true', 'domain': '.boyfriendtv.com'})
                    driver.add_cookie({'name': 'videosPerRow', 'value': '5', 'domain': '.boyfriendtv.com'})
                    self._login(driver)
                    BoyFriendTVBaseIE._COOKIES = driver.get_cookies()

                except Exception as e:
                    self.to_screen("error when login")                    
                    raise
                finally:
                    self.rm_driver(driver)
            
            for cookie in BoyFriendTVBaseIE._COOKIES:                
                self._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
        

class BoyFriendTVIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtv'
    _VALID_URL = r'https?://(?:(?P<prefix>m|www|es|ru|de)\.)?(?P<url>boyfriendtv\.com/videos/(?P<id>[0-9]+)/?(?:([0-9a-zA-z_-]+/?)|$))'

    def get_video_entry(self, url):
        
        self.report_extraction(url)

        try:        
            #webpage = None
            #self._init_client()
            
            webpage = try_get(self._send_request(url), lambda x: html.unescape(re.sub('[\t\n]', '', x.text)))
            if not webpage:
                raise ExtractorError("no webpage")
            
            _title = try_get(self._html_extract_title(webpage), lambda x: x.replace(" - BoyFriendTV.com", "").strip())
            if any(_ in _title.lower() for _ in ("deleted", "removed", "page not found")):
                raise ExtractorError("Page not found 404")   

            _rating = try_get(re.search(r'class="progress-big js-rating-title" title="(?P<rat>\d+)%"', webpage), lambda x: int(x.group('rat')))

            info_sources = try_get(re.findall(r'sources:\s+(\{.*\})\,\s+poster', webpage), lambda x: json.loads(js_to_json(x[0])))                    
           
            if not info_sources:
                raise ExtractorError("no video sources")                        

            _formats = []
            _headers = {'Referer': (urlp:=urlparse(url)).scheme + "//" + urlp.netloc + "/"}
            for _src in info_sources.get('mp4'):
                
                try:

                    _format_id = f"http-{_src.get('desc')}"
                    _url = unquote(_src.get('src'))
                    
                    _format = {
                        'url': _url,
                        'ext': 'mp4',
                        'format_id': _format_id,                            
                        'height': int_or_none(_src.get('desc').lower().replace('p','')),                            
                        'http_headers': _headers,
                    }                      
                    
                    _info_video = self._get_info_for_format(_url, headers=_headers)
                                                
                    if not _info_video:
                        self.logger_debug(f"[{url}][{_format_id}] no video info")
                    else:
                        _format.update({'url': _info_video.get('url'),'filesize': _info_video.get('filesize')})
                        
                    
                    _formats.append(_format)
                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.logger_debug(f"{repr(e)}\n{'!!'.join(lines)}")
                    
                    
            if not _formats:
                
                raise ExtractorError('404 no formats')
            
            self._sort_formats(_formats)
                
            return({
                'id': self._match_id(url),
                'title': sanitize_filename(_title, restricted=True),
                'formats': _formats,
                'ext': 'mp4',
                'webpage_url': url,
                'average_rating': _rating
        
            })
                
        except ExtractorError as e:
            self.logger_debug(f"[{url}] error \n{webpage}")
            raise
        except Exception as e:
            self.logger_debug(f"[{url}] error \n{webpage}")
            raise ExtractorError(repr(e))



    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
                
        return self.get_video_entry(url)

class BoyFriendTVEmbedIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtvembed'
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
            
                        
            res = self.send_http_request(_url)
            
            if not videoid:   
                videoid = self._match_id(str(res.url))
            
            webpage = re.sub('[\t\n]','', html.unescape(res.text))
            
            _formats = []
            
            if 'class="video-container"' in webpage:
                
                _title_video = try_get(re.findall(r'<title>([^<]*)</title>', webpage), lambda x: x[0].replace(" - ", "").replace("BoyFriendTv.com", "")) or ""
                _formats = self.get_formats_single_video(webpage)
                
            if not _formats: raise ExtractorError("404 no video formats")
                   
            for el in _formats: 
                el.update({'http_headers': {'Referer': (urlp:=urlparse(url)).scheme + "//" + urlp.netloc + "/"}})
            
            self._sort_formats(_formats)
            
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


class BoyFriendTVPLBaseIE(BoyFriendTVBaseIE):

    def _get_entries_page(self, url_page, _min_rating, _q):
        
        try:
            logger.debug(f"page: {url_page}")
            driver = self._init_driver()
            self._send_request(url_page, driver)
            el_videos = self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CSS_SELECTOR, self._CSS_SEL)))
            entries = []
            if el_videos:
                for el in el_videos:
                    try:
                        (_thumb, _title, _url) = try_get(el.find_elements(By.CSS_SELECTOR, 'a'), lambda x: (try_get(x[0].find_elements(By.TAG_NAME, 'img'), lambda y: (y[0].get_attribute('src'), y[0].get_attribute('alt'),x[0].get_attribute('href').rsplit("/", 1)[0])))) or ("", "", "")
                        if 'img/removed-video' in _thumb or not _url: 
                            continue
                        _rating = try_get(el.find_elements(By.CSS_SELECTOR, 'div.progress-small.js-rating-title.green'), lambda x: try_get(x[0].text.strip('%'), lambda y: int(y) if y.isdecimal() else 0))
                                              
                        if _rating and (_rating < _min_rating): 
                            continue
                        if _title and _q:
                            if not any(_.lower() in _title.lower() for _ in _q):
                                continue
                        entries.append(self.url_result(_url, ie=BoyFriendTVIE.ie_key(), video_id=try_get(re.search(BoyFriendTVIE._VALID_URL, _url), lambda x: x.group('id')), video_title=sanitize_filename(_title, restricted=True), average_rating=_rating, original_url=url_page.strip('/').rsplit('/',1)[0]))
                    except Exception as e:
                        logger.exception(repr(e))
                        
            return(entries)
        except Exception as e:
            logger.exception(repr(e))
        finally:
            self.rm_driver(driver)
        
    def _real_initialize(self):
        super()._real_initialize()
        
    def _real_extract(self, url):
        mobj = re.match(self._VALID_URL, url)
        playlist_id = mobj.group('playlist_id')
        query = mobj.group('query')
        if query:
            params =  { el.split('=')[0]: el.split('=')[1] for el in mobj.group('query').split('&')}
        else: params = {}
        driver = self._init_driver()
        try:        
            self.to_screen(self._BASE_URL % playlist_id)
            self.to_screen(params)
            self._send_request(self._BASE_URL % playlist_id, driver)
            
            _title = try_get(self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "h1"))), lambda x: x.text.splitlines()[0])
            _min_rating = int(params.get('rating', 0))
            _q = try_get(params.get('q'), lambda x: x.split(','))
            last_page = try_get(driver.find_elements(By.CSS_SELECTOR, "a.rightKey"), lambda x: try_get(re.search(r'(?P<last>\d+)/?$', x[-1].get_attribute('href')), lambda y: int(y.group('last')))) or 1
            self.to_screen(f"last_page: {last_page}, minrating: {_min_rating}")
            with ThreadPoolExecutor(thread_name_prefix='bftvlist', max_workers=8) as ex:
                futures = {ex.submit(self._get_entries_page, self._BASE_URL % playlist_id + str(page+1), _min_rating, _q): page for page in range(last_page)}
            
            _entries = []
            
            for fut in futures:
                try:
                    if _ent:=fut.result():
                        _entries.extend(_ent)                       
                    else:
                        self.report_warning(f"[{url}][page {futures[fut]}] no entries")                 
                except Exception as e:
                    self.report_warning(f"[{url}][page {futures[fut]}] {repr(e)}")
                     
                    
            if not _entries: raise ExtractorError("cant find any video")
            
            return {
                '_type': 'playlist',
                'id': playlist_id,
                'title': sanitize_filename(_title, restricted=True),
                'entries': _entries,
            }
            
        except ExtractorError as e:
            raise    
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}  \n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))            
        finally:
            self.rm_driver(driver)
      
    

class BoyFriendTVSearchIE(BoyFriendTVPLBaseIE):
    IE_NAME = 'boyfriendtv:playlist:search'
    IE_DESC = 'boyfriendtv:playlist:search'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/search/(?P<playlist_id>[^/?$]*)/?(\?(?P<query>.+))?'
    _BASE_URL = f'{BoyFriendTVBaseIE._SITE_URL}search/%s/'
    _CSS_SEL = "li.js-pop.thumb-item.videospot.inrow5" 

class BoyFriendTVProfileFavIE(BoyFriendTVPLBaseIE):
    IE_NAME = 'boyfriendtv:playlist:profilefav'
    IE_DESC = 'boyfriendtv:playlist:profilefav'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/profiles/(?P<playlist_id>\d*)/?(\?(?P<query>.+))?'
    _BASE_URL = f'{BoyFriendTVBaseIE._SITE_URL}profiles/%s/videos/favorites/?page='
    _CSS_SEL = "li.js-pop.thumb-item.videospot" 


class BoyFriendTVPlayListIE(BoyFriendTVPLBaseIE):
    IE_NAME = 'boyfriendtv:playlist'
    IE_DESC = 'boyfriendtv:playlist'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/playlists/(?P<playlist_id>\d*)/?(\?(?P<query>.+))?'
    _BASE_URL = f'{BoyFriendTVBaseIE._SITE_URL}playlists/%s/'
    _CSS_SEL = "li.playlist-video-thumb.thumb-item.videospot"

