# coding: utf-8
from __future__ import unicode_literals

import re
import threading

from .webdriver import SeleniumInfoExtractor
from ..utils import (
    ExtractorError, 
    int_or_none,
    sanitize_filename,
    std_headers
)

import hashlib
import sys
import traceback

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException
import httpx

import traceback

from ratelimit import limits, sleep_and_retry
from backoff import constant, on_exception
class NetDNAIE(SeleniumInfoExtractor):
    IE_NAME = "netdna"
    _VALID_URL = r'https?://(www\.)?netdna-storage\.com/f/[^/]+/(?P<title_url>[^\.]+)\.(?P<ext>[^\.]+)\..*'
    _CLIENT = httpx.Client(timeout=30, limits=httpx.Limits(max_keepalive_connections=None, max_connections=None), headers=std_headers, follow_redirects=True)
                            
    @classmethod
    def close(cls):
        NetDNAIE._CLIENT.close()            
                           
    @classmethod
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @sleep_and_retry
    @limits(calls=1, period=0.1)
    def _send_request(cls, url):
        res = NetDNAIE._CLIENT.get(url)
        res.raise_for_status()
        if "internal server error" in res.text.lower():
            raise Exception("error")
        return res
    
    
    def get_entry(self, url, ytdl=None):
        
        _info_video = NetDNAIE.get_video_info(url)
        #entry =  {'_type' : 'url', 'url' : _info_video.get('url'), 'ie' : 'NetDNA', 'title': _info_video.get('title'), 'id' : _info_video.get('id'), 'filesize': _info_video.get('filesize')}
        _title_search =  _info_video.get('title').replace("_",",")
        _id = _info_video.get('id')
        if not ytdl:
            ytdl = self._downloader 
        #para poder obtener la release date hay que buscar el post asociado en gaybeeg
        if not ytdl: 
            self.report_warning("not downloader in the extractor, couldnt get modification time info")
            return _info_video.update({'_type': 'url'})
        else:
            _info = ytdl.extract_info(f"https://gaybeeg.info/?s={_title_search}", download=False)
        
            _entries = _info.get('entries')
            for _entry in _entries:
                if _entry['id'] == _id:
                    return _entry
        
        
        
    @classmethod
    def get_video_info(cls, item):
        
        _DICT_BYTES = {'KB': 1024, 'MB': 1024*1024, 'GB' : 1024*1024*1024}
 
        if item.startswith('http'):

            title = None
            _num = None
            _unit = None
            # _timeout = httpx.Timeout(15, connect=15)        
            # _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
            # client = httpx.Client(timeout=_timeout, limits=_limits, follow_redirects=True, headers=std_headers)
            
            try:
                
                res = NetDNAIE._send_request(item)    

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
            except Exception as e:
                pass                                
            

                
            if not title or not _num or not _unit: return({'error': 'max tries'})

                                    
            str_id = f"{title}{_num}"
            videoid = int(hashlib.sha256(str_id.encode('utf-8')).hexdigest(),16) % 10**8
            return({'id': str(videoid), 'url': item, 'title': title, 'ext': ext, 'name': f"{videoid}_{title}.{ext}", 'filesize': float(_num)*_DICT_BYTES[_unit]})
            
       

        else:
            
            mobj = re.findall(r'(?:Download\s+)?([^\.]+)\.([^\s]+)\s+\[([^\[]+)\]', item)
            _num, _unit = mobj[0][2].split(' ')
            _num = _num.replace(',', '.')
            if _num.count('.') == 2:  _num = _num.replace('.','', 1)
            _num = f"{float(_num):.2f}"
            title = mobj[0][0].replace('-', '_').upper()
            ext = mobj[0][1]
            str_id = f"{title}{_num}"
            videoid = int(hashlib.sha256(str_id.encode('utf-8')).hexdigest(),16) % 10**8
            return({'id': str(videoid), 'title': title, 'ext': ext, 'name': f"{videoid}_{title}.{ext}", 'filesize': float(_num)*_DICT_BYTES[_unit]})
  
    def get_format(self, text, url):
        
        try:
            res = NetDNAIE._send_request(url)   
            mobj = re.search(r'file: \"(?P<file>[^\"]+)\"', res.text)
            if not mobj:
                self.to_screen(f"ERROR:{url}\n{res.text}")
                raise ExtractorError('cant find video url')
               
            else:
                _video_url = mobj.group('file')            
                _info = self.get_info_for_format(_video_url, headers={'Referer': 'https://netdna-storage.com/'})
                if not _info: ExtractorError("no video info")
                return ({'format_id': text, 'url': _info.get('url'), 'ext': 'mp4', 'filesize': _info.get('filesize')})
        except Exception as e:
            self.to_screen(repr(e))
            raise
    
    
    def _real_extract(self, url):        
        
        info_video = NetDNAIE.get_video_info(url)
        self.report_extraction(f"[{info_video.get('id')}][{info_video.get('title')}]")        

        
        driver = self.get_driver()
              
        
        try:

            count = 0
            
            while count < 3:        
            
                try:

                    entry = None
                    driver.get(url) #using firefox extension universal bypass to get video straight forward
                    
                    self.wait_until(driver, 30, ec.url_contains("netdna-storage.com/download/"))

                    
                    if not "netdna-storage.com/download/" in (_curl:=driver.current_url): 
                        self.write_debug(f"{info_video.get('title')} Bypass stopped at: {_curl}")
                        raise ExtractorError(f"{url} - Bypass stopped at: {_curl}") 
                    else:
                        
                        #self.to_screen(_curl)
                        
                        try:
                        
                            # _timeout = httpx.Timeout(15, connect=15)        
                            # _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
                            # client = httpx.Client(timeout=_timeout, limits=_limits, headers=std_headers, follow_redirects=True, verify=(not self._downloader.params.get('nocheckcertificate')))
                            
                            
                            el_formats = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CSS_SELECTOR,"a.btn.btn--small")))
                            
                            if el_formats: 
                                
                                _formats = [self.get_format(_el.text, _el.get_attribute('href')) for _el in el_formats]
                                
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
                                    _video_url = el_download.get_attribute('href')
                                    _info = self.get_info_for_format(_video_url, headers={'Referer': 'https://netdna-storage.com/'})
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
                        
                        
                
                except ExtractorError as e:
                    self.write_debug(f"{repr(e)}")
                    count += 1
                    self.write_debug(f"[count] {count}")
                    if count == 3: raise ExtractorError("max attempts to get info")
                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.write_debug(f"{repr(e)}, will retry \n{'!!'.join(lines)}")
                    raise ExtractorError(repr(e)) from e 
                      
        finally:
            try:
                self.rm_driver(driver)
            except Exception:
                pass 
   