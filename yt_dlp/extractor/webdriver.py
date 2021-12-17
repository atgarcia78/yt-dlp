from __future__ import unicode_literals
import threading

from .common import (
    InfoExtractor,
    ExtractorError
)


import sys
import traceback


import tempfile
import shutil

from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import httpx
from urllib.parse import unquote

from ..utils import (
    std_headers,
    int_or_none
)

from queue import Queue, Empty
class SeleniumInfoExtractor(InfoExtractor):
    
    _FF_PROF = '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/22jv66x2.selenium0'
    _MASTER_LOCK = threading.Lock()
    _QUEUE = Queue()
    _COUNT = 0
    _YTDL = None 
    
    @classmethod
    def logger_info(cls, msg):
        if SeleniumInfoExtractor._YTDL:
            if (_logger:=SeleniumInfoExtractor._YTDL.params.get('logger')):
                _logger.info(f"[{cls.__name__[:-2].lower()}]{msg}")
            else:
                SeleniumInfoExtractor._YTDL.to_screen(f"[{cls.__name__[:-2].lower()}]{msg}")
        
    @classmethod       
    def logger_debug(cls, msg):
        if SeleniumInfoExtractor._YTDL:
            if (_logger:=SeleniumInfoExtractor._YTDL.params.get('logger')):
                _logger.debug(f"[{cls.__name__[:-2].lower()}]{msg}")
            else:
                SeleniumInfoExtractor._YTDL.to_screen(f"[{cls.__name__[:-2].lower()}]{msg}")
    
    @classmethod
    def close(cls):
        while True:
            try:
                _driver = SeleniumInfoExtractor._QUEUE.get(block=False)                
                cls.rm_driver(_driver)               
            
            except Empty:
                if SeleniumInfoExtractor._YTDL:
                    SeleniumInfoExtractor._YTDL.to_screen(f'[{cls.__name__[:-2].lower()}] queue empty')
                break
            except Exception:
                pass
    
    @classmethod
    def rm_driver(cls, driver, tempdir=None):
        
        if not tempdir:
            tempdir = driver.caps.get('moz:profile')
        if tempdir: shutil.rmtree(tempdir, ignore_errors=True)
        
        try:
            driver.quit()
        except:
            pass
    
    
    def _real_initialize(self):
        SeleniumInfoExtractor._YTDL = self._downloader 

    def get_driver(self, noheadless=False, host=None, port=None, msg=None, usequeue=False):
        
        
        def _get_driver(_noheadless, _host, _port, _msg):
            if _msg: pre = f'{_msg} '
            else: pre = ''        
            prof = self._FF_PROF
                
            tempdir = tempfile.mkdtemp(prefix='asyncall-')
            
            res = shutil.copytree(prof, tempdir, dirs_exist_ok=True)
            
            if res != tempdir:
                raise ExtractorError("error when creating profile folder")
            
            opts = Options()
            
            if not _noheadless:
                opts.add_argument("--headless")
            
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-application-cache")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--profile")
            opts.add_argument(tempdir)
            
            if not _host and not _port:
                if self._downloader:
                    if (proxy:=self._downloader.params.get('proxy')):
                        proxy = proxy.replace('https://', '').replace('http://', '')
                        _host = proxy.split(":")[0]
                        _port = proxy.split(":")[1]
                    
            if _host and _port:
                opts.set_preference("network.proxy.type", 1)
                opts.set_preference("network.proxy.http",_host)
                opts.set_preference("network.proxy.http_port",int(_port))
                opts.set_preference("network.proxy.https",_host)
                opts.set_preference("network.proxy.https_port",int(_port))
                opts.set_preference("network.proxy.ssl",_host)
                opts.set_preference("network.proxy.ssl_port",int(_port))
                opts.set_preference("network.proxy.ftp",_host)
                opts.set_preference("network.proxy.ftp_port",int(_port))
                opts.set_preference("network.proxy.socks",_host)
                opts.set_preference("network.proxy.socks_port",int(_port))
            
            else:
                opts.set_preference("network.proxy.type", 0)
                
                    
            opts.set_preference("dom.webdriver.enabled", False)
            opts.set_preference("useAutomationExtension", False)
            
            self.to_screen(f"{pre}ffprof[{prof}]")
            #self.to_screen(f"tempffprof[{tempdir}]")
            
            serv = Service(log_path="/dev/null")
            
            try:
            
                driver = Firefox(service=serv, options=opts)
            
                driver.maximize_window()
            
                self.wait_until(driver, 3, ec.title_is("DUMMYFORWAIT"))
                
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f'{pre}{repr(e)} \n{"!!".join(lines)}')
                shutil.rmtree(tempdir, ignore_errors=True)  
                raise ExtractorError(repr(e)) from e
            
            return driver
    
        if usequeue:
            with SeleniumInfoExtractor._MASTER_LOCK:
                if SeleniumInfoExtractor._COUNT < self._downloader.params.get('winit', 5):
                    driver = _get_driver(noheadless, host, port, msg)
                    SeleniumInfoExtractor._COUNT += 1                    
                else:
                    driver = SeleniumInfoExtractor._QUEUE.get(block=True, timeout=120)
            return driver
        
        else: return _get_driver(noheadless, host, port, msg)
            
    def wait_until(self, driver, time, method):
        try:
            el = WebDriverWait(driver, time).until(method)
        except Exception as e:
            el = None
            
        return el 
    
    def wait_until_not(self, _driver, time, method):
        try:
            el = WebDriverWait(_driver, time).until_not(method)
        except Exception as e:
            el = None
            
        return el
    
            
    
    def get_info_for_format(self, url, client=None, headers=None, verify=True):
        
        if not client:                
            _timeout = httpx.Timeout(30, connect=30)        
            _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
            if not verify:
                _verify = False
            else:
                _verify = not self._downloader.params.get('nocheckcertificate')
            client = httpx.Client(timeout=_timeout, limits=_limits, headers=std_headers, verify=_verify)
            close_client = True
        else: close_client = False           
               
        try:
            res = client.head(url, follow_redirects=True, headers=headers)
            
            res.raise_for_status()
            _filesize = int_or_none(res.headers.get('content-length'))
            _url = unquote(str(res.url))
            return ({'url': _url, 'filesize': _filesize})
        
        except Exception as e:
            self.to_screen(f"{repr(e)}")
            raise        
        finally:
            if close_client:
                try:
                    client.close()
                except Exception:
                    pass
            
    
    

            

    
    
