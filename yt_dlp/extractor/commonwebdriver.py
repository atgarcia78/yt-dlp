from __future__ import unicode_literals

import shutil
import sys
import tempfile
import threading
import time
import traceback
from queue import Empty, Queue
from urllib.parse import unquote

import httpx
from httpx import HTTPStatusError
from backoff import constant, on_exception
from pyrate_limiter import Duration, Limiter, RequestRate
from selenium.webdriver import Firefox, FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys

import re
import html

import copy
import functools
import random

from ..utils import int_or_none, try_get, classproperty
from .common import ExtractorError, InfoExtractor

limiter_0_005 = Limiter(RequestRate(1, 0.005 * Duration.SECOND))
limiter_0_07 = Limiter(RequestRate(1, 0.07 * Duration.SECOND))
limiter_0_05 = Limiter(RequestRate(1, 0.05 * Duration.SECOND))
limiter_0_01 = Limiter(RequestRate(1, 0.01 * Duration.SECOND))
limiter_0_1 = Limiter(RequestRate(1, 0.1 * Duration.SECOND))
limiter_0_5 = Limiter(RequestRate(1, 0.5 * Duration.SECOND))
limiter_1 = Limiter(RequestRate(1, Duration.SECOND))
limiter_1_5 = Limiter(RequestRate(1, 1.5 * Duration.SECOND))
limiter_2 = Limiter(RequestRate(1, 2 * Duration.SECOND))
limiter_5 = Limiter(RequestRate(1, 5 * Duration.SECOND))
limiter_7 = Limiter(RequestRate(1, 7 * Duration.SECOND))
limiter_10 = Limiter(RequestRate(1, 10 * Duration.SECOND))
limiter_15 = Limiter(RequestRate(1, 15 * Duration.SECOND))

def my_jitter(value: float) -> float:

    return int(random.uniform(value, value*1.25))

def my_jitter2(value: float) -> float:

    return int(random.uniform(value, value*2))

class StatusError503(Exception):
    """Error during info extraction."""

    def __init__(self, msg):
        
        super().__init__(msg)

        self.exc_info = sys.exc_info()  # preserve original exception

dec_on_exception = on_exception(constant, Exception, max_tries=3, jitter=my_jitter, raise_on_giveup=False, interval=10)
dec_on_exception2 = on_exception(constant, StatusError503, max_time=300, jitter=my_jitter2, raise_on_giveup=False, interval=15)
dec_on_exception3 = on_exception(constant, (TimeoutError, ExtractorError), max_tries=3, jitter=my_jitter, raise_on_giveup=False, interval=10)


import logging
logger = logging.getLogger("Commonwebdriver")


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
    
    _FF_PROF =  '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/ln3i0v51.default-release'
    _MASTER_LOCK = threading.Lock()
    _QUEUE = Queue()
    _MASTER_COUNT = 0
    _YTDL = None
    #_USER_AGENT = None
    _CLIENT_CONFIG = {}
    _CLIENT = None
    _CONFIG_REQ = {
                    ('userload', 'evoload', 'highload',): {
                                                            'ratelimit': limiter_15, 
                                                            'maxsplits': 4},
                    ('doodstream','vidoza',): {
                                        'ratelimit': limiter_5,
                                        'maxsplits': 2}, 
                    ('tubeload', 'embedo',): {
                                        'ratelimit': limiter_5, 
                                        'maxsplits': 4},
                    ('fembed', 'streamtape', 'gayforfans', 'gayguytop', 'upstream', 'videobin', 'xvidgay',): {
                        'ratelimit': limiter_5, 'maxsplits': 16}, 
               }
    _MASTER_INIT = False
    _MAX_NUM_WEBDRIVERS = 0
    _SERVER_NUM = 0
    _FIREFOX_HEADERS =  {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'accept-encoding': 'gzip, deflate',
        'accept-language': 'en,es-ES;q=0.5',        
        'connection': 'keep-alive',        
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1', 
    }
    
    @classproperty
    def IE_NAME(cls):
        return cls.__name__[:-2].lower()
    
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
                _logger.debug(f"[debug+][{cls.__name__[:-2].lower()}]{msg}")
            else:
                SeleniumInfoExtractor._YTDL.to_screen(f"[debug][{cls.__name__[:-2].lower()}]{msg}")
    
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
        
        tempdir = try_get(driver.caps, lambda x: x.get('moz:profile', None))
        
        try:
            driver.close()
        except Exception:
            pass
        
        try:
            driver.quit()
        except Exception:
            pass       
        finally:            
            if tempdir: shutil.rmtree(tempdir, ignore_errors=True)
            with SeleniumInfoExtractor._MASTER_LOCK:
                SeleniumInfoExtractor._MASTER_COUNT -= 1
        
    def _real_initialize(self):
        
        import logging
        logger = logging.getLogger("Commonwebdriver")
        
        try:  
        
            with SeleniumInfoExtractor._MASTER_LOCK:
                if not SeleniumInfoExtractor._MASTER_INIT:
                    
                    SeleniumInfoExtractor._YTDL = self._downloader
                    SeleniumInfoExtractor._MAX_NUM_WEBDRIVERS = SeleniumInfoExtractor._YTDL.params.get('winit', 5)

                    #SeleniumInfoExtractor._USER_AGENT = SeleniumInfoExtractor._YTDL.params.get('user_agent')

                    _headers = copy.deepcopy(SeleniumInfoExtractor._YTDL.params.get('http_headers'))
                    
                    #print(f"SEL HEADERS: {_headers}")

                    SeleniumInfoExtractor._CLIENT_CONFIG.update({'timeout': httpx.Timeout(20), 'limits': httpx.Limits(max_keepalive_connections=None, max_connections=None), 'headers': _headers, 'follow_redirects': True, 'verify': not SeleniumInfoExtractor._YTDL.params.get('nocheckcertificate', False)})
                    
                    #self.write_debug(SeleniumInfoExtractor._CLIENT_CONFIG)
                    
                    #SeleniumInfoExtractor._FIREFOX_HEADERS['User-Agent'] = SeleniumInfoExtractor._USER_AGENT
                    
                    SeleniumInfoExtractor._CLIENT_CONFIG.update({'verify': False})
                    
                    _config = SeleniumInfoExtractor._CLIENT_CONFIG.copy()
                    SeleniumInfoExtractor._CLIENT = httpx.Client(timeout=_config['timeout'], limits=_config['limits'], headers=_config['headers'], follow_redirects=_config['follow_redirects'], verify=_config['verify'])
                    SeleniumInfoExtractor._MASTER_INIT = True
                    
                    self.logger_debug(SeleniumInfoExtractor._CLIENT.headers)
                    
        except Exception as e:
            logger.exception(e)

    def _real_extract(self, url):
        """Real extraction process. Redefine in subclasses."""
        raise NotImplementedError('This method must be implemented by subclasses')
        
    def get_driver(self, noheadless=False, devtools=False, host=None, port=None, usequeue=False):        


        driver = None
        
        if usequeue:
        
            with SeleniumInfoExtractor._MASTER_LOCK:
                if SeleniumInfoExtractor._QUEUE._qsize() > 0:
                    driver = SeleniumInfoExtractor._QUEUE.get()
                else:    
                    if SeleniumInfoExtractor._MASTER_COUNT < SeleniumInfoExtractor._MAX_NUM_WEBDRIVERS:
                        driver = self._get_driver(noheadless, host, port)
                        SeleniumInfoExtractor._MASTER_COUNT += 1                    
                    else:
                        driver = SeleniumInfoExtractor._QUEUE.get(block=True, timeout=600)            
    
        else: 

            with SeleniumInfoExtractor._MASTER_LOCK:
                driver = self._get_driver(noheadless, devtools, host, port)
                SeleniumInfoExtractor._MASTER_COUNT += 1    

            

        return driver
        
    def _get_driver(self, _noheadless, _devtools, _host, _port):
        
        
        tempdir = tempfile.mkdtemp(prefix='asyncall-') 
        
        shutil.rmtree(tempdir, ignore_errors=True) 
        res = shutil.copytree(SeleniumInfoExtractor._FF_PROF, tempdir, dirs_exist_ok=True)            
        
        if res != tempdir:
            raise ExtractorError("error when creating profile folder")
        
        opts = FirefoxOptions()
        
        if not _noheadless:
            opts.add_argument("--headless")
        
        if _devtools:
            opts.add_argument("--devtools")
            opts.set_preference("devtools.toolbox.selectedTool", "netmonitor")
            opts.set_preference("devtools.netmonitor.persistlog", True)
            opts.set_preference("devtools.debugger.skip-pausing", True);
        
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
                
               
                return driver
                
            except Exception as e:
                n += 1
                if driver: 
                    driver.quit()
                    driver = None
                if 'Status code was: 69' in repr(e):
                    shutil.rmtree(tempdir, ignore_errors=True)
                    self.report_warning(f'Firefox needs to be relaunched')
                    raise ExtractorError(f'Firefox needs to be relaunched')
                if n == 3:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
                    shutil.rmtree(tempdir, ignore_errors=True)  
                    raise ExtractorError(repr(e))

    def put_in_queue(self, driver):
        SeleniumInfoExtractor._QUEUE.put_nowait(driver)
    
    # def start_browsermob(self):
        
    #     with SeleniumInfoExtractor._MASTER_LOCK:
    #         while True:
    #             _server_port = 18080 + SeleniumInfoExtractor._SERVER_NUM*1000                 
    #             _server = Server(path="/Users/antoniotorres/Projects/async_downloader/browsermob-proxy-2.1.4/bin/browsermob-proxy", options={'port': _server_port})
    #             try:
    #                 if _server._is_listening():
    #                     SeleniumInfoExtractor._SERVER_NUM += 1
    #                     if SeleniumInfoExtractor._SERVER_NUM == 5: raise Exception("mobproxy max tries")
    #                 else:
    #                     _server.start({"log_path": "/dev", "log_file": "null"})
    #                     self.to_screen(f"[start_browsermob] start OK on port {_server_port}")
    #                     SeleniumInfoExtractor._SERVER_NUM += 1
    #                     return (_server, _server_port)
    #             except Exception as e:
    #                 lines = traceback.format_exception(*sys.exc_info())
    #                 self.to_screen(f'[start_browsermob] start error {repr(e)} \n{"!!".join(lines)}')
    #                 if _server.process:
    #                     self.stop_browsermob(_server)
                    
    # def stop_browsermob(self, server, timeout=30):
        
    #     _pgid = os.getpgid(server.process.pid)
    #     self.logger_info(f"[stop_server] pgid {_pgid}")
        
    #     _pids = re.findall(r'(\d+)\n', subprocess.run(["ps", "-g", str(_pgid), "-o" , "pid"], encoding='utf-8', capture_output=True).stdout)
        
    #     self.logger_info(f"[stop_server] procs with pgid: {_pids}")
        
    #     if not _pids: return
        
    #     os.killpg(_pgid, signal.SIGTERM)
        
    #     server.process.wait()
        
    #     _started = time.monotonic()
        
    #     while(True):
                            
    #         if not psutil.pid_exists(int(_pids[-1])):
    #             self.logger_info(f"[stop_server] {_pids[-1]} term")                                   
    #             break
            
    #         time.sleep(0.25)
    #         if (time.monotonic() - _started) > timeout:
    #             self.logger_info(f"[stop_server] timeout")
    #             break

    def scan_for_request(self, driver, _link, _all=False, timeout=60):

       
        def _get_har():
            return (driver.execute_async_script(
                        "HAR.triggerExport().then(arguments[0]);")).get('entries')

        _list_hints = []
                
        _started = time.monotonic()        
        while(True):

            _har = _get_har()
 
            for entry in _har:

                if re.search(_link, (_url:=entry['request']['url'])):
                    if (_resp_content:=entry.get('response', {}).get('content', {}).get('text', "")):
                        _hint = (_url, _resp_content)
                        if not _all: return(_hint)   
                        else:                    
                            _list_hints.append(_hint)
                    
                                        
            
            if _all and _list_hints: 
                return(_list_hints)
            
            if (time.monotonic() - _started) >= timeout:
                if _all: return([])
                else: return(None,None)
            else:
                time.sleep(0.5)
                
    
    def scan_for_json(self, _driver, _link, _all=False):

        import logging
        import json
        import html
        
        logger = logging.getLogger("YTDL_SUPPORT")
        
        _hints = self.scan_for_request(_driver, _link, _all)
        
        logger.debug(f"[scan_json] {_hints}")
        
        if not _all:
            _info_json = try_get(_hints, lambda x: json.loads(re.sub('[\t\n]', '', html.unescape(x[1]))) if x[1] else "")
            return(_info_json)
        else:            
            if _hints:
                _list_info_json = []           
                        
                for el in _hints:
                    _info_json = try_get(el, lambda x: json.loads(re.sub('[\t\n]', '', html.unescape(x[1]))) if x[1] else "")
                    if _info_json: 
                        _list_info_json.append(_info_json)
                
                return(_list_info_json)
    
    
    
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
    
    def get_info_for_format(self, url, **kwargs):
        
        try:
            res = None
            _msg_err = ""
            client = kwargs.get('client', None)
            headers = kwargs.get('headers', None)
            if client:
                res = client.head(url, headers=headers)
            else:
                # _config = copy.deepcopy(SeleniumInfoExtractor._CLIENT_CONFIG)
                # if not verify and _config['verify']:

                #     if headers: _config['headers'].update(headers)
                #     res = httpx.head(url, verify=False, timeout=_config['timeout'], headers=_config['headers'], follow_redirects=_config['follow_redirects'])
                # else:    
                #     res = SeleniumInfoExtractor._CLIENT.head(url, headers=headers)
                res = SeleniumInfoExtractor._CLIENT.head(url, headers=headers)
            res.raise_for_status()

            _filesize = int_or_none(res.headers.get('content-length'))
            _url = unquote(str(res.url))
            if _filesize:
                return ({'url': _url, 'filesize': _filesize})
            
        # except Exception as e:
        #     if not res:
        #         self.logger_debug(f"{repr(e)}")

        #     else:
        #         self.logger_debug(f"{repr(e)} {res.request} \n{res.request.headers}")
        #         if res.status_code == 404:
        #             res.raise_for_status()
                
        #     raise ExtractorError(repr(e))
        except Exception as e:
            _msg_err = repr(e)
            if res and res.status_code == 404:           
                res.raise_for_status()
            elif res and res.status_code == 503:
                raise StatusError503(repr(e))
            elif not res:
                raise TimeoutError(repr(e))
            else:
                raise ExtractorError(_msg_err)                
        finally:                
            self.logger_debug(f"[get_info_for_format][{self._get_url_print(url)}] {res}:{_msg_err}")   


    
    def _check_init(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if not SeleniumInfoExtractor._MASTER_INIT:
                self._real_initialize()
            return func(self, *args, **kwargs)
        return wrapper
        
    @_check_init
    def _get_extractor(self, url):
        
        # if not SeleniumInfoExtractor._MASTER_INIT:
        #     self._real_initialize()
        ies = SeleniumInfoExtractor._YTDL._ies
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
        
        #_url_str = self._get_url_print(url)
        
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
        
    def _is_valid(self, url, msg=None):
        
        def transp(func):
            return func
        
        def getter(x):
        
            value, key_text = try_get([(v,kt) for k,v in SeleniumInfoExtractor._CONFIG_REQ.items() if any(x in (kt:=_) for _ in k)], lambda y: y[0]) or ("","") 
            if value:
                return(value['ratelimit'].ratelimit(key_text, delay=True))
        
        if not url: 
            return False
        
        _url_str = self._get_url_print(url)
        
        if msg:
            _pre_str = f'[{msg}]:[{_url_str}]'
        else:
            _pre_str = f'[{_url_str}]'
            
        self.logger_debug(f'[valid]{_pre_str} start checking')
        
        
        try:

            if any(_ in url for _ in ['twitter.com', 'sxyprn.net', 'gaypornmix.com', 'thisvid.com/embed', 'xtube.com', 'xtapes.to', 'gayforit.eu/playvideo.php']):
                self.logger_debug(f'[valid]{_pre_str}:False')
                return False
            elif any(_ in url for _ in ['gayforit.eu/video']):
                self.logger_debug(f'[valid]{_pre_str}:True')
                return True                
                
            else:  
                _extr_name = self._get_ie_name(url).lower()
                if _extr_name in ['xhamster', 'xhamsterembed']:
                    return True
                if _extr_name == 'generic':
                    _decor = transp
                else:
                    _decor = getter(_extr_name) or transp
                
                @dec_on_exception3
                @dec_on_exception2
                @_decor
                def _throttle_isvalid(_url, method="GET"):
                    try:
                        res = self.send_http_request(_url, _type=method, headers=SeleniumInfoExtractor._FIREFOX_HEADERS, msg=f'[valid]{_pre_str}')
                        if not res: 
                            return ""
                        else:
                            return res
                    except HTTPStatusError as e:
                        self.report_warning(f"[valid]{_pre_str}:{e}")
                        #logger.exception(repr(e))
                        #return ""
 
                res = _throttle_isvalid(url.replace("streamtape.com", "streamtapeadblock.art"), method="HEAD")
            
                if res:
                        
                        
                    if res.headers.get('content-type') == "video/mp4":
                        valid = True
                        self.logger_debug(f'[valid][{_pre_str}:video/mp4:{valid}')
                        
                    else:

                        webpage = try_get(_throttle_isvalid(url.replace("streamtape.com", "streamtapeadblock.art")), lambda x: html.unescape(x.text) if x else None)
                        if not webpage: 
                            valid = False
                            self.logger_debug(f'[valid]{_pre_str}:{valid} couldnt download webpage')
                        else:
                            valid = not any(_ in str(res.url) for _ in ['status=not_found', 'status=broken']) and not any(_ in webpage.lower() for _ in ['has been deleted', 'has been removed', 'was deleted', 'was removed', 'video unavailable', 'video is unavailable', 'video disabled', 'not allowed to watch', 'video not found', 'post not found', 'limit reached', 'xtube.com is no longer available', 'this-video-has-been-removed', 'has been flagged', 'embed-sorry'])
                        
                            self.logger_debug(f'[valid]{_pre_str}:{valid} check with webpage content')
                
                else: 
                    valid = False
                    self.logger_debug(f'[valid]{_pre_str}:{valid} couldnt send HEAD request')
                    
                return valid
        
        except Exception as e:
            self.report_warning(f'[valid]{_pre_str} error {repr(e)}')
            logger.exception(e)
            return False
    
    def send_http_request(self, url, **kwargs):        
        
        try:
            res = ""
            _msg_err = ""
            _type = kwargs.get('_type', "GET")
            headers = kwargs.get('headers', None)
            data = kwargs.get('data', None)
            msg = kwargs.get('msg', None)
            premsg = f'[send_http_request][{self._get_url_print(url)}][{_type}]'
            if msg: 
                premsg = f'{msg}{premsg}'           

            #print(f"HEADERS: {headers}")
            req = SeleniumInfoExtractor._CLIENT.build_request(_type, url, data=data, headers=headers)
            res = SeleniumInfoExtractor._CLIENT.send(req)
            if res:
                res.raise_for_status()
                return res
            else: return ""
        except Exception as e:
            
            _msg_err = repr(e)
            #logger.exception(_msg_err)
            if res and res.status_code == 404:           
                res.raise_for_status()
            elif res and res.status_code == 503:
                raise StatusError503(repr(e))
            elif not res:
                raise TimeoutError(_msg_err)
            else:
                raise ExtractorError(_msg_err) 
        finally:                
            self.logger_debug(f"{premsg} {res}:{_msg_err}")
            
                   
                
         

    
    
    

            

    
    
