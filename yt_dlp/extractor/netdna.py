# coding: utf-8
from __future__ import unicode_literals
from concurrent.futures import ThreadPoolExecutor

import re

from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_0_005,
    limiter_1
)

from ..utils import (
    ExtractorError, 
    sanitize_filename,
    try_get
)

import hashlib
import sys
import traceback

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import traceback


from backoff import constant, on_exception

from urllib.parse import unquote

import time

class fast_forward():     
    def __init__(self, orig, logger):
        self.url_orig = orig
        self.logger = logger
        self.pers_error = False
        self.init = True

    
    def __call__(self, driver):
        _curl = driver.current_url        
        self.logger(f"{unquote(_curl)}:{unquote(self.url_orig)}")
        if "netdna-storage.com/download/" in _curl:
            return "OK"
        
        if self.init == True:
            self.url_orig = _curl
            self.init == False
            return False
        
        if unquote(_curl) != unquote(self.url_orig):            
            self.url_orig = _curl
            return False            
        
        elif "netdna-storage.com" in _curl:
            # if self.init == True:
            #     self.init = False
            #     return False
                
            if 'file not found' in (_title:=driver.title.lower()): 
                return "Error 404"
            elif 'error' in _title:
                driver.refresh()
                return False
            else:
                if self.pers_error: 
                    return "Error addon fast forward"
                else:
                    self.pers_error = True
                    driver.refresh()
                    return False
                
        else: return False

class NetDNAIE(SeleniumInfoExtractor):
    IE_NAME = "netdna"
    _VALID_URL = r'https?://(www\.)?netdna-storage\.com/f/[^/]+/(?P<title_url>[^\.]+)\.(?P<ext>[^\.]+)\..*' 
    _DICT_BYTES = {'KB': 1024, 'MB': 1024*1024, 'GB' : 1024*1024*1024}


    @on_exception(constant, Exception, max_tries=5, interval=0.01)
    @limiter_0_005.ratelimit("netdna1", delay=True)
    def _send_request(self, url, _type=None):
        
        if not _type:
            try:
                res = NetDNAIE._CLIENT.get(url)
                try:
                    res.raise_for_status()
                except Exception as e:
                    raise ExtractorError('error 404')
                
                if "internal server error" in res.text.lower():
                    raise ExtractorError("error internal server 404")
                
                return res
            
            except ExtractorError as e:
                self.to_screen(f'[send_request][{url}] {str(e)}')
                return
            
        
        elif _type == "GET_INFO":            
            return self.get_info_for_format(url, headers={'referer': 'https://netdna-storage.com/'})
        
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @limiter_1.ratelimit("netdna2", delay=True)
    def url_request(self, driver, url):
                
        driver.execute_script("window.stop();")
        driver.get(url)

    @on_exception(constant, ExtractorError, max_tries=5, interval=0.02)
    def get_format(self, formatid, ext, url):
        
        try:
            _info = try_get(
                self._send_request(url),
                lambda x: try_get(
                    re.search(r'file: \"(?P<file>[^\"]+)\"', x.text),
                    lambda y: self._send_request(y.group('file'), "GET_INFO")
                )
            )
            if not _info: raise ExtractorError('no video info')
            return ({'format_id': formatid, 'url': _info.get('url'), 'ext': ext, 'filesize': _info.get('filesize'), 'http_headers': {'Referer': 'https://netdna-storage.com/'}})

        except Exception as e:
            self.write_debug(repr(e))
            raise       

    def get_video_info_url(self, url):
        
        title = _num = _unit = None
        
        try:
            
            if not self._MASTER_INIT: 
                super()._real_initialize()
                                    
            res = self._send_request(url) 
            if not res: 
                return({'error': 'webpage nok 404'})
            
            _num_list = re.findall(r'File size: <strong>([^\ ]+)\ ([^\<]+)<',res.text)
            if _num_list:
                _num = _num_list[0][0].replace(',','.')
                if _num.count('.') == 2:
                    _num = _num.replace('.','', 1)
                _num = f"{float(_num):.2f}"
                _unit = _num_list[0][1]
            _title_list = re.findall(r'h1 class="h2">([^\.]+).([^\<]+)<',res.text)
            if _title_list:
                title = _title_list[0][0].upper().replace("-","_")
                ext = _title_list[0][1].lower()
                
            if any((not title, not _num, not _unit)): 
                return({'error': 'no video info'})
                                
            str_id = f"{title}{_num}"
            videoid = int(hashlib.sha256(str_id.encode('utf-8')).hexdigest(),16) % 10**8
        
            return({'id': str(videoid), 'url': url, 'title': title, 'ext': ext,
                    'name': f"{videoid}_{title}.{ext}", 'filesize': float(_num)*NetDNAIE._DICT_BYTES[_unit]})
        
        except Exception as e:
            return({'error': repr(e)})     
        
    def get_entry(self, url, ytdl=None):        
        
        
        if not self._MASTER_INIT: 
            super()._real_initialize()
        
        _info_video = self.get_video_info_url(url)
        if (_error:=_info_video.get('error')): raise ExtractorError(_error) 
        _title_search =  _info_video.get('title', '').replace("_",",")
        _id = _info_video.get('id')
        if not ytdl:
            ytdl = self._downloader 
        #para poder obtener la release date hay que buscar el post asociado en gaybeeg
        if not ytdl: 
            self.report_warning("not downloader in the extractor, couldnt get modification time info")
            _info_video.update({'_type': 'url'})
            return _info_video
        else:
            _info = ytdl.extract_info(f"https://gaybeeg.info/?s={_title_search}")
        
            _entries = _info.get('entries')
            for _entry in _entries:
                if _entry['id'] == _id:
                    res = _entry #devuelve el más antiguo
            
            return res

    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):        
        
        
        info_video = self.get_video_info_url(url)
        if (_error:=info_video.get('error')): raise ExtractorError(_error)

        count = 0
        
        while count < 3:        
        
            self.report_extraction(f"[{url}] attempt[{count+1}/3]")
            driver = self.get_driver(usequeue=True)
            
            try:

                self.url_request(driver, url) #using firefox extension universal bypass to get video straight forward
                
                el_res = self.wait_until(driver, 60, fast_forward(url, self.to_screen), poll_freq=4)
                
                if not el_res:
                    msg_error = f"[{url}] attempt[{count+1}/3] Bypass stopped at: {driver.current_url}"
                    self.to_screen(msg_error)
                    count += 1
                    if count == 3: raise ExtractorError("max attempts to get info")
                elif el_res in ["Error 404" , "Error addon fast forward"]: raise ExtractorError(el_res)
                elif el_res != "OK":
                    msg_error = f"[{url}] attempt[{count+1}/3] Bypass stopped at: {driver.current_url}"
                    self.to_screen(msg_error)
                    count += 1
                    if count == 3: raise ExtractorError("max attempts to get info")

                else:                        
 
                    entry = None
                    try:                        
                        
                        el_formats = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CSS_SELECTOR,"a.btn.btn--small")))
                        
                        if el_formats:

                            with ThreadPoolExecutor(thread_name_prefix='fmt_netdna', max_workers=len(el_formats)) as ex:
                                futures = [ex.submit(self.get_format, _el.text, info_video.get('ext'), _el.get_attribute('href')) for _el in el_formats]
                                
                            _formats = []
                            _reset = False
                            for fut in futures:    
                                try:                                    
                                    _formats.append(fut.result())
                                
                                except Exception as e:
                                    msg_error = f"[{url}] attempt[{count+1}/3] error when getting formats {repr(e)}"
                                    self.to_screen(msg_error)
                                    count += 1
                                    if count == 3: raise ExtractorError("max attempts to get info")
                                    else: _reset = True
                            
                            if _reset: continue
                            if _formats:    
                                self._sort_formats(_formats)
                            
                                entry = {
                                    'id' : info_video.get('id'),
                                    'title': sanitize_filename(info_video.get('title'),restricted=True),
                                    'formats': _formats,
                                    'ext' : info_video.get('ext')
                                }
                                
                        else:
                            el_download = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME,"btn.btn--xLarge")))
                            if el_download:
                                try:
                                    _video_url = el_download.get_attribute('href')
                                    _info = self._send_request(_video_url, "GET_INFO")
                                
                                except Exception as e:
                                    msg_error = f"[{url}] attempt[{count+1}/3] error when getting formats"
                                    self.to_screen(msg_error)
                                    count += 1
                                    if count == 3: raise ExtractorError("max attempts to get info")
                                    else: continue
                                    
                                _formats = [{'format_id': 'ORIGINAL', 'url': _info.get('url'), 'filesize': _info.get('filesize'), 'ext': info_video.get('ext'), 'http_headers': {'Referer': 'https://netdna-storage.com/'}}]
                                                                
                                entry = {
                                    'id' : info_video.get('id'),
                                    'title': sanitize_filename(info_video.get('title'),restricted=True),
                                    'formats': _formats,
                                    'ext' : info_video.get('ext')
                                } 
                                    
                        if not entry: raise ExtractorError("no video info")
                        else:
                            return entry                               
                        
                    
                    except Exception as e:
                        lines = traceback.format_exception(*sys.exc_info())
                        self.write_debug(f"{repr(e)}, \n{'!!'.join(lines)}")
                        raise                    
                    
            
            except ExtractorError:
                raise
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.write_debug(f"{repr(e)}\n{'!!'.join(lines)}")
                raise ExtractorError(repr(e))                    
            finally:
                self.put_in_queue(driver)
            
             
   