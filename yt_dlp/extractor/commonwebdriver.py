import html
import json
import logging
import random
import re
import shutil
import tempfile
import time
from threading import Event, Lock
import functools
from urllib.parse import unquote, urlparse
import subprocess
import os

from backoff import constant, on_exception
from httpx import (
    Client,
    ConnectError,
    HTTPError,
    HTTPStatusError,
    Limits,
    StreamError,
    Timeout,
    Response)

from pyrate_limiter import Duration, Limiter, RequestRate, LimitContextDecorator
from selenium.webdriver import Firefox, FirefoxOptions
from seleniumwire.webdriver import Firefox as Firefoxwire, FirefoxOptions as FirefoxOptionswire
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium.webdriver.remote.webelement import WebElement

assert Keys  # for flake8

from ..minicurses import MultilinePrinter
from .common import ExtractorError, InfoExtractor
from ..utils import classproperty, int_or_none, traverse_obj, try_get, unsmuggle_url, ReExtractInfo
from ..YoutubeDL import YoutubeDL
from ..cookies import extract_cookies_from_browser

from typing import (
    cast,
    Callable,
    Sequence,
    Tuple,
    Dict,
    TypeVar,
    Union,
    Type,
    Optional,
    Iterable,
)

assert Tuple
assert Dict
assert Iterable
assert Type
assert Optional
assert Sequence
assert TypeVar

from _thread import RLock  # type: ignore

from functools import cached_property

_NOT_FOUND = object()


class cached_classproperty(cached_property):
    __slots__ = ("func", "attrname", "__doc__", "lock")

    def __init__(self, func, attrname=None):
        self.func = func
        self.attrname = attrname
        self.__doc__ = func.__doc__
        self.lock = RLock()

    def __set_name__(self, owner, name):
        if self.attrname is None:
            self.attrname = name
        elif name != self.attrname:
            raise TypeError(
                "Cannot assign the same cached_property to two different names "
                f"({self.attrname!r} and {name!r})."
            )

    def __get__(self, instance, owner=None):
        if owner is None:
            raise TypeError("Cannot use cached_classproperty without an owner class.")
        if self.attrname is None:
            raise TypeError("Cannot use cached_classproperty instance without calling __set_name__ on it.")
        try:
            cache = owner.__dict__
        except AttributeError:  # not all objects have __dict__ (e.g. class defines slots)
            msg = f"No '__dict__' attribute on {owner.__name__!r} " f"to cache {self.attrname!r} property."
            raise TypeError(msg) from None
        val = cache.get(self.attrname, _NOT_FOUND)
        if val is _NOT_FOUND or val is self:
            with self.lock:  # type: ignore
                # check if another thread filled cache while we awaited lock
                val = cache.get(self.attrname, _NOT_FOUND)
                if val is _NOT_FOUND or val is self:
                    val = self.func(owner)
                    setattr(owner, self.attrname, val)
        return val


def get_host(url: str) -> str:
    _host = urlparse(url).netloc
    return re.sub(r'^www\.', '', _host)


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


def my_limiter(seconds: Union[str, int, float]):

    if seconds == "non":
        return Limiter(RequestRate(10000, 0))
    elif isinstance(seconds, (int, float)):
        return Limiter(RequestRate(1, seconds * Duration.SECOND))  # type: ignore


def my_jitter(value: float) -> float:

    return int(random.uniform(value * 0.75, value * 1.25))


def my_dec_on_exception(exception, **kwargs):

    if "jitter" in kwargs and kwargs["jitter"] == 'my_jitter':
        kwargs["jitter"] = my_jitter

    return on_exception(
        constant, exception, **kwargs)


limiter_non = Limiter(RequestRate(10000, 0))
limiter_0_005 = Limiter(RequestRate(1, 0.005 * Duration.SECOND))  # type: ignore
limiter_0_07 = Limiter(RequestRate(1, 0.07 * Duration.SECOND))  # type: ignore
limiter_0_05 = Limiter(RequestRate(1, 0.05 * Duration.SECOND))  # type: ignore
limiter_0_01 = Limiter(RequestRate(1, 0.01 * Duration.SECOND))  # type: ignore
limiter_0_1 = Limiter(RequestRate(1, 0.1 * Duration.SECOND))  # type: ignore
limiter_0_5 = Limiter(RequestRate(1, 0.5 * Duration.SECOND))  # type: ignore
limiter_1 = Limiter(RequestRate(1, Duration.SECOND))
limiter_1_5 = Limiter(RequestRate(1, 1.5 * Duration.SECOND))  # type: ignore
limiter_2 = Limiter(RequestRate(1, 2 * Duration.SECOND))
limiter_5 = Limiter(RequestRate(1, 5 * Duration.SECOND))
limiter_7 = Limiter(RequestRate(1, 7 * Duration.SECOND))
limiter_10 = Limiter(RequestRate(1, 10 * Duration.SECOND))
limiter_15 = Limiter(RequestRate(1, 15 * Duration.SECOND))

dec_on_exception = on_exception(
    constant, Exception, max_tries=3, jitter=my_jitter, raise_on_giveup=False, interval=10)
dec_on_exception2 = on_exception(
    constant, StatusError503, max_time=300, jitter=my_jitter, raise_on_giveup=False, interval=15)
dec_on_exception3 = on_exception(
    constant, (TimeoutError, ExtractorError), max_tries=3, jitter=my_jitter, raise_on_giveup=False, interval=0.1)
dec_retry = on_exception(
    constant, ExtractorError, max_tries=3, raise_on_giveup=True, interval=2)
dec_retry_on_exception = on_exception(
    constant, Exception, max_tries=3, raise_on_giveup=True, interval=2)
dec_retry_raise = on_exception(
    constant, ExtractorError, max_tries=3, interval=10)
dec_retry_error = on_exception(
    constant, (HTTPError, StreamError), max_tries=3, jitter=my_jitter, raise_on_giveup=False, interval=10)
dec_on_driver_timeout = on_exception(
    constant, TimeoutException, max_tries=3, raise_on_giveup=True, interval=5)
dec_on_reextract = on_exception(
    constant, ReExtractInfo, max_time=300, jitter=my_jitter, raise_on_giveup=True, interval=30)
retry_on_driver_except = on_exception(
    constant, WebDriverException, max_tries=3, raise_on_giveup=True, interval=2)

map_limiter = {
    15: limiter_15, 10: limiter_10, 5: limiter_5, 2: limiter_2, 1: limiter_1,
    0.5: limiter_0_5, 0.1: limiter_0_1, 0.01: limiter_0_01, 0: limiter_non}


CONFIG_EXTRACTORS_MODE = "ie_per_key"


def load_config_extractors(mode=CONFIG_EXTRACTORS_MODE):
    try:

        data = httpx.get('https://raw.githubusercontent.com/atgarcia78/yt-dlp/master/config_extractors.json').json()

    except Exception:
        print("ERROR LOADING CONFIG EXTRACTORS FILE")
        raise

    if mode == "legacy":
        return {
            tuple(key.split('#')): {
                'interval': value.get('ratelimit', 1),
                'ratelimit': map_limiter[value.get('ratelimit', 1)],
                'maxsplits': value.get('maxsplits', 16)
            }
            for key, value in data.items()
        }
    else:
        return {
            ie: {
                'interval': value.get('ratelimit', 1),
                'ratelimit': map_limiter[value.get('ratelimit', 1)],
                'maxsplits': value.get('maxsplits', 16)
            }
            for key, value in data.items() for ie in key.split('#')
        }


# CONFIG_EXTRACTORS = load_config_extractors()
def getter_basic_config_extr(ie_name, config, mode=CONFIG_EXTRACTORS_MODE):

    if not ie_name or ie_name.lower() == "generic":
        return
    x = ie_name.split(':')[0]
    if mode == "legacy":
        value, key_text = try_get(
            [(v, sk) for k, v in config.items() for sk in k if sk == x],
            lambda y: y[0]) or (None, None)
    else:
        key_text = x
        value = config.get(x)
    if value:
        return (value, key_text)


def getter_config_extr(ie_name, config, mode=CONFIG_EXTRACTORS_MODE) -> LimitContextDecorator:

    x = ie_name.split(':')[0]
    if x != 'generic':
        if mode == "legacy":
            value, key_text = try_get(
                [(v, sk) for k, v in config.items() for sk in k if sk == x],
                lambda y: y[0]) or ("", "")
        else:
            key_text = x
            value = config.get(x)
        if value:
            return (value['ratelimit'].ratelimit(key_text, delay=True))

    return limiter_non.ratelimit("nonlimit", delay=True)


class scroll:
    '''
        To use as a predicate in the webdriver waits to scroll down to the end of the page
        when the page has an infinite scroll where it is adding new elements dynamically
    '''
    _WAIT_TIME_SCROLL = 3

    def __init__(self, wait_time=2):
        self.wait_time = wait_time
        self.last_height = 0
        self.timer = ProgressTimer()

        if self.wait_time <= self._WAIT_TIME_SCROLL:
            self.exit_func = functools.partial(self.upt_height, lock=True)
        else:
            self.exit_func = lambda x: False

        self._page = None

        self._el_footer = 'NOTINIT'

    def upt_height(self, driver, lock=False):
        if (not lock and self.timer.has_elapsed(self._WAIT_TIME_SCROLL)) or (lock and self.timer.wait_haselapsed(self._WAIT_TIME_SCROLL)):
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == self.last_height:
                return True
            self.last_height = new_height

    def __call__(self, driver):
        if self._el_footer == 'NOTINIT':
            self._el_footer = try_get(driver.find_elements(By.CSS_SELECTOR, "div#footer"), lambda x: x[0])

        if self._el_footer:
            self._el_footer = cast(WebElement, self._el_footer)
            driver.execute_script(
                "window.scrollTo(arguments[0]['x'], arguments[0]['y']);", self._el_footer.location)
            return True

        else:

            if not self._page:
                self._page = driver.find_element(By.XPATH, "//body")
            time_start = time.monotonic()
            self.timer.reset()
            while ((time.monotonic() - time_start) <= self.wait_time):
                if self.upt_height(driver):
                    return True
                self._page.send_keys(Keys.PAGE_DOWN)

            if self.exit_func(driver):
                return True
            return False


class checkStop:

    def __init__(self, checkstop):
        self.checkstop = checkstop

    def __call__(self, driver):

        self.checkstop()
        return False


class ProgressTimer:
    TIMER_FUNC = time.monotonic

    def __init__(self):
        self._last_ts = self.TIMER_FUNC()

    def __repr__(self):
        return (f"{self.elapsed_seconds():.2f}")

    def reset(self):
        self._last_ts = self.TIMER_FUNC()

    def elapsed_seconds(self) -> float:
        return self.TIMER_FUNC() - self._last_ts

    def has_elapsed(self, seconds: float) -> bool:
        assert seconds > 0.0
        elapsed_seconds = self.elapsed_seconds()
        if elapsed_seconds < seconds:
            return False

        self._last_ts += elapsed_seconds - elapsed_seconds % seconds
        return True

    def wait_haselapsed(self, seconds: float):
        while True:
            if self.has_elapsed(seconds):
                return True
            else:
                time.sleep(0.2)


class myHAR:

    @classmethod
    @dec_retry_on_exception
    def get_har(cls, driver=None, har=None, _method="GET", _mimetype=None):

        _res = []
        if driver and not har:
            _res = try_get(
                driver.execute_async_script("HAR.triggerExport().then(arguments[0]);"),
                lambda x: x.get('entries') if x else None)

        elif har:
            if isinstance(har, dict):
                _res = traverse_obj(har, ('log', 'entries'))
            elif isinstance(har, str):
                with open(har, 'r') as f:
                    _res = traverse_obj(json.load(f), ('log', 'entries'))

        if not _res:
            raise Exception('no HAR entries')

        else:
            assert isinstance(_res, list)
            if _mimetype:
                if isinstance(_mimetype, (list, tuple)):
                    _mimetype_list = list(_mimetype)
                else:
                    _mimetype_list = [_mimetype]
                _non_mimetype_list = []
            else:
                _non_mimetype_list = ['image', 'css', 'font', 'octet-stream']
                _mimetype_list = []

            _res_filt = [el for el in _res if all(
                [
                    traverse_obj(el, ('request', 'method'), default='') == _method,
                    int(traverse_obj(el, ('response', 'bodySize'), default='0')) >= 0,  # type: ignore
                    not any([_ in traverse_obj(el, ('response', 'content', 'mimeType'), default='')  # type: ignore
                             for _ in _non_mimetype_list]) if _non_mimetype_list else True,
                    any([_ in traverse_obj(el, ('response', 'content', 'mimeType'), default='')  # type: ignore
                        for _ in _mimetype_list]) if _mimetype_list else True
                ])]

            return _res_filt

    @classmethod
    def headers_from_entry(cls, entry):
        return {
            header['name']: header['value']
            for header in traverse_obj(entry, ('request', 'headers'))  # type: ignore
            if header['name'] != 'Host'}

    @classmethod
    def scan_har_for_request(
            cls, _valid_url, driver=None, har=None, _method="GET", _mimetype=None, _all=False, timeout=10, response=True,
            inclheaders=False, check_event=None):

        _har_old = []

        _list_hints_old = []
        _list_hints = []
        _first = True

        _started = time.monotonic()

        while (time.monotonic() - _started) < timeout:

            _newhar = myHAR.get_har(driver=driver, har=har, _method=_method, _mimetype=_mimetype)
            assert _newhar
            _har = _newhar[len(_har_old):]
            _har_old = _newhar
            for entry in _har:

                _hint = {}
                _url = cast(str, traverse_obj(entry, ('request', 'url')))
                if not _url or not re.search(_valid_url, _url):
                    continue
                _hint.update({'url': _url})
                if inclheaders:
                    _hint.update({'headers': cls.headers_from_entry(entry)})
                if not response:
                    if not _all:
                        return _hint
                    else:
                        _list_hints.append(_hint)
                else:
                    _resp_status = traverse_obj(entry, ('response', 'status'))
                    _resp_content = traverse_obj(entry, ('response', 'content', 'text'))

                    _hint.update({
                        'content': _resp_content,
                        'status': int_or_none(_resp_status)})

                    if not _all:
                        return (_hint)
                    else:
                        _list_hints.append(_hint)

                if check_event:
                    if isinstance(check_event, Callable):
                        check_event()
                    elif isinstance(check_event, Event):
                        if check_event.is_set():
                            raise StatusStop("stop event")
            if har:
                break

            if _all:
                if not _first and (len(_list_hints) == len(_list_hints_old)):
                    return _list_hints
                if _first:
                    _first = False
                    if not _list_hints:
                        time.sleep(0.5)
                    else:
                        time.sleep(0.01)
                else:
                    time.sleep(0.01)

                _list_hints_old = _list_hints

            else:
                if _first:
                    _first = False
                    time.sleep(0.5)
                else:
                    time.sleep(0.01)

        # timeout or har file
        if _all:
            return _list_hints
        else:
            return

    @classmethod
    def scan_har_for_json(
            cls, _link, driver=None, har=None, _method="GET", _all=False, timeout=10, inclheaders=False, check_event=None):

        _hints = myHAR.scan_har_for_request(
            _link, driver=driver, har=har, _method=_method, _mimetype="json", _all=_all,
            timeout=timeout, inclheaders=inclheaders, check_event=check_event)

        if not _hints:
            return

        else:

            def func_getter(x):
                _info_json = json.loads(re.sub('[\t\n]', '', html.unescape(x.get('content')))) if x.get('content') else ""
                if inclheaders:
                    return (_info_json, x.get('headers'))
                else:
                    return _info_json

            if not _all:
                return try_get(_hints, func_getter)

            else:
                return [_info_json for el in _hints if (_info_json := try_get(el, func_getter))]

    class getNetworkHAR:

        def __init__(self, har_file, logger=None, msg=None, port=8080):
            self.har_file = har_file
            self.port = port
            self.cmd = f"mitmdump -p {port} -s /Users/antoniotorres/Projects/async_downloader/share/har_dump.py --set hardump={self.har_file}"
            self.logger = logger if logger else logging.getLogger('getHAR').debug
            self.pre = msg if msg else ''

        def __enter__(self):
            self.ps = subprocess.Popen(self.cmd.split(' '), stdout=subprocess.PIPE)
            self.ps.poll()
            time.sleep(2)
            self.ps.poll()
            if self.ps.returncode is not None:
                _log = ''
                if self.ps.stdout:
                    _log = '\n'.join([line.decode('utf-8').strip() for line in self.ps.stdout])
                self.logger(f"{self.pre}error executing mitmdump, returncode[{self.ps.returncode}]\n{_log}")
                raise Exception("couldnt launch mitmdump")
            return self

        def __exit__(self, *args):
            self.ps.terminate()

            def wait_for_file(file, timeout):
                start = time.monotonic()
                while (time.monotonic() - start < timeout):
                    if not os.path.exists(file):
                        time.sleep(0.2)
                    else:
                        return True
                return False

            if not wait_for_file(self.har_file, 5):
                raise Exception("couldnt get har file")

            self.logger(f'{self.pre} har file ready in {self.har_file}')

    @classmethod
    def network_har_handler(cls, har_file, logger=None, msg=None, port=8080):
        return cls.getNetworkHAR(har_file, logger=logger, msg=msg, port=port)


from ipaddress import ip_address
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx


class myIP:
    URLS_API_GETMYIP = {
        "httpbin": {"url": "https://httpbin.org/get", "key": "origin"},
        "ipify": {"url": "https://api.ipify.org?format=json", "key": "ip"},
        "ipapi": {"url": "http://ip-api.com/json", "key": "query"}
    }

    @classmethod
    def get_ip(cls, key=None, timeout=1, api="ipify", ie=None):

        if api not in cls.URLS_API_GETMYIP:
            raise Exception("api not supported")

        _urlapi = cls.URLS_API_GETMYIP[api]['url']
        _keyapi = cls.URLS_API_GETMYIP[api]['key']

        try:
            if not ie:
                _proxies = {'all://': f'http://127.0.0.1:{key}'} if key is not None else None
                myip = try_get(
                    httpx.get(
                        _urlapi, timeout=httpx.Timeout(timeout=timeout),
                        proxies=_proxies, follow_redirects=True),  # type: ignore
                    lambda x: x.json().get(_keyapi))  # type: ignore
            else:
                myip = try_get(
                    ie.send_http_request(_urlapi, timeout=httpx.Timeout(timeout=timeout)),
                    lambda x: x.json().get(_keyapi))
            return myip
        except Exception as e:
            return repr(e)

    @classmethod
    def get_myiptryall(cls, key=None, timeout=1, ie=None):

        def is_ipaddr(res):
            try:
                ip_address(res)
                return True
            except Exception:
                return False
        exe = ThreadPoolExecutor(thread_name_prefix="getmyip")
        futures = {
            exe.submit(cls.get_ip, key=key, timeout=timeout, api=api, ie=ie): api
            for api in cls.URLS_API_GETMYIP}
        for el in as_completed(futures):
            if not el.exception():
                _res = el.result()
                if is_ipaddr(_res):
                    exe.shutdown(wait=False, cancel_futures=True)
                    return _res

    @classmethod
    def get_myip(cls, key=None, timeout=1, ie=None):
        return cls.get_myiptryall(key=key, timeout=timeout, ie=ie)


class YDLLogger:
    _pre = ''

    def __init__(self, ydl, msg=None):
        _opts = ydl.params.copy()
        _opts.pop('logger', None)
        _opts.pop('noprogress', None)
        _opts['verbose'] = False
        self._ydl = YoutubeDL(_opts, auto_init='no_verbose_header')  # type: ignore
        if msg:
            YDLLogger._pre = msg

    def debug(self, message):
        assert message

    def info(self, message):
        if self._ydl:
            self._ydl.to_screen(f'{self._pre} {message}')

    def warning(self, message, only_once=False):
        if self._ydl:
            self._ydl.report_warning(message, only_once)

    def error(self, message):
        if self._ydl:
            self._ydl.report_error(message)

    class ProgressBar(MultilinePrinter):
        _DELAY, _timer = 0.1, 0
        _logger = logging.getLogger('progressbar')

        # to stop sending events to loggers while progressbar is printing
        def __enter__(self):
            try:
                self._logger.parent.handlers[0].stop()  # type: ignore
            except Exception:
                pass
            return self

        def __exit__(self, *args):
            try:
                self._logger.parent.handlers[0].start()  # type: ignore
            except Exception:
                pass
            super().__exit__(*args)
            self.print('')

        def print(self, message):
            if time.time() - self._timer > self._DELAY:
                self.print_at_line(f'{YDLLogger._pre} {message}', 0)
                self._timer = time.time()

    def progress_bar(self):
        """
        Return a context manager with a print method. (Optional)
        Do not print to files/pipes, loggers, or when --no-progress is used
        """
        file = self._ydl._out_files.error
        return self.ProgressBar(file, preserve_output=False)


def raise_extractor_error(msg, expected=True):
    raise ExtractorError(msg, expected=expected)


class SeleniumInfoExtractor(InfoExtractor):

    _FF_BINARY = r'/Applications/Firefox Nightly.app/Contents/MacOS/firefox'
    _FF_PROF = '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/b33yk6rw.selenium'
    _MASTER_LOCK = Lock()
    _YTDL = None
    _CONFIG_REQ = load_config_extractors()
    _FIREFOX_HEADERS = {
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
    }
    _SELENIUM_FACTORY = {'wire': {'ff': Firefoxwire, 'ffopts': FirefoxOptionswire}, 'standard': {'ff': Firefox, 'ffopts': FirefoxOptions}}

    @classproperty
    def IE_NAME(cls):
        return cls.__name__[:-2].lower()  # type: ignore

    @classproperty
    def LOGGER(cls):
        return logging.getLogger('yt_dlp')

    #  @classproperty(cache=True)  # type: ignore
    @cached_classproperty
    def IE_LIMITER(cls):
        return getter_config_extr(cls.IE_NAME, cls._CONFIG_REQ)

    # @classproperty(cache=True)  # type: ignore
    @cached_classproperty
    def _RETURN_TYPE(cls):
        """What the extractor returns: "video", "playlist", "any", or None (Unknown)"""
        tests = tuple(cls.get_testcases(include_onlymatching=False))
        if tests:

            if not any(k.startswith('playlist') for test in tests for k in test):
                return 'video'
            elif all(any(k.startswith('playlist') for k in test) for test in tests):
                return 'playlist'
            return 'any'

        else:
            if 'playlist' in cls.IE_NAME:
                return 'playlist'
            else:
                return 'video'

    @cached_classproperty
    def _COOKIES_JAR(cls):
        with SeleniumInfoExtractor._MASTER_LOCK:
            cls.LOGGER.info(f"[{cls.IE_NAME}] Loading cookies from Firefox")
            return extract_cookies_from_browser('firefox')

    def logger_info(self, msg):
        if (_logger := self.get_param('logger')):
            _logger.info(f"[{self.IE_NAME}] {msg}")
        else:
            self.to_screen(msg)

    def logger_debug(self, msg):
        if (_logger := self.get_param('logger')):
            _logger.debug(f"[debug+][{self.IE_NAME}] {msg}")
        else:
            self.to_screen(f"[debug] {msg}")

    def create_progress_bar(self, msg=None):
        ydllogger = YDLLogger(self._downloader, msg=msg)
        return ydllogger.progress_bar()

    def _get_extractor(self, _args):

        assert self._downloader

        if _args.startswith('http'):

            ies = self._downloader._ies
            ie_key = 'Generic'
            for key, ie in ies.items():
                try:
                    if ie.suitable(_args):
                        if key == 'Generic':
                            continue
                        else:
                            ie_key = key
                            break
                except Exception as e:
                    self.report_warning(f'[get_extractor] error with {key} - {repr(e)}')

        else:
            ie_key = _args

        try:
            _extractor = self._downloader.get_info_extractor(ie_key)
            _extractor._ready = False
            _extractor._real_initialize()
            return _extractor
        except Exception:
            self.logger_debug(f"extractor doesnt exist with ie_key {ie_key}")
            raise

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

    @staticmethod
    def _get_url_print(url):
        if url:
            if len(url) > 150:
                return (f'{url[:140]}...{url[-10:]}')
            else:
                return url

    def close(self):
        try:
            assert self._CLIENT
            self._CLIENT.close()
        except Exception:
            pass

    def initialize(self):

        super().initialize()
        self._ready = False

    def _real_initialize(self):

        assert self._downloader

        with SeleniumInfoExtractor._MASTER_LOCK:
            if self._YTDL != self._downloader:

                self._downloader.params.setdefault('stop_dl', try_get(self._YTDL, lambda x: traverse_obj(x.params, ('stop_dl'), {}) if x else {}))
                self._downloader.params.setdefault('sem', try_get(self._YTDL, lambda x: traverse_obj(x.params, ('sem'), {}) if x else {}))
                self._downloader.params.setdefault('lock', try_get(self._YTDL, lambda x: traverse_obj(x.params, ('lock'), Lock()) if x else Lock()))
                self._downloader.params.setdefault('stop', try_get(self._YTDL, lambda x: traverse_obj(x.params, ('stop'), Event()) if x else Event()))
                self._downloader.params.setdefault('routing_table', try_get(self._YTDL, lambda x: traverse_obj(x.params, ('routing_table'))))

                SeleniumInfoExtractor._YTDL = self._downloader

            self._CLIENT_CONFIG = {
                'timeout': Timeout(20),
                'limits': Limits(max_keepalive_connections=None, max_connections=None),
                'headers': self.get_param('http_headers', {}).copy(),
                'follow_redirects': True,
                'verify': False,
                'proxies': {'http://': _proxy, 'https://': _proxy} if (_proxy := self.get_param('proxy')) else None}

            self._CLIENT = Client(**self._CLIENT_CONFIG)

    def extract(self, url):

        url, data = unsmuggle_url(url)

        self.indexdl = traverse_obj(data, 'indexdl')
        self.args_ie = traverse_obj(data, 'args')

        return super().extract(url)

    def get_ytdl_sem(self, _host) -> Lock:

        assert self._downloader

        with self._downloader.params.setdefault('lock', Lock()):
            self._downloader.params.setdefault('sem', {})
            return self._downloader.params['sem'].setdefault(_host, Lock())

    def raise_from_res(self, res, msg):

        if res and (isinstance(res, str) or not res.get('error_res')):
            return

        def _getter(_res):
            for key, value in res.items():
                if 'error' in key:
                    return f" - {value}"
            return ""

        raise_extractor_error(f"{msg}{_getter(res)}")

    def check_stop(self):
        try:
            _stopg = self.get_param('stop')
            _stop = None
            if (_index := getattr(self, 'indexdl', None)):
                _stop = try_get(self.get_param('stop_dl'), lambda x: x.get(str(_index)))

            if any([_stop and _stop.is_set(), _stopg and _stopg.is_set()]):
                self.to_screen("stop event")
                raise StatusStop("stop event")

        except StatusStop:
            raise

    @classmethod
    @dec_retry
    def _get_driver(cls, noheadless=False, devtools=False, host=None, port=None, selenium_factory="standard", verbose=False):

        tempdir = tempfile.mkdtemp(prefix='asyncall-')
        shutil.rmtree(tempdir, ignore_errors=True)
        res = shutil.copytree(SeleniumInfoExtractor._FF_PROF, tempdir, dirs_exist_ok=True)
        if res != tempdir:
            raise ExtractorError("error when creating profile folder")

        opts = cls._SELENIUM_FACTORY[selenium_factory]['ffopts']()

        opts.binary_location = SeleniumInfoExtractor._FF_BINARY

        if not noheadless:
            opts.add_argument("--headless")

        # opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-application-cache")
        # opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--profile")
        opts.add_argument(tempdir)

        if devtools:
            opts.add_argument("--devtools")
            opts.set_preference("devtools.toolbox.selectedTool", "netmonitor")
            opts.set_preference("devtools.netmonitor.persistlog", False)
            opts.set_preference("devtools.debugger.skip-pausing", True)

        if host and port:
            opts.set_preference("network.proxy.type", 1)
            opts.set_preference("network.proxy.http", host)
            opts.set_preference("network.proxy.http_port", int(port))
            opts.set_preference("network.proxy.https", host)
            opts.set_preference("network.proxy.https_port", int(port))
            opts.set_preference("network.proxy.ssl", host)
            opts.set_preference("network.proxy.ssl_port", int(port))
            opts.set_preference("network.proxy.ftp", host)
            opts.set_preference("network.proxy.ftp_port", int(port))
            opts.set_preference("network.proxy.socks", host)
            opts.set_preference("network.proxy.socks_port", int(port))

        else:
            opts.set_preference("network.proxy.type", 0)

        opts.set_preference("dom.webdriver.enabled", False)
        opts.set_preference("useAutomationExtension", False)
        opts.set_preference("fission.webContentIsolationStrategy", 0)
        opts.set_preference("fission.bfcacheInParent", False)

        opts.page_load_strategy = 'eager'  # type: ignore

        _logs = {True: '/Users/antoniotorres/Projects/common/logs/geckodriver.log', False: '/dev/null'}

        serv = Service(log_path=_logs[verbose])  # type: ignore

        def return_driver():
            _driver = None
            try:
                _driver = cls._SELENIUM_FACTORY[selenium_factory]['ff'](service=serv, options=opts)  # type: ignore
                _driver.maximize_window()
                time.sleep(2)
                _driver.set_script_timeout(20)
                _driver.set_page_load_timeout(25)
                return _driver
            except Exception as e:
                cls.LOGGER.exception(f"[{cls.IE_NAME}] Firefox fails starting - {str(e)}")
                if _driver:
                    cls.rm_driver(_driver)

        with SeleniumInfoExtractor._MASTER_LOCK:
            driver = return_driver()

        if not driver:
            shutil.rmtree(tempdir, ignore_errors=True)
            raise ExtractorError("firefox failed init")

        return (driver, opts)

    def get_driver(self, noheadless=False, devtools=False, host=None, port=None, selenium_factory="standard", verbose=False):

        _proxy = traverse_obj(self._CLIENT_CONFIG, ('proxies', 'http://'))
        if not host and _proxy and isinstance(_proxy, str):
            _host, _port = (urlparse(_proxy).netloc).split(':')
            self.to_screen(f"[get_driver] {_host} - {int(_port)}")
        else:
            _host, _port = host, port

        driver, _ = SeleniumInfoExtractor._get_driver(
            noheadless=noheadless, devtools=devtools, host=_host, port=_port, selenium_factory=selenium_factory, verbose=verbose)

        return driver

    @classmethod
    def rm_driver(cls, driver):

        tempdir = driver.caps.get('moz:profile')
        try:
            driver.quit()
        except Exception:
            pass
        finally:
            if tempdir:
                shutil.rmtree(tempdir, ignore_errors=True)

    def get_har_logs(self, key, videoid, msg=None, port=8080):
        folder = f"/Users/antoniotorres/.cache/yt-dlp/{key}"
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
        har_file = f"{folder}/dump_{videoid}_{time.strftime('%y%m%d-%H%M%S')}.har"
        return myHAR.network_har_handler(har_file, logger=self.logger_info, msg=msg, port=port)

    def scan_for_request(
            self, _valid_url, driver=None, har=None, _method="GET", _mimetype=None, _all=False,
            timeout=10, response=True, inclheaders=False):

        return myHAR.scan_har_for_request(
            _valid_url, driver=driver, har=har, _method=_method, _mimetype=_mimetype, _all=_all, timeout=timeout,
            response=response, inclheaders=inclheaders, check_event=self.check_stop)

    def scan_for_json(self, _valid_url, driver=None, har=None, _method="GET", _all=False, timeout=10, inclheaders=False):

        return myHAR.scan_har_for_json(
            _valid_url, driver=driver, har=har, _method=_method, _all=_all, timeout=timeout,
            inclheaders=inclheaders, check_event=self.check_stop)

    def wait_until(self, driver: Firefox, timeout: float = 60, method: Union[None, Callable] = None, poll_freq: float = 0.5):

        _poll_freq = poll_freq
        if not method:
            method = ec.title_is("DUMMYFORWAIT")
            _poll_freq = 0.01
        try:
            return WebDriverWait(
                driver, timeout, poll_frequency=_poll_freq).until(
                    ec.any_of(checkStop(self.check_stop), method))  # type: ignore
        except StatusStop:
            raise
        except Exception:
            pass

    def get_info_for_format(self, url, **kwargs):

        res = None
        _msg_err = ""
        try:

            client = kwargs.get('client', self._CLIENT)
            headers = kwargs.get('headers', None)
            assert client
            res = client.head(unquote(url), headers=headers, timeout=5)
            res.raise_for_status()
            _filesize = int_or_none(res.headers.get('content-length'))
            _url = unquote(str(res.url))
            _accept_ranges = any([res.headers.get('accept-ranges'), res.headers.get('content-range')])
            if _filesize:
                return ({'url': _url, 'filesize': _filesize, 'accept_ranges': _accept_ranges})
            else:
                raise ReExtractInfo('no filesize')
        except ConnectError as e:
            _msg_err = f'{repr(e)} - {str(e)}'
            if 'errno 61' in _msg_err.lower():
                raise
            else:
                raise ExtractorError(_msg_err)
        except HTTPStatusError as e:
            _msg_err = f'{repr(e)} - {str(e)}'
            if e.response.status_code == 403:
                raise ReExtractInfo(_msg_err)
            elif e.response.status_code == 503:
                raise StatusError503(_msg_err)
            else:
                raise
        except ReExtractInfo as e:
            _msg_err = f'{repr(e)} - {str(e)}'
            raise
        except Exception as e:
            _msg_err = f'{repr(e)} - {str(e)}'
            if not res:
                raise TimeoutError(_msg_err)
            else:
                raise ExtractorError(_msg_err)
        finally:
            self.logger_debug(f"{res}:{_msg_err}")

    def _is_valid(self, url, msg=None):

        if not url:
            return False

        _pre_str = f'[{self._get_url_print(url)}]'
        if msg:
            _pre_str = f'[{msg}]{_pre_str}'

        self.logger_debug(f'[valid]{_pre_str} start checking')

        try:
            if any(_ in url for _ in ['rawassaddiction.blogspot', 'twitter.com', 'sxyprn.net', 'gaypornmix.com',
                                      'thisvid.com/embed', 'xtube.com', 'xtapes.to',
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
                    _decor = getter_config_extr(_extr_name, SeleniumInfoExtractor._CONFIG_REQ)

                @dec_on_exception3
                @dec_on_exception2
                @_decor
                def _throttle_isvalid(_url, short) -> Union[None, Response]:
                    try:
                        _headers = SeleniumInfoExtractor._FIREFOX_HEADERS.copy()
                        if short:
                            _headers.update({'Range': 'bytes=0-100'})
                        return self.send_http_request(_url, _type="GET", headers=_headers, msg=f'[valid]{_pre_str}')
                    except (HTTPStatusError, ConnectError) as e:
                        self.report_warning(f"[valid]{_pre_str}:{e}")

                res = _throttle_isvalid(url, True)

                if res and isinstance(res, Response):

                    if res.headers.get('content-type') == "video/mp4":
                        valid = True
                        self.logger_debug(f'[valid][{_pre_str}:video/mp4:{valid}')

                    if not (_path := urlparse(str(res.url)).path) or _path in ('', '/'):
                        valid = False
                        self.logger_debug(f'[valid][{_pre_str}] not path in reroute url {str(res.url)}:{valid}')
                    else:
                        webpage = try_get(_throttle_isvalid(url, False), lambda x: html.unescape(x.text) if x else None)
                        if not webpage:
                            valid = False
                            self.logger_debug(f'[valid]{_pre_str}:{valid} couldnt download webpage')
                        else:
                            valid = not any(_ in str(res.url) for _ in ['status=not_found', 'status=broken'])
                            valid = valid and not any(
                                _ in webpage.lower()
                                for _ in ['has been deleted', 'has been removed', 'was deleted', 'was removed',
                                          'video unavailable', 'video is unavailable', 'video disabled',
                                          'not allowed to watch', 'video not found', 'post not found',
                                          'limit reached', 'xtube.com is no longer available',
                                          'this-video-has-been-removed', 'has been flagged', 'embed-sorry'])

                            self.logger_debug(f'[valid]{_pre_str}:{valid} check with webpage content')

                else:
                    valid = False
                    self.logger_debug(f'[valid]{_pre_str}:{valid} couldnt send HEAD request')

                return valid

        except Exception as e:
            self.report_warning(f'[valid]{_pre_str} error {repr(e)}')
            return False

    def get_ip_origin(self, key=None, timeout=1, own=True):

        if own:
            ie = self
        else:
            ie = None

        return myIP.get_myip(key=key, timeout=timeout, ie=ie)

    def stream_http_request(self, url, **kwargs):

        premsg = f'[stream_http_request][{self._get_url_print(url)}]'
        msg = kwargs.get('msg', None)
        if msg:
            premsg = f'{msg}{premsg}'

        chunk_size = kwargs.get('chunk_size', 16384)
        # could be a string i.e. download until this text is found, or max bytes to download,
        # or None, im that case will download the whole content
        truncate_after = kwargs.get('truncate')

        res = None
        _msg_err = ""

        client = kwargs.get('client', self._CLIENT)

        try:

            _kwargs = kwargs.copy()
            _kwargs.pop('msg', None)
            _kwargs.pop('chunk_size', None)
            _kwargs.pop('truncate', None)
            _kwargs.pop('client', None)

            assert client

            with client.stream("GET", url, **_kwargs) as res:
                res.raise_for_status()

                if isinstance(truncate_after, str):
                    _res = ""
                    for chunk in res.iter_text(chunk_size=chunk_size):
                        if chunk:
                            _res += chunk
                            if truncate_after in _res:
                                break

                    return _res

                else:
                    _res = b""
                    for chunk in res.iter_bytes(chunk_size=chunk_size):
                        if chunk:
                            _res += chunk
                            if truncate_after and res.num_bytes_downloaded >= truncate_after:
                                break
                    return _res

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

    def send_http_request(self, url, **kwargs) -> Union[None, Response]:

        kwargs.setdefault('client', self._CLIENT)
        return SeleniumInfoExtractor._send_http_request(url, **kwargs)

    @classmethod
    def _send_http_request(cls, url, **kwargs) -> Union[None, Response]:
        res = None
        req = None
        _msg_err = ""
        _type = kwargs.get('_type', "GET")
        msg = kwargs.get('msg', None)
        premsg = f'[send_http_request][{cls._get_url_print(url)}][{_type}]'
        if msg:
            premsg = f'{msg}{premsg}'

        client = kwargs.get('client')

        try:

            _kwargs = kwargs.copy()

            _kwargs.pop('_type', None)
            _kwargs.pop('msg', None)
            _kwargs.pop('client', None)

            assert client

            req = client.build_request(_type, url, **_kwargs)
            res = client.send(req)
            if res:
                res.raise_for_status()
                return res
            else:
                return None
        except ConnectError as e:
            _msg_err = str(e)
            if 'errno 61' in _msg_err.lower():
                raise
            else:
                raise ExtractorError(_msg_err)
        except HTTPStatusError as e:
            _msg_err = str(e)
            if e.response.status_code == 403:
                raise ReExtractInfo(_msg_err)
            elif e.response.status_code == 503:
                raise StatusError503(_msg_err)
            else:
                raise
        except Exception as e:
            _msg_err = str(e)
            if not res:
                raise TimeoutError(_msg_err)
            else:
                raise ExtractorError(_msg_err)
        finally:
            cls.LOGGER.debug(f"[{cls.IE_NAME}] {premsg} {req}:{res}:{_msg_err}")
