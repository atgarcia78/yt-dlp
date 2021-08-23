# coding: utf-8
from __future__ import unicode_literals

import re

from .common import InfoExtractor
from ..utils import (
    ExtractorError, 
    int_or_none,
    sanitize_filename
)

import hashlib
import sys
import traceback


import shutil
from selenium.webdriver import Firefox
from selenium.webdriver import FirefoxProfile
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
import time
import httpx

import traceback


class NetDNAIE(InfoExtractor):
    IE_NAME = "netdna"
    _VALID_URL = r'https?://(www\.)?netdna-storage\.com/f/[^/]+/(?P<title_url>[^\.]+)\.(?P<ext>[^\.]+)\..*'
    _DICT_BYTES = {'KB': 1024, 'MB': 1024*1024, 'GB' : 1024*1024*1024}

    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/0khfuzdw.selenium0']
    


 
    @staticmethod
    def get_video_info(url):
        
 
        title = None
        _num = None
        _unit = None
        
        count = 0        
        while(count<3):        
            try:                
                res = httpx.get(url)

                if res.status_code < 400:
                    _num_list = re.findall(r'File size: <strong>([^\ ]+)\ ([^\<]+)<',res.text)
                    if _num_list:
                        _num = _num_list[0][0].replace(',','.')
                        if _num.count('.') == 2:
                            _num = _num.replace('.','', 1)
                        _unit = _num_list[0][1]
                    _title_list = re.findall(r'h1 class="h2">([^\.]+).([^\<]+)<',res.text)
                    if _title_list:
                        title = _title_list[0][0].upper().replace("-","_")
                        ext = _title_list[0][1].lower()
                        
                if title and _num and _unit: break
                else: count += 1
                
                
            except Exception as e:
                #lines = traceback.format_exception(*sys.exc_info())
                #NetDNAIE.to_screen(NetDNAIE, f"Error: {repr(e)}\n{'!!'.join(lines)}")
                count += 1
              
       
        if title and _num and _unit:             
            str_id = f"{title}{_num}"
            videoid = int(hashlib.sha256(str_id.encode('utf-8')).hexdigest(),16) % 10**8
            return({'id': str(videoid), 'title': title, 'ext': ext, 'name': f"{videoid}_{title}.{ext}", 'filesize': float(_num)*NetDNAIE._DICT_BYTES[_unit]})
        else:
            return({'id': None})


    def wait_until(self, driver, time, method):        
        
        try:
            el = WebDriverWait(driver, time).until(method)
        except Exception as e:
            el = None
    
        return el   

    
    def _get_filesize(self, url):
        
        count = 0
        try:
            cl = httpx.Client()
            _res = None
            while (count<3):
                
                try:
                    
                    res = cl.head(url)
                    if res.status_code > 400:
                        time.sleep(1)
                        count += 1
                    else: 
                        _res = int_or_none(res.headers.get('content-length')) 
                        break
            
                except (httpx.HTTPError, httpx.CloseError, httpx.RemoteProtocolError, httpx.ReadTimeout, 
                        httpx.ProxyError, AttributeError, RuntimeError) as e:
                    count += 1
        except Exception as e:
            pass
        finally:
            cl.close()
        
        return _res   
        
    
    def _real_extract(self, url):        
        
        info_video = NetDNAIE.get_video_info(url)
        self.report_extraction(info_video.get('title'))
        
        count = 0
        
        while True:        
        
            try:
                
                opts = Options()
                opts.headless = True
                prof_ff = self._FF_PROF.pop() 
                self._FF_PROF.insert(0,prof_ff)
                driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof_ff))
 
                
                driver.set_window_size(1920,575)
                
                
                driver.get("https://gaybeeg.info") 
                self.wait_until(driver, 30, ec.title_contains("GayBeeg"))            
                        
                entry = None
                driver.get(url)
                time.sleep(1)
                _reswait = self.wait_until(driver, 90, ec.url_contains("download"))
                if not _reswait:

                    self.to_screen(f"{url} - Bypass stopped at: {driver.current_url}")
                    _reswait = self.wait_until(driver, 30, ec.presence_of_element_located((By.ID, "x-token")))
                    if _reswait:
                        _reswait.submit()
                        time.sleep(10)
                        _reswait = self.wait_until(driver, 30, ec.presence_of_element_located((By.ID, "x-token")))
                        if _reswait:
                            _reswait.submit()
                            time.sleep(1)
                            _reswait = self.wait_until(driver, 30, ec.url_contains("download"))
                            
                _title = driver.title.lower()        
                if "file not found" in _title or "error" in _title:
                    self.to_screen(f"{info_video.get('title')} Page not found - {url}")
                    raise ExtractorError(f"Page not found - {url}")
                
                elif not "download" in (_curl:=driver.current_url): 
                    self.to_screen(f"{info_video.get('title')} Bypass stopped at: {_curl}")
                    raise ExtractorError(f"{url} - Bypass stopped at: {_curl}") 
                else:
                    
                    self.to_screen(_title)
                    
                    
            
                    time.sleep(1)
                    formats_video = []
                    _reswait = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR,"a.btn.btn--xLarge")))
                    _filesize = None
                    if _reswait:
                        _url = _reswait.get_attribute('href')
                        _filesize = self._get_filesize(_url)
                        self.to_screen(f"url[{_url}]")
                    
                    if not _filesize:
                        driver.get(url)
                        _reswait = self.wait_until(driver, 90, ec.url_contains("download"))
                        if not _reswait:
                            raise ExtractorError(f"Bypass didnt work till the last page - {url}")

                        self.to_screen(driver.title)
                        time.sleep(1)                        

                        _reswait = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR,"a.btn.btn--xLarge")))
                        _filesize = None
                        if _reswait:
                            _url = _reswait.get_attribute('href')
                            _filesize = self._get_filesize(_url)
                        if not _filesize:
                            raise ExtractorError(f"error404 - {url}")
                    
                    formats_video.append({'format_id': 'ORIGINAL', 
                                                'url': _url,
                                                'ext': info_video.get('ext'),
                                                'filesize' : _filesize 
                                            })
                    
                    _reswait = self.wait_until(driver, 1, ec.presence_of_all_elements_located((By.CSS_SELECTOR,"a.btn.btn--small")))
                    
                    el_formats = []
                    if _reswait:
                        el_formats = [{'url' : el.get_attribute('href'), 'text': el.get_attribute('innerText')} 
                                    for el in _reswait]
                    
                    if el_formats and len(el_formats) > 1: 
                        
                        for fmt in el_formats[1:]:
                            
                            driver.get(fmt['url'])
                            el_url = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR,"a.btn.btn--xLarge")))
                            if el_url:
                                formats_video.append({'format_id': fmt['text'], 
                                                'url': (_url:=el_url.get_attribute('href')),
                                                'ext': info_video.get('ext'),
                                                'filesize' : self._get_filesize(_url)
                                                
                                            })
                            
                    self._sort_formats(formats_video)
                        
                    entry = {
                        'id' : info_video.get('id'),
                        'title': sanitize_filename(info_video.get('title'),restricted=True),
                        'formats': formats_video,
                        'ext' : info_video.get('ext')
                    }
                        
                break  
                    
            except Exception as e:  
                          
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f"{repr(e)}, will retry \n{'!!'.join(lines)}")
                count += 1
                self.to_screen(f"[count] {count}")
                driver.quit()
                
                if (count == 3):
                
                    if isinstance(e, ExtractorError):
                        raise
                    else:
                        raise ExtractorError(str(e)) from e 
            finally:
                driver.quit()
                
        return entry     
            
                     
            
            