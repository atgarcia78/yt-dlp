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
from backoff import constant, on_exception
from pyrate_limiter import Duration, Limiter, RequestRate
from selenium.webdriver import Firefox, FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys

from browsermobproxy import Server

from ..utils import int_or_none, try_get
from .common import ExtractorError, InfoExtractor

limiter_0_005 = Limiter(RequestRate(1, 0.005 * Duration.SECOND))
limiter_0_01 = Limiter(RequestRate(1, 0.01 * Duration.SECOND))
limiter_0_1 = Limiter(RequestRate(1, 0.1 * Duration.SECOND))
limiter_0_5 = Limiter(RequestRate(1, 0.5 * Duration.SECOND))
limiter_1 = Limiter(RequestRate(1, Duration.SECOND))
limiter_2 = Limiter(RequestRate(1, 2 * Duration.SECOND))
limiter_5 = Limiter(RequestRate(1, 5 * Duration.SECOND))
limiter_7 = Limiter(RequestRate(1, 7 * Duration.SECOND))
limiter_10 = Limiter(RequestRate(1, 10 * Duration.SECOND))
limiter_15 = Limiter(RequestRate(1, 15 * Duration.SECOND))
dec_on_exception = on_exception(constant, Exception, max_tries=3, interval=1, raise_on_giveup=False)


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
    _FF_PROF_IG = '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/ln3i0v51.default-release'
    _MASTER_LOCK = threading.Lock()
    _QUEUE = Queue()
    _MASTER_COUNT = 0
    _YTDL = None
    _USER_AGENT = None
    _CLIENT_CONFIG = {}
    _CLIENT = None
    _CONFIG_REQ = {('userload', 'evoload', 'highload'): {'ratelimit': limiter_15},
               'doodstream': {'ratelimit': limiter_10},
               'tubeload': {'ratelimit': limiter_15} }
    _MASTER_INIT = False
    _MAX_NUM_WEBDRIVERS = 0
    _SERVER_NUM = 0
    _FIREFOX_HEADERS =  {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'en,es-ES;q=0.5',        
        'Connection': 'keep-alive',        
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1', 
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
    def rm_driver(cls, driver):
        
        tempdir = driver.caps.get('moz:profile')
        if tempdir: shutil.rmtree(tempdir, ignore_errors=True)
        
        try:
            driver.quit()
        except Exception:
            pass
        
    
        
    
    def _real_initialize(self, prof=None):
          
        with SeleniumInfoExtractor._MASTER_LOCK:
            if not SeleniumInfoExtractor._MASTER_INIT:
                
                SeleniumInfoExtractor._YTDL = self._downloader
                SeleniumInfoExtractor._MAX_NUM_WEBDRIVERS = SeleniumInfoExtractor._YTDL.params.get('winit', 5)

                init_drivers = []
                try:
                    # with ThreadPoolExecutor(thread_name_prefix='init_firefox',max_workers=SeleniumInfoExtractor._MAX_NUM_WEBDRIVERS) as ex:
                    #     futures = {ex.submit(self.get_driver): i for i in range(SeleniumInfoExtractor._MAX_NUM_WEBDRIVERS)}
                    
                    
                    # for fut in futures:
                    #     try:
                    #         init_drivers.append(fut.result())
                    #     except Exception as e:
                    #         lines = traceback.format_exception(*sys.exc_info())
                    #         self.to_screen(f'[init_drivers][{futures[fut]}] {repr(e)} \n{"!!".join(lines)}')
                    init_drivers.append(self.get_driver(prof=prof))

                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')  
                    
                finally:
                    if init_drivers:
                        SeleniumInfoExtractor._USER_AGENT = init_drivers[0].execute_script("return navigator.userAgent")
                        # for driver in init_drivers:
                        #     SeleniumInfoExtractor._QUEUE.put_nowait(driver)
                        #     SeleniumInfoExtractor._MASTER_COUNT += 1
                        self.rm_driver(init_drivers[0])
                
             
                _headers = dict(httpx.Headers(SeleniumInfoExtractor._YTDL.params.get('http_headers')).copy())
                _headers.update({'user-agent': SeleniumInfoExtractor._USER_AGENT})
                
                SeleniumInfoExtractor._CLIENT_CONFIG.update({'timeout': httpx.Timeout(60, connect=60), 'limits': httpx.Limits(max_keepalive_connections=None, max_connections=None), 'headers': _headers, 'follow_redirects': True, 'verify': not SeleniumInfoExtractor._YTDL.params.get('nocheckcertificate', False)})
                #self.write_debug(SeleniumInfoExtractor._CLIENT_CONFIG)
                
                SeleniumInfoExtractor._FIREFOX_HEADERS['User-Agent'] = SeleniumInfoExtractor._CLIENT_CONFIG['headers']['user-agent']
                
                _config = SeleniumInfoExtractor._CLIENT_CONFIG.copy()
                SeleniumInfoExtractor._CLIENT = httpx.Client(timeout=_config['timeout'], limits=_config['limits'], headers=_config['headers'], follow_redirects=_config['follow_redirects'], verify=_config['verify'])
                SeleniumInfoExtractor._MASTER_INIT = True


    def _real_extract(self, url):
        """Real extraction process. Redefine in subclasses."""
        raise NotImplementedError('This method must be implemented by subclasses')
        
    def get_driver(self, prof=None, noheadless=False, host=None, port=None, msg=None, usequeue=False):        

        
       
        if usequeue:
        
            with SeleniumInfoExtractor._MASTER_LOCK:
            #self.write_debug(f"drivers qsize: {SeleniumInfoExtractor._QUEUE._qsize()}")
                if SeleniumInfoExtractor._QUEUE._qsize() > 0:
                    driver = SeleniumInfoExtractor._QUEUE.get()
                else:    
                    if SeleniumInfoExtractor._MASTER_COUNT < SeleniumInfoExtractor._MAX_NUM_WEBDRIVERS:
                        driver = self._get_driver(prof, noheadless, host, port, msg)
                        SeleniumInfoExtractor._MASTER_COUNT += 1                    
                    else:
                        driver = SeleniumInfoExtractor._QUEUE.get(block=True, timeout=600)            
    
        else: 

            driver = self._get_driver(prof, noheadless, host, port, msg)
             
        
 
        
        return driver
        
    def _get_driver(self, _prof, _noheadless, _host, _port, _msg):
        
        if _msg: pre = f'{_msg} '
        else: pre = ''
        
        tempdir = tempfile.mkdtemp(prefix='asyncall-') 
        if _prof:
            self.to_screen("FF profile for IG")
            res = shutil.copytree(SeleniumInfoExtractor._FF_PROF_IG, tempdir, dirs_exist_ok=True)
        else:           
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
    
    
    def start_browsermob(self, url):
        
        while True:
            _server_port = 18080 + SeleniumInfoExtractor._SERVER_NUM*100                 
            _server = Server(path="/Users/antoniotorres/Projects/async_downloader/browsermob-proxy-2.1.4/bin/browsermob-proxy", options={'port': _server_port})
            try:
                if _server._is_listening():
                    SeleniumInfoExtractor._SERVER_NUM += 1
                    if SeleniumInfoExtractor._SERVER_NUM == 25: raise Exception("mobproxy max tries")
                else:
                    _server.start({"log_path": "/dev", "log_file": "null"})
                    self.to_screen(f"[{url}] browsermob-proxy start OK on port {_server_port}")
                    SeleniumInfoExtractor._SERVER_NUM += 1
                    return (_server, _server_port)
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f'[{url}] {repr(e)} \n{"!!".join(lines)}')
                if _server.process: _server.stop()                   
                raise ExtractorError(f"[{url}] browsermob-proxy start error - {repr(e)}")
              
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

   
    def _get_extractor(self, url):
        
        ies = self._downloader._ies
        for ie_key, ie in ies.items():
            if ie.suitable(url):
                extractor = ie
                if ie_key == 'Generic': 
                    continue
                else:                    
                    break
        return extractor
        
    
    def _get_ie_name(self, url):    
        
        extractor = self._get_extractor(url)
        
        _url_str = self._get_url_print(url)
        
        extr_name = extractor.IE_NAME
        
        #self.to_screen(f"[get_extr_name]:{_url_str}:{extr_name}")
        return extr_name
    
    def _get_ie_key(self, url):    
        
        extractor = self._get_extractor(url)
        
        _url_str = self._get_url_print(url)
        
        extr_key = extractor.ie_key()
        
        #self.to_screen(f"[get_extr_key]:{_url_str}:{extr_key}")
        return extr_key
    
    def _get_url_print(self, url):
        if len(url) > 150:
            return(f'{url[:140]}...{url[-10:]}')
        else: return url
        
    
    def _is_valid(self, url, msg):
        
        def transp(func):
            return func
        
        def getter(x):
        
            value = try_get([v for k,v in SeleniumInfoExtractor._CONFIG_REQ.items() if x in k], lambda y: y[0]) 
            if value:
                return(value['ratelimit'].ratelimit(x, delay=True))
        
        if not url: 
            return False
        
        _url_str = self._get_url_print(url)
        
        if msg:
            _pre_str = f'[{msg}]:[{_url_str}]'
        else:
            _pre_str = f'[{_url_str}]'
            
        self.to_screen(f'[valid]{_pre_str} start checking')
        
        
        try:

            if any(_ in url for _ in ['twitter.com', 'sxyprn.net', 'gaypornmix.com', 'thisvid.com/embed', 'xtube.com', 'xtapes.to', 'gayforit.eu/playvideo.php']):
                self.to_screen(f'[valid]{_pre_str}:False')
                return False
            elif any(_ in url for _ in ['gayforit.eu/video']):
                self.to_screen(f'[valid]{_pre_str}:True')
                return True                
                
            else:  
                _extr_name = self._get_ie_name(url)
                if _extr_name == 'generic':
                    _decor = transp
                else:
                    _decor = getter(_extr_name) or transp
                
                @dec_on_exception
                @_decor
                def _throttle_isvalid(_url, method="GET"):
                    try:
                        return self.send_http_request(_url, _type=method, headers=SeleniumInfoExtractor._FIREFOX_HEADERS, msg=f'[valid]{_pre_str}')
                    except httpx.HTTPStatusError as e:
                        self.to_screen(f"[valid]{_pre_str}:{e}")
                        

                        
                
                res = _throttle_isvalid(url.replace("streamtape.com", "streamtapeadblock.art"), method="HEAD")
            
                if res:
                    # if (st_code:=res.status_code) >= 400: 
                    #     valid = False
                    #     self.to_screen(f'[valid]{_pre_str}:{st_code}:{valid}\n{res.request.headers}')
                        
                        
                    if res.headers.get('content-type') == "video/mp4":
                        valid = True
                        self.to_screen(f'[valid][{_pre_str}:video/mp4:{valid}')
                        
                    else:

                        webpage = try_get(_throttle_isvalid(url.replace("streamtape.com", "streamtapeadblock.art")), lambda x: x.text)
                        if not webpage: 
                            valid = False
                            self.to_screen(f'[valid]{_pre_str}:{valid} couldnt download webpage')
                        else:
                            valid = not any(_ in str(res.url) for _ in ['status=not_found', 'status=broken']) and not any(_ in webpage.lower() for _ in ['has been deleted', 'has been removed', 'was deleted', 'was removed', 'video unavailable', 'video is unavailable', 'video disabled', 'not allowed to watch', 'video not found', 'post not found', 'limit reached', 'xtube.com is no longer available', 'this-video-has-been-removed', 'has been flagged', 'embed-sorry'])
                        
                            self.to_screen(f'[valid]{_pre_str}:{valid} check with webpage content')
                
                else: 
                    valid = False
                    self.to_screen(f'[valid]{_pre_str}:{valid} couldnt send HEAD request')
                    
                return valid
        
        except Exception as e:
            self.report_warning(f'[valid]{_pre_str} error {repr(e)}')
            return False
    
    def send_http_request(self, url, _type="GET", data=None, headers=None, msg=None):        
        
        try:
            res = ""
            _msg_err = ""
            req = SeleniumInfoExtractor._CLIENT.build_request(_type, url, data=data, headers=headers)
            res = SeleniumInfoExtractor._CLIENT.send(req)
            
            res.raise_for_status()
            return res
        except Exception as e:
            _msg_err = repr(e)
            raise
        finally:
            if not msg: msg = f'[{self._get_url_print(url)}]'
            self.to_screen(f"[send_http_request][{msg}][{_type}] {res}:{_msg_err}")
    
    
    

            

    
    
