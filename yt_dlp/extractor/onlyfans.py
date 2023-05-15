import logging
import re
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import cast, Union, Any
from collections import OrderedDict

import httpx

from .commonwebdriver import (
    By,
    Keys,
    SeleniumInfoExtractor,
    dec_on_exception,
    ec,
    limiter_0_1,
)
from ..utils import ExtractorError, int_or_none, traverse_obj, try_get

import hashlib
import time
import urllib3.util.url as urllib3_url

logger = logging.getLogger('onlyfans')


def hook_invalid_chars(component, allowed_chars):
    # handle url encode here, or do nothing
    return component


urllib3_url._encode_invalid_chars = hook_invalid_chars  # type: ignore


class AccountBase:
    _CONFIG_RULES = 'https://raw.githubusercontent.com/SneakyOvis/onlyfans-dynamic-rules/main/rules.json'

    def __init__(self, ie, **kwargs):
        self.cookies = kwargs.get('cookie', '')
        self.xbc = kwargs.get('x-bc')
        self.userAgent = kwargs.get('user-agent')
        self.ie = ie

        if any([not self.cookies, not self.xbc, not self.userAgent]):
            raise Exception('error when init account')

        self.authID = self.getAuthID()
        self.session = self.ie._CLIENT

        rules = self.session.get(AccountBase._CONFIG_RULES).json()
        self.appToken = rules['app-token']
        self.signStaticParam = rules['static_param']
        self.signChecksumConstant = rules['checksum_constant']
        self.signChecksumIndexes = rules['checksum_indexes']
        self.signPrefix = rules['prefix']
        self.signSuffix = rules['suffix']

        self.logger = logging.getLogger('onlyfans_api')

    def getAuthID(self):
        for cookie in self.cookies.split(';'):
            name, value = cookie.strip().split('=')
            if name == 'auth_id':
                return value
        return ''

    def createHeaders(self, path):
        timestamp = str(int(time.time() * 1000))
        sha = hashlib.sha1('\n'.join([self.signStaticParam, timestamp, path, self.authID]).encode('utf-8')).hexdigest()
        checksum = sum(ord(sha[n]) for n in self.signChecksumIndexes) + self.signChecksumConstant
        sign = ':'.join([self.signPrefix, sha, '%x' % checksum, self.signSuffix])
        return {
            'accept': 'application/json, text/plain, */*',
            'app-token': self.appToken,
            'cookie': self.cookies,
            'sign': sign,
            'time': timestamp,
            'user-id': self.authID,
            'user-agent': self.userAgent,
            'x-bc': self.xbc
        }

    def get(self, path) -> Any:
        with limiter_0_1.ratelimit("onlyfans2", delay=True):
            headers = self.createHeaders(path)
            response = self.session.get(f'https://onlyfans.com{path}', headers=headers)

            self.logger.debug(f'[get] {response.request.url}')

            if response.status_code == 200:
                return response.json()
            else:
                self.logger.error(f'Error: {response.status_code}, response text: {response.text}')
                return {}


class Account(AccountBase):
    def getMe(self) -> dict:
        return self.get('/api2/v2/users/me')

    def getUserId(self, account) -> Union[int, None]:
        if (data := self.get(f'/api2/v2/users/{account}')):
            return data.get('id')

    def getUserName(self, userid) -> Union[str, None]:
        if (data := self.get(f'/api2/v2/users/list?x[]={userid}')):
            return data.get(str(userid), {}).get('username')

    def getActSubs(self) -> dict:
        offset = 0
        subs = {}
        _base_url = '/api2/v2/lists/994217785/users?offset=%s&limit=10'
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

    def getVideoPosts(self, userid, order="publish_date_desc", num=10):
        count = 0
        posts = []
        limit = 50
        if 0 < num < 50:
            limit = num
        _base_url = f'/api2/v2/users/{userid}/posts/videos?limit=%s&order={order}&skip_users=all&format=infinite&%s'
        _tail = "counters=1"
        while True:
            _url = _base_url % (limit, _tail)
            self.logger.info(f'[getvideoposts] {_url}')
            data = self.get(_url)
            if not data:
                break
            posts.extend(data['list'])
            count += len(data['list'])
            if (counters := data.get('counters')):
                self.logger.info(f'[getvideoposts] Counters: {counters}')
            self.logger.info(f'[getvideoposts] Count: {count}')
            if not (_res := data['hasMore']) or _res == 'false':
                break
            if num > 0:
                _pend = num - count
                if _pend <= 0:
                    break
                if 0 < _pend < 50:
                    limit = _pend
            _tail = f"counters=0&beforePublishTime={data['tailMarker']}"

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
        limit = 50
        offset = 0
        videos = []
        _base_url = f'/api2/v2/posts/paid?limit={limit}&skip_users=all&format=infinite&sort=all&offset=%s'
        while True:
            _url = _base_url % offset
            self.logger.info(f'[getpurchased] {_url}')
            data = self.get(_url)
            if not data:
                break
            videos.extend(data.get('list'))
            self.logger.info(f'[getpurchased] Count: {len(videos)}')
            if not (_res := data['hasMore']) or _res == 'false':
                break
            offset += limit

        return videos


def upt_dict(info_dict: Union[dict, list[dict]], **kwargs) -> Union[dict, list[dict]]:
    if isinstance(info_dict, dict):
        info_dict_list = [info_dict]
    else:
        info_dict_list = info_dict
    for _el in info_dict_list:
        _el.update(**kwargs)
    return info_dict


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

    _css_selec = "div.b-chats__scrollbar.m-custom-scrollbar.b-chat__messages.m-native-custom-scrollbar.m-scrollbar-y.m-scroll-behavior-auto"
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


class OnlyFansBaseIE(SeleniumInfoExtractor):

    _SITE_URL = "https://onlyfans.com"
    _NETRC_MACHINE = 'twitter2'
    _LOCK = threading.Lock()
    _USERS = {}
    conn_api: Account

    @dec_on_exception
    @limiter_0_1.ratelimit("onlyfans1", delay=True)
    def _get_filesize(self, _vurl):

        res = httpx.head(_vurl, follow_redirects=True)
        res.raise_for_status()

        return (int_or_none(res.headers.get('content-length')))

    @dec_on_exception
    @limiter_0_1.ratelimit("onlyfans2", delay=True)
    def send_driver_request(self, driver, url):

        driver.execute_script("window.stop();")
        driver.get(url)

    def _get_conn_api(self):

        driver = self.get_driver(selenium_factory="wire")

        try:
            _auth_config = self.cache.load('onlyfans', 'auth_config')
            if not _auth_config:
                _auth_config = self._get_auth_config(driver)
            OnlyFansBaseIE.conn_api = Account(**_auth_config)

            if OnlyFansBaseIE.conn_api.getMe():
                return True
            else:
                _auth_config = self._get_auth_config(driver)
                OnlyFansBaseIE.conn_api = Account(self, **_auth_config)
                if OnlyFansBaseIE.conn_api .getMe():
                    return True
                self.report_warning('[get_conn_api] fail when checking config')
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'[get_conn_api] {repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(f'[get_conn_api] {repr(e)}')
        finally:
            self.rm_driver(driver)

    def _get_auth_config(self, driver):
        _auth_config = {}
        del driver.requests
        self._login(driver)
        del driver.requests
        self.send_driver_request(driver, self._SITE_URL)
        req = driver.wait_for_request('onlyfans.com/api2/v2')
        if req:
            for _header_name in ('cookie', 'x-bc', 'user-agent'):
                _auth_config.update({_header_name: req.headers.get(_header_name)})
            self.cache.store('onlyfans', 'auth_config', _auth_config)
        return _auth_config

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
                        raise ExtractorError("Error in relogin via twitter: couldnt find any of the twitter login elements")

            else:
                raise ExtractorError("Error in login via twitter: couldnt find any of the twitter login elements")

        except Exception as e:
            self.to_screen(f'{repr(e)}')
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise
        finally:
            driver.execute_script("window.stop();")
            self.wait_until(driver, 1)

    def _extract_from_json(self, data_post, user_profile=None):

        try:

            account = user_profile or OnlyFansBaseIE._USERS.get(traverse_obj(data_post, ('fromUser', 'id'), ('author', 'id')))
            _datevideo = cast(str, traverse_obj(data_post, 'createdAt', 'postedAt', default=''))
            if not _datevideo:
                raise ExtractorError("no datevideo")
            date_timestamp = int(datetime.fromisoformat(_datevideo).timestamp())

            _entries = []

            for _media in data_post['media']:

                if _media['type'] == "video" and _media['canView']:

                    videoid = _media['id']
                    _formats = []

                    # # de momento disabled
                    # if (_drm := traverse_obj(_media, ('ffffffffffiles', 'drm'))):
                    #     if (_mpd_url := traverse_obj(_drm, ('manifest', 'dash'))):
                    #         _signature = cast(dict, traverse_obj(_drm, ('signature', 'dash'), default={}))

                    #         _cookie = "; ".join([f'{key}={val}' for key, val in _signature.items()]) + "; " + OnlyFansBaseIE.conn_api.cookies
                    #         _headers = {'cookie': _cookie, 'referer': 'https://onlyfans.com/', 'origin': 'https://onlyfans.com'}
                    #         _formats_dash, _ = self._extract_mpd_formats_and_subtitles(_mpd_url, videoid, mpd_id='dash', headers=_headers)
                    #         for _fmt in _formats_dash:
                    #             if (_head := _fmt.get('http_headers')):
                    #                 _head.update(_headers)
                    #             else:
                    #                 _fmt.update({'http_headers': _headers})
                    #         _formats.extend(_formats_dash)
                    # else:
                    if True:
                        orig_width = orig_height = None
                        if (_url := traverse_obj(_media, ('source', 'source'))):
                            #  _filesize = self._get_filesize(_url)

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
                            "id": str(videoid),
                            "release_timestamp": date_timestamp,
                            "release_date": _datevideo.split("T")[0].replace("-", ""),
                            "title": f'{_datevideo.split("T")[0].replace("-", "")}_from_{account}',
                            "webpage_url": f'https://onlyfans.com/{data_post["id"]}/{account}',
                            "formats": _formats,
                            "duration": _media.get('info', {}).get('source', {}).get('duration', 0),
                            "ext": "mp4",
                            "extractor": "onlyfans:post:playlist",
                            "extractor_key": "OnlyFansPostIE"}

                        _entries.append(_entry)

            # self.write_debug(f'[extract_from_json][output] {_entries}')
            return _entries

        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'[extract_from_json][output] {repr(e)} \n{"!!".join(lines)}')

    def _real_initialize(self):

        super()._real_initialize()
        with OnlyFansBaseIE._LOCK:
            if not hasattr(OnlyFansBaseIE, 'conn_api'):
                self._get_conn_api()
                if (_dict := self.cache.load('only_fans', 'users_dict')):
                    OnlyFansBaseIE._USERS.update(_dict)
        assert OnlyFansBaseIE.conn_api
        OnlyFansBaseIE.conn_api = cast(Account, OnlyFansBaseIE.conn_api)


class OnlyFansPostIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:post:playlist'  # type: ignore
    IE_DESC = 'onlyfans:post:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans.com/(?P<post>[\d]+)/(?P<account>[\da-zA-Z]+)"

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
            #  self.to_screen(data_json)
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
    _VALID_URL = r"https?://(?:www\.)?onlyfans.com/(?P<account>\w+)/((?P<mode>(?:all|latest|chat|favorites|tips))/?)$"
    _MODE_DICT = {"favorites": {"order": "favorites_count_desc", "num": 25},
                  "tips": {"order": "tips_summ_desc", "num": 25},
                  "all": {"order": "publish_date_desc", "num": -1},
                  "latest": {"order": "publish_date_desc", "num": 10}}

    def _real_initialize(self):
        super()._real_initialize()

    def _get_videos_from_subs(self, userid, account, mode='None'):

        _url_videos = f"https://onlyfans.com/{account}/{mode}"
        self.report_extraction(_url_videos)
        pre = f'[get_videos_subs][{account}]'
        try:
            if mode == 'chat':
                list_json = OnlyFansBaseIE.conn_api.getMessagesChat(userid)
            else:
                list_json = OnlyFansBaseIE.conn_api.getVideoPosts(userid, **self._MODE_DICT.get(mode, {}))

            if not list_json:
                raise ExtractorError(f"{pre} no entries")

            with ThreadPoolExecutor(thread_name_prefix='onlyfans') as exe:
                futures = {exe.submit(self._extract_from_json, info_json, user_profile=account): info_json for info_json in list_json}

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
                    self.to_screen(f"{pre} error with postid {futures[fut].get('id')}/{account} - {repr(e)}")

            return entries

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(f'{pre} {repr(e)}')

    def _real_extract(self, url):

        account, mode = try_get(
            re.search(self._VALID_URL, url),  # type: ignore
            lambda x: x.group("account", "mode"))
        if not mode:
            mode = "latest"
        try:
            userid = OnlyFansBaseIE.conn_api.getUserId(account)
            if (entries := self._get_videos_from_subs(userid, account, mode)):
                entries_list = upt_dict(list(entries.values()), original_url=url)
                return self.playlist_result(
                    entries=entries_list, playlist_id=f"onlyfans:{account}:{mode}", playlist_title=f"onlyfans:{account}:{mode}")
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
                return self.playlist_result(entries=entries_list, playlist_id="onlyfans:paid", playlist_title="onlyfans:paid")
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

    def _get_videos_from_actsubs(self, userid, account):

        _url_videos = f"https://onlyfans.com/{account}/videos"
        self.report_extraction(_url_videos)
        pre = f'[get_videos_act_subs][{account}]'
        try:
            list_json = OnlyFansBaseIE.conn_api.getVideoPosts(userid)
            if not list_json:
                raise ExtractorError(f"[{_url_videos}] no entries")

            with ThreadPoolExecutor(thread_name_prefix='onlyfans') as exe:
                futures = {exe.submit(self._extract_from_json, info_json, user_profile=account): info_json for info_json in list_json}

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
                    self.to_screen(f"{pre} error with postid {futures[fut].get('id')}/{account} - {repr(e)}")

            return list(entries.values())

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(f'{pre} {repr(e)}')

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
        try:
            self.to_screen("start getting act subs")
            actsubs_dict = OnlyFansBaseIE.conn_api.getActSubs()
            entries = []
            if actsubs_dict:
                self.to_screen(f"act_subs:\n{actsubs_dict}")
                with ThreadPoolExecutor(thread_name_prefix='OFPlaylist') as ex:
                    futures = [ex.submit(self._get_videos_from_actsubs, _userid, _account) for _account, _userid in list(actsubs_dict.items())]

                for fut in futures:
                    try:
                        entries += upt_dict(fut.result(), original_url=url)
                    except Exception as e:
                        self.to_screen(repr(e))

                return self.playlist_result(entries, "onlyfans:actsubs", "onlyfans:actsubs")

            else:
                raise ExtractorError("no entries")

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))
