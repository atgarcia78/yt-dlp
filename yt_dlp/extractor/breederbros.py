# coding: utf-8
from __future__ import unicode_literals

import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_1, By, ec

from queue import Empty, Queue


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
            

class BreederBrosBaseIE(SeleniumInfoExtractor):
    _LOGIN_URL = "https://members.breederbros.com"
    _SITE_URL = "https://www.breederbros.com"
    _BASE_URL_PL = "https://members.breederbros.com/index.php?page="

    _NETRC_MACHINE = 'fraternityx'    

    _MLOCK = threading.Lock() 
   
    _MAX_PAGE = None
    
    _server = None
   
    _numdriver = 0
    
    _LOCALQ = Queue()
    
    
    @dec_on_exception
    @limiter_1.ratelimit("breederbros", delay=True)
    def _send_request(self, url, headers=None, driver=None):
        
        try:
        
            if not driver:
                            
                res = SeleniumInfoExtractor._CLIENT.get(url, headers=headers)
                res.raise_for_status()
                return res
            
            else:
                
                driver.execute_script("window.stop();")
                driver.get(url)
                
        except Exception as e:
            self.report_warning(f"[{url}] {repr(e)}")
            raise
        
    def _login(self, _driver):
        
            
        self._send_request(self._LOGIN_URL, driver=_driver)
        
        el_top = self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "ul")))
        if "MEMBERS" in el_top.get_attribute('innerText').upper():
            self.report_login()
            username, password = self._get_login_info()

            if not username or not password:
                self.raise_login_required(
                    'A valid %s account is needed to access this media.'
                    % self._NETRC_MACHINE)
            
           # self._send_request(self._LOGIN_URL, driver=_driver)
            res = self.wait_until(_driver, 60, waitforlogin(username, password, self.to_screen))
            if res != "OK": raise ExtractorError("couldnt log in")
        
        self.to_screen("Login OK")    
            

    def _real_initialize(self):
        super()._real_initialize()        
        
        with BreederBrosBaseIE._MLOCK:
            
            if not BreederBrosBaseIE._server:
                BreederBrosBaseIE._server, _server_port = self.start_browsermob(f"breederbros")
                            
            if not BreederBrosBaseIE._MAX_PAGE:
                
                try:
                    
                    webpage = try_get(self._send_request("https://www.breederbros.com"), lambda x: x.text.replace("\n","").replace("\t","")) 
                    BreederBrosBaseIE._MAX_PAGE  = try_get(re.findall(r'>(\d+)</a></li></ul></div><!-- pagination-center -->', webpage), lambda x: int(x[0])) or 50
                
                except Exception as e:
                    self.to_screen("error when init")
        

    def scan_for_request(self, _harproxy, _ref, _link):

        _started = time.monotonic()
        #_harproxy.wait_for_traffic_to_stop(5000, 30000)
        while(True):
            _har  = _harproxy.har
            #self.write_debug(_har)
            for entry in _har['log']['entries']:
                if entry['pageref'] == _ref:
                    if _link in (entry['request']['url']):
                        return entry.get('response', {}).get('content', {}).get('text')
            if (_t:=(time.monotonic() - _started)) >= 60:
                return
            else:
                time.sleep(0.5)
            
  

    def _new_proxy_and_driver(self):
        with BreederBrosBaseIE._MLOCK:
            if BreederBrosBaseIE._numdriver < 6:
                _port = int(BreederBrosBaseIE._server.port) + (BreederBrosBaseIE._numdriver + 1)*100
                BreederBrosBaseIE._numdriver += 1
            else: return
        _host = 'localhost' 
        _harproxy = BreederBrosBaseIE._server.create_proxy({'port' : _port})
        self.to_screen(f"proxy started at port {_port}")
        _driver  = self.get_driver(host=_host, port=_port)
        self._login(_driver)
        return (_driver, _harproxy)

    def _extract_from_video_page(self, url, pid=None):        
        
        try:
            _driver, _harproxy = BreederBrosBaseIE._LOCALQ.get(block=False)        
        except Empty:             
            _driver, _harproxy = try_get(self._new_proxy_and_driver(), lambda x: (x[0], x[1])) or BreederBrosBaseIE._LOCALQ.get(block=True, timeout=600)
        
 
        pre = f"[page_{pid}]" if pid else ""
                            
        try:
            self.to_screen(f"{pre}[{url}]")
            videoid = try_get(re.search(BreederBrosIE._VALID_URL, url), lambda x: f"{x.group('id')}BB")
            
            _harproxy.new_har(options={'captureHeaders': True, 'captureContent': True}, ref=f"har_{videoid}", title=f"har_{videoid}")            
            
            self._send_request(url, driver=_driver)
            
            def replTxt(match):
                repl_dict = {"+": "PLUS", "&": "AND", "'": "", "-": "", ",": ""}
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
            
            title = re.sub(r'([ ]+)', ' ', re.sub(r'(.)?([\+\&\'-,])(.)?', replTxt, try_get(self.wait_until(_driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "div.name"))), lambda x: x.text)))
            
            m3u8_doc = self.scan_for_request(_harproxy, f"har_{videoid}", f".m3u8")           
                            

            _url = try_get(re.findall(r"(https://.*)", m3u8_doc), lambda x: x[0]) 
            if _url:
                murl, params = _url.split('?')
                manifesturl = murl.rsplit('/',1)[0] + '/playlist.m3u8?' + params
                self.write_debug(manifesturl)
                formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                    m3u8_doc, manifesturl, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")
            
                if not formats_m3u8:
                    raise ExtractorError(f"[{url}] Can't find any M3U8 format")

                self._sort_formats(formats_m3u8)
                
                headers = {            
                    "Accept" : "*/*",
                    "Referer" : url                
                }
                
                for _format in formats_m3u8:
                    if (_head:=_format.get('http_headers')):
                        _head.update(headers)
                    else:
                        _format.update({'http_headers': headers})               
                        
                return ({
                    "id": videoid,
                    "title": sanitize_filename(title, restricted=True).upper(),
                    "webpage_url": url,
                    "formats": formats_m3u8
                })            

        
        except ExtractorError as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            if pid:
                BreederBrosBaseIE._LOCALQ.put_nowait((_driver, _harproxy))
            else:
                _harproxy.close()
                BreederBrosBaseIE._server.stop()
                self.rm_driver(_driver)
            


    def _extract_all_list(self):
        
        entries = []
        try:
            
            with ThreadPoolExecutor(thread_name_prefix="ExtrListAll", max_workers=10) as ex:
                futures = {ex.submit(self._extract_list, i, allpages=True): i for i in range(1, BreederBrosAllPagesPlaylistIE._MAX_PAGE+1)}             
            
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
        finally:
            try:
                [(self.rm_driver(_driver), _harproxy.close()) for (_driver, _harproxy) in list(BreederBrosBaseIE._LOCALQ.queue)]
            except Exception:
                pass
            try:
                BreederBrosBaseIE._server.stop()
            except Exception:
                pass
        
        

    def _extract_list(self, plid, allpages=False):
 
        if plid == '1': url_pl = "https://members.breederbros.com/index.php"
        url_pl = f"{self._BASE_URL_PL}{plid}"
        self.to_screen(url_pl)
        
        if allpages:
            self.report_extraction(url_pl)

        entries = []
        
        try:

            res = self._send_request(url_pl.replace('members', 'www'))

            url_list = try_get(re.findall(r'description">\s+<a href="trailer\.php\?id=(\d+)"', res.text.replace("\n", "").replace("\t", "")), lambda x: ["https://members.breederbros.com/gallery.php?id=" + el for el in x])

            self.to_screen(f'[page_{plid}] num videos {len(url_list)}')
            
        except Exception as e:
            self.to_screen(f'[page_{plid}] {repr(e)}')

                        
        
        if not url_list: raise ExtractorError(f'[page_{plid}] no videos for playlist')
        
        try:
       
            with ThreadPoolExecutor(thread_name_prefix="ExtrList", max_workers=10) as ex:
                futures = {ex.submit(self._extract_from_video_page, _url, pid=plid): (i, _url) for i, _url in enumerate(url_list)}
                
            
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
        finally:
            if not allpages:
                
                try:
                    [(self.rm_driver(_driver), _harproxy.close()) for (_driver, _harproxy) in list(BreederBrosBaseIE._LOCALQ.queue)]
                except Exception:
                    pass
                try:
                    BreederBrosBaseIE._server.stop()
                except Exception:
                    pass
                



class BreederBrosIE(BreederBrosBaseIE):
    IE_NAME = 'breederbros'
    IE_DESC = 'breederbros'
    _VALID_URL = r'https://members\.breederbros\.com/gallery\.php\?id=(?P<id>\d+)'

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

class BreederBrosOnePagePlaylistIE(BreederBrosBaseIE):
    IE_NAME = 'breederbros:playlist'
    IE_DESC = 'breederbros:playlist'
    _VALID_URL = r"https://members\.breederbros\.com/index\.php(?:\?page=(?P<id>\d+)|$)"

    def _real_initialize(self):
        super()._real_initialize()
       
    
    def _real_extract(self, url):

        self.report_extraction(url)
        playlistid = re.search(self._VALID_URL, url).group("id") or '1'
        entries = None
        
        try:              

            if int(playlistid) > BreederBrosOnePagePlaylistIE._MAX_PAGE:
                raise ExtractorError("episodes page not found 404")
            entries = self._extract_list(playlistid)  
       
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))

            
        if not entries: raise ExtractorError("no video list") 
        
        return self.playlist_result(entries, f"breederbros:page_{playlistid}", f"breederbros:page_{playlistid}")

class BreederBrosAllPagesPlaylistIE(BreederBrosBaseIE):
    IE_NAME = 'breederbros:allpages:playlist'
    IE_DESC = 'breederbros:allpages:playlist'
    _VALID_URL = r"https://members\.breederbros\.com/index.php\?page=all"
 
    def _real_initialize(self):
        super()._real_initialize()
        
        # def put_in_queue(fut):
        #     try:
        #         res = fut.result()
        #         if res:
        #             BreederBrosBaseIE._LOCALQ.put_nowait(res)
        #     except Exception as e:
        #         self.to_screen(repr(e))
        
        # with ThreadPoolExecutor() as ex:
        #     futures = [ex.submit(self._new_proxy_and_driver) for i in range(6)]
        #     for fut in futures: fut.add_done_callback(put_in_queue)
       
    
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
        
        return self.playlist_result(entries, f"breederbros:AllPages", f"breederbros:AllPages")
