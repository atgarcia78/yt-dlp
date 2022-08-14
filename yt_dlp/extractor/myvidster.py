import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock
from urllib.parse import unquote
import html
import re


from ..utils import (ExtractorError, datetime_from_str, get_elements_by_class,
                     sanitize_filename, try_get, urljoin)
from .commonwebdriver import ec, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_0_1, HTTPStatusError, By


class MyVidsterBaseIE(SeleniumInfoExtractor):

    _LOGIN_URL = "https://www.myvidster.com/user/"
    _SITE_URL = "https://www.myvidster.com"
    _NETRC_MACHINE = "myvidster"
    
    _LOCK = Lock()
    _COOKIES = {}
    _RSS = {}

    @dec_on_exception3
    @dec_on_exception2
    @limiter_0_1.ratelimit("myvidster", delay=True)
    def _send_request(self, url, _type="GET", data=None, headers=None):        
            
        try:
            self.logger_debug(f"[send_req] {self._get_url_print(url)}") 
            return(self.send_http_request(url, _type=_type, data=data, headers=headers))
        except HTTPStatusError as e:
            self.report_warning(f"[send_request] {self._get_url_print(url)}: error - {repr(e)}")
        
            
    @dec_on_exception3
    @dec_on_exception2
    @limiter_0_1.ratelimit("myvidster", delay=True)
    def _get_infovideo(self, url, headers=None):       
        
        try:
            return self.get_info_for_format(url, headers=headers)
        except HTTPStatusError as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")


    def _login(self):
        
        res = self._send_request(self._LOGIN_URL, _type="GET")
        if res and "www.myvidster.com/user/home.php" in str(res.url):
            self.logger_debug("LOGIN already OK")
            return
        self.report_login()
        
        username, password = self._get_login_info()
        
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
                self.logger_debug("LOGIN OK")
                return
            elif res and "www.myvidster.com/user" in str(res.url):
                res2 = self._send_request(self._LOGIN_URL, _type="GET")
                if res2 and "www.myvidster.com/user/home.php" in str(res2.url):
                    self.logger_debug("LOGIN OK")
                    return
                else:
                    raise ExtractorError(f"Login failed: {res2} : {res2.url if res2 else None}")     
            else:
                raise ExtractorError(f"Login failed: {res} : {res.url if res else None}")
           
        except ExtractorError:            
            raise
        except Exception as e:            
            self.to_screen(repr(e))
            raise ExtractorError(repr(e))
            
    
    def _login_driver(self, driver):
        
        driver.get(self._SITE_URL)
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
                    MyVidsterBaseIE._COOKIES = SeleniumInfoExtractor._CLIENT.cookies                                        
        
                except Exception as e:
                    self.to_screen(repr(e))                    
                    raise
            else:    
                for cookie in MyVidsterBaseIE._COOKIES.jar:
                    SeleniumInfoExtractor._CLIENT.cookies.set(name=cookie.name, value=cookie.value, domain=cookie.domain)
                
class MyVidsterIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:playlist'
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/(?:video|vsearch)/(?P<id>\d+)/?(?:.*|$)'
    _NETRC_MACHINE = "myvidster"
    
  
    _URLS_CHECKED = []
    
    def _already_analysed(self, url1):
        for url2 in MyVidsterIE._URLS_CHECKED:
            if url1 == url2: 
                return url2
            if ((_extr:=self._get_ie_name(unquote(url1))) == self._get_ie_name(unquote(url2))):
                if _extr != 'generic':
                    #ie = self._downloader.get_info_extractor(self._get_ie_key(unquote(url1)))
                    ie = self._get_extractor(unquote(url1))
                    #ie._real_initialize()
                    mobj1 = re.search(ie._VALID_URL, url1)
                    mobj2 = re.search(ie._VALID_URL, url2)
                    if mobj1.groupdict() == mobj2.groupdict():
                        return url2
        
    
    def getbestvid(self, x, msg=None):

        pre = f"[getbestvid]"
        if msg: pre = f'{msg}{pre}'
        
        if isinstance(x, list):            
            _x = [unquote(_el) for _el in list(set(x))]            
        else:
            _x = [unquote(x)]     
            
        self.logger_debug(f"{pre} urls to check: {_x}")
       
        for el in _x:
            
            try:
            
                if "//syndication" in el: 
                    continue
                
                if "?thumb=http" in el:
                    continue
                
                if (url2:=self._already_analysed(el)):
                    self.logger_debug(f"{pre}[{self._get_url_print(el)}] already analysed, same result as {url2}")
                    continue
                    
                if (_id:=try_get(re.findall(r'locotube\.site/pn/\?c\=(\d+)', el), lambda x: x[0])):
                    el = f'https://thisvid.com/embed/{_id}'
                
                _extr_name = self._get_ie_name(el)
                
                def _check_extr(x):
                    if (try_get([kt for k in SeleniumInfoExtractor._CONFIG_REQ.keys() if any(x==(kt:=_) for _ in k)], lambda y: y[0])):
                        return True
                
                
                if _check_extr(_extr_name): #get entry                    
                    ie = self._get_extractor(el)
                    try:
                        _ent = ie._get_entry(el, check_active=True, msg=pre)
                        if _ent:
                            self.logger_debug(f"{pre}[{self._get_url_print(el)}] OK got entry video\n {_ent}")
                            return _ent
                        else:
                            self.logger_debug(f'{pre}[{self._get_url_print(el)}] WARNING not entry video')
                    except Exception as e:
                        self.logger_debug(f'{pre}[{self._get_url_print(el)}] WARNING error entry video {repr(e)}')


                #elif _extr_name in ['xhamster', 'xhamsterembed', 'noodlemagazine']:
                elif _extr_name != 'generic':
                    
                    try:
                        _ent = self._downloader.extract_info(el, download=False)
                        if _ent:
                            self.logger_debug(f"{pre}[{self._get_url_print(el)}] OK got entry video\n {_ent}")
                            return self._downloader.sanitize_info(_ent)
                        else:
                            self.logger_debug(f'{pre}[{self._get_url_print(el)}] WARNING not entry video')
                    except Exception as e:
                        self.logger_debug(f'{pre}[{self._get_url_print(el)}] WARNING error entry video {repr(e)}')
                             
                        
                else:
                    if self._is_valid(el, msg=pre):
                        return el
                
            
            except Exception as e:
                self.logger_debug(f'{pre}[{self._get_url_print(el)}] WARNING error entry video {repr(e)}')
            finally:
                MyVidsterIE._URLS_CHECKED.append(el)
                


    def _get_entry(self, url, **args):
        
        video_id = self._match_id(url)
        url = url.replace("vsearch", "video")


        _urlh, webpage = try_get(self._send_request(url), lambda x: (str(x.url), re.sub('[\t\n]', '', html.unescape(x.text)) if x else (None, None)))
        if not webpage: raise ExtractorError("Couldnt download webpage")
        if any(_ in str(_urlh) for _ in ['status=not_found', 'status=broken', 'status=removed']): raise ExtractorError("Error 404: Page not found") 
        
        
        title = try_get(re.findall(r"<title>([^<]+)<", webpage), lambda x: x[0]) or url.split("/")[-1]
        
        postdate = try_get(re.findall(r"<td><B>Bookmark Date:</B>([^<]+)</td>", webpage), lambda x: datetime.strptime(x[0].strip(), "%d %b, %Y"))
        if postdate:
            _entry = {'release_date': postdate.strftime("%Y%m%d"), 'release_timestamp': int(postdate.timestamp())}
        else:
            _entry = {}    


        source_url_res = try_get(re.findall(r'source src=[\'\"]([^\'\"]+)[\'\"] type=[\'\"]video', webpage), 
                                 lambda x: self.getbestvid(x[0], 'source_url') if x else None) 
        
            
        if source_url_res:
            
            if isinstance(source_url_res, str):
                self.logger_debug(f"source url: {source_url_res}")
            
                _headers = {'referer': 'https://www.myvidster.com'}
            
                _info_video = self._get_infovideo(source_url_res, headers=_headers)
            
                if not _info_video:                    
                    raise ExtractorError('error 404: couldnt get info video details')
                
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
                    'ext': 'mp4',
                    'webpage_url': url
                })
                
                return _entry
        
        
        else:
            
            embedlink_res = None
            videolink_res = None

            embedlink_res = try_get(re.findall(r'reload_video\([\'\"]([^\'\"]+)[\'\"]', webpage),
                                    lambda x: self.getbestvid(x[0], 'embedlink') if x else None)
            
            if not embedlink_res or isinstance(embedlink_res, str):           
                
                videolink_res =  try_get(re.findall(r'rel=[\'\"]videolink[\'\"] href=[\'\"]([^\'\"]+)[\'\"]', webpage),
                                         lambda x: self.getbestvid(x[0], 'videolink') if x else None)
                    
            if not embedlink_res and not videolink_res: 
                raise ExtractorError("Error 404: no video urls found")
            
            if isinstance(embedlink_res, dict):
                embedlink_res.update({'original_url': url})
                embedlink_res.update(_entry)
                return embedlink_res
            if isinstance(videolink_res, dict):
                videolink_res.update({'original_url': url})
                videolink_res.update(_entry)
                return videolink_res
            
            if embedlink_res and videolink_res:
                if self._get_ie_name(embedlink_res) != 'generic':
                    real_url = embedlink_res
                elif self._get_ie_name(videolink_res) != 'generic':
                    real_url = videolink_res
                else:
                    real_url = embedlink_res
            else:
                real_url = embedlink_res or videolink_res

            self.logger_debug(f"url selected: {real_url}")
            
            if real_url:
                _entry.update({
                    '_type': 'url',
                    'url' : real_url,
                    'ie_key': self._get_ie_key(real_url)                     
                })
                
                return _entry
                
            else: 
                raise ExtractorError("url video not found")
        

    def _real_initialize(self):
        super()._real_initialize()
        
    
    def _real_extract(self, url):

        self.report_extraction(url)
        
        try:            
            return(self._get_entry(url))        

        except ExtractorError as e:
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}') 
            raise ExtractorError("No video info")
        

class MyVidsterChannelPlaylistIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:channel:playlist'   
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/channel/(?P<id>\d+)/?(?P<title>\w+)?(\?(?P<query>.+))?'
    _POST_URL = "https://www.myvidster.com/processor.php"
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
        channelid = self._match_id(url)
        
        self.report_extraction(url)

        try:


            webpage = try_get(self._send_request(url), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)))
            if not webpage: raise ExtractorError("Couldnt download webpage")
            
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

            webpage = try_get(self._send_request(self._POST_URL, _type="POST", data=info, headers=_headers_post), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)))
            if not webpage: raise ExtractorError("Couldnt display channel")

            el_videos = get_elements_by_class("thumbnail", webpage)
            entries = []
            
            query = try_get(re.search(self._VALID_URL, url), lambda x: x.group('query'))
            if query:
                params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
                _first = params.get('first')
                _last = params.get('last')
                el_videos = el_videos[int(_first) - 1: int(_last)]
            
            
            for el in el_videos:
                video_url = try_get(re.findall(r'<a href=\"(/video/[^\"]+)\" class', el), lambda x: f'{self._SITE_URL}{x[0]}')
                posted_date = try_get(get_elements_by_class("mvp_grid_panel_details", el), lambda x: datetime.strptime(x[0].replace('Posted ', '').strip(), '%B %d, %Y'))
                if video_url:
                    
                    _entry = {'_type':'url', 'url': video_url, 'ie_key': 'MyVidster', 'original_url': url}
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
        
       
class MyVidsterSearchPlaylistIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:search:playlist'   
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/search/?\?(?P<query>.+)'
    
    '''
        Inside query, if there is param 'pages', that it is the max number of pages of
        search result that will be evaluated. By default: 5
    '''
    
    _NETRC_MACHINE = "myvidster"
    _SEARCH_URL = 'https://www.myvidster.com/search/?'
    
    def _get_videos(self, _urlq):
        
        webpage = try_get(self._send_request(_urlq), lambda x: html.unescape(x.text))
        if webpage:
            list_videos =  re.findall(r'<a href="(/vsearch/[^"]+)">', webpage)
            return list_videos
       
    def _get_last_page(self, _urlqbase):
        i = 1
        while(True):
            webpage = try_get(self._send_request(f"{_urlqbase}{i}"), lambda x: html.unescape(x.text))
            if "next »" in webpage:
                i += 1
            else:
                break
        return(i-1)
            
        
         
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):

        self.report_extraction(url)        

        query = try_get(re.search(self._VALID_URL, url), lambda x: x.group('query'))
        
        params = { el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
        
        if not params.get('filter_by'): params['filter_by'] = 'myvidster'
        if not params.get('cfilter_by'): params['cfilter_by'] = 'all'
        if not params.get('sortby'): params['sortby'] = 'utc_posted'
        
                
        npages = params.pop('pages', 5)
        firstpage = params.pop('from', 1)
        
        query_str = "&".join([f"{_key}={_val}" for _key, _val in params.items()])
        base_search_url = f"{self._SEARCH_URL}{query_str}&page="
        
        last_page = self._get_last_page(base_search_url)
        
        if last_page == 0:
            raise ExtractorError("no search results")
        
        if npages == 'all':
            _max = last_page
        else:
            _max = int(firstpage) + int(npages) - 1
            if _max > last_page:
                self.logger_debug(f'[{self._get_url_print(url)}] pages requested > max page website: will check up to max page')
                _max = last_page
                

        list_search_urls = [f"{base_search_url}{i}" for i in range(int(firstpage), _max + 1)] 
        
        self.logger_debug(list_search_urls)
                
        try:            
            
            with ThreadPoolExecutor(max_workers=min(len(list_search_urls), 5)) as exe:
                futures = {exe.submit(self._get_videos, _urlq): _urlq for _urlq in list_search_urls}
                
            list_videos = []
            for fut in futures:
                try:
                    _res = fut.result()
                    if _res:
                        list_videos += _res
                    else: raise ExtractorError("no entries")
                except Exception as e:
                    self.report_warning(f"[get_entries][{futures[fut]}] error - {repr(e)}")
            
            if list_videos:
                entries = [{'_type':'url', 'url': f'{self._SITE_URL}{video}', 'ie_key': 'MyVidster', 'original_url': url} for video in list_videos]
                
                return {
                    '_type': 'playlist',
                    'id': query_str,
                    'title': 'Search',
                    'entries': entries,
                }
            
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
            for subwebpage in webpage.split('</div></td></tr><tr><td><div class="border1"><img src="/images/spacer.gif" width="311" height="3" border="0" alt=""></div></td></tr><tr><td><div style="position:relative;"><div style="display: block;height:75px;"><div class="vidthumbnail" style="margin-right:6px;margin-bottom:2px;">'):
                for line in subwebpage.split("</span><br><div>"):
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
 