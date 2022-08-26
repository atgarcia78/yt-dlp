import shutil
import sys
import tempfile
import threading
import time
from urllib.parse import unquote, urlparse

import httpx
from httpx import HTTPStatusError, HTTPError, StreamError, ConnectError
from backoff import constant, on_exception
from pyrate_limiter import Duration, Limiter, RequestRate

from cs.threads import PriorityLock

from selenium.webdriver import Firefox, FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys

import re
import html
import json


import copy
import functools
import random

from ..utils import int_or_none, traverse_obj, try_get, classproperty
from .common import ExtractorError, InfoExtractor

import logging
logger = logging.getLogger("Commonwebdriver")


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

CONFIG_EXTRACTORS = {
    ('userload', 'evoload', 'highload',): {
                                            'ratelimit': limiter_15, 
                                            'maxsplits': 4},
                ('doodstream','vidoza',): {
                                            'ratelimit': limiter_5,
                                            'maxsplits': 2}, 
                ('tubeload', 'embedo',
                'thisvidgay','redload',
                'biguz', 'gaytubes',): {
                                            'ratelimit': limiter_0_5, 
                                            'maxsplits': 4},
    ('fembed', 'streamtape', 'gayforfans', 
     'gayguytop', 'upstream', 'videobin', 
                'gayforiteu', 'xvidgay',): {
                                            'ratelimit': limiter_1, 
                                            'maxsplits': 16},
          ('odnoklassniki', 'thisvid', 
           'gaystreamembed','pornhat', 
             'yourporngod', 'ebembed', 
            'gay0day', 'onlygayvideo',
            'txxx','thegay','homoxxx',
               'gaygo','pornone',): {
                                            'ratelimit': limiter_1, 
                                            'maxsplits': 16}
}

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
dec_on_exception3 = on_exception(constant, (TimeoutError, ExtractorError), max_tries=5, jitter=my_jitter2, raise_on_giveup=False, interval=10)
dec_retry = on_exception(constant, ExtractorError, max_tries=3, raise_on_giveup=False, interval=2)
dec_retry_raise = on_exception(constant, ExtractorError, max_tries=3, interval=10)
dec_retry_error = on_exception(constant, (HTTPError, StreamError), max_tries=3, jitter=my_jitter, raise_on_giveup=False, interval=10)

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
 
def _check_init(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not SeleniumInfoExtractor._MASTER_INIT:
            self._real_initialize()
        return func(self, *args, **kwargs)
    return wrapper

def transp(func):
    return func
        
def getter(x):
        
    value, key_text = try_get([(v,kt) for k,v in SeleniumInfoExtractor._CONFIG_REQ.items() if any(x==(kt:=_) for _ in k)], lambda y: y[0]) or ("","") 
    if value:
        return(value['ratelimit'].ratelimit(key_text, delay=True))
    else:
        return transp

def _limit(func):
    @functools.wraps(func)  
    def wrapper(self, *args, **kwargs):
        decor = getter(self.IE_NAME)
        with decor:
            return func(self, *args, **kwargs)
    return wrapper
    

class SeleniumInfoExtractor(InfoExtractor):
    
    _FF_PROF =  '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/ln3i0v51.default-release'
    
    _MASTER_INIT = False
    
    _MASTER_LOCK = threading.Lock()
    
    _YTDL = None
    _CLIENT_CONFIG = {}
    _CLIENT = None
    _CONFIG_REQ = copy.deepcopy(CONFIG_EXTRACTORS)
   
    _FIREFOX_HEADERS =  {      
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Pragma': 'no-cache', 
        'Cache-Control': 'no-cache', 
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
    
    @_check_init
    def _get_extractor(self, _args):

        if _args.startswith('http'):

            ies = SeleniumInfoExtractor._YTDL._ies
            for ie_key, ie in ies.items():
                if ie.suitable(_args):
                    if ie_key == 'Generic': 
                        continue
                    else:                    
                        break
        else:
            ie_key = _args       
        
        try:
            if (_extractor:=self._downloader.get_info_extractor(ie_key)):
                _extractor._real_initialize()
                return _extractor
        except Exception as e:
            self.logger_debug(f"extractor doesnt exist with ie_key {ie_key}")
        
    def _get_ie_name(self, url=None):    
        
        if url:
            extractor = self._get_extractor(url)        
            extr_name = extractor.IE_NAME       
            return extr_name.lower()
        else:
            return self.IE_NAME.lower()
    
    def _get_ie_key(self, url=None):    
        
        if url:
            extractor = self._get_extractor(url)        
            extr_key = extractor.ie_key()        
            return extr_key
        else:
            return self.ie_key()
        
    def _get_url_print(self, url):
        if len(url) > 150:
            return(f'{url[:140]}...{url[-10:]}')
        else: return url
   
    def close(self):        

        try:
            SeleniumInfoExtractor._CLIENT.close()
        except Exception:
            pass        
        SeleniumInfoExtractor._MASTER_INIT = False 


    def _real_initialize(self):

        try:        
            with SeleniumInfoExtractor._MASTER_LOCK:
                if not SeleniumInfoExtractor._MASTER_INIT:                    
                    SeleniumInfoExtractor._YTDL = self._downloader                    
                    SeleniumInfoExtractor._YTDL.params['sem'] = {} # for the ytdlp cli                    
                    SeleniumInfoExtractor._YTDL.params['lock'] = SeleniumInfoExtractor._MASTER_LOCK
                    _headers = copy.deepcopy(SeleniumInfoExtractor._YTDL.params.get('http_headers'))
                    SeleniumInfoExtractor._CLIENT_CONFIG.update({'timeout': httpx.Timeout(20), 
                                                                 'limits': httpx.Limits(max_keepalive_connections=None, max_connections=None), 
                                                                 'headers': _headers, 'follow_redirects': True, 
                                                                 'verify': not SeleniumInfoExtractor._YTDL.params.get('nocheckcertificate', False)})
                    
                    #no verifciamos nunca el cert
                    SeleniumInfoExtractor._CLIENT_CONFIG.update({'verify': False})
                    
                    _config = copy.deepcopy(SeleniumInfoExtractor._CLIENT_CONFIG)
                    SeleniumInfoExtractor._CLIENT = httpx.Client(timeout=_config['timeout'], limits=_config['limits'], headers=_config['headers'], 
                                                                 follow_redirects=_config['follow_redirects'], verify=_config['verify'])
                    
                    SeleniumInfoExtractor._MASTER_INIT = True
        except Exception as e:
            logger.exception(e)

        
    def get_driver(self, noheadless=False, devtools=False, host=None, port=None):        

        with SeleniumInfoExtractor._MASTER_LOCK:
            driver = self._get_driver(noheadless, devtools, host, port)
        return driver
        
    def _get_driver(self, noheadless, devtools, host, port):        
        
        tempdir = tempfile.mkdtemp(prefix='asyncall-') 
        shutil.rmtree(tempdir, ignore_errors=True) 
        res = shutil.copytree(SeleniumInfoExtractor._FF_PROF, tempdir, dirs_exist_ok=True)            
        if res != tempdir:
            raise ExtractorError("error when creating profile folder")
        
        opts = FirefoxOptions()
        
        if not noheadless:
            opts.add_argument("--headless")
        
        if devtools:
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
        
        # if not host and not port:
        #     if SeleniumInfoExtractor._YTDL:
        #         if (proxy:=SeleniumInfoExtractor._YTDL.params.get('proxy')):
        #             proxy = proxy.replace('https://', '').replace('http://', '')
        #             host = proxy.split(":")[0]
        #             port = proxy.split(":")[1]
                
        if host and port:
            opts.set_preference("network.proxy.type", 1)
            opts.set_preference("network.proxy.http",host)
            opts.set_preference("network.proxy.httpport",int(port))
            opts.set_preference("network.proxy.https",host)
            opts.set_preference("network.proxy.httpsport",int(port))
            opts.set_preference("network.proxy.ssl",host)
            opts.set_preference("network.proxy.sslport",int(port))
            opts.set_preference("network.proxy.ftp",host)
            opts.set_preference("network.proxy.ftpport",int(port))
            opts.set_preference("network.proxy.socks",host)
            opts.set_preference("network.proxy.socksport",int(port))
        
        else:
            opts.set_preference("network.proxy.type", 0)            
                
        opts.set_preference("dom.webdriver.enabled", False)
        opts.set_preference("useAutomationExtension", False)
        
        serv = Service(log_path="/dev/null")
        
        @dec_retry 
        def return_driver():    
            _driver = None
            try:                
                _driver = Firefox(service=serv, options=opts)                
                _driver.maximize_window()                
                self.wait_until(_driver, 0.5)                
                return _driver                
            except Exception as e:  
                if _driver: 
                    _driver.quit()
                if 'Status code was: 69' in repr(e):                    
                    self.report_warning(f'Firefox needs to be relaunched')
                    return                    
                else: raise ExtractorError("firefox failed init")
                
        
        driver = return_driver()
        if not driver:
            shutil.rmtree(tempdir, ignore_errors=True)
        
        return driver

    @classmethod
    def rm_driver(cls, driver):
        
        tempdir = traverse_obj(driver.caps, 'moz:profile')        
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
                
    def scan_for_json(self, _driver, _link, _all=False, timeout=60):

        _hints = self.scan_for_request(_driver, _link, _all, timeout)

        logger.debug(f"[scan_json] {_hints}")
        
        func_getter = lambda x: json.loads(re.sub('[\t\n]', '', html.unescape(x[1]))) if x[1] else ""            
        
        if not _all:
            _info_json = try_get(_hints, func_getter)
            return(_info_json)
        else:            
            if _hints:
                _list_info_json = []                        
                for el in _hints:
                    _info_json = try_get(el, func_getter)
                    if _info_json: 
                        _list_info_json.append(_info_json)
                
                return(_list_info_json)
    
    def wait_until(self, driver, timeout=60, method=ec.title_is("DUMMYFORWAIT"), poll_freq=0.5):
        try:
            el = WebDriverWait(driver, timeout, poll_frequency=poll_freq).until(method)
        except Exception as e:
            el = None
                        
        return el 
    
    @_check_init
    def get_info_for_format(self, url, **kwargs):
        
        try:
            res = None
            _msg_err = ""
            client = kwargs.get('client', None)
            headers = kwargs.get('headers', None)
            if client:
                res = client.head(url, headers=headers)
            else:
                res = SeleniumInfoExtractor._CLIENT.head(url, headers=headers)            
            res.raise_for_status()
            _filesize = int_or_none(res.headers.get('content-length'))
            _url = unquote(str(res.url))
            if _filesize:
                return ({'url': _url, 'filesize': _filesize})
        except Exception as e:
            _msg_err = repr(e)
            if res and res.status_code == 404:           
                res.raise_for_status()
            elif res and res.status_code == 503:
                raise StatusError503(repr(e))            
            elif isinstance(e, ConnectError):
                if 'errno 61' in _msg_err.lower():
                    raise
                else:
                    raise ExtractorError(_msg_err)
            elif not res:
                raise TimeoutError(repr(e))
            else:
                raise ExtractorError(_msg_err)                
        finally:                
            self.logger_debug(f"[get_info_for_format][{self._get_url_print(url)}] {res}:{_msg_err}")   

    @_check_init
    def _is_valid(self, url, msg=None):
        
        if not url: 
            return False
        
        _pre_str = f'[{self._get_url_print(url)}]'
        if msg:
            _pre_str = f'[{msg}]{_pre_str}'            
            
        self.logger_debug(f'[valid]{_pre_str} start checking')
        
        
        # def transp(func):
        #     return func
        
        # def getter(x):        
        #     value, key_text = try_get([(v,kt) for k,v in SeleniumInfoExtractor._CONFIG_REQ.items() if any(x==(kt:=_) for _ in k)], lambda y: y[0]) or ("","") 
        #     if value:
        #         return(value['ratelimit'].ratelimit(key_text, delay=True))
        try:

            if any(_ in url for _ in ['rawassaddiction.blogspot', 'twitter.com', 'sxyprn.net', 'gaypornmix.com', 'thisvid.com/embed', 'xtube.com', 'xtapes.to', 
                                      'gayforit.eu/playvideo.php', '/noodlemagazine.com/player', 'pornone.com/embed/']):
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
                def _throttle_isvalid(_url, short):
                    try:
                        _headers = copy.deepcopy(SeleniumInfoExtractor._FIREFOX_HEADERS)
                        if short:
                            _headers.update({'Range': 'bytes=0-100'})
                        res = self.send_http_request(_url, _type="GET", headers=_headers, msg=f'[valid]{_pre_str}')
                        if not res: 
                            return ""
                        else:
                            return res
                    except (HTTPStatusError, ConnectError) as e:
                        self.report_warning(f"[valid]{_pre_str}:{e}")
 
                res = _throttle_isvalid(url, True)
            
                if res:                        
                    if res.headers.get('content-type') == "video/mp4":
                        valid = True
                        self.logger_debug(f'[valid][{_pre_str}:video/mp4:{valid}')
                    
                    elif not urlparse(str(res.url)).path:
                        valid = False
                        self.logger_debug(f'[valid][{_pre_str}] not path in reroute url {str(res.url)}:{valid}')
                    else:
                        webpage = try_get(_throttle_isvalid(url, False), lambda x: html.unescape(x.text) if x else None)
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
    
    @_check_init
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

            req = SeleniumInfoExtractor._CLIENT.build_request(_type, url, data=data, headers=headers)
            res = SeleniumInfoExtractor._CLIENT.send(req)
            if res:
                res.raise_for_status()
                return res
            else: return ""
        except Exception as e:            
            _msg_err = repr(e)
            if res and res.status_code == 404:           
                res.raise_for_status()
            elif res and res.status_code == 503:
                raise StatusError503(repr(e))
            elif isinstance(e, ConnectError):
                if 'errno 61' in _msg_err.lower():
                    
                    raise
                else:
                    raise ExtractorError(_msg_err)   
            elif not res:
                raise TimeoutError(_msg_err)
                         
            else:
                raise ExtractorError(_msg_err) 
        finally:                
            self.logger_debug(f"{premsg} {res}:{_msg_err}")