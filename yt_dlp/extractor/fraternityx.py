from __future__ import unicode_literals
from concurrent.futures import ThreadPoolExecutor

import re


from ..utils import (
    ExtractorError,
    sanitize_filename,
    js_to_json,
    try_get
)


import threading
import traceback
import sys

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


import json

from .commonwebdriver import SeleniumInfoExtractor


import html

from ratelimit import (
    sleep_and_retry,
    limits
)

from backoff import on_exception, constant

class FraternityXBaseIE(SeleniumInfoExtractor):
    _LOGIN_URL = "https://fratx.com/sign-in"
    _SITE_URL = "https://fratx.com"
    _BASE_URL_PL = "https://fratx.com/episodes/"

    _NETRC_MACHINE = 'fraternityx'

    _LOCK = threading.Lock()

    _COOKIES = None

    _MAX_PAGE = None
    
    @on_exception(constant, Exception, max_tries=5, interval=0.01)
    @sleep_and_retry
    @limits(calls=1, period=0.01)
    def _send_request_vs(self, url, headers=None):
        
        try:
 
            res = self._CLIENT.get(url, headers=headers)
            res.raise_for_status()
            return res
        
        except Exception as e:
            self.report_warning(f"[{url}] {repr(e)}")
            raise
    
    @on_exception(constant, Exception, max_tries=5, interval=0.01)
    @sleep_and_retry
    @limits(calls=1, period=0.01)
    def _send_request(self, url, headers=None, driver=None):
        
        try:
        
            if not driver:
                            
                res = self._CLIENT.get(url, headers=headers)
                res.raise_for_status()
                return res
            
            else:
                
                driver.execute_script("window.stop();")
                driver.get(url)
                
        except Exception as e:
            self.report_warning(f"[{url}] {repr(e)}")
            raise
        
    def _login(self, _driver):
        
        self._send_request(self._SITE_URL, driver=_driver)
        _title = _driver.title.upper()
        if "WARNING" in _title:
            self.to_screen("Adult consent")
            el_enter = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "a.enter-btn")))
            if not el_enter: raise ExtractorError("couldnt find adult consent button")
            _current_url = _driver.current_url
            el_enter.click()
            #el_enter.click() 
            self.wait_until(_driver, 60, ec.url_changes(_current_url))
        
        el_top = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "ul.inline-list")))
        if "MEMBERS" in el_top.get_attribute('innerText').upper():
            self.report_login()
            username, password = self._get_login_info()

            
            
            if not username or not password:
                self.raise_login_required(
                    'A valid %s account is needed to access this media.'
                    % self._NETRC_MACHINE)
            
            self._send_request(self._LOGIN_URL, driver=_driver)
            el_username = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#username")))
            el_password = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#password")))
            el_login = _driver.find_element(by=By.CSS_SELECTOR, value="button")
            if not el_username or not el_password or not el_login: raise ExtractorError("couldnt find text elements")
            el_username.send_keys(username)
            self.wait_until(_driver, 1)
            el_password.send_keys(password)
            self.wait_until(_driver, 1)
            #_title = _driver.title
            _current_url = _driver.current_url
            #self.to_screen(f"{_title}#{driver.current_url}")
            el_login.click()
            self.wait_until(_driver, 60, ec.url_changes(_current_url))
            count = 3
            while count > 0:
            
                if "episodes" in _driver.current_url:
                    el_top = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "ul.inline-list")))
                    if not "LOG OUT" in el_top.get_attribute('innerText').upper():
                        raise ExtractorError("Login failed")
                    else: break
                if "authorize2" in _driver.current_url:
                    el_email = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#email")))
                    el_lastname = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#last-name")))
                    el_enter = _driver.find_element(by=By.CSS_SELECTOR, value="button")
                    if not el_email or not el_lastname or not el_enter: raise ExtractorError("couldnt find text elements")
                    el_email.send_keys("a.tgarc@gmail.com")
                    self.wait_until(_driver, 1)
                    el_lastname.send_keys("Torres")
                    self.wait_until(_driver, 1)                
                    _current_url = _driver.current_url
                    el_enter.click()
                    self.wait_until(_driver, 60, ec.url_changes(_current_url))
                if "multiple-sessions" in _driver.current_url:                
                    self.to_screen("Abort existent session")
                    el_abort = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR,"button")))
                    if not el_abort: raise ExtractorError("couldnt find button to abort sessions")
                    _current_url = _driver.current_url
                    el_abort.click()
                    self.wait_until(_driver, 60, ec.url_changes(_current_url))
                
                count -= 1
                
            if count == 0: raise ExtractorError("couldnt log in")
        
        self.to_screen("Login OK")    
            

    def _init(self, ret_driver=True):
        
        if not FraternityXBaseIE._MASTER_INIT:
            super()._init()
        
        driver = None
        
        with FraternityXBaseIE._LOCK:            
                        
            if not FraternityXBaseIE._COOKIES:
                
                driver = self.get_driver(usequeue=True)
                
                try:
                    
                    self._login(driver)                
                    
                    FraternityXBaseIE._COOKIES = driver.get_cookies()
                    
                    for cookie in FraternityXBaseIE._COOKIES:
                        if (_name:=cookie['name']) != 'pp-accepted':
                            driver.delete_cookie(_name)
                    
                    self._send_request("https://fratx.com/episodes/1", driver=driver)
                    pag = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "pagination")))
                    if pag:
                        elnext = pag.find_elements(By.PARTIAL_LINK_TEXT, "NEXT")
                        totalpages = pag.find_elements(By.TAG_NAME, "a")
                        FraternityXBaseIE._MAX_PAGE = len(totalpages) - len(elnext)
                    else:
                        FraternityXBaseIE._MAX_PAGE = 50
                    
                
                except Exception as e:
                    self.to_screen("error when login")
                    #self.rm_driver(driver)
                    self.put_in_queue(driver)
                    raise
        
            for cookie in FraternityXBaseIE._COOKIES:
                self._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])

        if ret_driver:
            
            if not driver:
                                    
                driver = self.get_driver(usequeue=True)    
                self._send_request(self._SITE_URL, driver=driver)
                driver.add_cookie({'name': 'pp-accepted', 'value': 'true', 'domain': 'fratx.com'})
            
            return driver
        
        else:
            if driver: 
                self.put_in_queue(driver)

    def _extract_from_video_page(self, url, playlistid=None):        
        
        pre = f"[page_{playlistid}]" if playlistid else ""
        try:
            
            res = self._send_request(url)
            
            if not res: raise ExtractorError(f"{pre}[{url}] no res1")
            
            _title = try_get(re.findall(r'<h1>([^\<]+)<', html.unescape(res.text)), lambda x: x[0]) or url.split('/')[-1].replace("-","_").upper() 
           
            embedurl = try_get(re.findall(r'<iframe src=\"([^\"]+)\"', res.text), lambda x: x[0])
            if not embedurl:
                raise ExtractorError(f"{pre}[{url}] not embed url")

            res2 = self._send_request(embedurl)
            if not res2: raise ExtractorError(f"{pre}[{url}] no res2")
            
            tokenid = try_get(re.findall(r'globalSettings\s+\=\s+([^;]*);',res2.text), lambda x: json.loads(js_to_json(x[0]))['token'])
            
            if not tokenid: raise ExtractorError(f"{pre}[{url}] no token")

            videourl = "https://videostreamingsolutions.net/api:ov-embed/parseToken?token=" + tokenid
            
            headers = {
                "Referer" : embedurl,
                "Accept" : "*/*",
                "X-Requested-With" : "XMLHttpRequest"}

            res3 = self._send_request_vs(videourl, headers=headers)
            if not res3: raise ExtractorError(f"{pre}[{url}] no res3")
            info = res3.json()
            if not info: raise ExtractorError(f"{pre}[{url}] Can't find any JSON info")

            videoid = str(info.get('xdo',{}).get('video', {}).get('id', {}))
            manifestid = str(info.get('xdo',{}).get('video', {}).get('manifest_id', {}))
            manifesturl = "https://videostreamingsolutions.net/api:ov-embed/manifest/" + manifestid + "/manifest.m3u8"
            
            try:
                res4 = self._send_request_vs(manifesturl)
                if not res4 or not res4.content: raise ExtractorError(f"{pre}[{url}] no res4")
                m3u8_doc = (res4.content).decode('utf-8', 'replace')        
                formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                    m3u8_doc, manifesturl, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")

                if not formats_m3u8:
                    raise ExtractorError(f"[{url}] Can't find any M3U8 format")

                self._sort_formats(formats_m3u8)
        
                        
                return ({
                    "id": videoid,
                    "title": sanitize_filename(re.sub(r'([^_ -])-', r'\1_', _title.replace("'","").replace("&","AND")), restricted=True).upper(),
                    "original_url": url,
                    "formats": formats_m3u8
                })
            
            except Exception as e:
                raise ExtractorError(f"{pre}[{url}] Can't get M3U8 details: {repr(e)}")
        
        except Exception as e:
            raise

    def _extract_all_list(self):
        
        entries = []
        
        with ThreadPoolExecutor(thread_name_prefix="ExtrAllList", max_workers=10) as ex:
            futures = {ex.submit(self._extract_list, i, True): i for i in range(1, FraternityXAllPagesPlaylistIE._MAX_PAGE+1)}             
        
        for fut in futures:
            #self.to_screen(f'[page_{futures[fut]}] results')
            try:
                res = fut.result()                
                entries += res        
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.report_warning(f'[all_pages][page_{futures[fut]}] {repr(e)} \n{"!!".join(lines)}') 
                
        if not entries: raise ExtractorError(f"[all_pages] no videos found")
        
        return entries

    def _extract_list(self, plid, allpages=False):
 
        url_pl = f"{self._BASE_URL_PL}{plid}"
        
        self.report_extraction(url_pl)

        _driver = self._init()
        url_list = []
        entries = []
        try:
            self._send_request(url_pl, driver=_driver)
            el_listmedia = self.wait_until(_driver, 60, ec.presence_of_all_elements_located((By.CLASS_NAME, "description")))
            if not el_listmedia: raise ExtractorError("no info")
            
            for media in el_listmedia:
                el_tag = media.find_element(by=By.TAG_NAME, value="a")
                url_list.append(el_tag.get_attribute("href").replace("/index.php", ""))
        except Exception as e:
            self.to_screen(f'[page_{plid}] {repr(e)}')
        finally:
            self.put_in_queue(_driver)                    
        
        if not url_list: raise ExtractorError(f'[page_{plid}] no videos for playlist')
        
        self.to_screen(f'[page_{plid}] num videos {len(url_list)}')
       
        offset = (int(plid) - 1)*9 if allpages else 0
        with ThreadPoolExecutor(thread_name_prefix="ExtrList", max_workers=10) as ex:
            futures = {ex.submit(self._extract_from_video_page, _url, plid): (i, _url) for i, _url in enumerate(url_list)}
            
        
        for fut in futures:
            #self.to_screen(f'[page_{plid}] ({offset + futures[fut][0]}, {futures[fut][1]}')
            try:
                res = fut.result()
                res.update({'webpage_url': f"{self._BASE_URL_PL}{plid}"})
                entries.append(res)
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.report_warning(f'[page_{plid}] {repr(e)} \n{"!!".join(lines)}')  
        
        if not entries: raise ExtractorError(f"[page_{plid}] no videos found")
        return entries


class FraternityXIE(FraternityXBaseIE):
    IE_NAME = 'fraternityx'
    IE_DESC = 'fraternityx'
    _VALID_URL = r'https?://(?:www\.)?(?:fraternityx|fratx)\.com/episode/.*'

    def _real_initialize(self):
        self._init(ret_driver=False)
    
    def _real_extract(self, url):
        
        self.report_extraction(url)
        data = None
        try: 

            data = self._extract_from_video_page(url)
            
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))


        if not data:
            raise ExtractorError("Not any video format found")
        elif "error" in data['id']:
            raise ExtractorError(str(data['cause']))
        else:
            return(data)

class FraternityXOnePagePlaylistIE(FraternityXBaseIE):
    IE_NAME = 'fraternityx:onepage:playlist'
    IE_DESC = 'fraternityx:onepage:playlist'
    _VALID_URL = r"https?://(?:www\.)?(?:fraternityx|fratx)\.com/episodes/(?P<id>\d+)"

    def _real_initialize(self):
        self._init(ret_driver=False)
    
    def _real_extract(self, url):

        self.report_extraction(url)
        playlistid = re.search(self._VALID_URL, url).group("id")
        entries = None
        
        try:              

            if int(playlistid) > FraternityXOnePagePlaylistIE._MAX_PAGE:
                raise ExtractorError("episodes page not found 404")
            entries = self._extract_list(playlistid)  
       
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))

            
        if not entries: raise ExtractorError("no video list") 
        
        return self.playlist_result(entries, f"fraternityx:page_{playlistid}", f"fraternity:page_{playlistid}")

class FraternityXAllPagesPlaylistIE(FraternityXBaseIE):
    IE_NAME = 'fraternityx:allpagesplaylist'
    IE_DESC = 'fraternityx:allpagesplaylist'
    _VALID_URL = r"https?://(?:www\.)?(?:fraternityx|fratx)\.com/episodes/?$"
 
    def _real_initialize(self):
        self._init(ret_driver=False)
    
    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        entries = None
        
        try: 
            entries = self._extract_all_list()  
       
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))

            
        if not entries: raise ExtractorError("no video list")         
        
        return self.playlist_result(entries, f"fraternityx:AllPages", f"fraternityx:AllPages")