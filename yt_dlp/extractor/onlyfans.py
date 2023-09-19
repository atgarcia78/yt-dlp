import hashlib
import logging
import re
import sys
import os
import threading
import time
import traceback
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Union, cast
import json
import http

import httpx

from .commonwebdriver import (
    By,
    Keys,
    SeleniumInfoExtractor,
    dec_on_driver_timeout,
    dec_on_exception,
    ec,
    limiter_0_1,
)
from ..utils import (
    ExtractorError,
    find_available_port,
    int_or_none,
    traverse_obj,
    try_get,
)

from urllib.parse import urlparse

logger = logging.getLogger('onlyfans')


class AccountBase:
    _CONFIG_RULES = 'https://raw.githubusercontent.com/SneakyOvis/onlyfans-dynamic-rules/main/rules.json'
    _POST_LIMIT = 50
    _LOCK = threading.Lock()

    def __init__(self, ie, **kwargs):
        self.cookies = kwargs.get('cookie', '')
        self.xbc = kwargs.get('x-bc')
        self.userAgent = kwargs.get('user-agent')

        if any([not self.cookies, not self.xbc, not self.userAgent]):
            raise Exception('error when init account')

        self.session = httpx.Client(**ie._CLIENT_CONFIG)
        self.asession = httpx.AsyncClient(**ie._CLIENT_CONFIG)

        self.cache = ie.cache

        self.parse_cookies()

        self.count = {}

        rules = self.session.get(AccountBase._CONFIG_RULES).json()
        self.appToken = rules['app-token']
        self.signStaticParam = rules['static_param']
        self.signChecksumConstant = rules['checksum_constant']
        self.signChecksumIndexes = rules['checksum_indexes']
        self.signPrefix = rules['prefix']
        self.signSuffix = rules['suffix']

        self.logger = logging.getLogger('onlyfans_api')

    def parse_cookies(self):
        if ';' in self.cookies:
            _cookies = self.cookies.split(';')
        else:
            _cookies = self.cookies.split(',')

        self.authID = ''
        for cookie in _cookies:
            name, value = cookie.strip().split('=')
            if name == 'auth_id':
                self.authID = value
            self.session.cookies.set(name=name, value=value, domain='onlyfans.com')
            self.asession.cookies.set(name=name, value=value, domain='onlyfans.com')

    def createHeaders(self, path):
        timestamp = str(int(time.time() * 1000))
        sha = hashlib.sha1('\n'.join([self.signStaticParam, timestamp, path, self.authID]).encode('utf-8')).hexdigest()
        checksum = sum(ord(sha[n]) for n in self.signChecksumIndexes) + self.signChecksumConstant
        sign = ':'.join([self.signPrefix, sha, '%x' % checksum, self.signSuffix])
        return {
            'accept': 'application/json, text/plain, */*',
            'app-token': self.appToken,
            'sign': sign,
            'time': timestamp,
            'user-id': self.authID,
            'user-agent': self.userAgent,
            'x-bc': self.xbc
        }

    def get(self, path, _headers=None) -> Any:
        headers = self.createHeaders(path)
        if _headers:
            headers.update(_headers)
        response = self.session.get(f'https://onlyfans.com{path}', headers=headers)

        self.logger.debug(f'[get] {response.request.url}')

        if response.status_code == 200:
            return response.json()
        else:
            self.logger.error(f'Path: {path}, Error: {response.status_code}, response text: {response.text}')
            return {}

    def post(self, path, _headers=None, _content=None):
        headers = self.createHeaders(path)
        if _headers:
            headers.update(_headers)
        response = self.session.post(f'https://onlyfans.com{path}', headers=headers, content=_content)

        self.logger.debug(f'[get] {response.request.url} {response.request.headers} {response.request.content}')

        if response.status_code == 200:
            return response
        else:
            self.logger.error(f'Path: {path}, Error: {response.status_code}, response text: {response.text}')
            return {}


class Account(AccountBase):
    def getMe(self) -> dict:
        return self.get('/api2/v2/users/me')

    @lru_cache
    def getUserId(self, account) -> Union[int, None]:
        if (data := self.get(f'/api2/v2/users/{account}')):
            return data.get('id')

    @lru_cache
    def getUserName(self, userid) -> Union[str, None]:
        if (data := self.get(f'/api2/v2/users/list?a%5B%5D={userid}')):
            return data.get(str(userid), {}).get('username')

    @lru_cache
    def getActSubs(self) -> dict:
        offset = 0
        subs = {}
        _base_url = '/api2/v2/lists/994217785/users?offset=%s&limit=50'
        while True:
            _url = _base_url % offset
            data = self.get(_url)
            if not data:
                break
            subs.update({user['username']: user['id'] for user in data})
            if len(data) == 0 or len(data) < 10:
                break
            offset += 10

        return subs

    def getVideosCount(self, userid) -> Union[int, None]:
        if (data := self.get(f'/api2/v2/users/{userid}/posts/videos?limit=1&skip_users=all&format=infinite&counters=1')):
            if (_res := traverse_obj(data, ('counters', 'videosCount'), default=None)):
                _res = cast(int, _res)
                return int(_res)

    def getVideoPosts(self, userid, account, total, order="publish_date_desc", num=10, use_cache=False):
        count = 0
        posts = []

        if use_cache:
            if (_res := self.cache.load('onlyfans', f'{account}_{order}_num_{num}_limit_{self._POST_LIMIT}')):
                if (datetime.now() - datetime.fromtimestamp(os.stat(self.cache._get_cache_fn('onlyfans', f'{account}_{order}_num_{num}_limit_{self._POST_LIMIT}', 'json')).st_mtime)) < timedelta(days=1):
                    return _res

        limit = self._POST_LIMIT
        if num < self._POST_LIMIT:
            limit = num
        _base_url = f'/api2/v2/users/{userid}/posts/videos?limit=%s&order={order}&skip_users=all&format=infinite&%s'
        _tail = 'counters=0'
        while True:
            _url = _base_url % (limit, _tail)
            self.logger.info(f'[getvideoposts][{account}] {_url}')
            data = self.get(_url)
            if not data:
                break
            posts.extend(data['list'])
            count += (_count := len(data['list']))
            with AccountBase._LOCK:
                self.count[userid] += _count
                self.logger.info(f'[getvideoposts][{account}] Videos: {num} Count: {count} totalVideos: {total} totalCount: {self.count[userid]}')

            if (num == total):
                if (not (_res := data['hasMore']) or _res == 'false'):
                    self.logger.info(f'[getvideoposts][{account}] hasMore=False')
                    break
            else:
                _pend = num - count
                if _pend <= 0:
                    break
                if _pend < self._POST_LIMIT:
                    limit = _pend
                else:
                    limit = self._POST_LIMIT

            if order.endswith('desc'):
                _tail = f"counters=0&beforePublishTime={data['tailMarker']}"
            elif order.endswith('asc'):
                _tail = f"counters=0&afterPublishTime={data['tailMarker']}"

        if use_cache:
            self.cache.store('onlyfans', f'{account}_{order}_num_{num}_limit_{self._POST_LIMIT}', posts)

        return posts

    def getMessagesChat(self, userid):
        messages = []
        _base_url = f'/api2/v2/chats/{userid}/messages?limit=200&order=desc&skip_users=all%s'
        _tail = ''
        while True:
            _url = _base_url % _tail
            self.logger.info(f'[getmsgschat] {_url}')
            data = self.get(_url)
            if not data:
                break
            messages.extend(data['list'])
            self.logger.info(f'[getmsgschat] Count: {len(messages)}')
            if not (_res := data['hasMore']) or _res == 'false':
                break
            _tail = f'&id={messages[-1].get("id")}'

        return messages

    def getPost(self, postid):
        return self.get(f'/api2/v2/posts/{postid}?skip_users=all')

    def getPurchased(self):
        limit = self._POST_LIMIT
        offset = 0
        videos = []
        _base_url = f'/api2/v2/posts/paid?limit={limit}&skip_users=all&format=infinite&sort=all&offset=%s'
        while True:
            _url = _base_url % offset
            self.logger.debug(f'[getpurchased] {_url}')
            data = self.get(_url)
            if not data:
                break
            videos.extend(data.get('list'))
            self.logger.info(f'[getpurchased] Count: {len(videos)}')
            if not (_res := data['hasMore']) or _res == 'false':
                break
            offset += limit

        return videos


class error404_or_found:
    def __init__(self, class_name=None):
        self.class_name = class_name

    def __call__(self, driver):
        el = driver.find_elements(by=By.CLASS_NAME, value="b-404")
        if el:
            return ("error404", el[0])
        else:
            if self.class_name:
                el = driver.find_elements(by=By.CLASS_NAME, value=self.class_name)
                if el:
                    return (self.class_name, el[0])
                else:
                    return False
            else:
                el = driver.find_elements(by=By.CLASS_NAME, value="b-profile__user")
                if el:
                    return ("userfound", el[0])
                else:
                    el = driver.find_elements(by=By.CLASS_NAME, value="video-wrapper")
                    if el:
                        return ("postfound", el[0])
                    return False


class alreadylogin_or_reqtw:
    def __call__(self, driver):
        el = driver.find_elements(by=By.CSS_SELECTOR, value="nav.l-header__menu")
        if el:
            return ("loginok", el[0])
        else:

            el = driver.find_elements(by=By.CSS_SELECTOR, value="a.g-btn.m-rounded.m-twitter.m-lg")

            if el:
                return ("reqlogin", el[0])
            else:
                return False


class succ_or_twlogin:
    def __call__(self, driver):
        el = driver.find_elements(by=By.CSS_SELECTOR, value="nav.l-header__menu")
        if el:
            return ("loginok", el[0])
        else:

            el_username = driver.find_elements(by=By.CSS_SELECTOR, value="input#username_or_email.text")
            el_password = driver.find_elements(by=By.CSS_SELECTOR, value="input#password.text")
            el_login = driver.find_elements(by=By.CSS_SELECTOR, value="input#allow.submit.button.selected")

            if el_username and el_password and el_login:
                return ("twlogin", el_username[0], el_password[0], el_login[0])

            else:
                return False


class succ_or_twrelogin:
    def __call__(self, driver):
        el = driver.find_elements(by=By.CSS_SELECTOR, value="nav.l-header__menu")
        if el:
            return ("loginok", el[0])
        else:

            el_username = driver.find_elements(by=By.PARTIAL_LINK_TEXT, value="usuario") or driver.find_elements(by=By.PARTIAL_LINK_TEXT, value="user")
            el_password = driver.find_elements(by=By.PARTIAL_LINK_TEXT, value="Contra") or driver.find_elements(by=By.PARTIAL_LINK_TEXT, value="Pass")

            el_login = driver.find_elements(by=By.PARTIAL_LINK_TEXT, value="Iniciar") or driver.find_elements(by=By.PARTIAL_LINK_TEXT, value="Start")

            if el_username and el_password and el_login:
                return ("twrelogin", el_username[0], el_password[0], el_login[0])

            else:
                return False


class scroll_chat:

    _css_selec = "".join([
        "div.b-chats__scrollbar.m-custom-scrollbar.b-chat__messages.",
        "m-native-custom-scrollbar.m-scrollbar-y.m-scroll-behavior-auto"])

    _class_name = "infinite-loading-container.b-chat__loading.b-chat__loading-top"

    def __init__(self, pre, logger):
        self.logger = logger
        self.pre = pre
        self.init = False

    def __call__(self, driver):

        if not self.init:
            el_scroll = driver.find_element(By.CSS_SELECTOR, self._css_selec)
            el_cont = el_scroll.find_elements(By.CLASS_NAME, self._class_name)

            if not el_cont:
                return True
            else:
                self.scroll = el_scroll
                self.cont = el_cont[0]
                self.init = True

        try:
            self.cont.is_enabled()
            self.scroll.send_keys(Keys.HOME)
            return False
        except Exception as e:
            self.logger(f"{self.pre}[scroll_chat] {type(e)}")
            return True


def upt_dict(info_dict: Union[dict, list], **kwargs) -> Union[dict, list]:
    if isinstance(info_dict, dict):
        info_dict_list = [info_dict]
    else:
        info_dict_list = info_dict
    for _el in info_dict_list:
        _el.update(**kwargs)
    return info_dict


def get_list_unique(list_dict, key='id') -> list:
    _dict = OrderedDict()
    for el in list_dict:
        _dict.setdefault(el[key], el)
    return list(_dict.values())


def load_config():
    data = None
    try:
        with open("/Users/antoniotorres/.config/yt-dlp/onlyfans_conf.json", "r") as f:
            data = json.load(f)
    except Exception:
        pass
    return data if data else {"subs": {}}


class OnlyFansBaseIE(SeleniumInfoExtractor):

    _SITE_URL = "https://onlyfans.com"
    _NETRC_MACHINE = 'twitter2'
    _LOCK = threading.Lock()
    _MODE_DICT = {
        "favorites": {"order": "favorites_count_desc", "num": 25},
        "tips": {"order": "tips_summ_desc", "num": 25},
        "all": {"order": "publish_date_desc", "num": 0, "use_cache": True},
        "latest": {"order": "publish_date_desc", "num": 10}
    }
    conn_api: Account

    _CONF = load_config()

    @dec_on_exception
    @limiter_0_1.ratelimit("onlyfans", delay=True)
    def _get_filesize(self, _vurl):

        res = httpx.head(_vurl, follow_redirects=True)
        res.raise_for_status()

        return (int_or_none(res.headers.get('content-length')))

    @dec_on_driver_timeout
    @limiter_0_1.ratelimit("onlyfans2", delay=True)
    def send_driver_request(self, driver, url):

        driver.execute_script("window.stop();")
        driver.get(url)

    def _get_conn_api(self):

        try:
            if (_auth_config := (self.cache.load('onlyfans', 'auth_config') or self._get_auth_config())):
                OnlyFansBaseIE.conn_api = Account(self, **_auth_config)

                if OnlyFansBaseIE.conn_api.getMe():
                    return True

            if (_auth_config := self._get_auth_config()):
                OnlyFansBaseIE.conn_api = Account(self, **_auth_config)
                if OnlyFansBaseIE.conn_api .getMe():
                    return True

            self.report_warning('[get_conn_api] fail when checking config')
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'[get_conn_api] {repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(f'[get_conn_api] {repr(e)}')

    @SeleniumInfoExtractor.syncsem()
    def _get_auth_config(self):

        _auth_config = {}
        _port = find_available_port() or 8080
        driver = self.get_driver(host='127.0.0.1', port=_port)
        try:
            with self.get_har_logs('onlyfans', port=_port) as harlogs:
                _har_file = harlogs.har_file
                self._login(driver)

            req = try_get(
                self.scan_for_request(
                    r'api2/v2/.+', har=_har_file, inclheaders=True,
                    response=True, _all=True),
                lambda x: x[-1])
            if req:
                for _header_name in ('cookie', 'x-bc', 'user-agent'):
                    _auth_config.update({_header_name: req['headers'].get(_header_name)})
                self.cache.store('onlyfans', 'auth_config', _auth_config)
                try:
                    if os.path.exists(_har_file):
                        os.remove(_har_file)
                except OSError:
                    return self.logger_info("Unable to remove the har file")
            return _auth_config
        finally:
            self.rm_driver(driver)

    def _login(self, driver):

        username, password = self._get_login_info()

        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)

        self.report_login()

        try:

            self.send_driver_request(driver, self._SITE_URL)

            el_init = self.wait_until(driver, 60, alreadylogin_or_reqtw())
            if not el_init:
                raise ExtractorError("Error in login")
            if el_init[0] == "loginok":
                self.to_screen("Login OK")
                return
            else:

                self.send_driver_request(driver, el_init[1].get_attribute('href'))

            el = self.wait_until(driver, 60, succ_or_twlogin())

            if el:
                if el[0] == "loginok":
                    self.to_screen("Login OK")
                    return

                else:
                    username_element, password_element, login_element = el[1], el[2], el[3]
                    username_element.send_keys(username)
                    self.wait_until(driver, 0.5)
                    password_element.send_keys(password)
                    self.wait_until(driver, 0.5)
                    login_element.submit()

                    el = self.wait_until(driver, 60, succ_or_twrelogin())

                    if el:
                        if el[0] == "loginok":
                            self.to_screen("Login OK")
                            return
                        else:
                            username_element, password_element, login_element = el[1], el[2], el[3]
                            username_element.send_keys(username)
                            self.wait_until(driver, 0.5)
                            password_element.send_keys(password)
                            self.wait_until(driver, 0.5)
                            login_element.submit()
                            el = self.wait_until(driver, 30, ec.presence_of_all_elements_located(
                                (By.CSS_SELECTOR, "nav.l-header__menu")))
                            if el:
                                self.to_screen("Login OK")
                                return
                            else:
                                raise ExtractorError("login error")

                    else:
                        raise ExtractorError(
                            "Error in relogin via twitter: couldnt find any of the twitter login elements")

            else:
                raise ExtractorError(
                    "Error in login via twitter: couldnt find any of the twitter login elements")

        except Exception as e:
            self.to_screen(f'{repr(e)}')
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise
        finally:
            driver.execute_script("window.stop();")
            self.wait_until(driver, 1)

    def getlicense(self, licurl: str, challenge: bytes) -> bytes:
        headers = {'Origin': 'https://onlyfans.com', 'Referer': 'https://onlyfans.com/'}

        _path = cast(str, try_get(urlparse(licurl), lambda x: x.path + '?' + x.query))
        return OnlyFansBaseIE.conn_api.post(_path, _headers=headers, _content=challenge).content

    def _extract_from_json(self, data_post, user_profile=None):

        def save_config():
            try:
                with open("/Users/antoniotorres/.config/yt-dlp/onlyfans_conf.json", "w") as f:
                    json.dump(OnlyFansBaseIE._CONF, f)
            except Exception as e:
                self.report_warning(f'[extract_from_json] error when updating conf file {repr(e)}')

        try:
            account = user_profile
            if not account:
                userid = traverse_obj(data_post, ('fromUser', 'id'), ('author', 'id'))
                if not userid:
                    raise ExtractorError('no userid')
                else:
                    if str(userid) not in OnlyFansBaseIE._CONF['subs']:
                        if (account := OnlyFansBaseIE.conn_api.getUserName(userid)):
                            OnlyFansBaseIE._CONF['subs'][str(userid)] = account
                            save_config()
                    else:
                        account = OnlyFansBaseIE._CONF['subs'][str(userid)]

            _datevideo = cast(str, traverse_obj(data_post, 'createdAt', 'postedAt', default=''))
            if not _datevideo:
                raise ExtractorError("no datevideo")
            date_timestamp = int(datetime.fromisoformat(_datevideo).timestamp())

            _entries = []

            for _media in data_post['media']:

                if _media['type'] == "video" and _media['canView']:

                    videoid = str(_media['id'])
                    _formats = []

                    # de momento disabled
                    if (_drm := traverse_obj(_media, ('files', 'drm'))):
                        if (_mpd_url := traverse_obj(_drm, ('manifest', 'dash'))):
                            _signature = cast(dict, traverse_obj(_drm, ('signature', 'dash'), default={}))
                            for name, value in _signature.items():
                                OnlyFansBaseIE.conn_api.session.cookies.jar.set_cookie(http.cookiejar.Cookie(
                                    version=0, name=name, value=value, port=None, port_specified=False,
                                    domain='onlyfans.com', domain_specified=True, domain_initial_dot=True, path='/',
                                    path_specified=True, secure=False, expires=None, discard=False, comment=None,
                                    comment_url=None, rest={}))
                            _cookie_str = OnlyFansBaseIE.conn_api.cookies
                            self.logger_debug(f"[extract_from_json] cookies {_cookie_str}")
                            for cookie in OnlyFansBaseIE.conn_api.session.cookies.jar:
                                self._downloader.cookiejar.set_cookie(cookie)
                            _headers = {'referer': 'https://onlyfans.com/', 'origin': 'https://onlyfans.com'}
                            mpd_xml = self._download_xml(_mpd_url, video_id=videoid, headers=_headers)
                            _pssh_list = list(set(list(map(
                                lambda x: x.text, list(mpd_xml.iterfind('.//{urn:mpeg:cenc:2013}pssh'))))))
                            _base_api_media = "https://onlyfans.com/api2/v2/users/media"
                            _licurl = f"{_base_api_media}/{videoid}/drm/post/{data_post['id']}?type=widevine"
                            self.logger_debug(f"[extract_from_json] drm: licurl [{_licurl}] pssh {_pssh_list}")

                            _formats_dash, _ = self._extract_mpd_formats_and_subtitles(
                                _mpd_url, videoid, mpd_id='dash', headers=_headers)
                            for _fmt in _formats_dash:
                                if (_head := _fmt.get('http_headers')):
                                    _head.update(_headers)
                                else:
                                    _fmt.update({'http_headers': _headers})
                            _formats.extend(_formats_dash)
                    else:
                        _pssh_list = None
                        _licurl = None
                        orig_width = orig_height = None
                        if (_url := traverse_obj(_media, ('source', 'source'))):

                            _formats.append({
                                'url': _url,
                                'width': (orig_width := _media.get('info', {}).get('source', {}).get('width')),
                                'height': (orig_height := _media.get('info', {}).get('source', {}).get('height')),
                                'format_id': f"{orig_height}p-orig",
                                #  'filesize': _filesize,
                                'format_note': "original",
                                'ext': "mp4"
                            })

                        if _url2 := _media.get('videoSources', {}).get('720'):
                            #  _filesize2 = self._get_filesize(_url2)

                            if orig_width and orig_height and (orig_width > orig_height):
                                height = 720
                                width = 1280
                            else:
                                width = 720
                                height = 1280

                            _formats.append({
                                'format_id': f"{height}p",
                                'url': _url2,
                                'format_note': "720",
                                'height': height,
                                'width': width,
                                #  'filesize': _filesize2,
                                'ext': "mp4"
                            })

                        if _url3 := _media.get('videoSources', {}).get('240'):
                            #  _filesize3 = self._get_filesize(_url3)

                            if orig_width and orig_height and (orig_width > orig_height):
                                height = 240
                                width = 426
                            else:
                                width = 426
                                height = 240

                            _formats.append({
                                'format_id': f"{height}p",
                                'url': _url3,
                                'format_note': "240",
                                'height': height,
                                'width': width,
                                #  'filesize': _filesize3,
                                'ext': "mp4"
                            })

                    if _formats:

                        _entry = {
                            "id": videoid,
                            "release_timestamp": date_timestamp,
                            "release_date": _datevideo.split("T")[0].replace("-", ""),
                            "title": f'{_datevideo.split("T")[0].replace("-", "")}_from_{account}',
                            "webpage_url": f'https://onlyfans.com/{data_post["id"]}/{account}',
                            "formats": _formats,
                            "duration": _media.get('info', {}).get('source', {}).get('duration', 0),
                            "ext": "mp4",
                            "_drm": {'licurl': _licurl, 'pssh': _pssh_list},
                            "extractor": self.IE_NAME,
                            "extractor_key": self.ie_key()}

                        _entries.append(_entry)

            return _entries

        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'[extract_from_json][output] {repr(e)} \n{"!!".join(lines)}')

    def _get_videos_from_subs(self, userid, account, mode='latest'):

        _url_videos = f"https://onlyfans.com/{account}/{mode}"
        self.report_extraction(_url_videos)
        pre = f'[get_videos_subs][{account}][{mode}]'
        list_json = []
        OnlyFansBaseIE.conn_api.count[userid] = 0

        try:

            if mode == 'chat':
                list_json = OnlyFansBaseIE.conn_api.getMessagesChat(userid)

            else:
                _total = OnlyFansBaseIE.conn_api.getVideosCount(userid)

                if _total:

                    if mode == "all" and (_total > 6 * OnlyFansBaseIE.conn_api._POST_LIMIT):

                        with ThreadPoolExecutor(thread_name_prefix='onlyfans') as exe:
                            futures = [
                                exe.submit(OnlyFansBaseIE.conn_api.getVideoPosts, userid, account, _total,
                                           order="publish_date_desc", num=(_total // 2), use_cache=True),
                                exe.submit(OnlyFansBaseIE.conn_api.getVideoPosts, userid, account, _total,
                                           order="publish_date_asc", num=(_total // 2) + 1, use_cache=True)]

                        _list_json = futures[0].result() + list(reversed(futures[1].result()))
                        list_json = get_list_unique(_list_json, key='id')

                        self.to_screen(
                            f"{pre} From {len(_list_json)} number of video posts unique: {len(list_json)}")

                    else:
                        _conf = OnlyFansBaseIE._MODE_DICT[mode].copy()
                        if mode == "all":
                            _conf["num"] = _total
                        list_json = OnlyFansBaseIE.conn_api.getVideoPosts(userid, account, _total, **_conf)

                        self.to_screen(f"{pre} Number of video posts unique: {len(list_json)}")

            if not list_json:
                raise ExtractorError(f"{pre} no entries")

            entries = OrderedDict()
            for data_json in list_json:
                if (_entry := self._extract_from_json(data_json, user_profile=account)):
                    for _video in _entry:
                        if not _video['id'] in entries:
                            entries[_video['id']] = _video
                    else:
                        if _video.get('duration', 1) > entries[_video['id']].get('duration', 0):
                            entries[_video['id']] = _video

            return entries

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(f'{pre} {repr(e)}')

    def _real_initialize(self):

        super()._real_initialize()
        with OnlyFansBaseIE._LOCK:
            if not hasattr(OnlyFansBaseIE, 'conn_api'):
                self._get_conn_api()
        assert OnlyFansBaseIE.conn_api
        OnlyFansBaseIE.conn_api = cast(Account, OnlyFansBaseIE.conn_api)


class OnlyFansPostIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:post:playlist'  # type: ignore
    IE_DESC = 'onlyfans:post:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans.com/(?P<post>[\d]+)/(?P<account>[^/]+)"

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url: str):

        self.report_extraction(url)

        post, account = try_get(
            re.search(self._VALID_URL, url),  # type: ignore
            lambda x: x.group("post", "account"))

        self.to_screen("post:" + post + ":" + "account:" + account)

        assert OnlyFansBaseIE.conn_api

        data_json = OnlyFansBaseIE.conn_api.getPost(post)

        entries = OrderedDict()

        if data_json:
            # self.to_screen(data_json)
            if (_entry := self._extract_from_json(data_json, user_profile=account)):
                for _video in _entry:
                    if not _video['id'] in entries:
                        entries[_video['id']] = _video
                    else:
                        if _video['duration'] > entries[_video['id']]['duration']:
                            entries[_video['id']] = _video
        if entries:
            entries_list = upt_dict(list(entries.values()), original_url=url)
            return self.playlist_result(entries_list, f"onlyfans:{account}:{post}", f"onlyfans:{account}:{post}")
        else:
            raise ExtractorError("No entries")


class OnlyFansPlaylistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:playlist'  # type: ignore
    IE_DESC = 'onlyfans:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans.com/(?P<account>[^/]+)/(?P<mode>(?:all|latest|newest|new|chat|favorites|favourites|tips))(\?(?P<query>.+))?"

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        info = cast(dict, try_get(
            re.search(self._VALID_URL, url),  # type: ignore
            lambda x: x.groupdict()))
        self.to_screen(info)
        account, mode, query = info['account'], info.get('mode', 'latest'), info.get('query')
        if mode in ('new', 'newest'):
            mode = 'latest'
        elif mode == 'favourites':
            mode = 'favorites'
        params = {}
        if query:
            params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
        try:
            userid = OnlyFansBaseIE.conn_api.getUserId(account)
            if (entries := self._get_videos_from_subs(userid, account, mode=mode)):
                entries_list = cast(list, upt_dict(list(entries.values()), original_url=url))
                num_entries = len(entries_list)
                last = int_or_none(params.get('last'))
                first = int(params.get('first', 0))
                dur_min = int(params.get('duration-min', 0))
                if last and last > first:
                    entries_list = entries_list[first:last]
                else:
                    entries_list = entries_list[first:]
                if dur_min:
                    entries_list = list(filter(
                        lambda x: int(x.get('duration', dur_min)) >= dur_min,
                        entries_list))
                self.to_screen(f"Entries[{num_entries}] After filter duration min[{len(entries_list)}]")
                return self.playlist_result(
                    entries=entries_list, playlist_id=f"onlyfans:{account}:{mode}",
                    playlist_title=f"onlyfans:{account}:{mode}")
            else:
                raise ExtractorError("no entries")

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))


class OnlyFansPaidlistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:paidlist:playlist'  # type: ignore
    IE_DESC = 'onlyfanspaidlist:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans\.com/paid"

    def _real_initialize(self):
        super()._real_initialize()

    def _get_videos_purchased(self):
        self.report_extraction("https://onlyfans.com/paid")
        pre = '[get_videos_purchased]'

        try:
            list_json = OnlyFansBaseIE.conn_api.getPurchased()

            if not list_json:
                raise ExtractorError(f"{pre} no entries")

            with ThreadPoolExecutor(thread_name_prefix='onlyfans') as exe:
                futures = {exe.submit(self._extract_from_json, info_json): info_json for info_json in list_json}

            entries = OrderedDict()
            for fut in futures:
                try:
                    if (_entry := fut.result()):
                        for _video in _entry:
                            if not _video['id'] in entries:
                                entries[_video['id']] = _video
                            else:
                                if _video.get('duration', 1) > entries[_video['id']].get('duration', 0):
                                    entries[_video['id']] = _video
                except Exception as e:
                    self.to_screen(f"{pre} error with postid {futures[fut].get('id')} - {repr(e)}")

            return entries

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(f'{pre} {repr(e)}')

    def _real_extract(self, url):

        try:
            if (entries := self._get_videos_purchased()):
                entries_list = upt_dict(list(entries.values()), original_url=url)
                return self.playlist_result(
                    entries=entries_list, playlist_id="onlyfans:paid", playlist_title="onlyfans:paid")
            else:
                raise ExtractorError("no entries")

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))


class OnlyFansActSubslistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:actsubslist:playlist'  # type: ignore
    IE_DESC = 'onlyfansactsubslist:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans\.com/actsubs"
    _ACT_SUBS_URL = "https://onlyfans.com/my/subscriptions/active"
    _ACT_SUBS_PAID_URL = "https://onlyfans.com/collections/user-lists/994217785"

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
        try:
            entries = []
            if (actsubs_dict := OnlyFansBaseIE.conn_api.getActSubs()):
                self.to_screen(f"act_subs: {list(actsubs_dict.keys())}")
                with ThreadPoolExecutor(thread_name_prefix='OFPlaylist') as ex:
                    futures = [ex.submit(self._get_videos_from_subs, _userid, _account)
                               for _account, _userid in actsubs_dict.items()]

                for fut in futures:
                    try:
                        _entries = cast(dict, fut.result())
                        entries += upt_dict(list(_entries.values()), original_url=url)
                    except Exception as e:
                        self.to_screen(repr(e))

                return self.playlist_result(entries, "onlyfans:actsubs", "onlyfans:actsubs")

            else:
                raise ExtractorError("no entries")

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))
