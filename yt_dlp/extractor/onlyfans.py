import re
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import httpx
import atexit

from ..utils import ExtractorError, int_or_none, try_get, traverse_obj
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_0_1, scroll, By, ec, Keys

from queue import Queue, Empty

import logging

logger = logging.getLogger('onlyfans')


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

    def _extract_from_json(self, data_post, users_dict={}, user_profile=None):

        try:

            account = user_profile or users_dict.get(traverse_obj(data_post, ('fromUser', 'id')) or traverse_obj(data_post, ('author', 'id')))
            _datevideo = data_post.get('createdAt', data_post.get('postedAt', ''))
            date_timestamp = int(datetime.fromisoformat(_datevideo).timestamp())

            _entries = []

            for _media in data_post['media']:

                if _media['type'] == "video" and _media['canView']:

                    videoid = _media['id']
                    _formats = []
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

                        # if orig_width > orig_height:
                        #     self._sort_formats(_formats, field_preference=('height', 'width'))
                        # else:
                        #     self._sort_formats(_formats, field_preference=('width', 'height'))

                        _entry = {
                            "id": str(videoid),
                            "release_timestamp": date_timestamp,
                            "release_date": _datevideo.split("T")[0].replace("-", ""),
                            "title": _datevideo.split("T")[0].replace("-", "") + "_from_" + account,
                            "webpage_url": f'https://onlyfans.com/{data_post["id"]}/{account}',
                            "formats": _formats,
                            "duration": _media.get('info', {}).get('source', {}).get('duration', 0),
                            "ext": "mp4"}

                        _entries.append(_entry)

            # self.write_debug(f'[extract_from_json][output] {_entries}')
            return _entries

        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'[extract_from_json][output] {repr(e)} \n{"!!".join(lines)}')

    def _get_videos_from_userid_chat(self, driver, userid, account, msg=None):

        if not msg:
            pre = f'[get_videos_chat][{account}]'
        else:
            pre = f'{msg}[get_videos_chat][{account}]'

        url_chat = f"https://onlyfans.com/my/chats/chat/{userid}/"

        self.to_screen(f"{pre} {url_chat}")

        self.send_driver_request(driver, url_chat)

        self.wait_until(driver, 60, scroll_chat(pre, self.to_screen))

        _reg_str = f'/api2/v2/chats/{userid}/messages'
        data_json = self.scan_for_json(driver, _reg_str, _all=True)
        entries = {}
        if data_json:

            list_json = []
            for el in data_json:
                list_json += el.get('list')

            if list_json:

                for info_json in list_json:

                    _entry = self._extract_from_json(info_json, user_profile=account)
                    if _entry:
                        for _video in _entry:
                            if not _video['id'] in entries.keys():
                                entries[_video['id']] = _video
                            else:
                                if _video.get('duration', 1) > entries[_video['id']].get('duration', 0):
                                    entries[_video['id']] = _video
                        self.to_screen(f"{pre} {len(_entry)} vids")

        return (entries)

    def _get_videos_from_userid_grid(self, driver, userid, account, _all=False):

        _reg_str = r'/api2/v2/users/%s/posts/videos\?limit.*$' % userid
        pre = f'[get_videos_grid][{account}]'
        entries = {}
        data_json = self.scan_for_json(driver, _reg_str, _all=_all)
        if data_json:
            # self.write_debug(data_json)
            if isinstance(data_json, list):
                list_json = []
                for el in data_json:
                    list_json += el.get('list')
            else:
                list_json = data_json.get('list')

            with ThreadPoolExecutor(thread_name_prefix='onlyfans') as exe:
                futures = {exe.submit(self._extract_from_json, info_json, user_profile=account): info_json for info_json in list_json}

            for fut in futures:
                try:
                    _entry = fut.result()
                    if _entry:
                        for _video in _entry:
                            if not _video['id'] in entries:
                                entries[_video['id']] = _video
                            else:
                                if _video.get('duration', 1) > entries[_video['id']].get('duration', 0):
                                    entries[_video['id']] = _video
                            #  self.write_debug(f"{pre} {len(_entry)} vids")
                except Exception as e:
                    self.to_screen(f"{pre} error with postid {futures[fut].get('id')}/{account} - {repr(e)}")

        return entries

    def _get_videos_purchased(self, driver):

        entries = {}
        _reg_str = r'/api2/v2/posts/paid'
        data_json = self.scan_for_json(driver, _reg_str, _all=True)
        if data_json:
            logger.info(data_json)
            list_json = []
            for el in data_json:
                list_json += el['list']

            for info_json in list_json:
                logger.info(info_json)
                for _video in self._extract_from_json(info_json, users_dict=OnlyFansBaseIE._USERS):
                    if not _video['id'] in entries.keys():
                        entries[_video['id']] = _video
                    else:
                        if _video.get('duration', 1) > entries[_video['id']].get('duration', 0):
                            entries[_video['id']] = _video
        return (entries)

    def _get_actsubs(self, driver):
        entries = {}
        _reg_str = r'/api2/v2/subscriptions/subscribes'

        self.send_driver_request(driver, OnlyFansActSubslistIE._ACT_SUBS_URL)

        actsubs_json = self.scan_for_json(driver, _reg_str, _all=True)
        if actsubs_json:
            list_json = []
            for el in actsubs_json:
                list_json += el
            # self.write_debug(data_json)

            for user_json in list_json:
                entries.update({user_json['id']: user_json['username']})

        return (entries)

    def _real_initialize(self):

        super()._real_initialize()


class OnlyFansPostIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:post:playlist'  # type: ignore
    IE_DESC = 'onlyfans:post:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans.com/(?P<post>[\d]+)/(?P<account>[\da-zA-Z]+)"
    _DRIVER_QUEUE = None
    _COUNT_DRIVERS = 0

    def close(self):

        if OnlyFansPostIE._DRIVER_QUEUE:

            try:
                driver = OnlyFansPostIE._DRIVER_QUEUE.get(block=False)
                self.rm_driver(driver)
            except Empty:
                pass

        super().close()

    def _real_initialize(self):
        super()._real_initialize()
        with OnlyFansBaseIE._LOCK:
            if not OnlyFansPostIE._DRIVER_QUEUE:
                OnlyFansPostIE._DRIVER_QUEUE = Queue()
                OnlyFansPostIE._DRIVER_QUEUE.put_nowait(self.get_driver(devtools=True))
                OnlyFansPostIE._COUNT_DRIVERS += 1
                atexit.register(self.close)

    def _real_extract(self, url: str):

        if not url:
            raise ExtractorError('url cant be none')
        self.report_extraction(url)

        post, account = try_get(re.search(self._VALID_URL, url),  # type: ignore
                                lambda x: x.group("post", "account"))

        self.to_screen("post:" + post + ":" + "account:" + account)

        entries = {}

        assert isinstance(OnlyFansPostIE._DRIVER_QUEUE, Queue)

        with OnlyFansBaseIE._LOCK:
            if OnlyFansPostIE._COUNT_DRIVERS >= 3:
                _block = True
            else:
                _block = False

        try:
            driver = OnlyFansPostIE._DRIVER_QUEUE.get(block=_block)
        except Empty:
            with OnlyFansBaseIE._LOCK:
                OnlyFansPostIE._COUNT_DRIVERS += 1
            driver = self.get_driver(devtools=True)

        try:

            # with OnlyFansPostIE._LOCK:

            #     driver = self.get_driver(devtools=True)
            #     self._login(driver)

            self.send_driver_request(driver, url)
            res = self.wait_until(driver, 30, error404_or_found("b-post__wrapper"))

            if not res or "error404" in res:
                raise ExtractorError("Error 404: Post doesnt exists")
            #  self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "b-post__wrapper")))
            _pattern = r'/api2/v2/posts/%s\?skip_users=all$' % post
            data_json = self.scan_for_json(driver, _pattern)

        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(repr(e))
        finally:
            OnlyFansPostIE._DRIVER_QUEUE.put_nowait(driver)

        if data_json:
            #  self.to_screen(data_json)
            _entry = self._extract_from_json(data_json, user_profile=account)
            #  self.to_screen(_entry)
            if _entry:
                for _video in _entry:
                    if not _video['id'] in entries:
                        entries[_video['id']] = _video
                    else:
                        if _video['duration'] > entries[_video['id']]['duration']:
                            entries[_video['id']] = _video

        if entries:
            entries_list = [value for value in list(entries.values()) if try_get(value.update({'original_url': url}), lambda x: True)]
            return self.playlist_result(entries_list, f"onlyfans:{account}:{post}", f"onlyfans:{account}:{post}")
        else:
            raise ExtractorError("No entries")


class OnlyFansPlaylistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfans:playlist'  # type: ignore
    IE_DESC = 'onlyfans:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans.com/(?P<account>\w+)/((?P<mode>(?:all|latest|chat|favorites|tips))/?)$"
    _MODE_DICT = {"favorites": "?order=favorites_count_desc", "tips": "?order=tips_summ_desc", "all": "", "latest": ""}

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
        driver = self.get_driver(devtools=True, noheadless=True)
        #  self._login(driver)
        account, mode = try_get(re.search(self._VALID_URL, url),  # type: ignore
                                lambda x: x.group("account", "mode"))
        if not mode:
            mode = "latest"

        entries = {}

        #  self.to_screen(f"{account}:{mode}")

        try:
            self.send_driver_request(driver, f"{self._SITE_URL}/{account}")
            res = self.wait_until(driver, 60, error404_or_found())
            if not res or res[0] == "error404":
                raise ExtractorError("Error 404: User profile doesnt exists")

            userid = try_get(self.scan_for_json(driver, r'/api2/v2/users/%s$' % account), lambda x: x['id'])

            #  self.to_screen(f"{userid}")

            if mode in ("all", "latest", "favorites", "tips"):

                _url = f"{self._SITE_URL}/{account}/videos{self._MODE_DICT[mode]}"

                #  self.to_screen(f"{_url}")

                self.send_driver_request(driver, _url)
                self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CLASS_NAME, "b-photos.g-negative-sides-gaps")))
                if mode == 'latest':
                    entries = self._get_videos_from_userid_grid(driver, userid, account)

                else:
                    # lets scroll down in the videos pages till the end
                    self.wait_until(driver, 600, scroll(10))
                    entries = self._get_videos_from_userid_grid(driver, userid, account, _all=True)

            elif mode in ("chat"):

                entries = self._get_videos_from_userid_chat(driver, userid, account)

            if entries:
                entries_list = [value for value in list(entries.values()) if try_get(value.update({'original_url': url}), lambda x: True)]

                return self.playlist_result(entries=entries_list, playlist_id=f"onlyfans:{account}:{mode}", playlist_title=f"onlyfans:{account}:{mode}")

            else:
                raise ExtractorError("no entries")

        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(repr(e))
        finally:
            self.rm_driver(driver)


class OnlyFansPaidlistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfanspaidlist:playlist'  # type: ignore
    IE_DESC = 'onlyfanspaidlist:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans\.com/paid"
    _PAID_URL = "https://onlyfans.com/purchased"

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
        driver = self.get_driver(devtools=True)

        try:

            #   self._login(driver)

            self.send_driver_request(driver, self._SITE_URL)
            list_el = self.wait_until(driver, 60, ec.presence_of_all_elements_located(
                (By.CLASS_NAME, "b-tabs__nav__item")))

            if not list_el:
                raise ExtractorError("couldnt get nav bar")
            for el in list_el:
                if re.search(r'(?:purchased|comprado)', el.get_attribute("textContent").lower()):
                    el.click()
                    break
            self.wait_until(driver, 60, ec.presence_of_element_located(
                (By.CLASS_NAME, "user_posts")))

            self.wait_until(driver, 600, scroll(10))

            users_json = self.scan_for_json(driver, r'/api2/v2/users/list', _all=True)
            if users_json:

                for _users in users_json:
                    for user in _users.keys():
                        if (_uid := _users[user]['id']) not in OnlyFansBaseIE._USERS:
                            OnlyFansBaseIE._USERS.update({_uid: _users[user]['username']})

            entries_list = try_get(self._get_videos_purchased(driver), lambda x: list(x.values()))

            if entries_list:
                for _entry in entries_list:
                    _entry.update({'original_url': url})

                return self.playlist_result(entries_list, "onlyfans:paid", "onlyfans:paid")
            else:
                raise ExtractorError("no entries")

        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(repr(e))
        finally:
            self.rm_driver(driver)


class OnlyFansActSubslistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfansactsubslist:playlist'  # type: ignore
    IE_DESC = 'onlyfansactsubslist:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans\.com/actsubs"
    _ACT_SUBS_URL = "https://onlyfans.com/my/subscriptions/active"

    def _get_videos_from_actsubs(self, userid, account):

        _url_videos = f"https://onlyfans.com/{account}/videos"
        self.report_extraction(_url_videos)
        driver = self.get_driver(devtools=True)

        try:

            # with OnlyFansActSubslistIE._LOCK:
            #     driver = self.get_driver(devtools=True)
            #     self._login(driver)

            self.send_driver_request(driver, _url_videos)
            self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CLASS_NAME, "b-photos__item.m-video-item")))

            # only get the first ones
            entries = self._get_videos_from_userid_grid(driver, userid, account)

            if not entries:
                raise ExtractorError(f"[{_url_videos}] no entries")
            return list(entries.values())

        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'[{_url_videos}] {repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(f'[{_url_videos}] {repr(e)}')
        finally:
            self.rm_driver(driver)

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        # with OnlyFansActSubslistIE._LOCK:

        #     driver = self.get_driver(devtools=True)
        #     self._login(driver)

        driver = self.get_driver(devtools=True)

        try:

            self.to_screen("start getting act subs")
            self.send_driver_request(driver, OnlyFansActSubslistIE._ACT_SUBS_URL)

            actsubs_dict = self._get_actsubs(driver)
            entries = []
            if actsubs_dict:
                self.to_screen(f"act_subs:\n{actsubs_dict}")
                with ThreadPoolExecutor(thread_name_prefix='OFPlaylist', max_workers=len(actsubs_dict)) as ex:
                    futures = [ex.submit(self._get_videos_from_actsubs, _userid, _account) for _userid, _account in list(actsubs_dict.items())]

                for fut in futures:
                    try:
                        entries += fut.result()
                    except Exception as e:
                        self.to_screen(repr(e))

            if entries:
                for el in entries:
                    el.update({'original_url': 'https://onlyfans.com/actsubs'})

                return self.playlist_result(entries, "Onlyfans:subs", "Onlyfans:subs")

            else:
                raise ExtractorError("no entries")

        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(repr(e))
        finally:
            self.rm_driver(driver)


class OnlyFansAllChatslistIE(OnlyFansBaseIE):
    IE_NAME = 'onlyfansallchatslist:playlist'  # type: ignore
    IE_DESC = 'onlyfansallchatslist:playlist'
    _VALID_URL = r"https?://(?:www\.)?onlyfans\.com/allchats"
    _ALL_CHATS_URL = "https://onlyfans.com/my/chats"

    _LOCALQ = Queue()

    def _get_videos_from_chat(self, i):

        driver = self.get_driver(devtools=True)
        url_chat = ""
        try:
            # with OnlyFansAllChatslistIE._LOCK:

            #     driver = self.get_driver(devtools=True)
            #     self._login(driver)

            entries = []

            while (True):

                try:
                    userid = OnlyFansAllChatslistIE._LOCALQ.get()

                    if userid == "KILL":
                        break

                    url_chat = f"https://onlyfans.com/my/chats/chat/{userid}/"

                    account = OnlyFansAllChatslistIE._USERS[userid]

                    self.to_screen(f"[{i}] {url_chat}")

                    self.send_driver_request(driver, url_chat)

                    self.wait_until(driver, 60, scroll_chat(f'[{i}]', self.to_screen))

                    _entries = self._get_videos_from_userid_chat(driver, userid, account, f'[{i}]')

                    if _entries:
                        entries += list(_entries.values())

                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f'[{i}][{url_chat}] inside while - {repr(e)} \n{"!!".join(lines)}')

            return (entries)

        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'[{i}][{url_chat}] {repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(f'[{url_chat}] {repr(e)}')
        finally:
            self.rm_driver(driver)

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
        driver = self.get_driver(devtools=True)

        try:

            # with OnlyFansAllChatslistIE._LOCK:

            #     driver = self.get_driver(devtools=True)
            #     self._login(driver)

            self.send_driver_request(driver, self._ALL_CHATS_URL)

            self.wait_until(driver, 60, scroll(2))

            users_json = self.scan_for_json(driver, '/api2/v2/users/list', _all=True)
            if users_json:
                self.to_screen("users list attempt success")

                for _users in users_json:
                    for user in _users.keys():
                        if (_uid := _users[user]['id']) not in OnlyFansAllChatslistIE._USERS:
                            OnlyFansAllChatslistIE._USERS.update({int(_uid): _users[user]['username']})

            entries = []
            if OnlyFansAllChatslistIE._USERS:
                uid_list = list(OnlyFansAllChatslistIE._USERS.keys())
                self.to_screen(f"[all_chats] {uid_list}")

                for uid in uid_list:
                    OnlyFansAllChatslistIE._LOCALQ.put_nowait(uid)
                for i in range(5):
                    OnlyFansAllChatslistIE._LOCALQ.put_nowait("KILL")

                with ThreadPoolExecutor(thread_name_prefix='OFPlaylist', max_workers=5) as ex:
                    futures = [ex.submit(self._get_videos_from_chat, i) for i in range(5)]

                for fut in futures:
                    try:
                        res = fut.result()
                        if res:
                            entries += res

                    except Exception as e:
                        lines = traceback.format_exception(*sys.exc_info())
                        self.to_screen(f'[all_chats] error when getting fut result - {repr(e)} \n{"!!".join(lines)}')

            if entries:
                for el in entries:
                    el.update({'original_url': 'https://onlyfans.com/allchats'})

                return self.playlist_result(entries, "Onlyfans:allchats", "Onlyfans:allchats")

            else:
                raise ExtractorError("no entries")

        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(repr(e))
        finally:
            self.rm_driver(driver)
