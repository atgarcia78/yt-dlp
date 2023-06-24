from __future__ import unicode_literals

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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import httpx

from ..utils import (
    std_headers,
    int_or_none
)


class SeleniumInfoExtractor(InfoExtractor):
    
    _FF_PROF = '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/22jv66x2.selenium0'   
    
    
    def rm_driver(self, driver, tempdir=None):
        
        if not tempdir:
            tempdir = driver.caps.get('moz:profile')
        if tempdir: shutil.rmtree(tempdir, ignore_errors=True)
        
        try:
            driver.quit()
        except:
            pass
    

    def get_driver(self, prof=None, noheadless=False, host=None, port=None):
        
        if not prof:
            prof = self. _FF_PROF
            
        tempdir = tempfile.mkdtemp(prefix='asyncall-')
        
        shutil.copytree(prof, tempdir, dirs_exist_ok=True)
        
        opts = Options()
        
        if not noheadless:
            opts.add_argument("--headless")
        
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-application-cache")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--profile")
        opts.add_argument(tempdir)
        
        if not host and not port:
            if self._downloader:
                if (proxy:=self._downloader.params.get('proxy')):
                    proxy = proxy.replace('https://', '').replace('http://', '')
                    host = proxy.split(":")[0]
                    port = proxy.split(":")[1]
                
        if host and port:
            opts.set_preference("network.proxy.type", 1)
            opts.set_preference("network.proxy.http",host)
            opts.set_preference("network.proxy.http_port",int(port))
            opts.set_preference("network.proxy.https",host)
            opts.set_preference("network.proxy.https_port",int(port))
            opts.set_preference("network.proxy.ssl",host)
            opts.set_preference("network.proxy.ssl_port",int(port))
            opts.set_preference("network.proxy.ftp",host)
            opts.set_preference("network.proxy.ftp_port",int(port))
            opts.set_preference("network.proxy.socks",host)
            opts.set_preference("network.proxy.socks_port",int(port))
        
        else:
            opts.set_preference("network.proxy.type", 0)
            
                
        opts.set_preference("dom.webdriver.enabled", False)
        opts.set_preference("useAutomationExtension", False)
        
        self.to_screen(f"ffprof[{prof}]")
        self.to_screen(f"tempffprof[{tempdir}]")
        
        try:
        
            driver = Firefox(options=opts)
        
            driver.maximize_window()
        
            self.wait_until(driver, 3, ec.title_is("DUMMYFORWAIT"))
            
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')
            shutil.rmtree(tempdir, ignore_errors=True)  
            raise ExtractorError(str(e)) from e
        
        return driver
    
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
    

    def get_info_for_format(self, url, client=None, headers=None, fatal=False):
        
        count = 0
        if not client:
            _timeout = httpx.Timeout(15, connect=15)        
            _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
            client = httpx.Client(timeout=_timeout, limits=_limits, headers=std_headers, verify=(not self._downloader.params.get('nocheckcertificate')))
            close_client=True
        else: close_client=False
            
        try:
            
           
            while (count<3):
                
                try:
                    
                    #res = self._send_request(client, url, 'HEAD')
                    res = client.head(url, follow_redirects=True, headers=headers)
                    res.raise_for_status()
                    _filesize = int_or_none(res.headers.get('content-length'))
                    _url = str(res.url)
                    break
                        
            
                except Exception as e:
                    _error = e
                    count += 1
        except Exception as e:
            pass
        finally:
            if close_client:
                try:
                    client.close()
                except Exception:
                    pass

        if count < 3: return ({'url': _url, 'filesize': _filesize}) 
        else: 
            if not fatal: return ({'error': f'max retries - {repr(_error)}'})
            else: raise ExtractorError(f'info for format - max retries - {repr(_error)}')
    
    def logger_info(self, msg):
        if (_logger:=self._downloader.params.get('logger')):
            _logger.info(f"[{self.IE_NAME}]{msg}")
        else:
            self.to_screen(msg)
            
    
        