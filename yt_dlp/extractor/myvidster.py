from __future__ import unicode_literals

import html
import re
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock
from urllib.parse import unquote


from httpx import HTTPStatusError
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

from ..utils import (ExtractorError, datetime_from_str, get_elements_by_class,
                     sanitize_filename, try_get, urljoin)
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_0_1


class MyVidsterBaseIE(SeleniumInfoExtractor):

    _LOGIN_URL = "https://www.myvidster.com/user/"
    _SITE_URL = "https://www.myvidster.com"
    _NETRC_MACHINE = "myvidster"
    
    _LOCK = Lock()
    _COOKIES = {}
    _RSS = {}

 
    @dec_on_exception
    @limiter_0_1.ratelimit("myvidster", delay=True)
    def _send_request(self, url, _type="GET", data=None, headers=None):        
        
        self.logger_debug(f"[_send_request] {self._get_url_print(url)}") 
        return(self.send_http_request(url, _type=_type, data=data, headers=headers))
        
            

    @dec_on_exception
    @limiter_0_1.ratelimit("myvidster", delay=True)
    def _get_infovideo(self, url, headers=None):       
        
        return self.get_info_for_format(url, headers=headers)

    

    

    def _login(self):
        
        username, password = self._get_login_info()
        self.report_login()
        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)

        data = {
            "user_id": username,
            "password": password,
            "save_login" : "on",
            "submit" : "Log+In",
            "action" : "log_in"
        }

        _headers_post = {
                "Referer": self._LOGIN_URL,
                "Origin": self._SITE_URL,
                "Content-Type": "application/x-www-form-urlencoded",
                "Upgrade-Insecure-Requests": "1"
        }        
        
        try:

            res = self._send_request(self._LOGIN_URL, _type="POST", data=data, headers=_headers_post)
            if res and "www.myvidster.com/user/home.php" in str(res.url):
                self.to_screen("LOGIN OK")                
            else:
                raise ExtractorError(f"Login failed: {res} : {res.url if res else None}")
           
        except ExtractorError:            
            raise
        except Exception as e:            
            self.to_screen(repr(e))
            raise ExtractorError(repr(e))
            
    
    def _login_driver(self, driver):
        
        el_sddm = try_get(self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.ID, 'sddm'))), lambda x: x[0].text) or ''
        if not el_sddm or 'log in' in el_sddm: 
            self.to_screen("Not logged with Selenium/Firefox webdriver. Lets login")
            driver.get("https://myvidster.com/user/")
            username, password = self._get_login_info()
            el_username = try_get(self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CSS_SELECTOR, 'input#user_id'))), lambda x: x[0])
            el_password = try_get(self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CSS_SELECTOR, 'input#password'))), lambda x: x[0])
            el_button = try_get(self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CSS_SELECTOR, 'button'))), lambda x: x[0])
            el_username.send_keys(username)
            self.wait_until(driver, 2)
            el_password.send_keys(password)
            self.wait_until(driver, 2)
            el_button.click()
            self.wait_until(driver, 60, ec.url_changes("https://www.myvidster.com/user/"))
            if not "www.myvidster.com/user/home.php" in driver.current_url:
                raise ExtractorError("no logged")
    
    def _real_initialize(self):
            
        with MyVidsterBaseIE._LOCK:
            
            if not self._MASTER_INIT:
                super()._real_initialize()
                #SeleniumInfoExtractor._FIREFOX_HEADERS['User-Agent'] = MyVidsterBaseIE._CLIENT_CONFIG['headers']['user-agent']        
            
            if not MyVidsterBaseIE._COOKIES:
                        
                try:
                    self._login()
                    MyVidsterBaseIE._COOKIES = self._CLIENT.cookies                                        
        
                except Exception as e:
                    self.to_screen(repr(e))                    
                    raise
                
            for cookie in MyVidsterBaseIE._COOKIES.jar:
                self._CLIENT.cookies.set(name=cookie.name, value=cookie.value, domain=cookie.domain)

class MyVidsterIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster'
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/(?:video|vsearch)/(?P<id>\d+)/?(?:.*|$)'
    _NETRC_MACHINE = "myvidster"

    def _real_initialize(self):
        super()._real_initialize()
        
    
    def _real_extract(self, url):

        self.report_extraction(url)
        video_id = self._match_id(url)
        url = url.replace("vsearch", "video")

        try:

            res = self._send_request(url)
            if not res: raise ExtractorError("Couldnt download webpage")
            if any(_ in str(res.url) for _ in ['status=not_found', 'status=broken']): raise ExtractorError("Error 404: Page not found or Page broken") 
            
            webpage = re.sub('[\t\n]', '', html.unescape(res.text))
            
            title = try_get(re.findall(r"<title>([^<]+)<", webpage), lambda x: x[0]) or url.split("/")[-1]
            
            postdate = try_get(re.findall(r"<td><B>Bookmark Date:</B>([^<]+)</td>", webpage), lambda x: datetime.strptime(x[0], "%d %b, %Y"))
            if postdate:
                _entry = {'release_date': postdate.strftime("%Y%m%d"), 'release_timestamp': int(postdate.timestamp())}
            else:
                _entry = {}
                
            def _getter(x,msg):
                if x:
                    for el in list(set(x)):
                        if not '//syndication.' in el:
                            if self._is_valid(unquote(el), msg): return unquote(el)


            source_url = try_get(re.findall(r'source src=[\'\"]([^\'\"]+)[\'\"] type=[\'\"]video', webpage), lambda x: _getter(x, 'source_url')) 
            
             
            if source_url:
                
                self.to_screen(f"source url: {source_url}")
                
                _headers = {'Referer': 'https://www.myvidster.com'}
                
                _info_video = self._get_infovideo(source_url, headers=_headers)
                
                if not _info_video:                    
                    raise ExtractorError('couldnt get info video details')
                    
                _format_video = {
                    'format_id' : 'http-mp4',
                    'url': _info_video.get('url'),
                    'filesize': _info_video.get('filesize'),
                    'http_headers': _headers,
                    'ext' : 'mp4'
                }
                
                _entry.update({
                    'id' : video_id,
                    'title' : sanitize_filename(title, restricted=True),
                    'formats' : [_format_video],
                    'ext': 'mp4'
                })
                
                return _entry
            
            
            else:
                

                    
                videolink =  try_get(re.findall(r'rel=[\'\"]videolink[\'\"] href=[\'\"]([^\'\"]+)[\'\"]', webpage), lambda x: _getter(x, 'videolink'))
                #embedlink = try_get(re.findall(r'<iframe src=[\'\"]([^\'\"]+)[\'\"]', webpage), lambda x: _getter(x, 'embedlink')) or try_get(re.findall(r'reload_video\([\'\"]([^\'\"]+)[\'\"]', webpage), lambda x: _getter(x, 'embedlink'))
                embedlink = try_get(re.findall(r'<iframe src=[\'\"](https://[^\'\"]+)[\'\"]', webpage) + re.findall(r'reload_video\([\'\"](https://[^\'\"]+)[\'\"]', webpage), lambda x: _getter(x, 'embedlink')) 
                #re.findall(r'iframe src=[\"\']((?!.*https://syndication)[^\"\']+)[\"\']', webpage)

                if not videolink and not embedlink: raise ExtractorError("Error 404: no video urls found")
                elif videolink and embedlink:

                    _videolink = None if (self._get_ie_key(videolink) in ['Generic','MyVidster']) else videolink
                    _embedlink = None if (self._get_ie_key(embedlink) == 'Generic') else embedlink

                    real_url = _embedlink or _videolink or embedlink

                else: real_url = videolink or embedlink
                
                self.to_screen(f"url selected: {real_url}")
                
                if real_url:
                    _entry.update({
                        #'_type' : 'url_transparent',
                        '_type': 'url',
                        #'id' : video_id,
                        #'title': sanitize_filename(re.sub(r"([_ ]at[_ ][^$]+$)", "", title), True),
                        'url' : unquote(real_url),
                        'ie_key': self._get_ie_key(real_url)                     
                    })
                    
                    return _entry
                    
                else: raise ExtractorError("Page not found")

        except ExtractorError as e:
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}') 
            raise ExtractorError("No video info")
        

class MyVidsterChannelPlaylistIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:channel:playlist'   
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/channel/(?P<id>\d+)/?(?P<title>\w+)?'
    _POST_URL = "https://www.myvidster.com/processor.php"
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
        channelid = self._match_id(url)
        
        self.report_extraction(url)

        try:

            res = self._send_request(url)
            if not res: raise ExtractorError("Couldnt download webpage")
            webpage = re.sub('[\t\n]', '', html.unescape(res.text))
            
            title = try_get(re.findall(r'<title>([\w\s]+)</title>', webpage), lambda x: x[0]) or f"MyVidsterChannel_{channelid}"
            num_videos = try_get(re.findall(r"display_channel\(.*,[\'\"](\d+)[\'\"]\)", webpage), lambda x: x[0]) or 100000

            info = {
                'action' : 'display_channel',
                'channel_id': channelid,
                'page' : '1',
                'thumb_num' : num_videos,
                'count' : num_videos
            }
            
            _headers_post = {
                "Referer": url,                
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "X-Requested-With" : "XMLHttpRequest",
                "Accept": "*/*"
            }

            res = self._send_request(self._POST_URL, _type="POST", data=info, headers=_headers_post)    
            if not res: raise ExtractorError("Couldnt display channel")
            webpage = re.sub('[\t\n]', '', html.unescape(res.text))

            el_videos = get_elements_by_class("thumbnail", webpage)
            #videos = re.findall(r'<a href=\"(/video/[^\"]+)\" class', webpage)
            entries = []
            for el in el_videos:
                video_url = try_get(re.findall(r'<a href=\"(/video/[^\"]+)\" class', el), lambda x: f'{self._SITE_URL}{x[0]}')
                posted_date = try_get(get_elements_by_class("mvp_grid_panel_details", el), lambda x: datetime.strptime(x[0].replace('Posted ', '').strip(), '%B %d, %Y'))
                if video_url:
                    _entry = {'_type':'url_transparent', 'url': video_url, 'ie_key': 'MyVidster'}
                    if posted_date:
                        _entry.update({'release_date': posted_date.strftime("%Y%m%d"), 'release_timestamp': int(posted_date.timestamp())})
                    entries.append(_entry)
            
            if entries:
                return {
                    '_type': 'playlist',
                    'id': channelid,
                    'title': sanitize_filename(title, True),
                    'entries': entries,
                }
            else: raise ExtractorError("no entries found")
                
        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(repr(e))
        
class MyVidsterRSSPlaylistIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:subs:playlist'   
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/subscriptions/atgarcia'
    _POST_URL = "https://www.myvidster.com/processor.php"
    _NETRC_MACHINE = "myvidster"
    
    def _getter(self, x):
 
        try:
            
            _path, _profile = x.groups()
            self.to_screen(f'[getter] {_path}:{_profile}')
            _subs_link = urljoin("https://myvidster.com", _path)
            if not _profile:
                res = self._send_request(_subs_link)
                if res:
                    _profile = try_get(re.findall(r'by <a href="/profile/([^"]+)"', res.text), lambda x: x[0])
            return (_subs_link, _profile)
                        
        except Exception as e:
            self.to_screen(repr(e))
    
    
    def _get_rss(self):

        info = {
            'action' : 'display_subscriptions',
            'disp_name': 'Atgarcia',
            'page' : '1',
            'thumb_num' : 100,
            'count' : 100
        }
        
        _headers_post = {
            "Referer": self._SITE_URL,
            "Origin": self._SITE_URL,                
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "x-Requested-With" : "XMLHttpRequest",
            "Accept": "*/*"
        }
        
        res = self._send_request(self._POST_URL, _type="POST", data={'action': 'loading'}, headers=_headers_post)
        #self.to_screen(f'{res.text}\n\n\n\n\n')
        res = self._send_request(self._POST_URL, _type="POST", data=info, headers=_headers_post)
        if not res: self.to_screen(f'Couldnt get subscriptions')
        else:
            webpage = re.sub('[\t\n]', '', html.unescape(res.text)).lower()
            #self.to_screen(webpage)
            #self.to_screen(f'{webpage}\n\n\n')
            for subwebpage in webpage.split('</div></td></tr><tr><td><div class="border1"><img src="/images/spacer.gif" width="311" height="3" border="0" alt=""></div></td></tr><tr><td><div style="position:relative;"><div style="display: block;height:75px;"><div class="vidthumbnail" style="margin-right:6px;margin-bottom:2px;">'):
                for line in subwebpage.split("</span><br><div>"):
                    #self.to_screen(f'\t{line}\n')
                    if not 'atgarcia&action' in line:
                        rss_link, profile = try_get(re.search(r'<a href="(/subscriptions/atgarcia/[^"]+)".*<a href="/profile/([^"]*)">', line), self._getter) or (None, None)
                        self.to_screen(f'\t\t{rss_link}:{profile}')
                        if rss_link: 
                            if not (MyVidsterBaseIE._RSS.get(profile)):
                                MyVidsterBaseIE._RSS[profile] = {'user': None, 'collections': [], 'channels': []}
                            if 'user' in rss_link: 
                                MyVidsterBaseIE._RSS[profile]['user'] = rss_link
                            elif 'gallery' in rss_link:
                                MyVidsterBaseIE._RSS[profile]['collections'].append(rss_link)
                            elif 'channel' in rss_link:
                                MyVidsterBaseIE._RSS[profile]['channels'].append(rss_link)
                                                                               

    def _query_rss(self, q):
        info = {
            'action' : 'query_subscriptions',
            'disp_name': 'Atgarcia',
            'q': q
        }
        
        _headers_post = {
            "Referer": self._SITE_URL,
            "Origin": self._SITE_URL,                
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "x-Requested-With" : "XMLHttpRequest",
            "Accept": "*/*"
        }
        
        res = self._send_request(self._POST_URL, _type="POST", data={'action': 'loading'}, headers=_headers_post)
        res = self._send_request(self._POST_URL, _type="POST", data=info, headers=_headers_post)
        if res:
            self.to_screen(res.text)
            return res
        

    def _real_initialize(self):
        super()._real_initialize()
        self._get_rss()
       # self.to_screen(f"\n{MyVidsterBaseIE._RSS}")
        
    def _real_extract(self, url):
        
        self.report_extraction(url)
        driver = self.get_driver()
        
        try:
            driver.get(self._SITE_URL)
            self._login_driver(driver)
            driver.get(url)
            el_posted_videos = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CLASS_NAME,'posted_video')))
            entries = []
            for el in el_posted_videos:
                video_url = try_get(el.find_elements(By.TAG_NAME, 'a'), lambda x: x[0].get_attribute('href'))
                postdate_text = try_get(el.find_elements(By.CLASS_NAME, 'postdate'), lambda x: x[0].text.replace(" by", "").replace(":", ""))
                if 'Posted' in postdate_text:
                    postdate = datetime_from_str(f'now+1hour-{postdate_text.replace("Posted", "").replace("ago", "").replace(" ","")}')
                    entries.append({'_type': 'url_transparent', 'url': video_url, 'release_date': postdate.strftime("%Y%m%d"), 'release_timestamp': int(postdate.timestamp())})
            if entries:
                return self.playlist_result(entries, playlist_id='myvidster_rss', playlist_title='myvidster_rss')
            else: raise ExtractorError("no entries found")
        
        except ExtractorError as e:
            self.to_screen(repr(e))
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(repr(e))
        finally:
            self.rm_driver(driver)
        
class MyVidsterSearchPlaylistIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:search:playlist'   
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/search/\?(?P<query>.+)'
    
    '''
        Inside query, if there is param 'pages', that it is the max number of pages of
        search result that will be evaluated. By default: 5
    '''
    
    _NETRC_MACHINE = "myvidster"
    _SEARCH_URL = 'https://www.myvidster.com/search/?'
    
    def _get_videos(self, _urlq):
        
        res = self._send_request(_urlq)
        if res:
            list_videos =  re.findall(r'<a href="(/vsearch/[^"]+)">', res.text)
            return list_videos
        
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):

        self.report_extraction(url)        

        query = re.search(self._VALID_URL, url).group('query')
        
        params = { el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
        
        if not params.get('filter_by'): params['filter_by'] = 'myvidster'
        if not params.get('cfilter_by'): params['cfilter_by'] = 'all'
                
        max_pages = int(params.pop('pages', 5))
        
        query_str = "&".join([f"{_key}={_val}" for _key, _val in params.items()])
        
        list_search_urls = [f"{self._SEARCH_URL}{query_str}&page={i+1}" for i in range(max_pages)] 
        
        self.to_screen(list_search_urls)
                
        try:            
            
            with ThreadPoolExecutor(max_workers=min(len(list_search_urls), 5)) as exe:
                futures = [exe.submit(self._get_videos, _urlq) for _urlq in list_search_urls]
                
            list_videos = []
            for fut in futures:
                try:
                    list_videos += fut.result()
                except Exception as e:
                    self.to_screen(repr(e))
            
            if list_videos:
                entries = [{'_type':'url', 'url': f'{self._SITE_URL}{video}', 'ie_key': 'MyVidster'} for video in list_videos]
                
                return {
                    '_type': 'playlist',
                    'id': 'myvidster_search_results',
                    'title': 'myvidster_search_results',
                    'entries': entries,
                }
            
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(repr(e))

    
    
