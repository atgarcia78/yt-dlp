# coding: utf-8
from __future__ import unicode_literals

import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_1_5, By, ec

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
        if not "LOG OUT" in el_top.get_attribute('innerHTML').upper():
            return({"error": "Login failed"})
        else: return("OK")
     
class BBGroupIE(SeleniumInfoExtractor):
    
    

    
    def _send_request(self, url, headers=None, driver=None):

        @dec_on_exception
        @limiter_1_5.ratelimit(self.IE_NAME.split(":")[0], delay=True)
        def _temp():
            self.logger_debug(f'[send_req][{self.IE_NAME.split(":")[0]}] {url}')
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
        
        return _temp()
        
    def _login(self, _driver):        
            
        try:        
            self._send_request(self._LOGIN_URL, driver=_driver)
            
            if not "LOG OUT" in (try_get(self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "ul"))),
                                         lambda x: x.get_attribute('innerHTML').upper()) or ""):
            
                self.report_login()
                username, password = self._get_login_info()

                if not username or not password:
                    self.raise_login_required(
                        'A valid %s account is needed to access this media.'
                        % self._NETRC_MACHINE)

                if (self.wait_until(_driver, 60, waitforlogin(username, password, self.to_screen)) != "OK"):
                    raise ExtractorError("couldnt log in")
            
            self.to_screen("[login] Login OK")
            return "OK"
        
        except Exception as e:
            #lines = traceback.format_exception(*sys.exc_info())
            #self.to_screen(f"[login] Login NOK - {repr(e)}\n{'!!'.join(lines)}")
            self.to_screen("[login] Login NOK")
            return "NOK"
        
    def _real_initialize(self):
        
        self.to_screen(f'[real_init] {type(self)}')
        super()._real_initialize()
                            
                        
        if not type(self)._MAX_PAGE:
            
            try:
                
                webpage = try_get(self._send_request(self._SITE_URL),
                                    lambda x: x.text.replace("\n","").replace("\t",""))
                type(self)._MAX_PAGE  = try_get(re.findall(r'>(\d+)</a></li></ul></div><!-- pagination-center -->', webpage),
                                                        lambda x: int(x[0])) or 50
            
            except Exception as e:
                self.to_screen("error when init")
        

    
    def _new_driver(self):
        with type(self)._MLOCK:
           
            if type(self)._NUMDRIVERS < 10:
                
                type(self)._NUMDRIVERS += 1
                
            else: 
                return (None, None)
        
        _driver  = self.get_driver(devtools=True)
        return(_driver, self._login(_driver))
        

    def _extract_from_video_page(self, url, pid=None, nent=None):        
        
        def replTxt(match):
            repl_dict = {"+": "PLUS", "&": "AND", "'": "", "-": "", ",": ""}
            if match:
                _res = try_get(match.groups(), lambda x: (x[0] or "", x[2] or "")) or ("","")
                _key = try_get(match.groups(), lambda x: x[1]) or 'dummmy'
                if (_key in repl_dict):
                    if _key not in ["'","-"]:
                        _txt = [_res[0] + ' ' if _res[0] not in [' ',''] else _res[0],
                                ' ' + _res[1] if _res[1] not in [' ',''] else _res[1]]
                    elif _key in ["-"]:
                        _txt = [_res[0],
                                ' ' + _res[1] if _res[1] not in [' ',''] and _res[0] not in [' ',''] else _res[1]]
                        if _txt== [' ', ' ']: _txt = [' ','']
                    elif _key in ["'"]:
                        if _res[1] == 'S':
                            _txt = [_res[0], 'S']
                        else:
                            _txt = [_res[0],
                                    ' ' + _res[1] if _res[1] not in [' ',''] and _res[0] not in [' ',''] else _res[1]]
                        if _txt == [' ', ' ']: _res = [' ','']

                return f"{_txt[0]}{repl_dict[_key]}{_txt[1]}"
        
        try:
            
            pre = f"[extract_entry][page_{pid}]" if pid else f"[extract_entry]"
            self.to_screen(f"{pre} start for {url}")
            
            _driver = None
            _res = "NOK" 
            try:
                _driver = type(self)._LOCALQ.get(block=False)
                _res = "OK"                     
            except Empty:             
                _driver, _res = try_get(self._new_driver(), lambda x: (x[0], x[1])) 
                if not _driver:
                    _driver, _res = try_get(type(self)._LOCALQ.get(block=True, timeout=600),
                                                    lambda x: (x[0], "OK"))
            
            if _res == "NOK":
              
                return self.url_result(url, ie=self.ie_key().split('AllPages')[0].split('OnePage')[0], error="login NOK")
  

            videoid = try_get(re.search(r'gallery\.php\?id=(?P<id>\d+)', url), lambda x: f"{x.group('id')}{self._SUFFIX}")
            if videoid in self._TRAD_FROM_NEW_TO_OLD: 
                videoid = self._TRAD_FROM_NEW_TO_OLD[videoid]
            
            self._send_request(url.split('&page')[0], driver=_driver)
            
            title = re.sub(r'([ ]+)', ' ',
                           re.sub(r'(.)?([\+\&\'-,])(.)?', replTxt,
                                  try_get(self.wait_until(_driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "div.name"))),
                                          lambda x: x.get_attribute('innerText'))))

            formats_m3u8 = None
            
            headers = {            
                "Accept" : "*/*",
                "Referer" : url.split('&page')[0]               
            }
            
            def _getter(x):
                _temp = ""
                for el in x:
                    _url = el.get_attribute('src')
                    if not _url: continue
                    if 'playlist' in _url:
                        return _url                    
                    elif 'membersvideoplayer' in _url.lower():
                        _temp = _url

                return _temp
            
            manifesturl = try_get(self.wait_until(_driver, 60, ec.presence_of_all_elements_located((By.TAG_NAME, 'video'))), _getter) 
            
            self.write_debug(f"[{videoid}] {manifesturl}")
            
            if manifesturl:
                
                if not "playlist" in manifesturl:

                    self.write_debug(f"[{videoid}] start scan har")

                    m3u8_url, m3u8_doc = self.scan_for_request(_driver, f".m3u8")           
                    if m3u8_url:
                        if not "playlist" in m3u8_url:
                            if m3u8_doc:
                                _url = try_get(re.findall(r"(https://.*)", m3u8_doc), lambda x: x[0]) 
                                if _url:
                                    murl, params = _url.split('?')
                                    manifesturl = murl.rsplit('/',1)[0] + '/playlist.m3u8?' + params                    
                                    self.write_debug(f"[{videoid}] {manifesturl}")
                                    formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                                        m3u8_doc, manifesturl, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")
                        else:
                            formats_m3u8, _ = self._extract_m3u8_formats_and_subtitles(m3u8_url, video_id=videoid, ext="mp4", 
                                                                            entry_protocol="m3u8_native", m3u8_id="hls", headers=headers)
                            
                        
                else:                    
                    formats_m3u8, _ = self._extract_m3u8_formats_and_subtitles(manifesturl, video_id=videoid, ext="mp4", 
                                                                            entry_protocol="m3u8_native", m3u8_id="hls", headers=headers)
                
            if not formats_m3u8:
                raise ExtractorError(f"[{url}] Can't find any M3U8 format")

            self._sort_formats(formats_m3u8)
            
            
            
            for _format in formats_m3u8:
                if (_head:=_format.get('http_headers')):
                    _head.update(headers)
                else:
                    _format.update({'http_headers': headers})               
                    
            return ({
                "id": videoid,
                "title": sanitize_filename(title, restricted=True).upper(),
                "webpage_url": url.split('&page')[0],
                "formats": formats_m3u8
            })            

        
        except ExtractorError as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            #raise
            if '&page' in url or not pid:
                raise
            else:
                return self.url_result(f"{url}&page={pid}", ie=self.ie_key().split('AllPages')[0].split('OnePage')[0], webpage_url=url)
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            with type(self)._MLOCK:
                
                type(self)._NENTRIES += 1
                            
                            
                if pid and _res == "OK" and not '&page' in url and  (not nent or nent > type(self)._NENTRIES):
                    if _driver:
                        type(self)._LOCALQ.put_nowait(_driver)
                else:
                    if _driver:
                        try:
                            #_harproxy.close()                
                            self.rm_driver(_driver)
                        except Exception:
                            pass
                        
                        type(self)._NUMDRIVERS -= 1
                    

                    if not pid or (nent and nent == type(self)._NENTRIES):

                        # try:
                        #     self.stop_browsermob(type(self)._SERVER)
                        # except Exception:
                        #     pass
                        
                        # type(self)._SERVER = None
                        type(self)._NENTRIES = 0


    def _extract_all_list(self, firstpage="1", npages="all"):
        
        _entries = []
        try:
            if npages == 'all': 
                _max = self._MAX_PAGE
            else: 
                _max = int(firstpage) + int(npages) - 1
                if _max > self._MAX_PAGE:
                    self.report_warning(f'[all_pages] pages requested > max page website: will check up to max page')
                    _max = self._MAX_PAGE
                    
                
            with ThreadPoolExecutor(thread_name_prefix="ExtrListAll", max_workers=10) as ex:
                futures = {ex.submit(self._extract_list, i, allpages=True): i 
                           for i in range(int(firstpage), _max + 1)}             
            
            for fut in futures:
                #self.to_screen(f'[page_{futures[fut]}] results')
                try:
                    res = fut.result()
                    _entries += res        
                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.report_warning(f'[all_pages][page_{futures[fut]}] {repr(e)} \n{"!!".join(lines)}') 
                    
            if not _entries: raise ExtractorError(f"[all_pages] no videos found")
            _nentries = 0
            
            self.to_screen(f'[all_pages] {_entries}')
            for el in _entries:
                if el.get('_type') == 'url' and not el.get('error'): _nentries += 1
            for el in _entries:
                if el.get('_type') == 'url' and not el.get('error'):
                    el['url'] = f"{el['url']}&nent={_nentries}"        
            return _entries
        finally:
            while(True):
                try:                        
                    _driver = type(self)._LOCALQ.get(block=False)
                    self.rm_driver(_driver)
                    #_harproxy.close()
                except Empty:
                    break
            
            type(self)._LOCALQ = Queue()
            type(self)._NUMDRIVERS = 0
            type(self)._NENTRIES = 0
            
            # try:
            #     self.stop_browsermob(type(self)._SERVER)
            # except Exception:
            #     pass
            
            # type(self)._SERVER = None
        

    def _extract_list(self, plid, allpages=False):
 
        url_pl = f"{self._BASE_URL_PL}{plid}"
        self.to_screen(f"[page_{plid}] extract list videos")

        
        try:

            res = self._send_request(url_pl.replace('members', 'www'))

            url_list = try_get(re.findall(r'<a href="trailer\.php\?id=(\d+)"',
                                          res.text.replace("\n", "").replace("\t", "")),
                               lambda x: list(({f"{self._LOGIN_URL}/gallery.php?id=" + el:"" for el in x}).keys()))

            self.to_screen(f'[page_{plid}] {len(url_list)} videos\n[{",".join(url_list)}]')

            if not url_list: raise ExtractorError(f'[page_{plid}] no videos for playlist')
            
            entries = []
            futures = {}
                
            def get_res(fut):                
                try:
                    res = fut.result()
                    res.update({'original_url': f"{self._BASE_URL_PL}{plid}"})
                    self.to_screen(f"[page_{plid}] {futures[fut][0]} {res}")
                    entries.append([futures[fut][0], res])
                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.report_warning(f'[page_{plid}] not entry for {futures[fut]} - {repr(e)} \n{"!!".join(lines)}')  
                    #self.report_warning(f'[page_{plid}] not entry for {futures[fut]} - {repr(e)}')

            with ThreadPoolExecutor(thread_name_prefix="ExtrList", max_workers=10) as ex:
                futures = {ex.submit(self._extract_from_video_page, _url, pid=plid): [i, _url] 
                                for (i, _url) in enumerate(url_list)}
                for fut in futures: fut.add_done_callback(get_res)

            if not entries: raise ExtractorError(f"[page_{plid}] no videos found")
            _entries = [el[1] for el in sorted(entries, key=lambda x: x[0])]
            if not allpages:
                _nentries = 0
                for el in _entries:
                    if el.get('_type') == 'url' and not el.get('error'): _nentries += 1
                for el in _entries:
                    if el.get('_type') == 'url' and not el.get('error'):
                        el['url'] = f"{el['url']}&nent={_nentries}"

            self.to_screen(_entries)
            return _entries
            
        finally:
            if not allpages:
                
                while(True):
                    try:                        
                        _driver = type(self)._LOCALQ.get(block=False)
                        self.rm_driver(_driver)
                        #_harproxy.close()
                    except Empty:
                        break
                type(self)._LOCALQ = Queue()
                type(self)._NUMDRIVERS = 0
                type(self)._NENTRIES = 0
                
                # try:
                #     self.stop_browsermob(type(self)._SERVER)
                # except Exception as e:
                #     lines = traceback.format_exception(*sys.exc_info())
                #     self.report_warning(f'[page_{plid}][stop_server]  {repr(e)} \n{"!!".join(lines)}') 
                
                # type(self)._SERVER = None
                

                    
                
           

class SketchySexBaseIE(BBGroupIE):
    _LOGIN_URL = "https://members.sketchysex.com"
    _SITE_URL = "https://www.sketchysex.com"
    _BASE_URL_PL = "https://members.sketchysex.com/index.php?page="

    _NETRC_MACHINE = 'sketchysex'    

    _SUFFIX = "SX"
    
    _TRAD_FROM_NEW_TO_OLD = {'19SX': '5433', '20SX': '5528', '21SX': '5498', '22SX': '5587', '23SX': '5472', '24SX': '5563',
                             '25SX': '5511', '26SX': '5617', '27SX': '5637', '28SX': '5735', '29SX': '5758', '30SX': '5709',
                             '31SX': '5684', '32SX': '5788', '33SX': '5821', '34SX': '5662', '36SX': '5910', '37SX': '5853',
                             '38SX': '5948', '39SX': '5968', '40SX': '5998', '41SX': '6028', '42SX': '6063', '43SX': '6098',
                             '44SX': '6127', '45SX': '6152', '46SX': '6200', '47SX': '6172', '48SX': '6288', '49SX': '6263',
                             '50SX': '6231', '51SX': '6321', '52SX': '6370', '53SX': '6340', '54SX': '6420', '55SX': '6392',
                             '56SX': '6449', '57SX': '6500', '58SX': '6472', '59SX': '6555', '60SX': '6591', '61SX': '6530',
                             '62SX': '6824', '63SX': '6845', '64SX': '6889', '65SX': '6677', '66SX': '6754', '67SX': '6928',
                             '68SX': '6977', '69SX': '856', '70SX': '1788', '71SX': '1796', '72SX': '1803', '73SX': '2900',
                             '74SX': '2893', '75SX': '1827', '76SX': '469', '77SX': '1131', '78SX': '515', '79SX': '798',
                             '80SX': '3104', '81SX': '2781', '82SX': '4359', '83SX': '2047', '84SX': '3256', '85SX': '4588',
                             '86SX': '5164', '87SX': '5224', '88SX': '5207', '89SX': '5277', '90SX': '5402', '91SX': '5303',
                             '92SX': '5367', '93SX': '882', '94SX': '946', '96SX': '1833', '97SX': '1520', '98SX': '654',
                             '100SX': '1256', '143SX': '7000', '144SX': '7033', '145SX': '7079', '35SX': '5882'}
    
    _MLOCK = threading.Lock()
    
    _INIT = False
    
    _MAX_PAGE = None
    
    #_SERVER = None
   
    _NUMDRIVERS = 0
    
    _NENTRIES = 0
    
    _LOCALQ = Queue()
    
    def _real_initialize(self):
        
        super()._real_initialize()
    
class BreederBrosBaseIE(BBGroupIE):
    _LOGIN_URL = "https://members.breederbros.com"
    _SITE_URL = "https://www.breederbros.com"
    _BASE_URL_PL = "https://members.breederbros.com/index.php?page="

    _NETRC_MACHINE = 'fraternityx'
    
    _SUFFIX = "BB"
    
    _TRAD_FROM_NEW_TO_OLD = {}

    _MLOCK = threading.Lock()
    
    _INIT = False
   
    _MAX_PAGE = None
    
    #_SERVER = None
   
    _NUMDRIVERS = 0
    
    _NENTRIES = 0
    
   
    _LOCALQ = Queue()
    
    def _real_initialize(self):
       
        super()._real_initialize()
                

class SketchySexIE(SketchySexBaseIE):
    IE_NAME = 'sketchysex'
    IE_DESC = 'sketchysex'
    _VALID_URL = r'https://members\.sketchysex\.com/gallery\.php\?id=(?P<id>\d+)(&page=(?P<pid>\d+))?(&nent=(?P<nent>\d+))?'
    
    
    
    def _real_initialize(self):
        with SketchySexBaseIE._MLOCK:
            if not SketchySexBaseIE._INIT:
                super()._real_initialize()
                SketchySexBaseIE._INIT = True
    
    def _real_extract(self, url):
        
        self.report_extraction(url)
       
        try: 
            pid, nent = try_get(re.search(self._VALID_URL, url), lambda x: (x.group('pid'), x.group('nent') or 1))
            #self.to_screen(f"page: {pid}")
            data = self._extract_from_video_page(url, pid, nent)
            if not data:
                raise ExtractorError("not any video found")            
            if (_error:=data.get('error')):
                raise ExtractorError(_error)
            return data 
        
        except ExtractorError:
            raise    
        except Exception as e:
            #lines = traceback.format_exception(*sys.exc_info())
            #self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))

 

class SketchySexOnePagePlaylistIE(SketchySexBaseIE):
    IE_NAME = 'sketchysex:playlist'
    IE_DESC = 'sketchysex:playlist'
    _VALID_URL = r"https://members\.sketchysex\.com/index\.php(?:\?page=(?P<id>\d+)|$)"

    def _real_initialize(self):
        with SketchySexBaseIE._MLOCK:
            if not SketchySexBaseIE._INIT:
                super()._real_initialize()
                SketchySexBaseIE._INIT = True
       
    
    def _real_extract(self, url):

        self.report_extraction(url)
        playlistid = re.search(self._VALID_URL, url).group("id") or '1'
               
        try:              

            if int(playlistid) > SketchySexOnePagePlaylistIE._MAX_PAGE:
                raise ExtractorError("episodes page not found 404")
            entries = self._extract_list(playlistid)
            if not entries: raise ExtractorError("no video list")  
            return self.playlist_result(entries, f"sketchysex:page_{playlistid}", f"sketchysex:page_{playlistid}")
       
        except ExtractorError:
            raise
        except Exception as e:
            #lines = traceback.format_exception(*sys.exc_info())
            #self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))


class SketchySexAllPagesPlaylistIE(SketchySexBaseIE):
    IE_NAME = 'sketchysex:allpages:playlist'
    IE_DESC = 'sketchysex:allpages:playlist'
    _VALID_URL = r"https://members\.sketchysex\.com/index.php\?(fpage=(?P<pid>\d+)&)?npages=(?P<npages>(?:\d+|all))"
 
    def _real_initialize(self):
        with SketchySexBaseIE._MLOCK:
            if not SketchySexBaseIE._INIT:
                super()._real_initialize()
                SketchySexBaseIE._INIT = True
       
    
    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        
        try: 
            fpage, npages = try_get(re.search(self._VALID_URL, url), lambda x: (x.group('pid') or "1", x.group('npages')))
            entries = self._extract_all_list(fpage, npages)
            if not entries: raise ExtractorError("no video list")         
        
            return self.playlist_result(entries, f"sketchysex:AllPages", f"sketchysex:AllPages") 
       
        except ExtractorError:
            raise
        except Exception as e:
            #lines = traceback.format_exception(*sys.exc_info())
            #self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        
class BreederBrosIE(BreederBrosBaseIE):
    IE_NAME = 'breederbros'
    IE_DESC = 'breederbros'
    _VALID_URL = r'https://members\.breederbros\.com/gallery\.php\?id=(?P<id>\d+)(&page=(?P<pid>\d+))?(&nent=(?P<nent>\d+))?'
    
    
    
    def _real_initialize(self):
        with BreederBrosBaseIE._MLOCK:
            if not BreederBrosBaseIE._INIT:
                super()._real_initialize()
                BreederBrosBaseIE._INIT = True
    
    def _real_extract(self, url):
        
        self.report_extraction(url)
       
        try: 
            pid, nent = try_get(re.search(self._VALID_URL, url), lambda x: (x.group('pid'), x.group('nent') or 1))
            #self.to_screen(f"page: {pid}")
            data = self._extract_from_video_page(url, pid, nent)
            if not data:
                raise ExtractorError("not any video found")  
            if (_error:=data.get('error')):
                raise ExtractorError(_error)          
            return data 
        
        except ExtractorError:
            raise    
        except Exception as e:
            #lines = traceback.format_exception(*sys.exc_info())
            #self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))


        

class BreederBrosOnePagePlaylistIE(BreederBrosBaseIE):
    IE_NAME = 'breederbros:playlist'
    IE_DESC = 'breederbros:playlist'
    _VALID_URL = r"https://members\.breederbros\.com/index\.php(?:\?page=(?P<id>\d+)|$)"

    def _real_initialize(self):
        with BreederBrosBaseIE._MLOCK:
            if not BreederBrosBaseIE._INIT:
                super()._real_initialize()
                BreederBrosBaseIE._INIT = True
       
    
    def _real_extract(self, url):

        self.report_extraction(url)
        playlistid = re.search(self._VALID_URL, url).group("id") or '1'
               
        try:              

            if int(playlistid) > BreederBrosOnePagePlaylistIE._MAX_PAGE:
                raise ExtractorError("episodes page not found 404")
            entries = self._extract_list(playlistid)
            if not entries: raise ExtractorError("no video list")
            #self.to_screen(entries)
            return self.playlist_result(entries, f"breederbros:page_{playlistid}", f"breederbros:page_{playlistid}")
       
        except ExtractorError:
            raise
        except Exception as e:
            #lines = traceback.format_exception(*sys.exc_info())
            #self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))

            
         
        
       

class BreederBrosAllPagesPlaylistIE(BreederBrosBaseIE):
    IE_NAME = 'breederbros:allpages:playlist'
    IE_DESC = 'breederbros:allpages:playlist'
    _VALID_URL = r"https://members\.breederbros\.com/index.php\?(fpage=(?P<pid>\d+)&)?npages=(?P<npages>(?:\d+|all))"
 
    def _real_initialize(self):
        with BreederBrosBaseIE._MLOCK:
            if not BreederBrosBaseIE._INIT:
                super()._real_initialize()
                BreederBrosBaseIE._INIT = True
       
    
    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        
        try: 
            
            fpage, npages = try_get(re.search(self._VALID_URL, url), lambda x: (x.group('pid') or "1", x.group('npages')))
            entries = self._extract_all_list(fpage, npages)
            if not entries: raise ExtractorError("no video list")         
        
            return self.playlist_result(entries, f"breederbros:AllPages", f"breederbros:AllPages") 
       
        except ExtractorError:
            raise
        except Exception as e:
            #lines = traceback.format_exception(*sys.exc_info())
            #self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))