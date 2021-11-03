from __future__ import unicode_literals

from .common import InfoExtractor, ExtractorError

import sys
import traceback

import threading
import tempfile
import shutil

from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By



class SeleniumInfoExtractor(InfoExtractor):
    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/22jv66x2.selenium0']
    
    _MASTERLOCK = threading.Lock()   
    
    def get_profile_path(self):
        
        with SeleniumInfoExtractor._MASTERLOCK:
            prof = SeleniumInfoExtractor._FF_PROF.pop() 
            SeleniumInfoExtractor._FF_PROF.insert(0,prof)
            
        return prof
    
    
    def rm_driver(self, driver, tempdir):
        
        try:
            driver.quit()
        except:
            pass
        
        shutil.rmtree(tempdir, ignore_errors=True)
    
    def get_opts(self, opts, prof=None, host=None, port=None):
        
                
        if not prof:
            prof = self.get_profile_path()
            
        tempdir = tempfile.mkdtemp(prefix='asyncall-')
        
        shutil.copytree(prof, tempdir, dirs_exist_ok=True)
        
        
        opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-application-cache")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--profile")
        opts.add_argument(tempdir)
        
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
        
        return (opts, tempdir)
    
    def get_driver(self, prof=None, noheadless=False, host=None, port=None):
        
        if not prof:
            prof = self.get_profile_path()
            
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
        
        return (driver, tempdir)
    
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