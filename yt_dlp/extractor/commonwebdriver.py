import copy
import functools
import html
import json
import logging
import random
import re
import shutil
import sys
import tempfile
import time
from threading import Event, Lock
from urllib.parse import unquote, urlparse

from backoff import constant, on_exception
from httpx import (
    Client,
    ConnectError,
    HTTPError,
    HTTPStatusError,
    Limits,
    StreamError,
    Timeout,
)
from pyrate_limiter import Duration, Limiter, RequestRate
from selenium.webdriver import Firefox, FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import WebDriverException, TimeoutException

from .common import ExtractorError, InfoExtractor
from ..utils import classproperty, int_or_none, traverse_obj, try_get, unsmuggle_url, ReExtractInfo

from typing import (Any, Callable, Coroutine, Dict, Generator, Sequence, Tuple,
                    TypeVar, Union)

T = TypeVar("T")
_MaybeSequence = Union[T, Sequence[T]]
_MaybeCallable = Union[T, Callable[[], T]]

logger = logging.getLogger("Commonwebdriver")

limiter_non = Limiter(RequestRate(10000, 0))
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

def my_limiter(value: float) -> Limiter:
    return Limiter(RequestRate(1, value*Duration.SECOND))

def my_jitter(value: float) -> float:

    return int(random.uniform(value, value*1.25))


def my_dec_on_exception(exception: _MaybeSequence[Type[Exception]], max_tries: Optional[_MaybeCallable[int]] = None, my_jitter: bool = False, raise_on_giveup: bool = True, interval: int=1):
    if not my_jitter: _jitter = None
    else: _jitter = my_jitter
    return on_exception(constant, exception, max_tries=max_tries, jitter=_jitter, raise_on_giveup=raise_on_giveup, interval=interval)



class StatusError503(Exception):
    """Error during info extraction."""

    def __init__(self, msg, exc_info=None):
        
        super().__init__(msg)

        self.exc_info = exc_info
        
class StatusStop(Exception):
    """Error during info extraction."""

    def __init__(self, msg, exc_info=None):
        
        super().__init__(msg)

        self.exc_info = exc_info

dec_on_exception = on_exception(constant, Exception, max_tries=3, jitter=my_jitter, raise_on_giveup=False, interval=10)

dec_on_exception2 = on_exception(constant, StatusError503, max_time=300, jitter=my_jitter, raise_on_giveup=False, interval=15)
dec_on_exception3 = on_exception(constant, (TimeoutError, ExtractorError), max_tries=3, jitter=my_jitter, raise_on_giveup=False, interval=0.1)
dec_retry = on_exception(constant, ExtractorError, max_tries=3, raise_on_giveup=False, interval=2)
dec_retry_raise = on_exception(constant, ExtractorError, max_tries=3, interval=10)
dec_retry_error = on_exception(constant, (HTTPError, StreamError), max_tries=3, jitter=my_jitter, raise_on_giveup=False, interval=10)

dec_on_driver_timeout = on_exception(constant, TimeoutException, max_tries=2, raise_on_giveup=True, interval=5)
dec_on_reextract = on_exception(constant, ReExtractInfo, max_tries=3, jitter=my_jitter, raise_on_giveup=True, interval=10)

CONFIG_EXTRACTORS = {
                ('userload', 'evoload',): {
                                            'ratelimit': limiter_5, 
                                            'maxsplits': 4},
                ('doodstream','vidoza',): {
                                            'ratelimit': limiter_1,
                                            'maxsplits': 2}, 
      ('highload', 'tubeload', 'embedo',
                 'thisvidgay','redload',
                   'biguz', 'gaytubes',): {
                                            'ratelimit': limiter_0_1, 
                                            'maxsplits': 4},
      ('boyfriendtv', 'nakedswordscene',): {'ratelimit': limiter_0_1, 
                                            'maxsplits': 16},
                     ('nakedswordscene',): {'ratelimit': limiter_0_1,
                                            'maxsplits': 16,
                                            'ratelimit': 7*1048576},
    ('videovard', 'fembed', 'streamtape',
           'gaypornvideos', 'gayforfans', 
      'gayguytop','upstream', 'videobin',
              'gayforiteu', 'xvidgay',): {
                                            'ratelimit': limiter_1, 
                                            'maxsplits': 16},
            ('odnoklassniki', 'thisvid',
             'gaystreamembed','pornhat',
               'yourporngod', 'ebembed',
              'gay0day', 'onlygayvideo',
              'txxx','thegay','homoxxx',
                      'youporn','gaygo',
               'youporngay', 'streamsb',
                'hexupload','pornone',): {
                                            'ratelimit': limiter_1, 
                                            'maxsplits': 16}
}


class scroll:
    '''
        To use as a predicate in the webdriver waits to scroll down to the end of the page
        when the page has an infinite scroll where it is adding new elements dynamically
    '''
    def __init__(self, wait_time=2):
        self.wait_time = wait_time
        
    def __call__(self, driver):
        el_footer = driver.find_elements(By.CSS_SELECTOR, "div#footer")
        if el_footer:
            driver.execute_script("window.scrollTo(arguments[0]['x'], arguments[0]['y']);", el_footer[0].location)
            return True
        
        else:
            last_height = driver.execute_script("return document.body.scrollHeight")
            time_start = time.monotonic()
            while((time.monotonic() - time_start) <= self.wait_time):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height: return True
            else: return False

class checkStop:

    def __init__(self, checkstop):
        self.checkstop = checkstop
    def __call__(self, driver):

        self.checkstop()
        return False                
  
def _check_init(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self._CLIENT:
            self._real_initialize()
        return func(self, *args, **kwargs)
    return wrapper

def getter(x):
    
    if x != 'generic':    
        value, key_text = try_get([(v,kt) for k,v in SeleniumInfoExtractor._CONFIG_REQ.items() if any(x==(kt:=_) for _ in k)], lambda y: y[0]) or ("","") 
        if value:
            return(value['ratelimit'].ratelimit(key_text, delay=True))
    
    return limiter_non.ratelimit("nonlimit", delay=True)


class SeleniumInfoExtractor(InfoExtractor):
    
    _FF_PROF =  '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/b33yk6rw.selenium'
    
    _MASTER_LOCK = Lock()
    
    _YTDL = None
    
    _CONFIG_REQ = CONFIG_EXTRACTORS.copy()
   
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
        if cls._YTDL:
            if (_logger:=cls._YTDL.params.get('logger')):
                _logger.info(f"[{cls.__name__[:-2].lower()}]{msg}")
            else:
                cls._YTDL.to_screen(f"[{cls.__name__[:-2].lower()}]{msg}")
        
    @classmethod       
    def logger_debug(cls, msg):
        if cls._YTDL:
            if (_logger:=cls._YTDL.params.get('logger')):
                _logger.debug(f"[debug+][{cls.__name__[:-2].lower()}]{msg}")
            else:
                cls._YTDL.to_screen(f"[debug][{cls.__name__[:-2].lower()}]{msg}")
    
    def _get_extractor(self, _args):

        if _args.startswith('http'):

            ies = self._YTDL._ies
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
                _extractor._ready = False
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
            self._CLIENT.close()
        except Exception:
            pass        


    @classmethod
    def suitable(cls, url):
        """Receives a URL and returns True if suitable for this IE."""
        # This function must import everything it needs (except other extractors),
        # so that lazy_extractors works correctly
        return cls._match_valid_url(url.split("#__youtubedl_smuggle=")[0]) is not None

    
    def initialize(self):

        self._ready = False        
        super().initialize()

    def _real_initialize(self):


        try:        
            with SeleniumInfoExtractor._MASTER_LOCK:
                if not SeleniumInfoExtractor._YTDL or SeleniumInfoExtractor._YTDL != self._downloader:                    
                    if SeleniumInfoExtractor._YTDL:
                        if not self._downloader.params.get('stop_dl'):
                            self._downloader.params['stop_dl'] = SeleniumInfoExtractor._YTDL.params.get('stop_dl', {}) 
                        if not self._downloader.params.get('sem'):
                            self._downloader.params['sem'] = SeleniumInfoExtractor._YTDL.params.get('sem', {}) 
                        if not self._downloader.params.get('lock'):
                            self._downloader.params['lock'] = SeleniumInfoExtractor._YTDL.params.get('lock', Lock())
                        if not self._downloader.params.get('stop'):
                            self._downloader.params['stop'] = SeleniumInfoExtractor._YTDL.params.get('stop', Event())
                        if not self._downloader.params.get('routing_table'):
                            self._downloader.params['routing_table'] = SeleniumInfoExtractor._YTDL.params.get('routing_table')
                    
                    SeleniumInfoExtractor._YTDL = self._downloader                
                
                if not SeleniumInfoExtractor._YTDL.params.get('stop_dl'):                     
                    SeleniumInfoExtractor._YTDL.params['stop_dl'] = {}
                if not SeleniumInfoExtractor._YTDL.params.get('sem'):                     
                    SeleniumInfoExtractor._YTDL.params['sem'] = {} # for the ytdlp cli                    
                if not SeleniumInfoExtractor._YTDL.params.get('lock'):
                    #SeleniumInfoExtractor._YTDL.params['lock'] = SeleniumInfoExtractor._MASTER_LOCK
                    SeleniumInfoExtractor._YTDL.params['lock'] = Lock()
                if not SeleniumInfoExtractor._YTDL.params.get('stop'):
                    SeleniumInfoExtractor._YTDL.params['stop'] = Event()

                _headers = SeleniumInfoExtractor._YTDL.params.get('http_headers', {}).copy()
                    
                self._CLIENT_CONFIG = {
                    'timeout': Timeout(20), 
                    'limits': Limits(max_keepalive_connections=None, max_connections=None), 
                    'headers': _headers,
                    'follow_redirects': True,
                    'verify': False,
                    'proxies': None}
                
                if _proxy:=SeleniumInfoExtractor._YTDL.params.get('proxy'):
                    self._CLIENT_CONFIG.update({'proxies': {'http://': _proxy, 'https://': _proxy}})

                _config = self._CLIENT_CONFIG.copy()
                
                self._CLIENT = Client(
                    proxies=_config['proxies'], timeout=_config['timeout'], 
                    limits=_config['limits'], headers=_config['headers'],
                    follow_redirects=_config['follow_redirects'], verify=_config['verify'])

                self.indexdl = None
                    
                    
        except Exception as e:
            logger.exception(e)

    def extract(self, url):

        url, self.indexdl = try_get(unsmuggle_url(url), lambda x: (x[0], x[1].get('indexdl') if x[1] else None))

        return super().extract(url)
        
    def get_driver(self, noheadless=False, devtools=False, host=None, port=None, temp_prof_dir=None):        

        def _get_driver(noheadless, devtools, host, port, temp_prof_dir):        
        
            if not temp_prof_dir:
                tempdir = tempfile.mkdtemp(prefix='asyncall-') 
                shutil.rmtree(tempdir, ignore_errors=True) 
                res = shutil.copytree(SeleniumInfoExtractor._FF_PROF, tempdir, dirs_exist_ok=True)            
                if res != tempdir:
                    raise ExtractorError("error when creating profile folder")
            else: tempdir = temp_prof_dir
            
            opts = FirefoxOptions()
            
            if not noheadless:
                opts.add_argument("--headless")
            
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-application-cache")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--profile")
            opts.add_argument(tempdir)

            if devtools:
                opts.add_argument("--devtools")
                opts.set_preference("devtools.toolbox.selectedTool", "netmonitor")
                opts.set_preference("devtools.netmonitor.persistlog", False)
                opts.set_preference("devtools.debugger.skip-pausing", True);
            
                    
            if host and port:
                opts.set_preference("network.proxy.type", 1)
                opts.set_preference("network.proxy.http", host)
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

        with SeleniumInfoExtractor._MASTER_LOCK:
            if not host and (_proxy:=traverse_obj(self._CLIENT_CONFIG, ('proxies', 'http://'))):
                _host, _port = (urlparse(_proxy).netloc).split(':')
                self.to_screen(f"[get_driver] {_host} - {int(_port)}")
            else:
                _host, _port = host, port
            
            return _get_driver(noheadless, devtools, _host, _port, temp_prof_dir)
        
        

    
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

    def raise_from_res(self, res, msg):
    
        if res and (isinstance(res, str) or not res.get('error_res')): return
        
        _msg_error = try_get(res, lambda x: f" - {x.get('error_res')}") or "" 
        raise ExtractorError(f"{msg}{_msg_error}")

    def check_stop(self):
        
        try:
            _stopg = self.get_param('stop')
            _stop = None
            if self.indexdl:
                _stop = traverse_obj(self.get_param('stop_dl'), str(self.indexdl))

            if any([_stop and _stop.is_set(), _stopg and _stopg.is_set()]):
                self.to_screen("stop event")
                raise StatusStop("stop event")
        
        except StatusStop as e:
            raise
        # except Exception as e:
        #     logger.exception(repr(e))

    def scan_for_request(self, driver, _link, _all=False, timeout=10, response=True):

        def _get_har():
            _res = (driver.execute_async_script(
                        "HAR.triggerExport().then(arguments[0]);")).get('entries')
            return copy.deepcopy(_res)

        _list_hints = []
                
        _started = time.monotonic()        
        
        while True:            

            _har = _get_har()
            for entry in _har:
                
                _url = traverse_obj(entry, ('request',  'url'))
                if _url and re.search(_link, _url):
                    if not response:
                        _hint = (_url, None)
                        if not _all: 
                            return(_hint)   
                        else:                    
                            _list_hints.append(_hint)
                    else:
                        _resp_status = traverse_obj(entry, ('response', 'status'))
                        _resp_content = traverse_obj(entry, ('response', 'content', 'text'))
                       
                        _hint = (_url, _resp_content, int(_resp_status))
                        if not _all: 
                            return(_hint)   
                        else:                    
                            _list_hints.append(_hint)

                self.check_stop()

            if _all and _list_hints: 
                return(_list_hints)
            
            if (time.monotonic() - _started) >= timeout:
                if _all: return([])
                else: return(None,None)
            else:
                time.sleep(0.5)

    def scan_for_json(self, _driver, _link, _all=False, timeout=10):

        _hints = self.scan_for_request(_driver, _link, _all, timeout)

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
            el = WebDriverWait(driver, timeout, poll_frequency=poll_freq).until(ec.any_of(checkStop(self.check_stop), method))
        except StatusStop as e:
            raise
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
                res = self._CLIENT.head(url, headers=headers)            
            res.raise_for_status()
            _filesize = int_or_none(res.headers.get('content-length'))
            _url = unquote(str(res.url))
            _accept_ranges = any([res.headers.get('accept-ranges'), res.headers.get('content-range')])
            if _filesize:
                return ({'url': _url, 'filesize': _filesize, 'accept_ranges': _accept_ranges})
        except Exception as e:
            _msg_err = repr(e)
            if res and (400 <= res.status_code < 500):           
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

    def _is_valid(self, url, msg=None):
        
        if not url: 
            return False
        
        _pre_str = f'[{self._get_url_print(url)}]'
        if msg:
            _pre_str = f'[{msg}]{_pre_str}'            
            
        self.logger_debug(f'[valid]{_pre_str} start checking')
        
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
                else:
                    _decor = getter(_extr_name)
                
                @dec_on_exception3
                @dec_on_exception2
                @_decor
                def _throttle_isvalid(_url, short):
                    try:
                        _headers = SeleniumInfoExtractor._FIREFOX_HEADERS.copy()
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
    
    @dec_on_exception3
    @dec_on_exception2
    def _get_ip_origin(self):
        return(try_get(self.send_http_request("https://api.ipify.org?format=json"), lambda x: x.json().get('ip') if x else ''))

    def stream_http_request(self, url, **kwargs):
        try:
            premsg = f'[stream_http_request][{self._get_url_print(url)}]'
            msg = kwargs.get('msg', None)
            if msg: premsg = f'{msg}{premsg}' 

            chunk_size = kwargs.get('chunk_size', 16384)
            stopper = kwargs.get('stopper', 'dummytogetwholefile')
            
            _kwargs = kwargs.copy()
            _kwargs.pop('msg',None)
            _kwargs.pop('chunk_size',None)
            _kwargs.pop('stopper',None)
            
                      
            res = None
            _msg_err = ""
            _res = ""
            with self._CLIENT.stream("GET", url, **_kwargs) as res:
                res.raise_for_status()                
                for chunk in res.iter_text(chunk_size=chunk_size):
                    if chunk:
                        _res += chunk
                        if stopper in _res: break

            if not _res: return ""
            else: return _res
           
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

    def send_http_request(self, url, **kwargs):
        try:
            _type = kwargs.get('_type', "GET")
            headers = kwargs.get('headers', None)
            data = kwargs.get('data', None)
            msg = kwargs.get('msg', None)
            premsg = f'[send_http_request][{self._get_url_print(url)}][{_type}]'
            if msg: 
                premsg = f'{msg}{premsg}'           

            res = None
            _msg_err = ""
            req = self._CLIENT.build_request(_type, url, data=data, headers=headers)
            res = self._CLIENT.send(req)
            if res:
                res.raise_for_status()                
                return res
            else: return ""
        except Exception as e:            
            _msg_err = repr(e)
            if res and res.status_code == 403:                
                raise ReExtractInfo(_msg_err)
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
            self.logger_debug(f"{premsg} {req}:{res}:{_msg_err}")

