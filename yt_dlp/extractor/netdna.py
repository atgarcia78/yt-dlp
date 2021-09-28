# coding: utf-8
from __future__ import unicode_literals

import re

from .common import InfoExtractor
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
from selenium.webdriver import FirefoxProfile
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
import time
import httpx

import traceback
import threading
from queue import Queue
import os


class NetDNAIE(InfoExtractor):
    IE_NAME = "netdna"
    _VALID_URL = r'https?://(www\.)?netdna-storage\.com/f/[^/]+/(?P<title_url>[^\.]+)\.(?P<ext>[^\.]+)\..*'
    

    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/0khfuzdw.selenium0']
    
    _QUEUE = Queue()    
    
    _LOCK = threading.Lock()
    
    _DRIVER = 0

 
    @staticmethod
    def get_video_info(item):
        
        _DICT_BYTES = {'KB': 1024, 'MB': 1024*1024, 'GB' : 1024*1024*1024}
 
        if item.startswith('http'):
        
            try:
                title = None
                _num = None
                _unit = None
                _timeout = httpx.Timeout(30, connect=30)        
                _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
                client = httpx.Client(timeout=_timeout, limits=_limits, headers=std_headers)
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
                    
                if count == 5: return({'id': None})
                else:
                                        
                    str_id = f"{title}{_num}"
                    videoid = int(hashlib.sha256(str_id.encode('utf-8')).hexdigest(),16) % 10**8
                    return({'id': str(videoid), 'title': title, 'ext': ext, 'name': f"{videoid}_{title}.{ext}", 'filesize': float(_num)*_DICT_BYTES[_unit]})
            finally:
                client.close()
       

        else:
            mobj = re.findall(r'Download ([^\.]+)\.([^ ]+) \[([^\[]+)\]', item)
            _num, _unit = mobj[0][2].split(' ')
            _num = _num.replace(',', '.')
            if _num.count('.') == 2:  _num = _num.replace('.','', 1)
            title = mobj[0][0]
            ext = mobj[0][1]
            str_id = f"{title}{_num}"
            videoid = int(hashlib.sha256(str_id.encode('utf-8')).hexdigest(),16) % 10**8
            return({'id': str(videoid), 'title': title, 'ext': ext, 'name': f"{videoid}_{title}.{ext}", 'filesize': float(_num)*_DICT_BYTES[_unit]})
  
            
            
            
    def wait_until(self, driver, time, method):        
        
        try:
            el = WebDriverWait(driver, time).until(method)
        except Exception as e:
            el = None
    
        return el   

    
    def _get_filesize(self, url):
        
        count = 0
        try:
            cl = httpx.Client(timeout=60,verify=(not self._downloader.params.get('nocheckcertificate')))
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
        
        with NetDNAIE._LOCK: 
                
            if NetDNAIE._DRIVER == self._downloader.params.get('winit'):
                
                driver = NetDNAIE._QUEUE.get(block=True)
                driver.execute_script('''location.replace("about:blank");''')
                
            else:
                
                
                prof = NetDNAIE._FF_PROF.pop()
                NetDNAIE._FF_PROF.insert(0, prof)
                driver = None
                NetDNAIE._DRIVER += 1
                
        if not driver:
                    
                opts = Options()
                opts.headless = True
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-application-cache")
                opts.add_argument("--disable-gpu")
                opts.add_argument("--disable-dev-shm-usage")
                os.environ['MOZ_HEADLESS_WIDTH'] = '1920'
                os.environ['MOZ_HEADLESS_HEIGHT'] = '1080'
                                
                driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof))
 
                self.to_screen(f"{url}:ffprof[{prof}]")
                
                driver.maximize_window()
        
        count = 0
        
        while count < 5:        
        
            try:
                

                entry = None
                driver.get(url) #using firefox extension universal bypass to get video straight forward
                
                _reswait = self.wait_until(driver, 120, ec.url_contains("download"))
                
                if not _reswait:
                    
                    _title = driver.title.lower()        
                    if any(_ in _title for _ in  ["file not found", "error"]):
                        self.to_screen(f"{info_video.get('title')} Page not found - {url}")
                        raise ExtractorError(f"404 - Page not found - {url}")

                    self.to_screen(f"{url} - Bypass stopped at: {driver.current_url}")
                    _reswait = self.wait_until(driver, 30, ec.presence_of_element_located((By.ID, "x-token")))
                    if _reswait:
                        
                        _reswait.submit()
                        #self.wait_until(driver, 10, ec.title_is("DUMMYFORWAIT"))
                        _reswait = self.wait_until(driver, 30, ec.presence_of_element_located((By.ID, "x-token")))
                        if _reswait:
                            
                            _reswait.submit()
                            #self.wait_until(driver, 1, ec.title_is("DUMMYFORWAIT"))
                            _reswait = self.wait_until(driver, 30, ec.url_contains("download"))
                            
                
                
                if not "download" in (_curl:=driver.current_url): 
                    self.to_screen(f"{info_video.get('title')} Bypass stopped at: {_curl}")
                    raise ExtractorError(f"{url} - Bypass stopped at: {_curl}") 
                else:
                    
                    self.to_screen(_title)
                    
                    
                    formats_video = []
                    _reswait = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR,"a.btn.btn--xLarge")))
                    _filesize = None
                    if _reswait:
                        _url = _reswait.get_attribute('href')
                        _filesize = self._get_filesize(_url)
                        self.to_screen(f"url[{_url}] filesize:{_filesize}")
                    
                    if not _filesize:
                        count += 1
                        continue

                    else:
                        
                        formats_video.append({'format_id': 'ORIGINAL', 
                                                    'url': _url,
                                                    'ext': info_video.get('ext'),
                                                    'filesize' : _filesize 
                                                })
                        
                        _reswait = self.wait_until(driver, 10, ec.presence_of_all_elements_located((By.CSS_SELECTOR,"a.btn.btn--small")))
                        
                        el_formats = []
                        if _reswait:
                            el_formats = [{'url' : el.get_attribute('href'), 'text': re.sub('[\t\n]', '', el.get_attribute('innerText'))} 
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
                            
                        return entry  
                    
            
            except ExtractorError as e:
                self.to_screen(f"{repr(e)}")
                count += 1
                self.to_screen(f"[count] {count}")
                if count == 5: raise
            except Exception as e:  
                          
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f"{repr(e)}, will retry \n{'!!'.join(lines)}")
                count += 1
                self.to_screen(f"[count] {count}")
                
                if (count == 5):  raise ExtractorError(str(e)) from e 
            finally:
                NetDNAIE._QUEUE.put_nowait(driver)
                with NetDNAIE._LOCK:
                
                    try:
                        self._downloader.params.get('dict_videos_to_dl', {}).get('NetDNA',[]).remove(url)
                    except ValueError as e:
                        self.to_screen(str(e))
                    count = len(self._downloader.params.get('dict_videos_to_dl', {}).get('NetDNA',[])) 
                    
                    self.to_screen(f"COUNT: [{count}]")
                    if count == 0:
                        self.to_screen("LETS CLOSE DRIVERS")
                        for __driver in list(NetDNAIE._QUEUE.queue):
                            try:
                                __driver.quit()
                                
                            except Exception as e:
                                self.to_screen(str(e))
                       
                
           
            
                     
            
            