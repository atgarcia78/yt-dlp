# coding: utf-8
from __future__ import unicode_literals

import re

from .commonwebdriver import SeleniumInfoExtractor
from ..utils import (
    ExtractorError, 
    sanitize_filename,
)

import hashlib
import sys
import traceback

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import traceback

from ratelimit import limits, sleep_and_retry
from backoff import constant, on_exception

class fast_forward():     
    def __call__(self, driver):
        _curl = driver.current_url
        if "netdna-storage.com/download/" in _curl: return "OK"
        elif any(_ in _curl for _ in ["gestyy.com", "sh.st"]):
            el_button = driver.find_elements(By.CSS_SELECTOR, "span#skip_button.skip-btn.show")
            if el_button:
                try:
                    el_button[0].click()
                    
                except Exception as e:
                    self.to_screen(repr(e))
            return False
        elif "moz-extension" in _curl: return False
        elif "netdna-storage" in _curl:
            if 'file not found' in (_title:=driver.title.lower()): return "Error 404"
            elif 'error' in _title:
                driver.refresh()
                return False
            else: return False
        else: return False

class NetDNAIE(SeleniumInfoExtractor):
    IE_NAME = "netdna"
    _VALID_URL = r'https?://(www\.)?netdna-storage\.com/f/[^/]+/(?P<title_url>[^\.]+)\.(?P<ext>[^\.]+)\..*' 
    _DICT_BYTES = {'KB': 1024, 'MB': 1024*1024, 'GB' : 1024*1024*1024}

    @classmethod
    def get_video_info_str(cls, item):

        mobj = re.findall(r'(?:Download\s+)?([^\.]+)\.([^\s]+)\s+\[([^\[]+)\]', item)
        _num, _unit = mobj[0][2].split(' ')
        _num = _num.replace(',', '.')
        if _num.count('.') == 2:  _num = _num.replace('.','', 1)
        _num = f"{float(_num):.2f}"
        title = mobj[0][0].replace('-', '_').upper()
        ext = mobj[0][1]
        str_id = f"{title}{_num}"
        videoid = int(hashlib.sha256(str_id.encode('utf-8')).hexdigest(),16) % 10**8
        return({'id': str(videoid), 'title': title, 'ext': ext, 'name': f"{videoid}_{title}.{ext}", 'filesize': float(_num)*NetDNAIE._DICT_BYTES[_unit]})
    

    @on_exception(constant, ExtractorError, max_tries=5, interval=0.01)
    @sleep_and_retry
    @limits(calls=1, period=0.005)
    def _send_request(self, url, _type=None):
        
        if not _type:
            try:
                res = NetDNAIE._CLIENT.get(url)
                res.raise_for_status()
                if "internal server error" in res.text.lower():
                    raise Exception("internal server error")
                return res
            except Exception as e:
                raise ExtractorError(repr(e))
        elif _type == "GET_INFO":
            return self.get_info_for_format(url, client=NetDNAIE._CLIENT, headers={'referer': 'https://netdna-storage.com/'})
            
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @sleep_and_retry
    @limits(calls=1, period=1)    
    def url_request(self, driver, url):
                
        driver.execute_script("window.stop();")
        driver.get(url)

    @on_exception(constant, ExtractorError, max_tries=5, interval=0.1)
    def get_format(self, text, url):
        
        try:
            res = self._send_request(url)   
            mobj = re.search(r'file: \"(?P<file>[^\"]+)\"', res.text)
            if not mobj:
                self.write_debug(f"ERROR:{url}\n{res.text}")
                raise ExtractorError('cant find video url')
               
            else:
                _video_url = mobj.group('file')            
                _info = self._send_request(_video_url, "GET_INFO")
                if not _info: ExtractorError("no video info")
                return ({'format_id': text, 'url': _info.get('url'), 'ext': 'mp4', 'filesize': _info.get('filesize')})
        except Exception as e:
            self.write_debug(repr(e))
            raise       

    def get_video_info_url(self, url):
        
        title = _num = _unit = None
        
        try:
            
            if not self._MASTER_INIT: self._init()
                                    
            res = self._send_request(url) 

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
                
            if not title or not _num or not _unit: return({'error': 'no video info'})
                                
            str_id = f"{title}{_num}"
            videoid = int(hashlib.sha256(str_id.encode('utf-8')).hexdigest(),16) % 10**8
        
            return({'id': str(videoid), 'url': url, 'title': title, 'ext': ext,
                    'name': f"{videoid}_{title}.{ext}", 'filesize': float(_num)*NetDNAIE._DICT_BYTES[_unit]})
        
        except Exception as e:
            return({'error': repr(e)})     
        
    def get_entry(self, url, ytdl=None):        
        
        
        if not self._MASTER_INIT: self._init()
        
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
                    return _entry

    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):        
        
        
        info_video = self.get_video_info_url(url)
        if (_error:=info_video.get('error')): raise ExtractorError(_error)

        count = 0
        
        while count < 3:        
        
            try:
                driver = self.get_driver(usequeue=True)
                entry = None
                self.report_extraction(f"[{url}] attempt[{count+1}/3]")
                self.url_request(driver, url) #using firefox extension universal bypass to get video straight forward
                
                el_res = self.wait_until(driver, 60, fast_forward())
                
                if el_res == "Error 404": raise ExtractorError(el_res)
                elif el_res != "OK":
                    msg_error = f"[{url}] attempt[{count+1}/3] Bypass stopped at: {driver.current_url}"
                    self.to_screen(msg_error)
                    count += 1
                    if count == 3: raise ExtractorError("max attempts to get info")
                    
                

                else:                        
                    
                    try:                        
                        
                        el_formats = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CSS_SELECTOR,"a.btn.btn--small")))
                        
                        if el_formats:
                            
                            try:
                            
                                _formats = [self.get_format(_el.text, _el.get_attribute('href')) for _el in el_formats]
                                
                            except Exception as e:
                                msg_error = f"[{url}] attempt[{count+1}/3] error when getting formats"
                                self.to_screen(msg_error)
                                count += 1
                                if count == 3: raise ExtractorError("max attempts to get info")
                                else: continue
                            
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
                                    
                                _formats = [{'format_id': 'ORIGINAL', 'url': _info.get('url'), 'filesize': _info.get('filesize'), 'ext': info_video.get('ext')}]
                                                                
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
            
             
   