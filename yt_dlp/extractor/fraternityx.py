from __future__ import unicode_literals
from concurrent.futures import ThreadPoolExecutor

import re


from ..utils import (
    ExtractorError,
    sanitize_filename,
    js_to_json
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
    #_LOGOUT_URL = "https://fraternityx.com/sign-out"
    #_MULT_URL = "https://fraternityx.com/multiple-sessions"
    #_ABORT_URL = "https://fraternityx.com/multiple-sessions/abort"
    #_AUTH_URL = "https://fraternityx.com/authorize2"
    _BASE_URL_PL = "https://fratx.com/episodes/"

    _NETRC_MACHINE = 'fraternityx'

    _LOCK = threading.Lock()
    
    
    _COOKIES = None

    _MAX_PAGE = None
    
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @sleep_and_retry
    @limits(calls=1, period=0.1)
    def _send_request(self, url, headers=None):
        
        res = self._CLIENT.get(url, headers=headers)
        res.raise_for_status()
        return res
        
        

    def _login(self, _driver):
        
        _driver.get(self._SITE_URL)
        _title = _driver.title.upper()
        #self.to_screen(_title)
        if "WARNING" in _title:
            self.to_screen("Adult consent")
            el_enter = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "a.enter-btn")))
            if not el_enter: raise ExtractorError("couldnt find adult consent button")
            _current_url = _driver.current_url
            el_enter.click()
            self.wait_until(_driver, 60, ec.url_changes(_current_url))
        
        el_top = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "ul.inline-list")))
        if "MEMBERS" in el_top.get_attribute('innerText').upper():
            self.report_login()
            username, password = self._get_login_info()

            
            
            if not username or not password:
                self.raise_login_required(
                    'A valid %s account is needed to access this media.'
                    % self._NETRC_MACHINE)
            
            _driver.get(self._LOGIN_URL)
            el_username = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#username")))
            el_password = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#password")))
            el_login = _driver.find_element(by=By.CSS_SELECTOR, value="button")
            if not el_username or not el_password or not el_login: raise ExtractorError("couldnt find text elements")
            el_username.send_keys(username)
            self.wait_until(_driver, 3, ec.title_is("DUMMYFORWAIT"))
            el_password.send_keys(password)
            self.wait_until(_driver, 3, ec.title_is("DUMMYFORWAIT"))
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
                    self.wait_until(_driver, 3, ec.title_is("DUMMYFORWAIT"))
                    el_lastname.send_keys("Torres")
                    self.wait_until(_driver, 3, ec.title_is("DUMMYFORWAIT"))                
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
                    
                
                except Exception as e:
                    self.to_screen("error when login")
                    #self.rm_driver(driver)
                    SeleniumInfoExtractor._QUEUE.put_nowait(driver)
                    raise
                
            for cookie in FraternityXBaseIE._COOKIES:
                self._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
                
        if ret_driver:
            
            if not driver:
                                    
                driver = self.get_driver(usequeue=True)    
                driver.get(self._SITE_URL)
                driver.add_cookie({'name': 'pp-accepted', 'value': 'true', 'domain': 'fratx.com'})
                
            if not FraternityXBaseIE._MAX_PAGE:                
                driver.get("https://fratx.com/episodes/1")
                pag = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "pagination")))
                if pag:
                    elnext = pag.find_elements(By.PARTIAL_LINK_TEXT, "NEXT")
                    totalpages = pag.find_elements(By.TAG_NAME, "a")
                    FraternityXBaseIE._MAX_PAGE = len(totalpages) - len(elnext)
            
            return driver
        
        else:
            if driver: 
                #self.rm_driver(driver)
                SeleniumInfoExtractor._QUEUE.put_nowait(driver)

    def _extract_from_page(self, url):        
        
 
        try:
            
            res = self._send_request(url)
            _title = None
            mobj = re.findall(r'<h1>([^\<]+)<', html.unescape(res.text))        
            if mobj:
                _title = mobj[0]
            
            if not _title: _title = url.split('/')[-1].replace("-","_").upper() 
            #self.to_screen(_title)
            mobj = re.findall(r'<iframe src=\"([^\"]+)\"', res.text)
            if mobj:
                embedurl = mobj[0]
            else: raise ExtractorError("not embed url")
            
            try:
                res2 = self._send_request(embedurl)
                mobj = re.findall(r'globalSettings\s+\=\s+([^;]*);',res2.text)
            except Exception:
                mobj = None
            if not mobj: raise ExtractorError("no token")
            _data_dict = json.loads(js_to_json(mobj[0]))
            tokenid = _data_dict.get('token')
            if not tokenid: raise ExtractorError("no token")            
            #self.to_screen(f"tokenid:{tokenid}") 
            videourl = "https://videostreamingsolutions.net/api:ov-embed/parseToken?token=" + tokenid
            #self.to_screen(videourl)
            headers = dict()
            headers.update({
                "Referer" : embedurl,
                "Accept" : "*/*",
                "X-Requested-With" : "XMLHttpRequest"})
            
            try:
                res3 = self._send_request(videourl, headers=headers)
                info = res3.json()
            except Exception:
                info = None
            if not info: raise ExtractorError("Can't find any JSON info")

            #print(info)
            videoid = str(info.get('xdo',{}).get('video', {}).get('id', {}))
            manifestid = str(info.get('xdo',{}).get('video', {}).get('manifest_id', {}))
            manifesturl = "https://videostreamingsolutions.net/api:ov-embed/manifest/" + manifestid + "/manifest.m3u8"
            
            try:
                res4 = self._send_request(manifesturl)
                if not res4 or not res4.content: raise ExtractorError("Cant get m3u8 doc")
                m3u8_doc = (res4.content).decode('utf-8', 'replace')        
                formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                    m3u8_doc, manifesturl, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")

                if not formats_m3u8:
                    raise ExtractorError("Can't find any M3U8 format")

                self._sort_formats(formats_m3u8)
        
                        
                return ({
                    "id": videoid,
                    "title": sanitize_filename(re.sub(r'([^_ -])-', r'\1_', _title.replace("'","").replace("&","AND")), restricted=True).upper(),
                    "original_url": url,
                    "formats": formats_m3u8
                })
            except Exception as e:
                raise ExtractorError(f"Can't get M3U8 details: {repr(e)}")
        
        except Exception as e:
            raise


    def _extract_list(self, _driver, playlistid, nextpages):
        
        entries = []

        i = 0

        while True:

            url_pl = f"{self._BASE_URL_PL}{int(playlistid) + i}"

            #self.to_screen(url_pl)
            with FraternityXBaseIE._LOCK:
                _driver.get(url_pl)
            el_listmedia = self.wait_until(_driver, 60, ec.presence_of_all_elements_located((By.CLASS_NAME, "description")))
            if not el_listmedia: raise ExtractorError("no info")
            futures = []
            _num_workers = min(self._downloader.params.get('winit', 5), len(el_listmedia))
            with ThreadPoolExecutor(max_workers=_num_workers) as ex:
                for media in el_listmedia:
                    el_tag = media.find_element(by=By.TAG_NAME, value="a")
                    _url = el_tag.get_attribute("href").replace("/index.php", "")
                    futures.append(ex.submit(self._extract_from_page, _url))

            
            for d in futures:
                try:
                    entries.append(d.result())
                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
                    raise ExtractorError(str(e)) from e        
            
            
            if not nextpages: break
            
            if "NEXT" in _driver.page_source:
                i += 1
            else:
                break

        if not entries: raise ExtractorError("no videos found")

        return entries


class FraternityXIE(FraternityXBaseIE):
    IE_NAME = 'fraternityx'
    IE_DESC = 'fraternityx'
    _VALID_URL = r'https?://(?:www\.)?(?:fraternityx|fratx)\.com/episode/.*'

    def _real_extract(self, url):
        
        self.report_extraction(url)
        data = None
        try:            
            
            self._init(ret_driver=False)
            data = self._extract_from_page(url)
                 
            
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


    def _real_extract(self, url):

        self.report_extraction(url)
        playlistid = re.search(self._VALID_URL, url).group("id")
        entries = None
        
        try:              
            
            
            driver = self._init()
            if int(playlistid) > FraternityXOnePagePlaylistIE._MAX_PAGE:
                raise ExtractorError("episodes page not found 404")
            entries = self._extract_list(driver, playlistid, nextpages=False)  
       
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            #self.rm_driver(driver)
            SeleniumInfoExtractor._QUEUE.put_nowait(driver)
            
        if not entries: raise ExtractorError("no video list") 
        
        return self.playlist_result(entries, f"fraternityx:page_{playlistid}", f"fraternity:page_{playlistid}")
    
class FraternityXAllPagesPlaylistIE(FraternityXBaseIE):
    IE_NAME = 'fraternityx:allpagesplaylist'
    IE_DESC = 'fraternityx:allpagesplaylist'
    _VALID_URL = r"https?://(?:www\.)?(?:fraternityx|fratx)\.com/episodes/?$"
   
 
    def _real_extract(self, url):
        
        entries = None
        
        try:              


            driver = self._init()
            
            entries = self._extract_list(driver, 1, nextpages=True)  
        
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))
        finally:
            #self.rm_driver(driver)
            SeleniumInfoExtractor._QUEUE.put_nowait(driver)
            
        if not entries: raise ExtractorError("no video list") 
        
        return self.playlist_result(entries, f"fraternityx:AllPages", f"fraternityx:AllPages")