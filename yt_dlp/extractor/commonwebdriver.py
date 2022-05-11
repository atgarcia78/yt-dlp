from __future__ import unicode_literals

import shutil
import sys
import tempfile
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue
from urllib.parse import unquote

import httpx
from pyrate_limiter import Duration, Limiter, RequestRate
from selenium.webdriver import Firefox, FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys

from ..utils import int_or_none, try_get
from .common import ExtractorError, InfoExtractor

limiter_0_005 = Limiter(RequestRate(1, 0.005 * Duration.SECOND))
limiter_0_01 = Limiter(RequestRate(1, 0.01 * Duration.SECOND))
limiter_0_1 = Limiter(RequestRate(1, 0.1 * Duration.SECOND))
limiter_1 = Limiter(RequestRate(1, Duration.SECOND))
limiter_2 = Limiter(RequestRate(1, 2 * Duration.SECOND))
limiter_5 = Limiter(RequestRate(1, 5 * Duration.SECOND))
limiter_7 = Limiter(RequestRate(1, 7 * Duration.SECOND))
limiter_10 = Limiter(RequestRate(1, 10 * Duration.SECOND))
limiter_15 = Limiter(RequestRate(1, 15 * Duration.SECOND))


class scroll():
    '''
        To use as a predicate in the webdriver waits to scroll down to the end of the page
        when the page has an infinite scroll where it is adding new elements dynamically
    '''
    def __init__(self, wait_time):
        self.wait_time = wait_time
        
    def __call__(self, driver):
        last_height = driver.execute_script("return document.body.scrollHeight")
        time_start = time.monotonic()
        while((time.monotonic() - time_start) <= self.wait_time):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height: return True
        else: return False
        


class SeleniumInfoExtractor(InfoExtractor):
    
    _FF_PROF = '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/22jv66x2.selenium0'
    _MASTER_LOCK = threading.Lock()
    _QUEUE = Queue()
    _MASTER_COUNT = 0
    _YTDL = None
    _USER_AGENT = None
    _CLIENT_CONFIG = {}
    _CLIENT = None
    _MASTER_INIT = False
    _MAX_NUM_WEBDRIVERS = 0
    _FIREFOX_HEADERS =  {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en,es-ES;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
        'TE': 'trailers'
    }
    
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
    
   
    def close(self, client=True):
        
        while True:
            try:
                _driver = SeleniumInfoExtractor._QUEUE.get(block=False)                
                SeleniumInfoExtractor.rm_driver(_driver)               
            
            except Empty:
                if SeleniumInfoExtractor._YTDL:
                    SeleniumInfoExtractor._YTDL.to_screen(f'[{self.__class__.__name__[:-2].lower()}] SeleniumInfoExtractor drivers queue empty')
                break
            except Exception:
                pass
        
        if client:
            try:
                SeleniumInfoExtractor._CLIENT.close()
                SeleniumInfoExtractor._YTDL.to_screen(f'[{self.__class__.__name__[:-2].lower()}] SeleniumInfoExtradctor httpx client close')
            except Exception:
                pass
        
        #just in case a selenium extractor is needed after closing its network resources
        SeleniumInfoExtractor._MASTER_INIT = False
        self._ready = False
        
        
        
    @classmethod
    def rm_driver(cls, driver, usequeue=None):
        
        tempdir = driver.caps.get('moz:profile')
        if tempdir: shutil.rmtree(tempdir, ignore_errors=True)
        
        try:
            driver.quit()
        except Exception:
            pass
        
        if usequeue:
            with SeleniumInfoExtractor._MASTER_LOCK:
                SeleniumInfoExtractor._MASTER_COUNT -= 1
    
    def _real_initialize(self):
          
        with SeleniumInfoExtractor._MASTER_LOCK:
            if not SeleniumInfoExtractor._MASTER_INIT:
                
                SeleniumInfoExtractor._YTDL = self._downloader
                SeleniumInfoExtractor._MAX_NUM_WEBDRIVERS = SeleniumInfoExtractor._YTDL.params.get('winit') or 5

                init_drivers = []
                try:
                    with ThreadPoolExecutor(thread_name_prefix='init_firefox',max_workers=SeleniumInfoExtractor._MAX_NUM_WEBDRIVERS) as ex:
                        futures = {ex.submit(self.get_driver): i for i in range(SeleniumInfoExtractor._MAX_NUM_WEBDRIVERS)}
                    
                    
                    for fut in futures:
                        try:
                            init_drivers.append(fut.result())
                        except Exception as e:
                            lines = traceback.format_exception(*sys.exc_info())
                            self.to_screen(f'[init_drivers][{futures[fut]}] {repr(e)} \n{"!!".join(lines)}')

                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')  
                    
                finally:
                    if init_drivers:
                        SeleniumInfoExtractor._USER_AGENT = init_drivers[0].execute_script("return navigator.userAgent")
                        for driver in init_drivers:
                            SeleniumInfoExtractor._QUEUE.put_nowait(driver)
                            SeleniumInfoExtractor._MASTER_COUNT += 1
                
             
                _headers = dict(httpx.Headers(SeleniumInfoExtractor._YTDL.params.get('http_headers')).copy())
                _headers.update({'user-agent': SeleniumInfoExtractor._USER_AGENT})
                
                SeleniumInfoExtractor._CLIENT_CONFIG.update({'timeout': httpx.Timeout(60, connect=60), 'limits': httpx.Limits(max_keepalive_connections=None, max_connections=None), 'headers': _headers, 'follow_redirects': True, 'verify': not SeleniumInfoExtractor._YTDL.params.get('nocheckcertificate', False)})
                #self.write_debug(SeleniumInfoExtractor._CLIENT_CONFIG)
                
                SeleniumInfoExtractor._FIREFOX_HEADERS['User-Agent'] = SeleniumInfoExtractor._CLIENT_CONFIG['headers']['user-agent']
                
                _config = SeleniumInfoExtractor._CLIENT_CONFIG.copy()
                SeleniumInfoExtractor._CLIENT = httpx.Client(timeout=_config['timeout'], limits=_config['limits'], headers=_config['headers'], follow_redirects=_config['follow_redirects'], verify=_config['verify'])
                SeleniumInfoExtractor._MASTER_INIT = True



    def get_driver(self, noheadless=False, host=None, port=None, msg=None, usequeue=False):        

        if usequeue:
            
            with SeleniumInfoExtractor._MASTER_LOCK:
                #self.write_debug(f"drivers qsize: {SeleniumInfoExtractor._QUEUE._qsize()}")
                if SeleniumInfoExtractor._QUEUE._qsize() > 0:
                    driver = SeleniumInfoExtractor._QUEUE.get()
                else:    
                    if SeleniumInfoExtractor._MASTER_COUNT < SeleniumInfoExtractor._MAX_NUM_WEBDRIVERS:
                        driver = self._get_driver(noheadless, host, port, msg)
                        SeleniumInfoExtractor._MASTER_COUNT += 1                    
                    else:
                        driver = SeleniumInfoExtractor._QUEUE.get(block=True, timeout=600)            
        
        else: driver = self._get_driver(noheadless, host, port, msg)
        
        return driver
        
    def _get_driver(self, _noheadless, _host, _port, _msg):
        
        if _msg: pre = f'{_msg} '
        else: pre = ''
        
        tempdir = tempfile.mkdtemp(prefix='asyncall-')            
        res = shutil.copytree(SeleniumInfoExtractor._FF_PROF, tempdir, dirs_exist_ok=True)            
        if res != tempdir:
            raise ExtractorError("error when creating profile folder")
        
        opts = FirefoxOptions()
        
        if not _noheadless:
            opts.add_argument("--headless")
        
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-application-cache")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--profile")
        opts.add_argument(tempdir)
        
        if not _host and not _port:
            if SeleniumInfoExtractor._YTDL:
                if (proxy:=SeleniumInfoExtractor._YTDL.params.get('proxy')):
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
        
        serv = Service(log_path="/dev/null")
        
        n = 0
        
        while n < 3:
        
            driver = None
            try:
            
                driver = Firefox(service=serv, options=opts)
            
                driver.maximize_window()
            
                self.wait_until(driver, 0.5)
                
                self.to_screen(f"{pre}New firefox webdriver")
                
                return driver
                
            except Exception as e:
                n += 1
                if driver: 
                    driver.quit()
                    driver = None
                if 'Status code was: 69' in repr(e):
                    shutil.rmtree(tempdir, ignore_errors=True)
                    self.report_warning(f'{pre}Firefox needs to be relaunched')
                    raise ExtractorError(f'{pre}Firefox needs to be relaunched')
                if n == 3:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f'{pre}{repr(e)} \n{"!!".join(lines)}')
                    shutil.rmtree(tempdir, ignore_errors=True)  
                    raise ExtractorError(repr(e))

    def put_in_queue(self, driver):
        SeleniumInfoExtractor._QUEUE.put_nowait(driver)
        
    def wait_until(self, driver, timeout=60, method=ec.title_is("DUMMYFORWAIT"), poll_freq=0.5):
        try:
            el = WebDriverWait(driver, timeout, poll_frequency=poll_freq).until(method)
        except Exception as e:
            el = None
                        
        return el 
    
    def wait_until_not(self, driver, timeout, method, poll_freq=0.5):
        try:
            el = WebDriverWait(driver, timeout, poll_frequency=poll_freq).until_not(method)
        except Exception as e:
            el = None
            
        return el
    
    
    
    def get_info_for_format(self, url, client=None, headers=None, verify=True):
        
        try:
            res = None
            if client:
                res = client.head(url, headers=headers)
            else:
                _config = SeleniumInfoExtractor._CLIENT_CONFIG.copy()
                if not verify and _config['verify']:

                    if headers: _config['headers'].update(headers)
                    res = httpx.head(url, verify=False, timeout=_config['timeout'], headers=_config['headers'], follow_redirects=_config['follow_redirects'])
                else:    
                    res = SeleniumInfoExtractor._CLIENT.head(url, headers=headers)
            
            res.raise_for_status()
            #self.write_debug(f"{res.request} \n{res.request.headers}")
            #self.logger_debug(f"{res.request} \n{res.request.headers}")

            _filesize = int_or_none(res.headers.get('content-length'))
            _url = unquote(str(res.url))
            return ({'url': _url, 'filesize': _filesize})
            
        except Exception as e:
            if not res:
                #self.write_debug(f"{repr(e)}")
                self.logger_debug(f"{repr(e)}")

            else:
                #self.write_debug(f"{repr(e)} {res.request} \n{res.request.headers}")
                self.logger_debug(f"{repr(e)} {res.request} \n{res.request.headers}")
                #HTTPErrorStatus exception raised to differenciate from ExtractorError from the function in the
                #extractor using this method
                if res.status_code == 404:
                    res.raise_for_status()
                
            raise ExtractorError(repr(e))      

    def _send_request(self, *args, **kargs):
        pass
    
    def _is_valid(self, url, msg):
        
        if not url: 
            return False
        if len(url) > 150:
            _url_str = f'{url[:140]}...{url[-10:]}'
        else: _url_str = url
        self.to_screen(f'[valid][{msg}]:{_url_str} start checking')
        
        
        try:

            if any(_ in url for _ in ['gaypornmix.com', 'thisvid.com/embed', 'xtube.com']):
                self.to_screen(f'[valid][{msg}]:{_url_str}:False')
                return False
                
            else:  

                res = self._send_request(url.replace("streamtape.com", "streamtapeadblock.art"), _type="HEAD", headers=SeleniumInfoExtractor._FIREFOX_HEADERS)
            
            if res:
                if (st_code:=res.status_code) >= 400: 
                    valid = False
                    self.to_screen(f'[valid][{msg}]:{_url_str}:{st_code}:{valid}\n{res.request.headers}')
                    
                    
                elif res.headers.get('content-type') == "video/mp4":
                    valid = True
                    self.to_screen(f'[valid][{msg}]:{_url_str}:video/mp4:{valid}')
                    
                else:

                    webpage = try_get(self._send_request(url.replace("streamtape.com", "streamtapeadblock.art"), headers=SeleniumInfoExtractor._FIREFOX_HEADERS), lambda x: x.text)
                    if not webpage: 
                        valid = False
                        self.to_screen(f'[valid][{msg}]:{_url_str}:{valid} couldnt download webpage')
                    else:
                        valid = not any(_ in str(res.url) for _ in ['status=not_found', 'status=broken']) and not any(_ in webpage.lower() for _ in ['has been deleted', 'has been removed', 'was deleted', 'was removed', 'video unavailable', 'video is unavailable', 'video disabled', 'not allowed to watch', 'video not found', 'limit reached', 'xtube.com is no longer available', 'this-video-has-been-removed', 'has been flagged', 'embed-sorry'])
                    
                        self.to_screen(f'[valid][{msg}]:{_url_str}:{valid} check with webpage content')
            
            else: 
                valid = False
                self.to_screen(f'[valid][{msg}]:{_url_str}:{valid} couldnt download webpage')
                
            return valid
        
        except Exception as e:
            self.report_warning(f'[valid][{msg}]:{_url_str} error {repr(e)}')
            return False
    
    def send_request(self, url, _type="GET", data=None, headers=None):        
        
        try:
            req = SeleniumInfoExtractor._CLIENT.build_request(_type, url, data=data, headers=headers)
            res = SeleniumInfoExtractor._CLIENT.send(req)
            #self.to_screen(f"[send_request][{url}] {res}")
            res.raise_for_status()
            return res
        except httpx.HTTPStatusError as e:
            self.to_screen(f"[send_request][{url}] {repr(e)}")    
            return res
        except Exception as e:
            self.to_screen(f"[send_request][{url}] {repr(e)}")            
            raise
    
    
    

            

    
    
