from __future__ import annotations

import contextlib
import functools
import html
import http.cookiejar
import json
import logging
import os
import random
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import typing
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from functools import cached_property
from io import TextIOWrapper
from ipaddress import ip_address
from threading import Event, Lock, RLock, Semaphore
from urllib.parse import unquote, urlparse

import httpx
from backoff import constant, on_exception
from httpx import (
    Client,
    ConnectError,
    HTTPError,
    HTTPStatusError,
    Limits,
    Response,
    StreamError,
    Timeout,
)
from pyrate_limiter import Duration, Limiter, RequestRate
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver import Firefox, FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.wait import WebDriverWait

from .common import ExtractorError, InfoExtractor
from ..cookies import YoutubeDLCookieJar
from ..minicurses import MultilinePrinter
from ..utils import (
    ReExtractInfo,
    find_available_port,
    int_or_none,
    traverse_obj,
    try_call,
    try_get,
    unsmuggle_url,
    variadic,
)
from ..utils.networking import random_user_agent
from ..YoutubeDL import YoutubeDL

assert Keys  # for flake8

assert WebElement

_NOT_FOUND = object()


class run_operation_in_executor:
    """
    decorator to run a sync function from sync context
    The func with this decorator returns without blocking
    a mysynasyncevent to stop the execution of the func, and a future
    that wrappes the function submitted with a thread executor
    """

    def __init__(self, name: str) -> None:
        self.name = name  # for thread prefix loggin and stop event name

    def __call__(self, func):
        name = self.name

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> tuple[Event, Future]:
            stop_event = Event()
            exe = ThreadPoolExecutor(thread_name_prefix=name)
            _kwargs = {"stop_event": stop_event}
            _kwargs.update(kwargs)
            fut = exe.submit(lambda: func(*args, **_kwargs))
            return (stop_event, fut)

        return wrapper


class BrowserCookieError(Exception):
    pass


class FirefoxBrowserCookies:
    tmp_file = ''

    def __init__(self, profile='b33yk6rw.selenium'):
        cookie_file = self.find_cookie_file(profile)
        self.tmp_file = self.create_local_copy(cookie_file)
        self.session_file = os.path.join(
            os.path.dirname(cookie_file), 'sessionstore.js')
        self.new_session_file = os.path.join(
            os.path.dirname(cookie_file), 'sessionstore-backups',
            'recovery.jsonlz4')
        self.session_file2 = os.path.join(
            os.path.dirname(cookie_file), 'sessionstore.jsonlz4')

    def __del__(self):
        os.remove(self.tmp_file)

    def __str__(self):
        return 'firefox'

    def create_local_copy(self, cookie_file):
        """
        Make a local copy of the sqlite cookie database and return the new filename.
        This is necessary in case this database is still being written to while the user browses
        to avoid sqlite locking errors.
        """
        if os.path.exists(cookie_file):
            from shutil import copyfile
            tmp_file = tempfile.NamedTemporaryFile(suffix='.sqlite').name
            copyfile(cookie_file, tmp_file)
            return tmp_file
        raise BrowserCookieError(f'Can not find cookie file at: {cookie_file}')

    def find_cookie_file(self, profile):
        return os.path.expanduser(
            f'~/Library/Application Support/Firefox/Profiles/{profile}/cookies.sqlite')

    def extractSessionCookie(self, sessionFile, cj):
        try:
            import lz4.block
            with open(sessionFile, 'rb') as in_file:
                data = b'{}'
                if in_file.read(8) == b'mozLz40\x00':
                    data = lz4.block.decompress(in_file.read())
            jsonData = json.loads(data.decode('utf-8'))
            cookies = jsonData.get('cookies', {})
            expires = str(int(time.time()) + 604800)
            for cookie in cookies:
                c = self.create_cookie(
                    cookie.get('host', ''), cookie.get('path', ''), False, expires,
                    cookie.get('name', ''), cookie.get('value', ''))
                cj.set_cookie(c)

        except Exception as ex:
            print(ex)

    def create_cookie(self, host, path, secure, expires, name, value):
        return http.cookiejar.Cookie(
            0, name, value, None, False, host, host.startswith('.'),
            host.startswith('.'), path, True, secure, expires, False,
            None, None, {})

    def load(self):
        # print('firefox', self.tmp_file)
        cj = YoutubeDLCookieJar()
        con = sqlite3.connect(self.tmp_file)
        try:
            cur = con.cursor()
            cur.execute(
                'select host, path, isSecure, expiry, name, value from moz_cookies')
            for item in cur.fetchall():
                c = self.create_cookie(*item)
                cj.set_cookie(c)
        except Exception as e:
            print(e)
        finally:
            con.close()

        if os.path.exists(self.session_file):
            try:
                json_data = json.loads(open(self.session_file, 'rb').read())
            except ValueError as e:
                print(f'Error parsing firefox session JSON: {str(e)}')
            else:
                expires = str(int(time.time()) + 604800)
                for window in json_data.get('windows', []):
                    for cookie in window.get('cookies', []):
                        c = self.create_cookie(
                            cookie.get('host', ''), cookie.get('path', ''), False,
                            expires, cookie.get('name', ''), cookie.get('value', ''))
                        cj.set_cookie(c)

        elif os.path.exists(self.new_session_file):
            # print(self.new_session_file)
            self.extractSessionCookie(self.new_session_file, cj)
        elif os.path.exists(self.session_file2):
            # print(self.session_file2)
            self.extractSessionCookie(self.session_file2, cj)
        else:
            print(f'Firefox session filename does not exist: {self.session_file}')
        return cj


def subnright(pattern, repl, text, n):
    pattern = re.compile(rf"{pattern}(?!.*{pattern})", flags=re.DOTALL)
    _text = text
    for _ in range(n):
        _text = pattern.sub(repl, _text)
    return _text


class classproperty(property):

    def __get__(self, owner_self, owner_cls):
        if self.fget:
            return self.fget(owner_cls)


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
        except AttributeError:
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


def get_host(url: str | None, restricted=True, shorten=None):
    if url:
        _host = urlparse(url).netloc
        if restricted:
            _host = re.sub(r'^www\.', '', urlparse(url).netloc)
        if shorten == 'vgembed':
            _nhost = _host.split('.')
            if _host.count('.') >= 3:
                _host = '.'.join(_nhost[-3:])
        return _host


class StatusError503(Exception):
    """Error during info extraction."""

    def __init__(self, msg, exc_info=None):
        super().__init__(msg)
        self.exc_info = exc_info


class StatusStop(Exception):
    """Error during info extraction."""

    def __init__(self, msg='stopevent', exc_info=None):
        super().__init__(msg)
        self.exc_info = exc_info


def my_limiter(seconds: str | int | float):
    if seconds == "non":
        return Limiter(RequestRate(10000, 0))
    elif isinstance(seconds, (int, float)):
        return Limiter(RequestRate(1, seconds * Duration.SECOND))  # type: ignore


def my_jitter(value: float):
    return int(random.uniform(value * 0.75, value * 1.25))


def my_dec_on_exception(exception, **kwargs):
    if "jitter" in kwargs and kwargs["jitter"] == 'my_jitter':
        kwargs["jitter"] = my_jitter
    return on_exception(
        constant, exception, **kwargs)


limiter_non = Limiter(RequestRate(10000, 0))
limiter_0_005 = Limiter(RequestRate(1, Duration.SECOND * 0.005))  # type: ignore
limiter_0_07 = Limiter(RequestRate(1, Duration.SECOND * 0.07))  # type: ignore
limiter_0_05 = Limiter(RequestRate(1, Duration.SECOND * 0.05))  # type: ignore
limiter_0_01 = Limiter(RequestRate(1, Duration.SECOND * 0.01))  # type: ignore
limiter_0_1 = Limiter(RequestRate(1, Duration.SECOND * 0.1))  # type: ignore
limiter_0_5 = Limiter(RequestRate(1, Duration.SECOND * 0.5))  # type: ignore
limiter_1 = Limiter(RequestRate(1, Duration.SECOND))
limiter_1_5 = Limiter(RequestRate(1, Duration.SECOND * 1.5))  # type: ignore
limiter_2 = Limiter(RequestRate(1, Duration.SECOND * 2))
limiter_5 = Limiter(RequestRate(1, Duration.SECOND * 5))
limiter_7 = Limiter(RequestRate(1, Duration.SECOND * 7))
limiter_10 = Limiter(RequestRate(1, Duration.SECOND * 10))
limiter_15 = Limiter(RequestRate(1, Duration.SECOND * 15))

dec_on_exception = on_exception(
    constant, Exception,
    max_tries=3, jitter=my_jitter, raise_on_giveup=False, interval=10)
dec_on_exception2 = on_exception(
    constant, StatusError503,
    max_time=300, jitter=my_jitter, raise_on_giveup=False, interval=15)
dec_on_exception3 = on_exception(
    constant, (TimeoutError, ExtractorError),
    max_tries=3, jitter=my_jitter, raise_on_giveup=False, interval=0.1)
dec_retry = on_exception(
    constant, ExtractorError,
    max_tries=3, raise_on_giveup=True, interval=2)
dec_retry_on_exception = on_exception(
    constant, Exception,
    max_tries=3, raise_on_giveup=True, interval=2)
dec_retry_raise = on_exception(
    constant, ExtractorError,
    max_tries=3, interval=10)
dec_retry_error = on_exception(
    constant, (HTTPError, StreamError),
    max_tries=3, jitter=my_jitter, raise_on_giveup=False, interval=10)
dec_on_driver_timeout = on_exception(
    constant, TimeoutException,
    max_tries=3, raise_on_giveup=True, interval=1)
dec_on_reextract = on_exception(
    constant, ReExtractInfo,
    max_time=300, jitter=my_jitter, raise_on_giveup=True, interval=30)
retry_on_driver_except = on_exception(
    constant, WebDriverException,
    max_tries=3, raise_on_giveup=True, interval=2)

map_limiter = {
    15: limiter_15, 10: limiter_10, 5: limiter_5, 2: limiter_2, 1: limiter_1,
    0.5: limiter_0_5, 0.1: limiter_0_1, 0.01: limiter_0_01, 0: limiter_non}

CONF_CONFIG_EXTR_LOCAL = "/Users/antoniotorres/Projects/yt-dlp/config_extractors.json"
CONF_CONFIG_EXTR_GH = 'https://raw.githubusercontent.com/atgarcia78/yt-dlp/master/config_extractors.json'
CONF_FF_BIN = r'/Applications/Firefox Nightly.app/Contents/MacOS/firefox'
CONF_FF_PROF = '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/b33yk6rw.selenium'


def load_config_extractors():
    try:
        with open(CONF_CONFIG_EXTR_LOCAL, "r") as file:
            data = json.loads(file.read())
    except Exception:
        try:
            data = httpx.get(CONF_CONFIG_EXTR_GH).json()
        except Exception:
            print("ERROR LOADING CONFIG EXTRACTORS FILE")
            raise

    return {
        key: {
            'interval': value.get('ratelimit', 1),
            'ratelimit': map_limiter[value.get('ratelimit', 1)],
            'maxsplits': value.get('maxsplits', 16)
        }
        for key, value in data.items()
    }


def getter_basic_config_extr(ie_name, config):

    if not ie_name or ie_name.lower() == "generic":
        return
    key_text = ie_name.split(':')[0]
    if value := config.get(key_text):
        return (value, key_text)


def getter_config_extr(
        ie_name, config):

    if (key_text := ie_name.split(':')[0]) != 'generic':
        if value := config.get(key_text):
            return (value['ratelimit'].ratelimit(key_text, delay=True))
    return limiter_non.ratelimit("nonlimit", delay=True)


class scroll:
    """
    To use as a predicate in the webdriver waits to scroll down to the end of the page
    when the page has an infinite scroll where it is adding new elements dynamically
    """
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
        if ((not lock and self.timer.has_elapsed(self._WAIT_TIME_SCROLL))
                or (lock and self.timer.wait_haselapsed(self._WAIT_TIME_SCROLL))):
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == self.last_height:
                return True
            self.last_height = new_height

    def __call__(self, driver):
        if self._el_footer == 'NOTINIT':
            self._el_footer = try_get(
                driver.find_elements(By.CSS_SELECTOR, "div#footer"),
                lambda x: x[0])

        if self._el_footer:
            self._el_footer = self._el_footer
            driver.execute_script(
                "window.scrollTo(arguments[0]['x'], arguments[0]['y']);",
                self._el_footer.location)
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
            return bool(self.exit_func(driver))


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

    def elapsed_seconds(self):
        return self.TIMER_FUNC() - self._last_ts

    def has_elapsed(self, seconds: float):
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
                time.sleep(0.05)


class MyHAR:

    @classmethod
    @dec_retry_on_exception
    def get_har(cls, driver=None, har=None, _method="GET", _mimetype=None):

        _res = []
        if driver and not har:
            # driver has ta have add on export trigger har
            _res = try_get(
                driver.execute_async_script("HAR.triggerExport().then(arguments[0]);"),
                lambda x: x.get('entries') if x else None)

        elif har:
            if isinstance(har, dict):
                _res = traverse_obj(har, ('log', 'entries')) or []
            elif isinstance(har, list):
                _res = har
            elif isinstance(har, str):
                with open(har, 'r') as f:
                    _res = traverse_obj(json.load(f), ('log', 'entries')) or []

        if not _res or not isinstance(_res, list):
            raise ExtractorError('no HAR entries')
        else:

            if _mimetype:
                _mimetype_list = list(variadic(_mimetype))
                _non_mimetype_list = []
            else:
                _non_mimetype_list = ['image', 'css', 'font']
                _mimetype_list = []

            return [
                el for el in _res
                if all([
                    traverse_obj(el, ('request', 'method')) == _method,
                    int(traverse_obj(el, ('response', 'bodySize'), default='0')) >= 0,  # type: ignore
                    all(
                        _ not in traverse_obj(el, ('response', 'content', 'mimeType'), default='')  # type: ignore
                        for _ in _non_mimetype_list
                    ) if _non_mimetype_list else True,
                    any(
                        _ in traverse_obj(el, ('response', 'content', 'mimeType'), default='')  # type: ignore
                        for _ in _mimetype_list
                    ) if _mimetype_list else True,
                ])
            ]

    @classmethod
    def headers_from_entry(cls, entry):
        _headers_dict = {'_cookies': []}
        for header in traverse_obj(entry, ('request', 'headers'), default=[]):  # type: ignore
            if header['name'] == 'cookie':
                _headers_dict['_cookies'].append(header['value'])
            elif header['name'] != 'Host':
                _headers_dict[header['name']] = header['value']
        if _headers_dict['_cookies']:
            _headers_dict['cookie'] = '; '.join(_headers_dict['_cookies'])  # type: ignore
        return _headers_dict

    @classmethod
    def scan_har_for_request(
            cls, _valid_url, driver=None, har=None, _method="GET", _mimetype=None,
            _all=False, timeout=10, response=True,
            inclheaders=False, check_event=None):

        def _get_hint(entry):
            _url = traverse_obj(entry, ('request', 'url'))
            if not _url or not re.search(_valid_url, _url):  # type: ignore
                return None
            _hint = {'url': _url}
            if inclheaders:
                _hint['headers'] = cls.headers_from_entry(entry)
            if response:
                _resp_status = traverse_obj(entry, ('response', 'status'))
                _resp_content = traverse_obj(entry, ('response', 'content', 'text'))
                _hint.update({
                    'content': _resp_content,
                    'status': int_or_none(_resp_status)})
            return _hint

        _har_old = []
        _list_hints_old = []
        _list_hints = []
        _first = True

        _started = time.monotonic()

        while (time.monotonic() - _started) < timeout:

            _newhar = MyHAR.get_har(
                driver=driver, har=har, _method=_method, _mimetype=_mimetype)
            _har = _newhar[len(_har_old):]
            _har_old = _newhar
            for entry in _har:
                if not (_hint := _get_hint(entry)):
                    continue
                if not _all:
                    return _hint
                else:
                    _list_hints.append(_hint)
                if check_event:
                    if callable(check_event):
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
                    if _list_hints:
                        time.sleep(0.01)
                    else:
                        time.sleep(0.5)
                else:
                    time.sleep(0.01)
                _list_hints_old = _list_hints

            elif _first:
                _first = False
                time.sleep(0.5)
            else:
                time.sleep(0.01)

        if _all:
            return _list_hints
        else:
            return

    @classmethod
    def scan_har_for_json(
            cls, _link, driver=None, har=None, _method="GET", _all=False,
            timeout=10, inclheaders=False, check_event=None):

        def func_getter(x):
            if _content := x.get('content'):
                _info = json.loads(re.sub('[\t\n]', '', html.unescape(_content)))
                x |= {'json': _info}
            return x

        _hints = MyHAR.scan_har_for_request(
            _link, driver=driver, har=har, _method=_method, _mimetype="json", _all=_all,
            timeout=timeout, inclheaders=inclheaders, check_event=check_event)

        if not _hints:
            return

        if not _all:
            return try_get(_hints, func_getter)
        else:
            return [_info for _info in list(map(func_getter, _hints)) if _info]

    class MyHARError(Exception):
        pass

    class getNetworkHAR:

        def __init__(self, har_file, msg=None, port=8080):
            self.har_file = har_file
            self.port = port
            self.cmd = f"mitmdump -p {port} --set hardump={self.har_file}"
            self.logger = logging.getLogger('getHAR')
            self.pre = '[getHAR]'
            if msg:
                self.pre += msg

        def _close_pipe_proc(self, stream):
            _log = ''
            try:
                if stream:
                    _log = '\n'.join(
                        [line.decode('utf-8').strip()
                            for line in stream])
            except Exception:
                pass
            finally:
                stream.close()
                return _log

        def _handle_close(self):
            return [
                self._close_pipe_proc(_pipe)
                for _pipe in [self.ps.stdout, self.ps.stderr]]

        def __enter__(self):
            self.ps = subprocess.Popen(
                shlex.split(self.cmd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            self.ps.poll()
            time.sleep(2)
            self.ps.poll()
            if self.ps.returncode is not None:
                _logs = self._handle_close()
                self.logger.error("".join([
                    f"{self.pre}error rcode[{self.ps.returncode}]\n",
                    f"LOGOUT{_logs[0]}\nLOGERR{_logs[1]}"]))
                raise MyHAR.MyHARError("couldnt launch mitmdump")
            return self

        def __exit__(self, *args):
            def wait_for_file(file, timeout):
                start = time.monotonic()
                while (time.monotonic() - start < timeout):
                    if not os.path.exists(file):
                        time.sleep(0.5)
                    else:
                        return True

            _logs = [None, None]
            try:
                self.ps.terminate()
                self.ps.poll()
                time.sleep(2)
                self.ps.poll()
                self.ps.wait()
                _logs = self._handle_close()
                if self.ps.returncode:
                    raise MyHAR.MyHARError("error closing")
            except Exception as e:
                self.logger.error(
                    f"{self.pre} error closing {repr(e)} - rcode[{self.ps.returncode}]\n"
                    + f"LOGOUT{_logs[0]}\nLOGERR{_logs[1]}")
            if not wait_for_file(self.har_file, 5):
                raise MyHAR.MyHARError("couldnt get har file")
            self.logger.debug(f'{self.pre} har file ready in {self.har_file}')

    @classmethod
    def network_har_handler(cls, har_file, msg=None, port=8080):
        return cls.getNetworkHAR(har_file, msg=msg, port=port)


class myIP:
    URLS_API_GETMYIP = {
        "httpbin": {"url": "https://httpbin.org/get", "key": "origin"},
        "ipify": {"url": "https://api.ipify.org?format=json", "key": "ip"},
        "ipapi": {"url": "http://ip-api.com/json", "key": "query"}
    }

    @classmethod
    def get_ip(cls, key=None, timeout=1, api="ipify", ie=None):

        if api not in cls.URLS_API_GETMYIP:
            raise ExtractorError("api not supported")

        _urlapi = cls.URLS_API_GETMYIP[api]['url']
        _keyapi = cls.URLS_API_GETMYIP[api]['key']

        try:
            if ie:
                return try_get(
                    ie.send_http_request(
                        _urlapi, timeout=httpx.Timeout(timeout=timeout)
                    ),
                    lambda x: x.json().get(_keyapi),
                )
            _proxies = {'all://': f'http://127.0.0.1:{key}'} if key is not None else None
            return try_get(
                httpx.get(
                    _urlapi,
                    timeout=httpx.Timeout(timeout=timeout),
                    proxies=_proxies,  # type: ignore
                    follow_redirects=True,
                ),  # type: ignore
                lambda x: x.json().get(_keyapi),
            )
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


class SilentLogger:
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


def ytdl_silent(ytdl):
    opts = {
        "quiet": True,
        "verbose": False,
        "verboseplus": False,
        "no_warnings": True,
        "logger": SilentLogger(),
    }
    return YoutubeDL(params={**ytdl.params, **opts}, auto_init=True)


if typing.TYPE_CHECKING:
    RequestStream = TextIOWrapper | YoutubeDL | None


class ProgressBar(MultilinePrinter):
    _DELAY = 0.1

    def __init__(
            self, stream: RequestStream, total: int | float,
            preserve_output: bool = True, block_logging: bool = True, msg: str | None = None):
        self._pre = ''
        if msg:
            self._pre = msg
        self._logger = logging.getLogger('progressbar')
        if not stream:
            _stream = sys.stderr
        elif isinstance(stream, YoutubeDL):
            _stream = stream._out_files.error
        else:
            _stream = stream

        super().__init__(_stream, preserve_output=preserve_output)
        self._total = total
        self._block = block_logging
        self._done = 0
        self._lock = RLock()
        self._timer = ProgressTimer()

    # to stop sending events to loggers while progressbar is printing
    def __enter__(self):
        try:
            if self._block:
                try_get(self._logger.parent.handlers, lambda x: x[0].stop())  # type: ignore
        except Exception as e:
            self._logger.exception(repr(e))
        self.write('\n')
        return self

    def __exit__(self, *args):
        try:
            if self._block:
                try_get(
                    self._logger.parent,
                    lambda x: x.handlers[0].start())  # type: ignore
        except Exception as e:
            self._logger.exception(repr(e))
        super().__exit__(*args)
        self.write('\n')

    def update(self, n=1):
        with self._lock:
            self._done += n

    def print(self, message):
        with self._lock:
            self._timer.wait_haselapsed(ProgressBar._DELAY)
            self.print_at_line(
                f'{self._pre} {message} {self._done}/{self._total}', 0)
            self._timer.reset()


def raise_extractor_error(msg, expected=True, _from=None):
    raise ExtractorError(msg, expected=expected) from _from


def raise_reextract_info(msg, expected=True, _from=None):
    raise ReExtractInfo(msg, expected=expected) from _from


class SeleniumInfoExtractor(InfoExtractor):

    _FF_BINARY = CONF_FF_BIN
    _FF_PROF = CONF_FF_PROF
    _MASTER_LOCK = Lock()
    _CONFIG_REQ = load_config_extractors()
    _WEBDRIVERS = {}
    _REFS = {}
    _SEMAPHORE = Semaphore(8)

    class syncsem:
        def __call__(self, func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with SeleniumInfoExtractor._SEMAPHORE:
                    return func(*args, **kwargs)
            return wrapper

    @classproperty
    def IE_NAME(cls):
        return cls.__name__[:-2].lower()

    @classproperty
    def LOGGER(cls):
        return logging.getLogger('yt_dlp')

    @cached_classproperty
    def TEMP_CLIENT_CONFIG(cls):
        return {
            'timeout': Timeout(20),
            'limits': Limits(),
            'follow_redirects': True,
            'verify': False,
            'headers': {"User-Agent": random_user_agent()}
        }

    @staticmethod
    def get_temp_client(config={}):
        return Client(**(SeleniumInfoExtractor.TEMP_CLIENT_CONFIG | config))

    @cached_classproperty
    def IE_LIMITER(cls):
        return getter_config_extr(cls.IE_NAME, cls._CONFIG_REQ)

    @cached_classproperty
    def _RETURN_TYPE(cls):
        """
        What the extractor returns: "video", "playlist", "any", or None (Unknown)
        """
        if not (tests := tuple(cls.get_testcases(include_onlymatching=False))):
            return 'playlist' if 'playlist' in cls.IE_NAME else 'video'
        if not any(k.startswith('playlist') for test in tests for k in test):
            return 'video'
        elif all(any(k.startswith('playlist') for k in test) for test in tests):
            return 'playlist'
        return 'any'

    @cached_classproperty
    def _FF_COOKIES_JAR(cls):
        with SeleniumInfoExtractor._MASTER_LOCK:
            cls.LOGGER.debug(f"[{cls.IE_NAME}] Loading cookies from Firefox")
            return FirefoxBrowserCookies().load()

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

    @staticmethod
    def _get_url_print(url):
        if url:
            return f'{url[:140]}...{url[-10:]}' if len(url) > 150 else url

    def close(self):
        with contextlib.suppress(Exception):
            self._CLIENT.close()
        with SeleniumInfoExtractor._MASTER_LOCK:
            SeleniumInfoExtractor._REFS.pop(id(self), None)
            if not SeleniumInfoExtractor._REFS and SeleniumInfoExtractor._WEBDRIVERS:
                _drivers = list(SeleniumInfoExtractor._WEBDRIVERS.values())
                for driver in _drivers:
                    with contextlib.suppress(Exception):
                        self.rm_driver(driver)

    def initialize(self):
        super().initialize()
        self._ready = False

    def _real_initialize(self):

        def _update():
            if self._downloader:
                self._downloader.params.setdefault('stop_dl', {})
                self._downloader.params.setdefault('sem', {})
                self._downloader.params.setdefault('lock', Lock())
                self._downloader.params.setdefault('stop', Event())
                self._downloader.params.setdefault('routing_table', None)

        _update()

        self._CLIENT_CONFIG = {
            'timeout': Timeout(20),
            'limits': Limits(),
            'headers': self.get_param('http_headers', default={}),
            'follow_redirects': True,
            'verify': False,
            'proxies': {'http://': _proxy, 'https://': _proxy}
            if (_proxy := self.get_param('proxy')) else None}

        self._CLIENT = Client(**self._CLIENT_CONFIG)

        with SeleniumInfoExtractor._MASTER_LOCK:
            SeleniumInfoExtractor._REFS[id(self)] = self

    def extract(self, url):
        url, data = unsmuggle_url(url, {})

        self.indexdl = traverse_obj(data, 'indexdl')
        _args = traverse_obj(data, 'args', default={})  # type: ignore
        if getattr(self, 'args_ie', None) is None:
            self.args_ie = _args
        elif _args:
            self.args_ie.update(_args)  # type: ignore

        return super().extract(url)

    def create_progress_bar(
            self, total: int | float, block_logging: bool = True,
            msg: str | None = None):
        return ProgressBar(self._downloader, total, block_logging=block_logging, msg=msg)

    def _get_extractor(self, _args):
        def get_extractor(url):
            ies = self._downloader._ies  # type: ignore
            for ie_key, ie in ies.items():
                try:
                    if ie.suitable(url) and (ie_key != "Generic"):
                        return (ie_key, self._downloader.get_info_extractor(ie_key))  # type: ignore
                except Exception as e:
                    self.LOGGER.exception(f'[get_extractor] fail with {ie_key} - {repr(e)}')
            return ("Generic", self._downloader.get_info_extractor("Generic"))  # type: ignore

        if _args.startswith('http'):
            ie_key, ie = get_extractor(_args)
        else:
            ie_key = _args
            ie = self._downloader.get_info_extractor(ie_key)  # type: ignore
        try:
            ie.initialize()
            return ie
        except Exception as e:
            self.LOGGER.exception(
                f"{repr(e)} extractor doesnt exist with ie_key {ie_key}")
        raise

    def _get_ie_name(self, url=None):

        if not url:
            return self.IE_NAME.lower()
        extractor = self._get_extractor(url)
        extr_name = extractor.IE_NAME
        return extr_name.lower()

    def _get_ie_key(self, url=None):

        if not url:
            return self.ie_key()
        extractor = self._get_extractor(url)
        return extractor.ie_key()

    def get_ytdl_sem(self, _host):
        _sem = None
        try:
            if self._downloader:
                with self._downloader.params.setdefault('lock', Lock()):
                    _sem = self._downloader.params.setdefault('sem', {}).setdefault(_host, Lock())
        except Exception:
            pass
        finally:
            return _sem or contextlib.nullcontext()

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

    def get_uc_chr(self, noheadless=False, host: str | None = None, port: int | None = None, logs=False):
        import seleniumwire.undetected_chromedriver as uc

        options = uc.ChromeOptions()
        options.binary_location = r"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if not noheadless:
            options.add_argument('--headless')
        if host:
            options.add_argument('--proxy-server=%s:%d' % (host, port))
        if logs:
            options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        options.add_argument('--user-data-dir=/Users/antoniotorres/Library/Application Support/Google/Chrome')
        options.add_argument('--profile-directory=Default')
        exepath = "/Users/antoniotorres/Downloads/chromedriver-mac-arm64/chromedriver"
        driver = uc.Chrome(options=options, version_main=123, driver_executable_path=exepath)
        SeleniumInfoExtractor._WEBDRIVERS[id(driver)] = driver
        return driver

    @classmethod
    @dec_retry
    def _get_driver(
        cls, noheadless=False, devtools=False,
            host=None, port=None, verbose=False):

        tempdir = tempfile.mkdtemp(prefix='asyncall-')
        shutil.rmtree(tempdir, ignore_errors=True)
        res = shutil.copytree(SeleniumInfoExtractor._FF_PROF, tempdir, dirs_exist_ok=True)
        if res != tempdir:
            raise ExtractorError("error when creating profile folder")

        opts = FirefoxOptions()

        opts.binary_location = SeleniumInfoExtractor._FF_BINARY

        if not noheadless:
            opts.add_argument("--headless")

        opts.add_argument("--disable-application-cache")
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

        opts.page_load_strategy = 'eager'  # type: ignore

        _logs = {
            True: '/Users/antoniotorres/Projects/common/logs/geckodriver.log',
            False: '/dev/null'}

        serv = Service(log_path=_logs[verbose])

        def return_driver():
            count = 0
            while count < 3:
                _driver = None
                try:
                    with SeleniumInfoExtractor._MASTER_LOCK:
                        _driver = Firefox(service=serv, options=opts)
                    time.sleep(1)
                    _driver.set_script_timeout(20)
                    _driver.set_page_load_timeout(25)
                    return _driver
                except Exception as e:
                    cls.LOGGER.error(  # type: ignore
                        f"[{cls.IE_NAME}] Firefox fails starting - {str(e)}")
                    if _driver:
                        cls.rm_driver(_driver)
                    count += 1

        if not (driver := return_driver()):
            raise ExtractorError("firefox failed init")

        return (driver, opts)

    def get_driver(
            self, noheadless=False, devtools=False, host=None,
            port=None, verbose=False):

        _proxy = traverse_obj(self._CLIENT_CONFIG, ('proxies', 'http://'))
        if not host and _proxy and isinstance(_proxy, str):
            _host, _port = (urlparse(_proxy).netloc).split(':')
            self.to_screen(f"[get_driver] {_host} - {int(_port)}")
        else:
            _host, _port = host, port

        if driver := try_get(
                SeleniumInfoExtractor._get_driver(
                    noheadless=noheadless, devtools=devtools, host=_host,
                    port=_port, verbose=verbose),
                lambda x: x[0]):

            SeleniumInfoExtractor._WEBDRIVERS[id(driver)] = driver
            return driver

    def set_driver_proxy_options(self, driver, **kwargs):

        '''
        proxy_type: int = 0 - manual, 1 - proxy
        port: int =  port
        host: str = IP
        '''
        proxy_type = kwargs.get("proxy_type", 1)
        port = kwargs.get("port")
        host = kwargs.get("host", "127.0.0.1")
        driver.timeouts.script = 60

        _script = []
        _script.append('var prefs = Components.classes["@mozilla.org/preferences-service;1"]\
                       .getService(Components.interfaces.nsIPrefBranch);')
        if proxy_type == 0:
            _script.append('prefs.setIntPref("network.proxy.type", 0);')
        else:
            _script.append('prefs.setIntPref("network.proxy.type", 1);')
            if host is not None:
                _script.append(f'prefs.setCharPref("network.proxy.http", "{host}");')
                _script.append(f'prefs.setCharPref("network.proxy.ssl", "{host}");')
                _script.append(f'prefs.setCharPref("network.proxy.socks", "{host}");')
            if port:
                _script.append(f'prefs.setIntPref("network.proxy.http_port", {port});')
                _script.append(f'prefs.setIntPref("network.proxy.ssl_port", {port});')
                _script.append(f'prefs.setIntPref("network.proxy.socks_port", {port});')

        orig_window = driver.current_window_handle
        driver.switch_to.new_window('tab')

        driver.get('about:preferences#general')

        _js_script = "\n".join(_script)
        driver.execute_script(_js_script)

        self.wait_until(driver, 0.5)

        driver.close()
        driver.switch_to.window(orig_window)

        self.wait_until(driver, 0.5)

    @classmethod
    def rm_driver(cls, driver):

        tempdir = None
        try:
            tempdir = driver.caps.get('moz:profile')
        except Exception:
            pass
        try:
            driver.quit()
        except Exception:
            pass
        finally:
            SeleniumInfoExtractor._WEBDRIVERS.pop(id(driver), None)
            if tempdir:
                shutil.rmtree(tempdir, ignore_errors=True)

    def find_free_port(self):
        with SeleniumInfoExtractor._MASTER_LOCK:
            return find_available_port()

    def get_har_logs(self, key, videoid=None, msg=None, port=8080):
        folder = f"/Users/antoniotorres/.cache/yt-dlp/{key}"
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
        t0 = datetime.now()
        _time_str = f"{t0.strftime('%H%M%S_')}{t0.microsecond}"
        _videoid_str = f"{f'{videoid}_' if videoid else ''}"
        har_file = f"{folder}/dump_{_videoid_str}{_time_str}.har"
        return MyHAR.network_har_handler(
            har_file, msg=msg, port=port)

    def scan_for_request(
            self, _valid_url, driver=None, har=None, _method="GET", _mimetype=None,
            _all=False, timeout=10, response=True, inclheaders=False):

        return MyHAR.scan_har_for_request(
            _valid_url, driver=driver, har=har, _method=_method, _mimetype=_mimetype,
            _all=_all, timeout=timeout, response=response, inclheaders=inclheaders,
            check_event=self.check_stop)

    def scan_for_json(
            self, _valid_url, driver=None, har=None, _method="GET", _all=False,
            timeout=10, inclheaders=False):

        return MyHAR.scan_har_for_json(
            _valid_url, driver=driver, har=har, _method=_method, _all=_all,
            timeout=timeout, inclheaders=inclheaders, check_event=self.check_stop)

    def wait_until(
        self, driver: Firefox, timeout: int | float = 60, method: None | Iterable | Callable = None,
        poll_freq: float = 0.5, get_all=False, fatal=True
    ):

        _poll_freq = poll_freq
        if not method:
            method = [ec.title_is("DUMMYFORWAIT")]
            _poll_freq = 0.01
        elif callable(method):
            method = [method]

        res = []
        for _method in method:

            try:
                _res = WebDriverWait(driver, timeout, poll_frequency=_poll_freq).until(
                    ec.any_of(checkStop(self.check_stop), _method))
                res.append(_res)
            except StatusStop:
                raise
            except Exception as e:
                if fatal:
                    return
                else:
                    res.append({'error': repr(e)})

        return res if get_all else try_call(lambda: res[-1])

    def clear_firefox_cache(self, driver: Firefox, timeout: float = 10):
        dialog_selector = 'vbox.dialogOverlay:nth-child(1) > vbox:nth-child(1) > browser:nth-child(2)'
        accept_dialog_script = '''
            const browser = document.querySelector("%s");
            browser.contentDocument.documentElement.querySelector("dialog")._buttons.accept.click()''' % dialog_selector

        def get_clear_site_data_button(driver):
            return driver.find_element(by=By.CSS_SELECTOR, value='#clearSiteDataButton')

        def get_clear_site_data_dialog(driver):
            return driver.find_element(by=By.CSS_SELECTOR, value=dialog_selector)

        orig_window = driver.current_window_handle
        driver.switch_to.new_window('tab')

        driver.get('about:preferences#privacy')
        wait = WebDriverWait(driver, timeout)

        # Click the "Clear Data..." button under "Cookies and Site Data".
        wait.until(get_clear_site_data_button)
        get_clear_site_data_button(driver).click()

        # Accept the "Clear Data" dialog by clicking on the "Clear" button.
        wait.until(get_clear_site_data_dialog)
        driver.execute_script(accept_dialog_script)

        driver.close()
        driver.switch_to.window(orig_window)

    def get_info_for_format(self, url, **kwargs):

        res = None
        info = {}
        _msg_err = ""
        try:
            _kwargs = {**kwargs, **{"_type": "HEAD", "timeout": 10}}
            _kwargs.setdefault('client', self._CLIENT)
            if not (res := SeleniumInfoExtractor._send_http_request(url, **_kwargs)):
                raise ReExtractInfo('no response')
            elif not (_filesize_str := res.headers.get('content-length')):
                raise ReExtractInfo('no filesize')
            else:
                _url = unquote(str(res.url))
                _accept_ranges = any([
                    res.headers.get('accept-ranges'), res.headers.get('content-range')])
                return {
                    'url': _url,
                    'filesize': int(_filesize_str),
                    'accept_ranges': _accept_ranges
                }
        except (ConnectError, HTTPStatusError, ReExtractInfo,
                TimeoutError, ExtractorError) as e:
            _msg_err = repr(e)
            raise
        except Exception as e:
            _msg_err = repr(e)
            raise ExtractorError(_msg_err) from None
        finally:
            self.logger_debug(
                f"[get_info_format] {url}:{res}:{_msg_err}:{info}")

    def _is_valid(self, url, timeout=45, msg=None, inc_error=False):

        _not_valid_url = [
            'rawassaddiction.blogspot', 'twitter.com', 'sxyprn.net', 'gaypornmix.com',
            'thisvid.com/embed', 'xtube.com', 'xtapes.to', 'pornone.com/embed/']

        _valid_url = ['xhamster', 'xhamsterembed']

        _transform_url = {'pornhub': lambda x: x.replace(get_host(x), 'pornhub.com')}

        _get_all_urls = {'xhamster': ['https://%s/xembed.php?video=%s', 'https://%s/movies/%s'],
                         'xhamsterembed': ['https://%s/xembed.php?video=%s', 'https://%s/movies/%s'],
                         'pornhub': ['https://%s/view_video.php?viewkey=%s', 'https://%s/embed/%s'],
                         'xvideos': ['https://%s/embedframe/%s', 'https://%s/video%s'],
                         'generic': ['%s%s']}

        _errors_page = [
            'has been deleted', 'has been removed', 'was deleted', 'was removed',
            'video unavailable', 'video is unavailable', 'video disabled',
            'not allowed to watch', 'video not found', 'post not found',
            'limit reached', 'xtube.com is no longer available',
            'this-video-has-been-removed', 'has been flagged', 'embed-sorry']

        _pre_str = f'[valid][{self._get_url_print(url)}]'
        if msg:
            _pre_str = f'[{msg}]{_pre_str}'
        self.logger_debug(f'{_pre_str} start checking')

        notvalid = {}
        okvalid = {}
        notvalid["valid"] = False
        okvalid["valid"] = True
        _res_valid = {True: okvalid, False: notvalid}

        if not url:
            return notvalid

        try:
            if any(_ in url for _ in _not_valid_url):
                self.logger_debug(f'{_pre_str}:False')
                return {'error': 'in error list', **notvalid} if inc_error else notvalid
            elif any(_ in url for _ in ['gayforit.eu/video']):
                self.logger_debug(f'{_pre_str}:True')
                return okvalid
            else:
                _extr_name = self._get_ie_name(url).lower()
                if _extr_name in _get_all_urls:
                    if _extr_name != 'generic':
                        ie = self._get_extractor(url)
                        _id = ie._match_id(url)
                        _host = get_host(url, restricted=False)
                    else:
                        _id = (
                            try_get(re.search(r'\?v=(?P<id>[\da-zA-Z]+)', url), lambda x: x.groupdict()['id'])
                            or try_get(re.search(r'embed/(?P<id>[\da-zA-Z]+$)', url), lambda x: x.groupdict()['id']))
                        _host = ''
                    if _id:
                        _all_urls = [_url % (_host, _id) for _url in _get_all_urls[_extr_name]]
                        okvalid['_all_urls'] = _all_urls
                        notvalid['_all_urls'] = _all_urls

                if _extr_name in _valid_url:
                    return okvalid

                if _extr_name in _transform_url:
                    url = _transform_url[_extr_name](url)

            _decor = getter_config_extr(
                _extr_name, SeleniumInfoExtractor._CONFIG_REQ)

            def _throttle_isvalid(_url, short):
                if (_res := self.cache.load('is_valid', get_host(_url))):
                    _time_modif = datetime.fromtimestamp(
                        os.stat(self.cache._get_cache_fn(
                            'is_valid', get_host(_url), 'json')).st_mtime)
                    if (datetime.now() - _time_modif) <= timedelta(hours=1):
                        return _res
                    with contextlib.suppress(OSError):
                        os.remove(self.cache._get_cache_fn('is_valid', get_host(_url), 'json'))
                with _decor:
                    try:
                        _headers = {}
                        if short:
                            _headers['range'] = 'bytes=0-100'
                        return self.send_http_request(
                            _url, _type="GET", timeout=timeout,
                            headers=_headers, msg=f'[valid]{_pre_str}')
                    except HTTPStatusError as e:
                        self.logger_debug(f"{_pre_str}:{e}")
                        if e.response.status_code >= 400:
                            self.cache.store(
                                'is_valid', get_host(_url), {'valid': False, 'error': str(e)})
                        return {'error': str(e)}
                    except Exception as e:
                        self.logger_debug(f"{_pre_str}:{e}")
                        return {'error': str(e)}

            if (res := _throttle_isvalid(url, True)) and isinstance(res, Response):

                if res.headers.get('content-type') == "video/mp4":
                    self.logger_debug(f'[valid][{_pre_str}:video/mp4:{okvalid}')
                    return okvalid

                elif not (_path := urlparse(str(res.url)).path) or _path in ('', '/'):

                    self.logger_debug(
                        f'[valid][{_pre_str}] not path in reroute url {str(res.url)}:{notvalid}')

                    if not inc_error:
                        return notvalid
                    else:
                        return {'error': f'not path in reroute url {str(res.url)}', **notvalid}

                else:
                    if not (webpage := try_get(
                            _throttle_isvalid(url, False),
                            lambda x: html.unescape(x.text) if x else None)):

                        self.logger_debug(f'[valid]{_pre_str}:{notvalid} couldnt download webpage')
                        return {'error': 'couldnt download webpage', **notvalid} if inc_error else notvalid
                    else:
                        _valid = all(
                            _ not in str(res.url)
                            for _ in ['status=not_found', 'status=broken'])
                        if _valid:
                            _valid = all(_ not in webpage.lower() for _ in _errors_page)

                        self.logger_debug(f'[valid]{_pre_str}:{_valid} check with webpage content')
                        _final_res = {'webpage': webpage, **_res_valid[_valid]}
                        if _valid or not inc_error:
                            return _final_res
                        else:
                            return {'error': 'video not found or deleted 404', **_final_res}

            else:
                self.logger_debug(
                    f'[valid]{_pre_str}:{notvalid} couldnt send check request')
                _error = 'error'
                if isinstance(res, dict):
                    _error = res.get('error', 'error')
                return {'error': _error, **notvalid} if inc_error else notvalid

        except Exception as e:
            self.logger_debug(f'[valid]{_pre_str} error {repr(e)}')
            _msgerror = 'timeout' if 'timeout' in repr(e).lower() else repr(e)
            return {'error': _msgerror, **notvalid} if inc_error else notvalid

    def get_ip_origin(self, key=None, timeout=1, own=True):
        ie = self if own else None
        return myIP.get_myip(key=key, timeout=timeout, ie=ie)

    def stream_http_request(self, url, **kwargs):
        def _get_error_message(e, res):
            result = repr(e)
            if not res:
                raise TimeoutError(result) from e
            if isinstance(e, ConnectError):
                if 'errno 61' in result.lower():
                    raise
                else:
                    raise_extractor_error(result, _from=e)

            if res.status_code == 404:
                res.raise_for_status()
            if res.status_code == 503:
                raise StatusError503(repr(e)) from None
            raise_extractor_error(result, _from=e)

            return result

        premsg = f'[stream_http_request][{self._get_url_print(url)}]'
        if msg := kwargs.get('msg', None):
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

            with client.stream("GET", url, **_kwargs) as res:

                res.raise_for_status()

                if isinstance(truncate_after, str):
                    _res = ""
                    for chunk in res.iter_text(chunk_size=chunk_size):
                        if chunk:
                            _res += chunk
                            if truncate_after in _res:
                                break
                else:
                    _check_max = lambda x: x >= truncate_after if truncate_after else False
                    _res = b""
                    for chunk in res.iter_bytes(chunk_size=chunk_size):
                        if chunk:
                            _res += chunk
                        if _check_max(res.num_bytes_downloaded):
                            break

                return _res

        except Exception as e:
            _msg_err = _get_error_message(e, res)
        finally:
            self.logger_debug(f"{premsg} {res}:{_msg_err}")

    def send_http_request(self, url, **kwargs):

        kwargs.setdefault('client', self._CLIENT)
        return SeleniumInfoExtractor._send_http_request(url, **kwargs)

    @classmethod
    def _send_http_request(cls, url, **kwargs):
        _type = kwargs.pop('_type', "GET")
        fatal = kwargs.pop('fatal', True)
        _logger = kwargs.pop('logger', cls.LOGGER.debug)  # type: ignore
        premsg = f'[send_http_request][{cls._get_url_print(url)}][{_type}]'
        if msg := kwargs.pop('msg', None):
            premsg = f'{msg}{premsg}'

        _close_cl = False
        if not (client := kwargs.pop('client', None)):
            client = cls.get_temp_client()
            _close_cl = True

        req = res = _msg_err = None

        try:
            req = client.build_request(_type, url, **kwargs)
            if not (res := client.send(req)):
                return None
            elif fatal:
                res.raise_for_status()
            return res
        except ConnectError as e:
            _msg_err = f"{premsg} {str(e)}"
            if 'errno 61' in _msg_err.lower():
                raise
            else:
                raise_extractor_error(_msg_err, _from=e)
        except HTTPStatusError as e:
            e.args = (e.args[0].split(' for url')[0],)
            _msg_err = f"{premsg} {str(e)}"
            if e.response.status_code == 403:
                raise_reextract_info(_msg_err)
            elif e.response.status_code in (502, 503):
                raise StatusError503(_msg_err) from None
            else:
                raise
        except Exception as e:
            _msg_err = f"{premsg} {repr(e)}"
            if not res:
                raise TimeoutError(_msg_err) from e
            else:
                raise_extractor_error(_msg_err, _from=e)
        finally:
            _error = f"Error: {_msg_err}\n" if _msg_err else ''
            _resp = f"{res}\n" if res else "<Response ''>\n"
            _req = f"{req}:{req.headers}" if req else "<Requests ''>"
            _logger(
                f"[{cls.IE_NAME}] {_error}{_resp}{_req}")
            if _close_cl:
                client.close()
