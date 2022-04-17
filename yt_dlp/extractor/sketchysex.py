# coding: utf-8
from __future__ import unicode_literals
from concurrent.futures import ThreadPoolExecutor

import re


from ..utils import (
    ExtractorError,
    sanitize_filename,
    try_get
)


import threading
import traceback
import sys

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_0_01
)



from backoff import on_exception, constant

import time

class waitforlogin():
    def __init__(self, username, password, logger):
        self.username = username
        self.password = password
        self.init = True
        self.logger = logger
    def __call__(self, driver):
        if self.init:
            el_username, el_password = driver.find_element(By.CLASS_NAME, "login_credentials").find_elements(By.TAG_NAME, "input")
            el_login = driver.find_element(By.CSS_SELECTOR, "input.submit_button")
            el_username.send_keys(self.username)
            time.sleep(1)
            el_password.send_keys(self.password)
            time.sleep(1)
            el_login.click()
            self.init = False
            return False            
        
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
            el_abort = driver.find_element(By.CSS_SELECTOR,"button.std-button")
            el_abort.click()
            return False
        
        el_top = driver.find_element(By.CSS_SELECTOR,  "ul")
        if not "LOG OUT" in el_top.get_attribute('innerText').upper():
            return({"error": "Login failed"})
        else: return("OK")
            

class SketchySexBaseIE(SeleniumInfoExtractor):
    _LOGIN_URL = "https://sketchysex.com/sign-in"
    _SITE_URL = "https://sketchysex.com"
    _BASE_URL_PL = "https://members.sketchysex.com/index.php?page="

    _NETRC_MACHINE = 'sketchysex'

    _LOCK = threading.Lock()

    _COOKIES = None

    _MAX_PAGE = None
    
    _TRAD_FROM_NEW_TO_OLD = {'19SX': '5433', '20SX': '5528', '21SX': '5498', '22SX': '5587', '23SX': '5472', '24SX': '5563', '25SX': '5511', '26SX': '5617', '27SX': '5637', '28SX': '5735', '29SX': '5758', '30SX': '5709', '31SX': '5684', '32SX': '5788', '33SX': '5821', '34SX': '5662', '36SX': '5910', '37SX': '5853', '38SX': '5948', '39SX': '5968', '40SX': '5998', '41SX': '6028', '42SX': '6063', '43SX': '6098', '44SX': '6127', '45SX': '6152', '46SX': '6200', '47SX': '6172', '48SX': '6288', '49SX': '6263', '50SX': '6231', '51SX': '6321', '52SX': '6370', '53SX': '6340', '54SX': '6420', '55SX': '6392', '56SX': '6449', '57SX': '6500', '58SX': '6472', '59SX': '6555', '60SX': '6591', '61SX': '6530', '62SX': '6824', '63SX': '6845', '64SX': '6889', '65SX': '6677', '66SX': '6754', '67SX': '6928', '68SX': '6977', '69SX': '856', '70SX': '1788', '71SX': '1796', '72SX': '1803', '73SX': '2900', '74SX': '2893', '75SX': '1827', '76SX': '469', '77SX': '1131', '78SX': '515', '79SX': '798', '80SX': '3104', '81SX': '2781', '82SX': '4359', '83SX': '2047', '84SX': '3256', '85SX': '4588', '86SX': '5164', '87SX': '5224', '88SX': '5207', '89SX': '5277', '90SX': '5402', '91SX': '5303', '92SX': '5367', '93SX': '882', '94SX': '946', '96SX': '1833', '97SX': '1520', '98SX': '654', '100SX': '1256', '143SX': '7000', '144SX': '7033', '145SX': '7079', '35SX': '5882'} 
    
    @on_exception(constant, Exception, max_tries=5, interval=0.01)
    @limiter_0_01.ratelimit("sketchysex1", delay=True)
    def _send_request_vs(self, url, headers=None):
        
        try:
 
            res = SketchySexBaseIE._CLIENT.get(url, headers=headers)
            res.raise_for_status()
            return res
        
        except Exception as e:
            self.report_warning(f"[{url}] {repr(e)}")
            raise
    
    @on_exception(constant, Exception, max_tries=5, interval=0.01)
    @limiter_0_01.ratelimit("sketchysex2", delay=True)
    def _send_request(self, url, headers=None, driver=None):
        
        try:
        
            if not driver:
                            
                res = SketchySexBaseIE._CLIENT.get(url, headers=headers)
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
        if _driver.find_elements(By.ID, "warningpopup"):
            self.to_screen("Adult consent")
            el_enter = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "a.btn-enter.s_enter")))
            if not el_enter: raise ExtractorError("couldnt find adult consent button")
            
            el_enter.click()
            self.wait_until(_driver, 5)
            try:
                el_enter.click() #por ublock 
            except Exception:
                pass
            
        
        el_top = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "ul")))
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
        
        
        with SketchySexBaseIE._LOCK:            
                        
            if not SketchySexBaseIE._COOKIES:
                
                driver = self.get_driver(usequeue=True)
                #driver = self.get_driver(noheadless=True)
                
                try:
                    
                    self._login(driver)                
                    
                    SketchySexBaseIE._COOKIES = driver.get_cookies()
                    
                    
                    for cookie in SketchySexBaseIE._COOKIES:
                        SketchySexBaseIE._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])                    
                        
                    
                    self._send_request("https://members.sketchysex.com", driver=driver)
                    el_pag = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "pagination")))
                    if el_pag:
                        elnext = el_pag.find_elements(By.PARTIAL_LINK_TEXT, "NEXT")
                        totalpages = el_pag.find_elements(By.TAG_NAME, "a")
                        SketchySexBaseIE._MAX_PAGE = len(totalpages) - len(elnext)
                    else: 
                        SketchySexBaseIE._MAX_PAGE = 50
                
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
            
            if not res: raise ExtractorError(f"{pre}[{url}] no res")
            
            title = try_get(re.findall(r'class="name"> <span>([^<]+)<', res.text), lambda x: x[0])
            
            videoid = try_get(re.findall(r'video id="video_([^"]+)"', res.text), lambda x: x[0] + "SX")
            
            if videoid in SketchySexBaseIE._TRAD_FROM_NEW_TO_OLD: 
                videoid = SketchySexBaseIE._TRAD_FROM_NEW_TO_OLD[videoid]
           
            manifesturl = try_get(re.findall(r'source src="([^"]+)"', res.text), lambda x: x[0])

            if not manifesturl: raise ExtractorError(f"{pre}[{url}] no manifesturl")
                        
            headers = {
                "Referer" : "https://members.sketchysex.com/",
                "Accept" : "*/*",
            }

            
            try:
                res2 = self._send_request_vs(manifesturl, headers=headers)
                if not res2 or not res2.content: raise ExtractorError(f"{pre}[{url}] no res2")
                m3u8_doc = (res2.content).decode('utf-8', 'replace')        
                formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                    m3u8_doc, manifesturl, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")

                if not formats_m3u8:
                    raise ExtractorError(f"[{url}] Can't find any M3U8 format")

                self._sort_formats(formats_m3u8)
        
                        
                return ({
                    "id": videoid,
                    "title": sanitize_filename(re.sub(r'([^_ -])-', r'\1_', title.replace("'","").replace("&","AND")), restricted=True).upper(),
                    "original_url": url,
                    "formats": formats_m3u8
                })
            
            except Exception as e:
                raise ExtractorError(f"{pre}[{url}] Can't get M3U8 details: {repr(e)}")
        
        except Exception as e:
            raise

    def _extract_all_list(self):
        
        entries = []
        
        with ThreadPoolExecutor(thread_name_prefix="ExtrListAll", max_workers=10) as ex:
            futures = {ex.submit(self._extract_list, i, True): i for i in range(1, SketchySexAllPagesPlaylistIE._MAX_PAGE+1)}             
        
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
        self.to_screen(url_pl)
        
        if allpages:
            self.report_extraction(url_pl)

        entries = []
        
        try:
            res = self._send_request(url_pl, headers={'Referer': 'https://members.sketchysex.com'})
            #self.to_screen(res.text)
            url_list = try_get(re.findall(r'<a href="gallery\.php\?id=([^"]+)"', res.text), lambda x: ["https://members.sketchysex.com/gallery.php?id=" + el for el in x])

            
        except Exception as e:
            self.to_screen(f'[page_{plid}] {repr(e)}')
                        
        
        if not url_list: raise ExtractorError(f'[page_{plid}] no videos for playlist')
        
        self.to_screen(f'[page_{plid}] num videos {len(url_list)}')
       
        with ThreadPoolExecutor(thread_name_prefix="ExtrList", max_workers=10) as ex:
            futures = {ex.submit(self._extract_from_video_page, _url, plid): (i, _url) for i, _url in enumerate(url_list)}
            
        
        for fut in futures:
            try:
                res = fut.result()
                res.update({'webpage_url': f"{self._BASE_URL_PL}{plid}"})
                entries.append(res)
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.report_warning(f'[page_{plid}] {repr(e)} \n{"!!".join(lines)}')  
        
        if not entries: raise ExtractorError(f"[page_{plid}] no videos found")
        return entries



class SketchySexIE(SketchySexBaseIE):
    IE_NAME = 'sketchysex'
    IE_DESC = 'sketchysex'
    _VALID_URL = r'https://members\.sketchysex\.com/gallery\.php.*'

    def _real_initialize(self):
       
        super()._real_initialize()
    
    def _real_extract(self, url):
        
        self.report_extraction(url)
        data = None
        try: 

            data = self._extract_from_video_page(url)
        
        except ExtractorError:
            raise    
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e))


        if not data:
            raise ExtractorError("Not any video format found")
        elif "error" in data['id']:
            raise ExtractorError(str(data['cause']))
        else:
            return(data)

class SketchySexOnePagePlaylistIE(SketchySexBaseIE):
    IE_NAME = 'sketchysex:playlist'
    IE_DESC = 'sketchysex:playlist'
    _VALID_URL = r"https://members\.sketchysex\.com/index\.php\?page=(?P<id>\d+)"

    def _real_initialize(self):
        super()._real_initialize()
       
    
    def _real_extract(self, url):

        self.report_extraction(url)
        playlistid = re.search(self._VALID_URL, url).group("id")
        entries = None
        
        try:              

            if int(playlistid) > SketchySexOnePagePlaylistIE._MAX_PAGE:
                raise ExtractorError("episodes page not found 404")
            entries = self._extract_list(playlistid)  
       
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))

            
        if not entries: raise ExtractorError("no video list") 
        
        return self.playlist_result(entries, f"sketchysex:page_{playlistid}", f"sketchysex:page_{playlistid}")

class SketchySexAllPagesPlaylistIE(SketchySexBaseIE):
    IE_NAME = 'sketchysex:allpages:playlist'
    IE_DESC = 'sketchysex:allpages:playlist'
    _VALID_URL = r"https://members\.sketchysex\.com/index.php\?page=all"
 
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
        
        return self.playlist_result(entries, f"sketchysex:AllPages", f"sketchysex:AllPages")