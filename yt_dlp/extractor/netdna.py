# coding: utf-8
from __future__ import unicode_literals

import re

from .seleniuminfoextractor import SeleniumInfoExtractor
from ..utils import (
    ExtractorError, 
    int_or_none,
    sanitize_filename,
    std_headers
)

import hashlib
import sys
import traceback


from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException
import httpx

import traceback


class NetDNAIE(SeleniumInfoExtractor):
    IE_NAME = "netdna"
    _VALID_URL = r'https?://(www\.)?netdna-storage\.com/f/[^/]+/(?P<title_url>[^\.]+)\.(?P<ext>[^\.]+)\..*'
    
    
    @staticmethod
    def get_entry(url, ytdl):
        
        _info_video = NetDNAIE.get_video_info(url)
        #entry =  {'_type' : 'url', 'url' : _info_video.get('url'), 'ie' : 'NetDNA', 'title': _info_video.get('title'), 'id' : _info_video.get('id'), 'filesize': _info_video.get('filesize')}
        _title_search =  _info_video.get('title').replace("_",",")
        _id = _info_video.get('id')
        
        _info = ytdl.extract_info(f"https://gaybeeg.info/?s={_title_search}", download=False)
        
        _entries = _info.get('entries')
        for _entry in _entries:
            if _entry['id'] == _id:
                return _entry
        
        
        
    @staticmethod
    def get_video_info(item):
        
        _DICT_BYTES = {'KB': 1024, 'MB': 1024*1024, 'GB' : 1024*1024*1024}
 
        if item.startswith('http'):

            title = None
            _num = None
            _unit = None
            _timeout = httpx.Timeout(30, connect=30)        
            _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
            client = httpx.Client(timeout=_timeout, limits=_limits, headers=std_headers)
            
            try:
                
                count = 0        
                while(count<5):        
                    try:                
                        res = client.get(item)

                        if res.status_code < 400:
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
                                
                            if title and _num and _unit: break
                            else: count += 1
                        else: count += 1                       
                        
                    except Exception as e:
                        #lines = traceback.format_exception(*sys.exc_info())
                        #NetDNAIE.to_screen(NetDNAIE, f"Error: {repr(e)}\n{'!!'.join(lines)}")
                        count += 1
            finally:
                client.close()
                        
            if count == 5: return({'error': 'max tries'})
            else:
                                    
                str_id = f"{title}{_num}"
                videoid = int(hashlib.sha256(str_id.encode('utf-8')).hexdigest(),16) % 10**8
                return({'id': str(videoid), 'title': title, 'ext': ext, 'name': f"{videoid}_{title}.{ext}", 'filesize': float(_num)*_DICT_BYTES[_unit]})
            
       

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
  

 

    
    def _get_info_format(self, url, client):
        
        count = 0
        try:
            
            _res = None
            while (count<3):
                
                try:
                    
                    #res = self._send_request(client, url, 'HEAD')
                    res = client.head(url, headers={'Referer': 'https://netdna-storage.com/'})
                    if res.status_code >= 400:
                        
                        count += 1
                    else: 
                        _filesize = int_or_none(res.headers.get('content-length'))
                        _url = str(res.url)
                        if _filesize and _url:
                            break
                        else:
                            count += 1
                        
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass

        if count < 3: return ({'url': _url, 'filesize': _filesize}) 
        else: return ({'error': 'max retries'})  
    


    def get_format(self, client, text, url):
        
        count = 0
        while (count < 3):
            try:
                res = client.get(url)
                break
            except Exception as e:
                count +=1
        
        if count == 3: raise ExtractorError('Couldn get format')    
        _video_url = re.search(r'file: \"(?P<file>[^\"]+)\"', res.text).group('file')
        _info = self._get_info_format(_video_url, client)
        return ({'format_id': text, 'url': _info.get('url'), 'ext': 'mp4', 'filesize': _info.get('filesize')})
  
    
    def _real_extract(self, url):        
        
        info_video = NetDNAIE.get_video_info(url)
        self.report_extraction(f"[{info_video.get('id')}][{info_video.get('title')}]")        

        
        driver, tempdir = self.get_driver(prof='/Users/antoniotorres/Library/Application Support/Firefox/Profiles/22jv66x2.selenium0')
              
        
        try:
            
            # driver.maximize_window()
            
            # self.wait_until(driver, 3, ec.title_is("DUMMYFORWAIT"))
            
            count = 0
            
            while count < 3:        
            
                try:

                    entry = None
                    driver.get(url) #using firefox extension universal bypass to get video straight forward
                    
                    _reswait = self.wait_until(driver, 120, ec.url_contains("netdna-storage.com/download/"))
                    
                    if not _reswait:
                        
                        _title = driver.title.lower()        
                        if any(_ in _title for _ in  ["file not found", "error"]):
                            self.write_debug(f"{info_video.get('title')} Page not found - {url}")
                            raise ExtractorError(f"404 - Page not found - {url}")

                        self.write_debug(f"{url} - Bypass stopped at: {driver.current_url}")
                        _reswait = self.wait_until(driver, 30, ec.presence_of_element_located((By.ID, "x-token")))
                        if _reswait:
                            
                            _reswait.submit()
                            #self.wait_until(driver, 10, ec.title_is("DUMMYFORWAIT"))
                            _reswait = self.wait_until(driver, 30, ec.presence_of_element_located((By.ID, "x-token")))
                            if _reswait:
                                
                                _reswait.submit()
                                #self.wait_until(driver, 1, ec.title_is("DUMMYFORWAIT"))
                                _reswait = self.wait_until(driver, 30, ec.url_contains("download"))
                                
                    
                    
                    if not "netdna-storage.com/download/" in (_curl:=driver.current_url): 
                        self.write_debug(f"{info_video.get('title')} Bypass stopped at: {_curl}")
                        raise ExtractorError(f"{url} - Bypass stopped at: {_curl}") 
                    else:
                        
                        #self.to_screen(_curl)
                        
                        try:
                        
                            _timeout = httpx.Timeout(30, connect=30)        
                            _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
                            client = httpx.Client(timeout=_timeout, limits=_limits, headers=std_headers, verify=(not self._downloader.params.get('nocheckcertificate')))
                            
                            
                            el_formats = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CSS_SELECTOR,"a.btn.btn--small")))
                            
                            if el_formats: 
                                
                                _formats = [self.get_format(client, _el.text, _el.get_attribute('href')) for _el in el_formats]
                                
                                self._sort_formats(_formats)
                                
                                entry = {
                                    'id' : info_video.get('id'),
                                    'title': sanitize_filename(info_video.get('title'),restricted=True),
                                    'formats': _formats,
                                    'ext' : info_video.get('ext')
                                }
                                    
                                return entry
                            
                            else:
                                el_download = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME,"btn.btn--xLarge")))
                                if el_download:
                                    _video_url = el_download.get_attribute('href')
                                    _info = self._get_info_format(_video_url, client)
                                    _formats = [{'format_id': 'ORIGINAL', 'url': _info.get('url'), 'filesize': _info.get('filesize'), 'ext': info_video.get('ext')}]
                                                                    
                                    entry = {
                                        'id' : info_video.get('id'),
                                        'title': sanitize_filename(info_video.get('title'),restricted=True),
                                        'formats': _formats,
                                        'ext' : info_video.get('ext')
                                    } 
                                    return entry  
                                    
                                    
                            
                        
                        except Exception as e:
                            lines = traceback.format_exception(*sys.exc_info())
                            self.write_debug(f"{repr(e)}, \n{'!!'.join(lines)}")
                            raise
                        finally:
                            client.close()
                        
                
                except ExtractorError as e:
                    self.to_screen(f"{repr(e)}")
                    count += 1
                    self.write_debug(f"[count] {count}")
                    if count == 3: raise
                except WebDriverException as e:
                    self.write_debug(f"{repr(e)}")
                    raise ExtractorError(str(e))
                    
                except Exception as e:  
                            
                    lines = traceback.format_exception(*sys.exc_info())
                    self.write_debug(f"{repr(e)}, will retry \n{'!!'.join(lines)}")
                    count += 1
                    self.write_debug(f"[count] {count}")
                    
                    if (count == 3):  raise ExtractorError(str(e))  
        finally:
            try:
                self.rm_driver(driver, tempdir)
            except Exception:
                pass 
                       
   