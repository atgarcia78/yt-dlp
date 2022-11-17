from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock
from urllib.parse import unquote, urljoin
import html
import re

from ..utils import (
    ExtractorError, 
    datetime_from_str, 
    get_elements_by_class,
    sanitize_filename, 
    try_get, 
    urljoin,
    get_domain)
from .commonwebdriver import (
    ec, 
    dec_on_exception2, 
    dec_on_exception3, 
    SeleniumInfoExtractor, 
    limiter_0_1, 
    HTTPStatusError, 
    ConnectError, 
    By, 
    ConnectError)

import logging
logger = logging.getLogger('myvidster')

_URL_NOT_VALID = [  '//syndication', '?thumb=http', 'rawassaddiction.blogspot', 'twitter.com', 'sxyprn.net', 'gaypornmix.com', 'thisvid.com/embed', 
                    'twinkvideos.com/embed','xtube.com', 'xtapes.to', 'gayforit.eu/playvideo.php', '/noodlemagazine.com/player', 
                    'pornone.com/embed/', 'player.vimeo.com/video', 'gaystreamvp.ga', 'gaypornvideos.cc/wp-content/']


class MyVidsterBaseIE(SeleniumInfoExtractor):

    _LOGIN_URL = "https://www.myvidster.com/user/"
    _SITE_URL = "https://www.myvidster.com"
    _NETRC_MACHINE = "myvidster"
    
    _LOCK = Lock()
    _COOKIES = {}
    _RSS = {}

    _URLS_CHECKED = []

    @dec_on_exception3
    @dec_on_exception2
    @limiter_0_1.ratelimit("myvidster", delay=True)
    def _send_request(self, url, **kwargs):        
            
        try:
            self.logger_debug(f"[send_req] {self._get_url_print(url)}") 
            return(self.send_http_request(url, **kwargs))
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[send_request] {self._get_url_print(url)}: error - {repr(e)}")
        
    @dec_on_exception3
    @dec_on_exception2
    @limiter_0_1.ratelimit("myvidster", delay=True)
    def _get_infovideo(self, url, **kwargs):       
        
        try:
            return self.get_info_for_format(url, **kwargs)
        except (HTTPStatusError, ConnectError) as e:
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
    
    def _get_videos(self, _urlq):
        
        if '/search/' in _urlq: 
            item = 'vsearch'
        else: 
            item = 'video'

        webpage = try_get(self._send_request(_urlq), lambda x: html.unescape(x.text))
        if webpage:
            list_videos =  [urljoin(self._SITE_URL, el.replace('vsearch', 'video')) for el in re.findall(rf'<a href="(/{item}/[^"]+)">', webpage)]
            return list_videos

    def _real_initialize(self):
            
        super()._real_initialize()
        
        if not MyVidsterBaseIE._COOKIES:
                    
            try:
                self._login()
                MyVidsterBaseIE._COOKIES = self._CLIENT.cookies                                        
    
            except Exception as e:
                self.to_screen(repr(e))                    
                raise
        else:    
            for cookie in MyVidsterBaseIE._COOKIES.jar:
                self._CLIENT.cookies.set(name=cookie.name, value=cookie.value, domain=cookie.domain)
                
class MyVidsterIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:playlist'
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/(?:video|vsearch)/(?P<id>\d+)/?(?:.*|$)'
    
    def getbestvid(self, x, **kwargs):
        
        msg = kwargs.get('msg', None)
        _check = kwargs.get('check_active', True)

        pre = f"[getbestvid]"
        if msg: pre = f'{msg}{pre}'
        
        if isinstance(x, list):            
            _x = [unquote(_el) for _el in list(set(x))]            
        else:
            _x = [unquote(x)]     
            
        self.logger_debug(f"{pre} urls to check: {_x}")
       
        for el in _x:
            
            try:            

                if el in MyVidsterBaseIE._URLS_CHECKED:
                    self.logger_debug(f"{pre}[{self._get_url_print(el)}] already analysed")
                    continue

                if any(_ in el for _ in _URL_NOT_VALID):
                    self.logger_debug(f"{pre}[{self._get_url_print(el)}] url not valid")
                    continue
                    
                if 'locotube.site/pn' in el:
                    _id, _id2 = try_get(re.search(r'locotube\.site/pn\?c\=(?P<id>[\d/]+)(&gfi=(?P<id2>[a-zA-Z0-9\-]+))?', el), 
                                        lambda x: x.group('id', 'id2') if x else (None, None))
                    if _id2:
                        el = f'https://gayforit.eu/playvideo.php?vkey={_id2}'
                    elif _id:
                        if '/' in _id:
                            el = f'https://www.boyfriendtv.com/embed/{_id}'
                        else:
                            el = f'https://thisvid.com/embed/{_id}'
                
                _extr_name = self._get_ie_name(el)
                
                def _check_extr(x):
                    if (try_get([kt for k in SeleniumInfoExtractor._CONFIG_REQ.keys() if any(x==(kt:=_) for _ in k)], 
                                lambda y: y[0])):
                        return True

                if _check_extr(_extr_name): #get entry                    
                    ie = self._get_extractor(el)
                    try:
                        _ent = ie._get_entry(el, check_active=_check, msg=pre)
                        if _ent:
                            self.logger_debug(f"{pre}[{self._get_url_print(el)}] OK got entry video\n {_ent}")
                            return _ent
                        else:
                            self.logger_debug(f'{pre}[{self._get_url_print(el)}] WARNING not entry video')
                            return {"error_getbestvid": f"[{el}] not entry video"}
                    except Exception as e:
                        self.logger_debug(f'{pre}[{self._get_url_print(el)}] WARNING error entry video {repr(e)}')
                        return {"error_getbestvid": f"[{el}] error entry video - {repr(e)}"}

                elif _extr_name != 'generic':
                    
                    try:
                        _ent = self._downloader.extract_info(el, download=False)
                        if _ent:
                            self.logger_debug(f"{pre}[{self._get_url_print(el)}] OK got entry video\n {_ent}")
                            return _ent
                        else:
                            self.logger_debug(f'{pre}[{self._get_url_print(el)}] WARNING not entry video')
                    except Exception as e:
                        self.logger_debug(f'{pre}[{self._get_url_print(el)}] WARNING error entry video {repr(e)}')                             
                        
                else: #url generic
                    if self._is_valid(el, msg=pre):
                        return el
                
            except Exception as e:
                self.logger_debug(f'{pre}[{self._get_url_print(el)}] WARNING error entry video {repr(e)}')
            finally:
                MyVidsterBaseIE._URLS_CHECKED.append(el)
                
    def _get_entry(self, url, **kwargs):
        
        _check = kwargs.get('check_active', True)
        video_id = self._match_id(url)
        url = url.replace("vsearch", "video")

        _urlh, webpage = try_get(self._send_request(url), 
                                 lambda x: (str(x.url), re.sub('[\t\n]', '', html.unescape(x.text)) 
                                            if x else (None, None)))
        if not webpage: raise ExtractorError("Couldnt download webpage")
        if any(_ in str(_urlh) for _ in ['status=not_found', 'status=broken', 'status=removed']): 
            raise ExtractorError("Error 404: Page not found") 
        
        title = try_get(re.findall(r"<title>([^<]+)<", webpage), lambda x: x[0]) or url.split("/")[-1]
        
        postdate = try_get(re.findall(r"<td><B>Bookmark Date:</B>([^<]+)</td>", webpage), 
                           lambda x: datetime.strptime(x[0].strip(), "%d %b, %Y"))
        if postdate:
            _entry = {'release_date': postdate.strftime("%Y%m%d"), 'release_timestamp': int(postdate.timestamp())}
        else:
            _entry = {}    

        source_url_res = try_get(re.findall(r'source src=[\'\"]([^\'\"]+)[\'\"] type=[\'\"]video', webpage), 
                                 lambda x: self.getbestvid(x[0], 'source_url') if x else None) 

        if source_url_res:
            
            if isinstance(source_url_res, dict):
                source_url_res.update({'original_url': url})
                source_url_res.update(_entry)
                return source_url_res
            
            elif isinstance(source_url_res, str):
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
                    'webpage_url': url,
                    'extractor': self.IE_NAME,
                    'extractor_key': self.ie_key()
                })
                
                return _entry

        else:
            
            embedlink_res = None
            videolink_res = None

            embedlink_res = try_get(re.findall(r'reload_video\([\'\"]([^\'\"]+)[\'\"]', webpage),
                                    lambda x: self.getbestvid(x[0], check_active=_check, msg='embedlink') if x else None)
            
            if not embedlink_res or isinstance(embedlink_res, str):           
                
                videolink_res =  try_get(re.findall(r'rel=[\'\"]videolink[\'\"] href=[\'\"]([^\'\"]+)[\'\"]', webpage),
                                         lambda x: self.getbestvid(x[0], check_active=_check, msg='videolink') if x else None)                
                
                if videolink_res and isinstance(videolink_res, dict):
                    if (_msg_error:=videolink_res.get('error_getbestvid')):
                        raise ExtractorError(_msg_error)
                    videolink_res.update({'original_url': url})
                    videolink_res.update(_entry)
                    if not videolink_res.get('title'): 
                        domain = get_domain(videolink_res['webpage_url'])
                        title = re.sub(r'(?i)(^(hd video|sd video|video))\s*:?\s*|((?:\s*.\s*|\s*at\s*|\s*)%s$)|(.mp4$)|(\s*[/|]\s*embed player)' % domain, '', title).strip('[,-_ ')
                        videolink_res['title'] = sanitize_filename(title, restricted=True)
                    return videolink_res
                
                if not videolink_res and not embedlink_res:
                    raise ExtractorError("Error 404: no video urls found")
            
            
            elif isinstance(embedlink_res, dict):
                if (_msg_error:=embedlink_res.get('error_getbestvid')):
                    raise ExtractorError(_msg_error)
                embedlink_res.update({'original_url': url})
                embedlink_res.update(_entry)
                if not embedlink_res.get('title'): 
                    domain = get_domain(embedlink_res['webpage_url'])
                    title = re.sub(r'(?i)(^(hd video|sd video|video))\s*:?\s*|((?:\s*.\s*|\s*at\s*|\s*)%s$)|(.mp4$)|(\s*[/|]\s*embed player)' % domain, '', title).strip('[,-_ ')
                    embedlink_res['title'] = sanitize_filename(title, restricted=True)
                return embedlink_res
            
            #llegados a este punto, los links serán generic y valid

            real_url = embedlink_res or videolink_res
           
            self.logger_debug(f"url selected: {real_url}")
            
            if real_url:
                ie = self._get_extractor('Generic')
                try:
                    _videoent = ie._real_extract(real_url)
                except Exception as e:
                    _videoent = {}
                
                if not _videoent:
                    raise ExtractorError("Unsupported URL")
                else:                    
                    _entry.update(_videoent)
                    _entry.update({'webpage_url': url})                         
                    _entry.update({'title': sanitize_filename(title, restricted=True)})
                    
                    return _entry
                
            else: 
                raise ExtractorError("url video not found")

    def _real_initialize(self):
        with MyVidsterBaseIE._LOCK:
            super()._real_initialize()
        
    def _real_extract(self, url):

        self.report_extraction(url)
        
        try:            
            return(self._get_entry(url))        

        except ExtractorError as e:
            raise 
        except Exception as e:
            raise ExtractorError(repr(e))
        
class MyVidsterChannelPlaylistIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:channel:playlist'   
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/channel/(?P<id>\d+)/?(?P<title>\w+)?(\?(?P<query>.+))?'
    _POST_URL = "https://www.myvidster.com/processor.php"
    
    
    def get_playlist_channel(self, url):

        try:

            channelid = self._match_id(url)

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
            results = []
            
            query = try_get(re.search(self._VALID_URL, url), lambda x: x.group('query'))
            if query:
                params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
                _first = params.get('first') or '1'
                _last = params.get('last') 
                if _last:
                    el_videos = el_videos[int(_first) - 1: int(_last)]
                else:
                    el_videos = el_videos[int(_first) - 1:]

                _check = params.get('check', True)
                if _check == 'no': _check = False
            
            
            for el in el_videos:
                video_url = try_get(re.findall(r'<a href=\"(/video/[^\"]+)\" class', el), 
                                    lambda x: f'{self._SITE_URL}{x[0]}')
                posted_date = try_get(get_elements_by_class("mvp_grid_panel_details", el), 
                                      lambda x: datetime.strptime(x[0].replace('Posted ', '').strip(), '%B %d, %Y'))
                
                if video_url:                    
                    _res = {'_type':'url', 'url': video_url, 'ie_key': 'MyVidster'}
                    if posted_date:
                        _res.update({'release_date': posted_date.strftime("%Y%m%d"), 'release_timestamp': int(posted_date.timestamp())})
                    results.append(_res)
            
            if results:

                if self.get_param('embed') or (self.get_param('extract_flat','') != 'in_playlist'):
                
                    iemv = self._get_extractor("MyVidster")
                    
                    with ThreadPoolExecutor(thread_name_prefix='ex_channelpl') as ex:
                        futures = {ex.submit(iemv._get_entry, el['url'], check_active=_check): el['url'] for el in results}

                    entries = []

                    for fut, ent in zip(futures, results):
                        try:
                            _res = fut.result()
                            if _res:
                                #self.logger_debug(f"%no%[res]\n{_res}\n[ent]\n{ent}")
                                _res.update({'release_data': ent.get('release_data'), 'release_timestamp': ent.get('release_timestamp')})
                                entries.append(_res)
                        except Exception as e:
                            self.report_warning(f"[get_entries][{futures[fut]}] error - {repr(e)}")
                            if self.get_param('embed'): 
                                entries.append({'url': futures[fut], 'error': repr(e)})

                else:
                    entries = results

                if entries:

                    return {
                        '_type': 'playlist',
                        'id': channelid,
                        'title': sanitize_filename(title, True),
                        'entries': entries,
                        }
                
            raise ExtractorError("no entries found")
                
        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(repr(e))

    def _real_initialize(self):
    
        with MyVidsterBaseIE._LOCK:
            super()._real_initialize()
    
    def _real_extract(self, url):
        
        
        self.report_extraction(url)
        return self.get_playlist_channel(url)

        
class MyVidsterSearchPlaylistIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:search:playlist'   
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/search/?\?(?P<query>.+)'

    _SEARCH_URL = 'https://www.myvidster.com/search/?'
    
    def _get_last_page(self, _urlqbase):
        i = 1
        while(True):
            webpage = try_get(self._send_request(f"{_urlqbase}{i}"), lambda x: html.unescape(x.text))
            if "next »" in webpage:
                i += 1
            else:
                break
        return(i-1)
            
    
    def get_playlist_search(self, url):

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
            
            #with ThreadPoolExecutor(max_workers=min(len(list_search_urls), 5)) as exe:
            with ThreadPoolExecutor(thread_name_prefix='ex_searchpl') as exed:
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

                if self.get_param('embed') or (self.get_param('extract_flat','') != 'in_playlist'):
                
                    with ThreadPoolExecutor(thread_name_prefix='ex_search2pl') as ex:
                            futures = {ex.submit(iemv._get_entry, _url): _url for _url in results}

                    entries = []

                    for fut in futures:
                        try:
                            _res = fut.result()
                            if _res:
                                _res['original_url'] = url
                                entries.append(_res)
                        except Exception as e:
                            self.report_warning(f"[get_entries][{futures[fut]}] error - {repr(e)}")     

                else:
                    entries = [{'_type':'url', 'url': video, 'ie_key': 'MyVidster', 'original_url': url} for video in list_videos]

                if entries:
                
                    return {
                        '_type': 'playlist',
                        'id': query_str,
                        'title': 'Search',
                        'entries': entries,
                    }

                raise ExtractorError("no entries found")
                
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(repr(e))

    def _real_initialize(self):
        with MyVidsterBaseIE._LOCK:
            super()._real_initialize()
    
    def _real_extract(self, url):
        self.report_extraction(url)
        return self.get_playlist_search(url)     



class MyVidsterRSSPlaylistIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:subs:playlist'   
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/subscriptions/Atgarcia/?(\?(?P<query>.+))?'
    _POST_URL = "https://www.myvidster.com/processor.php"    
    _RSS_URL = 'https://www.myvidster.com/subscriptions/Atgarcia'
    _SEARCH_URL =  "https://www.myvidster.com/search/?%s&filter_by=user_%s"
    
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
    
    def _follow_subs_user(self, username):
        
        webpage = try_get(self._send_request(f"https://myvidster.com/profile/{username}"), lambda x: html.unescape(x.text))
        if webpage:
            adduserurl = try_get(re.findall(r'name=[\"\']subscribe[\"\']\s+class=[\"\']mybutton[\"\']\s+onClick="window\.location=[\'\"]([^\'\"]+)[\'\"]', webpage), lambda x : f'https://myvidster.com/{x[0]}')
            if not adduserurl:
                self.to_screen(f'[follow_subs_user] Already following to {username}')
            else:
                res = self._send_request(adduserurl, headers={'Referer': f'https://myvidster.com/profile/{username}'})
                return (try_get(res, lambda x: 'You are now following this user' in x.text))
    
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
        res = self._send_request(self._POST_URL, _type="POST", data=info, headers=_headers_post)
        if not res: self.to_screen(f'Couldnt get subscriptions')
        else:
                        
            webpage = re.sub('[\t\n]', '', html.unescape(res.text))
            subwebpages = webpage.split('<div class="vidthumbnail" style="margin-right:6px;margin-bottom:2px;">')
            for sub in subwebpages[1:]:    
                username = try_get(re.findall(r'<a href=[\'\"]/profile/([^\'\"]+)[\'\"]', sub), lambda x: x[0])
                if username:
                    _subsuser  = try_get(self._query_rss(username), lambda x: x.text)
                    userid = try_get(re.findall(r'/(?:Atgarcia/user|images/profile)/(\d+)', _subsuser), lambda x: x[0])
                    channels = re.findall(r'/Atgarcia/channel/(\d+)', _subsuser)
                    collections = re.findall(r'/Atgarcia/gallery/(\d+)', _subsuser)                    
                    MyVidsterBaseIE._RSS.update({username: {'userid' : userid, 'channels': channels, 'collections': collections}})

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
        
        self._send_request(self._POST_URL, _type="POST", data={'action': 'loading'}, headers=_headers_post)
        res = self._send_request(self._POST_URL, _type="POST", data=info, headers=_headers_post)
        return res
        
    def get_playlist_rss_search(self, url):

        try:
            query = try_get(re.search(self._VALID_URL, url), lambda x: x.group('query'))
        
            params = {}
            if query:
                params = { el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
        
            
            if not params or list(params.keys()) == ['pages']:            

                results = []
                npages = int(params.get('pages', 1))
                _list_urls_rss_search = [self._RSS_URL + f'&page={i}' for i in range(1, npages + 1)]
                with ThreadPoolExecutor(thread_name_prefix='ex_rsspl') as ex:
                    futures = {ex.submit(self._get_videos, _url): _url for _url in _list_urls_rss_search}

                for fut in futures:
                    try:
                        _res = fut.result()
                        if _res:
                            results += _res
                        else: raise ExtractorError("no entries")
                    except Exception as e:
                        pass
                       
                
                if results:

                    if self.get_param('embed') or (self.get_param('extract_flat','') != 'in_playlist'):

                        iemv = self._get_extractor("MyVidster")

                        with ThreadPoolExecutor(thread_name_prefix='ex_rss2pl') as ex:
                            futures = {ex.submit(iemv._get_entry, _url): _url for _url in results}

                        entries = []

                        for fut in futures:
                            try:
                                _res = fut.result()
                                if _res:
                                    entries.append(_res)
                            except Exception as e:
                                self.report_warning(f"[get_entries][{futures[fut]}] error - {repr(e)}")                        
                        
                    else:
                        entries = [{'_type':'url', 'url': video, 'ie_key': 'MyVidster', 'original_url': url} for video in results]

                    if entries:

                        return self.playlist_result(entries, playlist_id='myvidster_rss', playlist_title='myvidster_rss')
                
                raise ExtractorError("no entries found")
                
            else:
                
                results = {}

                _list_urls_rss_search = [self._SEARCH_URL % (query, val['userid']) for user, val in MyVidsterBaseIE._RSS.items()]
                with ThreadPoolExecutor(thread_name_prefix='ex_rss3pl') as ex:
                    futures = {ex.submit(self._get_videos, _url): _url for _url in _list_urls_rss_search}
                    
                for fut in futures:
                    try:
                        _res = fut.result()
                        if _res:
                            results[futures[fut]] = _res
                        else: raise ExtractorError("no entries")
                    except Exception as e:
                        #self.report_warning(f"[get_entries][{futures[fut]}] error - {repr(e)}")
                        pass
                
                self.to_screen(results)
                if results:

                    if self.get_param('embed') or (self.get_param('extract_flat','') != 'in_playlist'):

                        iemv = self._get_extractor("MyVidster")
                        _list_urls_rss_search = {video: _url for _url, _videos in results.items() for video in _videos}
                        self.to_screen(_list_urls_rss_search )
                        with ThreadPoolExecutor(thread_name_prefix='ex_rss4pl') as ex:
                            futures = {ex.submit(iemv._get_entry, _url): _url for _url in _list_urls_rss_search}

                        entries = []
                        for fut in futures:
                            try:
                                _res = fut.result()
                                if _res:
                                    entries.append(_res)
                            except Exception as e:
                                logger.exception(f"[get_entries][{futures[fut]}] error - {repr(e)}")

                    else:
                     
                        entries = [{'_type':'url', 'url': video, 'ie_key': 'MyVidster', 'original_url': _url} for _url, _videos in results.items() for video in _videos]
                

                    if entries: 
                        
                        return self.playlist_result(entries, playlist_id=query.replace(' ', '_'), playlist_title='SearchMyVidsterRSS')

                 
                raise ExtractorError("no entries found")
                   
        
        except ExtractorError as e:
            self.to_screen(repr(e))
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(repr(e))

    def _real_initialize(self):
        
        with MyVidsterBaseIE._LOCK:
        
            super()._real_initialize()
            if not MyVidsterBaseIE._RSS:

                MyVidsterBaseIE._RSS = self.cache.load(self.ie_key(), 'rss')
                if not MyVidsterBaseIE._RSS:
                    self._get_rss()
                    if MyVidsterBaseIE._RSS:
                        self.cache.load(self.ie_key(), 'rss', MyVidsterBaseIE._RSS)            

    def _real_extract(self, url):
        
        self.report_extraction(url)

        return self.get_playlist_rss_search(url)
        


 