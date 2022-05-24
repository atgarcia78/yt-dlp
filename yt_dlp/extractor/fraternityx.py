from __future__ import unicode_literals

import html
import json
import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

import httpx
from backoff import constant, on_exception

from ..utils import ExtractorError, js_to_json, sanitize_filename, try_get
from .commonwebdriver import SeleniumInfoExtractor, limiter_0_01, By, ec


class waitforlogin():
    def __init__(self, username, password, logger):
        self.username = username
        self.password = password
        self.init = True
        self.logger = logger
    def __call__(self, driver):
        if self.init:
            el_username = driver.find_element(By.CSS_SELECTOR, "input#username")
            el_password = driver.find_element(By.CSS_SELECTOR, "input#password")
            el_login = driver.find_element(By.CSS_SELECTOR, "button")
            el_username.send_keys(self.username)
            time.sleep(1)
            el_password.send_keys(self.password)
            time.sleep(1)
            el_login.click()
            self.init = False
            return False            
        if "episodes" in driver.current_url:
            el_top = driver.find_element(By.CSS_SELECTOR,  "ul.inline-list")
            if not "LOG OUT" in el_top.get_attribute('innerText').upper():
                return({"error": "Login failed"})
            else: return("OK")
        if "authorize2" in driver.current_url:
            self.logger("Authorize2")
            el_email = driver.find_element(By.CSS_SELECTOR, "input#email")
            el_lastname = driver.find_element(By.CSS_SELECTOR, "input#last-name")
            el_enter = driver.find_element(By.CSS_SELECTOR, "button")
            el_email.send_keys("a.tgarc@gmail.com")
            time.sleep(1)
            el_lastname.send_keys("Torres")
            time.sleep(1)
            el_enter.click()
            return False
        if "multiple-sessions" in driver.current_url:                
            self.logger("Abort existent session")
            el_abort = driver.find_element(By.CSS_SELECTOR,"button.yellow-btn")
            el_abort.click()
            return False

class FraternityXBaseIE(SeleniumInfoExtractor):
    _LOGIN_URL = "https://fratx.com/sign-in"
    _SITE_URL = "https://fratx.com"
    _BASE_URL_PL = "https://fratx.com/episodes/"

    _NETRC_MACHINE = 'fraternityx'

    _LOCK = threading.Lock()

    _COOKIES = None

    _MAX_PAGE = None
    
    @on_exception(constant, Exception, max_tries=5, interval=0.01)
    @limiter_0_01.ratelimit("fratx1", delay=True)
    def _send_request_vs(self, url, headers=None):
        
        try:
 
            res = FraternityXBaseIE._CLIENT.get(url, headers=headers)
            res.raise_for_status()
            return res
        
        except Exception as e:
            self.report_warning(f"[{url}] {repr(e)}")
            raise
    
    @on_exception(constant, Exception, max_tries=5, interval=0.01)
    @limiter_0_01.ratelimit("fratx2", delay=True)
    def _send_request(self, url, headers=None, driver=None):
        
        try:
        
            if not driver:
                            
                res = FraternityXBaseIE._CLIENT.get(url, headers=headers)
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
            res = self.wait_until(_driver, 60, waitforlogin(username, password, self.to_screen))
            if res != "OK": raise ExtractorError("couldnt log in")
        
        self.to_screen("Login OK")    
            

    def _real_initialize(self):
        super()._real_initialize()
        
        
        with FraternityXBaseIE._LOCK:            
                        
            if not FraternityXBaseIE._COOKIES:
                
                driver = self.get_driver(usequeue=True)
                
                try:
                    
                    self._login(driver)                
                    
                    FraternityXBaseIE._COOKIES = driver.get_cookies()
                    
                    for cookie in FraternityXBaseIE._COOKIES:
                        FraternityXBaseIE._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
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
                    raise
                finally:
                    self.put_in_queue(driver)
    



    def _extract_from_video_page(self, url, playlistid=None):        
        
        pre = f"[page_{playlistid}]" if playlistid else ""
        try:
            
            res = self._send_request(url)
            
            if not res: raise ExtractorError(f"{pre}[{url}] no res1")
            
            _title = try_get(re.findall(r'<h1>([^\<]+)<', html.unescape(res.text)), lambda x: x[0]) or url.split('/')[-1].replace("-"," ").upper()
            
            def replTxt(match):
                repl_dict = {"+": "PLUS", "&": "AND", "'": "", "-": ""}
                if match:
                    _res = try_get(match.groups(), lambda x: (x[0] or "", x[2] or "")) or ("","")
                    _key = try_get(match.groups(), lambda x: x[1]) or 'dummmy'
                    if (_key in repl_dict):
                        if _key not in ["'","-"]:
                            _txt = [_res[0] + ' ' if _res[0] not in [' ',''] else _res[0], ' ' + _res[1] if _res[1] not in [' ',''] else _res[1]]
                        elif _key in ["-"]:
                            _txt = [_res[0], ' ' + _res[1] if _res[1] not in [' ',''] and _res[0] not in [' ',''] else _res[1]]
                            if _txt== [' ', ' ']: _txt = [' ','']
                        elif _key in ["'"]:
                            if _res[1] == 'S':
                                _txt = [_res[0], 'S']
                            else:
                                _txt = [_res[0], ' ' + _res[1] if _res[1] not in [' ',''] and _res[0] not in [' ',''] else _res[1]]
                            if _txt == [' ', ' ']: _res = [' ','']


                    return f"{_txt[0]}{repl_dict[_key]}{_txt[1]}"


            _title = re.sub(r'([ ]+)', ' ', re.sub(r'(.)?([\+,\&,\',-])(.)?', replTxt, _title))
           
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
                    "title": sanitize_filename(_title, restricted=True).upper(),
                    "webpage_url": url,
                    "formats": formats_m3u8
                })
            
            except Exception as e:
                raise ExtractorError(f"{pre}[{url}] Can't get M3U8 details: {repr(e)}")
        
        except Exception as e:
            raise

    def _extract_all_list(self):
        
        entries = []
        
        with ThreadPoolExecutor(thread_name_prefix="ExtrListAll", max_workers=10) as ex:
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
        
        if allpages:
            self.report_extraction(url_pl)

        url_list = []
        entries = []
        _config = SeleniumInfoExtractor._CLIENT_CONFIG.copy()
        client = httpx.Client(timeout=_config['timeout'], limits=_config['limits'], headers=_config['headers'], follow_redirects=_config['follow_redirects'], verify=_config['verify'])
        client.cookies.set(name="pp-accepted", value="true", domain="fratx.com")
        try:
            res = client.get(url_pl)
            url_list = try_get(re.findall(r'"description"><ahref="([^"]+)"', res.text.replace("\n", "").replace(" ", "")), lambda x: ["https://fratx.com" + el for el in x])

        except Exception as e:
            self.to_screen(f'[page_{plid}] {repr(e)}')
        finally:
            client.close()
        
        if not url_list: raise ExtractorError(f'[page_{plid}] no videos for playlist')
        
        self.to_screen(f'[page_{plid}] num videos {len(url_list)}')
       
        with ThreadPoolExecutor(thread_name_prefix="ExtrList", max_workers=10) as ex:
            futures = {ex.submit(self._extract_from_video_page, _url, plid): (i, _url) for i, _url in enumerate(url_list)}
            
        
        for fut in futures:
            try:
                res = fut.result()
                res.update({'original_url': f"{self._BASE_URL_PL}{plid}"})
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
        super()._real_initialize()
    
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
        super()._real_initialize()
      
    
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
        super()._real_initialize()
       
    
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
