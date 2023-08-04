from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock
from urllib.parse import unquote, urljoin
import html
from httpx import Cookies
import re

from ..utils import (
    ExtractorError,
    get_elements_by_class,
    sanitize_filename,
    try_get,
    get_domain,
    bug_reports_message,
    variadic
)

from .commonwebdriver import (
    Union,
    cast,
    ec,
    dec_on_exception2,
    dec_on_exception3,
    SeleniumInfoExtractor,
    limiter_0_5,
    HTTPStatusError,
    By,
    ConnectError,
    raise_extractor_error)

import logging
logger = logging.getLogger('myvidster')


class MyVidsterBaseIE(SeleniumInfoExtractor):

    _LOGIN_URL = "https://www.myvidster.com/user/"
    _SITE_URL = "https://www.myvidster.com"
    _NETRC_MACHINE = "myvidster"

    _LOCK = Lock()
    _COOKIES: Cookies = Cookies()

    _URLS_CHECKED = []

    # _NUM_VIDS_PL = {}

    @dec_on_exception3
    @dec_on_exception2
    @limiter_0_5.ratelimit("myvidster", delay=True)
    def _send_request(self, url, **kwargs):

        try:
            self.logger_debug(f"[send_req] {self._get_url_print(url)}")
            return (self.send_http_request(url, **kwargs))
        except (HTTPStatusError, ConnectError) as e:
            self.logger_debug(f"[send_request] {self._get_url_print(url)}: error - {repr(e)}")
        except Exception as e:
            self.report_warning(f"[send_request] {self._get_url_print(url)}: error - {repr(e)}")
            raise

    @dec_on_exception3
    @dec_on_exception2
    @limiter_0_5.ratelimit("myvidster", delay=True)
    def _get_infovideo(self, url, **kwargs):

        try:
            return self.get_info_for_format(url, **kwargs)
        except (HTTPStatusError, ConnectError) as e:
            self.logger_debug(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    def _login(self):

        _urlh, _ = try_get(
            self._send_request(self._LOGIN_URL, _type="GET"),
            lambda x: (str(x.url), re.sub('[\t\n]', '', html.unescape(x.text)))) or (None, None)
        if _urlh and "www.myvidster.com/user/home.php" in _urlh:
            self.logger_debug("LOGIN already OK")
            return
        self.report_login()

        username, password = self._get_login_info()

        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)

        data = {
            "user_id": username,
            "password": password,
            "save_login": "on",
            "submit": "Log+In",
            "action": "log_in"
        }

        _headers_post = {
            "Referer": self._LOGIN_URL,
            "Origin": self._SITE_URL,
            "Content-Type": "application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests": "1"
        }

        try:

            _urlh, _ = try_get(
                self._send_request(self._LOGIN_URL, _type="POST", data=data, headers=_headers_post),
                lambda x: (str(x.url), re.sub('[\t\n]', '', html.unescape(x.text)))) or (None, None)
            if _urlh and "www.myvidster.com/user/home.php" in _urlh:
                self.logger_debug("LOGIN OK")
                return
            elif _urlh and "www.myvidster.com/user" in _urlh:
                _urlh2, _ = try_get(
                    self._send_request(self._LOGIN_URL, _type="GET"),
                    lambda x: (str(x.url), re.sub('[\t\n]', '', html.unescape(x.text)))) or (None, None)
                if _urlh2 and "www.myvidster.com/user/home.php" in _urlh2:
                    self.logger_debug("LOGIN OK")
                    return
                else:
                    raise ExtractorError(f"Login failed: {_urlh2}")
            else:
                raise ExtractorError(f"Login failed:{_urlh}")

        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(repr(e))

    def _login_driver(self, driver):

        driver.get(self._SITE_URL)
        el_sddm = try_get(
            self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.ID, 'sddm'))),
            lambda x: x[0].text) or ''
        if not el_sddm or 'log in' in el_sddm:
            self.to_screen("Not logged with Selenium/Firefox webdriver. Lets login")
            driver.get("https://myvidster.com/user/")
            username, password = self._get_login_info()
            el_username = try_get(self.wait_until(driver, 60, ec.presence_of_all_elements_located(
                (By.CSS_SELECTOR, 'input#user_id'))), lambda x: x[0])
            el_password = try_get(self.wait_until(driver, 60, ec.presence_of_all_elements_located(
                (By.CSS_SELECTOR, 'input#password'))), lambda x: x[0])
            el_button = try_get(self.wait_until(driver, 60, ec.presence_of_all_elements_located(
                (By.CSS_SELECTOR, 'button'))), lambda x: x[0])
            if el_username and el_password and el_button:
                el_username.send_keys(username)
                self.wait_until(driver, 2)
                el_password.send_keys(password)
                self.wait_until(driver, 2)
                el_button.click()
                self.wait_until(driver, 60, ec.url_changes("https://www.myvidster.com/user/"))
                if "www.myvidster.com/user/home.php" not in driver.current_url:
                    raise ExtractorError("no logged")

    def _get_last_page(self, _urlqbase):
        i = 1
        while True:
            try:
                webpage = try_get(self._send_request(f"{_urlqbase}{i}"), lambda x: html.unescape(x.text))
                assert webpage
                if "next »" in webpage:
                    i += 1
                else:
                    break
            except Exception:
                break
        return (i - 1)

    def _get_videos(self, _urlq):

        if '/search/' in _urlq:
            item = 'vsearch'
        else:
            item = 'video'

        webpage = try_get(self._send_request(_urlq), lambda x: html.unescape(x.text))
        if webpage:
            list_videos = [
                urljoin(self._SITE_URL, el.replace('vsearch', 'video'))
                for el in re.findall(rf'<a href="(/{item}/[^"]+)">', webpage)]
            return list_videos

    def _get_videos_pages(self, urlpages, name):

        with ThreadPoolExecutor(thread_name_prefix=name) as exe:
            futures = {exe.submit(self._get_videos, _url): _url for _url in urlpages}

        list_videos = []
        for fut in futures:
            try:
                _res = fut.result()
                if _res:
                    list_videos += _res
                else:
                    raise_extractor_error("no entries")
            except Exception as e:
                self.logger_debug(f"[get_video_pages][{futures[fut]}] error - {repr(e)}")

        return list_videos

    def _real_initialize(self):

        super()._real_initialize()

        if not MyVidsterBaseIE._COOKIES:

            try:
                self._login()
                MyVidsterBaseIE._COOKIES = self._CLIENT.cookies

            except Exception as e:
                self.to_screen(repr(e))
                raise
        else:
            for cookie in MyVidsterBaseIE._COOKIES.jar:
                if cookie.value:
                    self._CLIENT.cookies.set(name=cookie.name, value=cookie.value, domain=cookie.domain)


class MyVidsterIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:playlist'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/(?:video|vsearch)/(?P<id>\d+)/?(?P<title>[\w\-\_]+)?'
    _conf = {
        'source_url': r'source src=[\'\"]([^\'\"]+)[\'\"] type=[\'\"]video',
        'videolink': r'rel=[\'\"]videolink[\'\"] href=[\'\"]([^\'\"]+)[\'\"]',
        'embedlink': r'reload_video\([\'\"]([^\'\"]+)[\'\"]'}
    _URL_NOT_VALID = [
        '//syndication', 'rawassaddiction.blogspot', 'twitter.com',
        'sxyprn.net', 'gaypornmix.com', 'thisvid.com/embed', 'twinkvideos.com/embed',
        'xtube.com', 'xtapes.to', '####gayforit######.eu/playvideo.php',
        '/#####noodlemagazine####.com/player', 'pornone.com/embed/', 'player.vimeo.com/video',
        'gaystreamvp.ga', 'gaypornvideos.cc/wp-content/', '//tubeload', 'broken.mp4']

    def getvid(self, x, **kwargs):

        def _check_extr(x):
            if x in SeleniumInfoExtractor._CONFIG_REQ:
                return True

        _check = kwargs.get('check', True)
        pre = "[getvid]"
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'

        _x = map(unquote, variadic(x))

        for el in _x:

            pre += f'[{self._get_url_print(el)}]'

            try:
                if not el:
                    continue

                if el in MyVidsterBaseIE._URLS_CHECKED:
                    self.logger_debug(f"{pre} already analysed")
                    continue

                if any(_ in el for _ in self._URL_NOT_VALID):
                    self.logger_debug(f"{pre} url not valid")
                    return {"error_getvid": f"[{el}] error url not valid"}

                if (_extr_name := self._get_ie_name(el)) == 'generic':
                    _res = self._is_valid(el, inc_error=True, msg=pre)
                    if _res.get("valid"):
                        return el
                    else:
                        _msg_error = _res.get('error', '').replace(bug_reports_message(), '')
                        return {"error_getvid": f"[{el}] error valid - {_msg_error }"}

                elif _check_extr(_extr_name):  # get entry
                    ie = self._get_extractor(el)
                    try:
                        if (_ent := ie._get_entry(el, check=_check, msg=pre)):
                            self.logger_debug(f"{pre} OK got entry video\n {_ent}")
                            return _ent
                        else:
                            self.logger_debug(f'{pre} not entry video')
                            return {"error_getvid": f"[{el}] not entry video"}
                    except Exception as e:
                        _msg_error = str(e).replace(bug_reports_message(), '')
                        self.logger_debug(f'{pre} error entry video {_msg_error}')
                        return {"error_getvid": f"[{el}] error entry video - {_msg_error}"}

                else:
                    ie = self._get_extractor(el)
                    try:
                        if (_ent := ie.extract(el)):
                            _ent.update({'extractor': ie.IE_NAME, 'extractor_key': type(ie).ie_key(), 'webpage_url': el})
                            self.logger_debug(f"{pre} OK got entry video\n {_ent}")
                            return _ent
                        else:
                            self.logger_debug(f'{pre} not entry video')
                            return {"error_getvid": f"[{el}] not entry video"}
                    except Exception as e:
                        _msg_error = str(e).replace(bug_reports_message(), '')
                        self.logger_debug(f'{pre} error entry video {_msg_error}')
                        return {"error_getvid": f"[{el}] error entry video - {_msg_error}"}

            except Exception as e:
                _msg_error = str(e).replace(bug_reports_message(), '')
                self.logger_debug(f'{pre} error entry video {_msg_error}')
                return {"error_getvid": f"[{el}] error entry video - {_msg_error}"}
            finally:
                MyVidsterBaseIE._URLS_CHECKED.append(el)

    def _get_entry(self, url, **kwargs):

        _check = kwargs.get('check', True)
        _from_list = kwargs.get('from_list', None)
        _progress_bar = kwargs.get('progress_bar', None)
        video_id = self._match_id(url)
        url = url.replace("vsearch", "video")

        try:
            _urlh, webpage = cast(list[str], try_get(
                self._send_request(url),
                lambda x: [str(x.url), re.sub('[\t\n]', '', html.unescape(x.text))]) or [None, None])
            if not webpage:
                raise_extractor_error("Couldnt download webpage")
            if not _urlh or any(
                    _ in str(_urlh)
                    for _ in ['status=not_found', 'status=broken', 'status=removed']):

                raise_extractor_error("Error 404: Page not found")

            title = cast(str, try_get(
                re.findall(r"<title>([^<]+)<", webpage),
                lambda x: x[0]) or url.split("/")[-1])

            postdate = try_get(re.findall(r"<td><B>Bookmark Date:</B>([^<]+)</td>", webpage, flags=re.I),
                               lambda x: datetime.strptime(x[0].strip(), "%d %b, %Y"))
            if postdate:
                _entry = {'release_date': postdate.strftime("%Y%m%d"),
                          'release_timestamp': int(postdate.timestamp())}
            else:
                _entry = {}

            def _getter(orderlinks):

                def _prepare_entry(info):
                    if (_msg_error := info.pop('error_getvid', None)):
                        info['error'] = _msg_error
                    info.update({'original_url': url})
                    info.update(_entry)
                    if not info.get('extractor'):
                        info['extractor'] = self.IE_NAME
                        info['extractor_key'] = self.ie_key()
                    if not info.get('id'):
                        info['id'] = video_id
                    if not (_title := info.get('title')):
                        if (wurl := info.get('webpage_url')):
                            domain = get_domain(wurl)
                            _pattern = r'''(?x)(?i)
                                (^(hd video|sd video|video))\s*:?\s*|
                                ((?:\s*.\s*|\s*at\s*|\s*)%s$)|(.mp4$)|
                                (\s*[/|]\s*embed player)''' % domain
                            _title = re.sub(_pattern, '', title).strip('[,-_ ')
                        else:
                            _title = title
                    info.update({'title': sanitize_filename(_title, restricted=True)})
                    return info

                if (source_url_res := try_get(
                        re.findall(self._conf['source_url'], webpage),
                        lambda x: self.getvid(x[0], msg='source_url') if x else None)):

                    if isinstance(source_url_res, dict):
                        return _prepare_entry(source_url_res)

                    elif isinstance(source_url_res, str):
                        self.logger_debug(f"source url: {source_url_res}")
                        _headers = {'referer': 'https://www.myvidster.com'}
                        _info_video = cast(dict, self._get_infovideo(source_url_res, headers=_headers))
                        if not _info_video:
                            raise_extractor_error('error 404: couldnt get info video details')
                        _format_video = {
                            'format_id': 'http-mp4',
                            'url': _info_video.get('url'),
                            'filesize': _info_video.get('filesize'),
                            'http_headers': _headers,
                            'ext': 'mp4'}
                        _entry.update({
                            'id': video_id,
                            'title': sanitize_filename(title, restricted=True),
                            'formats': [_format_video],
                            'ext': 'mp4',
                            'webpage_url': url,
                            'extractor': self.IE_NAME,
                            'extractor_key': self.ie_key()})
                        return _entry

                link0_res = None
                link1_res = None

                link0_res = try_get(
                    re.findall(self._conf[orderlinks[0]], webpage),
                    lambda x: self.getvid(x[0], check=_check, msg=orderlinks[0]) if x else None)

                if not link0_res or isinstance(link0_res, str):

                    link1_res = try_get(
                        re.findall(self._conf[orderlinks[1]], webpage),
                        lambda x: self.getvid(x[0], check=_check, msg=orderlinks[1]) if x else None)

                    if link1_res and isinstance(link1_res, dict):
                        return _prepare_entry(link1_res)

                    if not link1_res and link0_res:
                        raise_extractor_error("Error 404: no video urls found")

                elif isinstance(link0_res, dict):
                    return _prepare_entry(link0_res)

                # llegados a este punto, los links serán generic y valid

                real_url = link0_res or link1_res

                self.logger_debug(f"url selected: {real_url}")

                if real_url:
                    ie = self._get_extractor('Generic')
                    try:
                        _videoent = ie._real_extract(real_url)
                        _videoent.update(_entry)
                        _videoent.update({'original_url': url})
                        if not (_title := not _videoent.get('title')):
                            _title = title
                        _videoent.update({'title': sanitize_filename(_title, restricted=True)})
                        if not _videoent.get('id'):
                            _videoent['id'] = video_id
                        return _videoent
                    except Exception as e:
                        raise_extractor_error(str(e))
                else:
                    raise_extractor_error("url video not found")

            return _getter(['videolink', 'embedlink'])

        except ExtractorError as e:
            self.logger_debug(f"[{url}] error {repr(e)}")
            raise
        except Exception as e:
            self.logger_debug(f"[{url}] error {repr(e)}")
            raise
        finally:
            if _from_list:
                with MyVidsterBaseIE._LOCK:
                    # MyVidsterBaseIE._NUM_VIDS_PL[_from_list] -= 1
                    if _progress_bar:
                        _progress_bar.update()
                        _progress_bar.print("Entry OK")

    def _real_initialize(self):
        with MyVidsterBaseIE._LOCK:
            super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        try:
            return (self._get_entry(url))

        except ExtractorError:
            raise
        except Exception as e:
            raise_extractor_error(repr(e))


class MyVidsterChannelPlaylistIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:channel:playlist'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/channel/(?P<id>\d+)/?(?P<title>\w+)?(\?(?P<query>.+))?'
    _POST_URL = "https://www.myvidster.com/processor.php"

    def get_playlist_channel(self, url):

        get_posted_date = lambda x: try_get(
            get_elements_by_class("mvp_grid_panel_details", x),
            lambda y: datetime.strptime(y[0].replace('Posted ', '').strip(), '%B %d, %Y'))

        get_video_url = lambda x: try_get(
            re.findall(r'<a href=\"(/video/[^\"]+)\" class', el), lambda y: f'{self._SITE_URL}{y[0]}')

        def get_videos_channel(channelid: str, num_videos: int, date: Union[datetime, None] = None):

            _headers_post = {
                "Referer": url,
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "*/*"
            }
            info = {
                'action': 'display_channel',
                'channel_id': channelid,
                'page': '1',
                'thumb_num': str(num_videos),
                'count': str(num_videos)
            }
            el_videos = []
            if not date or num_videos < 500:

                webpage = try_get(
                    self._send_request(self._POST_URL, _type="POST", data=info, headers=_headers_post),
                    lambda x: re.sub('[\t\n]', '', html.unescape(x.text)))
                if webpage and (_videos := get_elements_by_class("thumbnail", webpage)):
                    el_videos.extend(_videos)
            else:
                _thumb_num = max(int((((int(num_videos) // 50) + 1) / 500) * 500), 500)  # max 50 POST to get every video of channel
                max_page = int(num_videos) // _thumb_num + 1
                info['thumb_num'] = str(_thumb_num)
                i = 0
                while i < max_page:
                    info['page'] = str(i + 1)
                    webpage = try_get(
                        self._send_request(self._POST_URL, _type="POST", data=info, headers=_headers_post),
                        lambda x: re.sub('[\t\n]', '', html.unescape(x.text)))
                    if webpage and (_videos := cast(list[str], get_elements_by_class("thumbnail", webpage))):
                        el_videos.extend(_videos)
                        if (posted_date := get_posted_date(el_videos[-1])) and posted_date < date:
                            break
                    i += 1

            return el_videos

        try:

            channelid = cast(str, self._match_id(url))

            webpage = cast(str, try_get(self._send_request(url), lambda x: re.sub('[\t\n]', '', html.unescape(x.text))))
            if not webpage:
                raise_extractor_error("Couldnt download webpage")

            title = cast(str, try_get(
                re.findall(r'<title>([\w\s]+)</title>', webpage),
                lambda x: x[0])) or f"MyVidsterChannel_{channelid}"
            num_videos = cast(int, try_get(
                re.findall(r"display_channel\(.*,[\'\"](\d+)[\'\"]\)", webpage), lambda x: int(x[0]))) or 100000

            query = try_get(re.search(self._VALID_URL, url), lambda x: x.group('query'))
            _date = None
            _check = True
            params = {}
            if query:
                params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
            if params.get('check', 'yes') == 'no':
                _check = False
            _date = cast(datetime, try_get(params.get('date'), lambda x: datetime.strptime(x, '%Y-%m-%d') if x else None))

            results = []
            el_videos = get_videos_channel(channelid, num_videos, _date)
            if not el_videos:
                raise ExtractorError('no videos')

            _first = params.get('first') or '1'
            _last = params.get('last')

            self.logger_debug(f"[get_playlist_channel] check[{_check}] date[{_date}] first - last[{_first} - {_last}]")

            if _last:
                el_videos = el_videos[int(_first) - 1: int(_last)]
            else:
                el_videos = el_videos[int(_first) - 1:]

            for el in el_videos:
                if not el:
                    continue

                if not (video_url := get_video_url(el)):
                    continue

                posted_date = get_posted_date(el)

                if _date:
                    if not posted_date or posted_date > _date:
                        # self.to_screen(f"> {'No date' if not posted_date else posted_date.strftime('%Y-%m-%d')} {video_url}")
                        continue
                    elif posted_date < _date:
                        self.to_screen(f"< {posted_date.strftime('%Y-%m-%d')} {video_url}")
                        break

                _res = {'_type': 'url', 'url': video_url, 'ie_key': 'MyVidster'}
                if posted_date:
                    _res.update({
                        'release_date': posted_date.strftime("%Y%m%d"),
                        'release_timestamp': int(posted_date.timestamp())})
                results.append(_res)

            if results:

                if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

                    iemv = cast(MyVidsterIE, self._get_extractor("MyVidster"))
                    # MyVidsterBaseIE._NUM_VIDS_PL[url] = len(results)

                    pre = f'[channel/{channelid}][Num_videos_pending]'

                    with self.create_progress_bar(len(results), block_logging=True, msg=pre) as pb:

                        with ThreadPoolExecutor(thread_name_prefix='ex_channelpl') as ex:
                            futures = {
                                ex.submit(
                                    iemv._get_entry, el['url'],
                                    check=_check, from_list=url, progress_bar=pb): el['url']
                                for el in results
                            }

                    entries = []

                    for fut, ent in zip(futures, results):
                        try:
                            if _res := fut.result():
                                if _res.get('webpage_url') == futures[fut]:
                                    _orig_url = url
                                else:
                                    _orig_url = futures[fut]
                                _res.update({
                                    'release_date': ent.get('release_date'),
                                    'release_timestamp': ent.get('release_timestamp'),
                                    'original_url': _orig_url,
                                    'playlist_url': url})
                                entries.append(_res)
                        except Exception as e:
                            _wurl = cast(str, futures[fut])
                            self.logger_debug(
                                f"[get_entries][{self._get_url_print(_wurl)}] error - {str(e)}",
                                exc_info=True)
                            _id, _title = cast(list[str], try_get(
                                MyVidsterIE._match_valid_url(_wurl),
                                lambda x: x.group('id', 'title') if x else (None, None)))
                            entries.append(
                                {
                                    'original_url': futures[fut],
                                    'playlist_url': url,
                                    'error': str(e),
                                    'formats': [],
                                    'id': _id,
                                    'title': sanitize_filename(_title, restricted=True),
                                    'extractor': iemv.IE_NAME,
                                    'extractor_key': iemv.ie_key()
                                })

                else:
                    entries = results

                if entries:

                    return {
                        '_type': 'playlist',
                        'id': channelid,
                        'title': sanitize_filename(title, True),
                        'entries': entries,
                    }

            raise_extractor_error("no entries found")

        except ExtractorError:
            raise
        except Exception as e:
            self.logger_debug(str(e), exc_info=True)
            self.report_warning(str(e))
            raise_extractor_error(str(e), _from=e)

    def _real_initialize(self):

        with MyVidsterBaseIE._LOCK:
            super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
        return self.get_playlist_channel(url)


class MyVidsterSearchPlaylistIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:search:playlist'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/search/?\?(?P<query>.+)'
    _SEARCH_URL = 'https://www.myvidster.com/search/?'

    def get_playlist_search(self, url):

        query = try_get(re.search(self._VALID_URL, url), lambda x: x.groupdict().get('query'))

        assert query

        params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&')}

        if not params.get('filter_by'):
            params['filter_by'] = 'myvidster'
        if not params.get('cfilter_by'):
            params['cfilter_by'] = 'gay'
        if not params.get('sortby'):
            params['sortby'] = 'utc_posted'
        _check = True
        if params.get('check', 'yes').lower() == 'no':
            _check = False

        npages = params.pop('pages', 5)
        firstpage = params.pop('from', 1)

        query_str = "&".join([f"{_key}={_val}" for _key, _val in params.items()])
        base_search_url = f"{self._SEARCH_URL}{query_str}&page="

        last_page = self._get_last_page(base_search_url)

        if last_page == 0:
            raise_extractor_error("no search results")

        if npages == 'all':
            _max = last_page
        else:
            _max = int(firstpage) + int(npages) - 1
            if _max > last_page:
                self.logger_debug(
                    f'[{self._get_url_print(url)}] pages requested > max page website: will check up to max page')
                _max = last_page

        list_search_urls = [f"{base_search_url}{i}" for i in range(int(firstpage), _max + 1)]

        self.logger_debug(list_search_urls)

        try:

            entries = []

            if (list_videos := self._get_videos_pages(list_search_urls, 'ex_searchpl')):

                if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

                    # MyVidsterBaseIE._NUM_VIDS_PL[url] = len(list_videos)
                    iemv = self._get_extractor("MyVidster")

                    with self.create_progress_bar(len(list_videos), msg=f'[search/?{url.split("?")[-1]}][Num_videos_pending]') as pb:

                        with ThreadPoolExecutor(thread_name_prefix='ex_searchpl2') as ex:
                            futures = {ex.submit(iemv._get_entry, _url, check=_check, from_list=url, progress_bar=pb): _url for _url in list_videos}

                    for fut in futures:
                        try:
                            _res = fut.result()
                            assert _res
                            if _res.get('webpage_url') == futures[fut]:
                                _orig_url = url
                            else:
                                _orig_url = futures[fut]
                            _res['original_url'] = _orig_url
                            _res['playlist_url'] = url
                            entries.append(_res)
                        except Exception as e:
                            self.logger_debug(f"[get_entries2][{futures[fut]}] error - {repr(e)}")
                            _id = iemv.get_temp_id(futures[fut])
                            entries.append({'original_url': futures[fut], 'playlist_url': url, 'error': str(e), 'formats': [],
                                            'id': _id, 'title': _id, 'ie_key': 'MyVidster'})
                else:
                    entries = [{
                        '_type': 'url',
                        'url': video,
                        'ie_key': 'MyVidster',
                        'original_url': url}
                        for video in list_videos]

            if entries:
                return self.playlist_result(entries, playlist_id=query_str, playlist_title='Search')

            raise_extractor_error("no entries found")

        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise_extractor_error(repr(e))

    def _real_initialize(self):
        with MyVidsterBaseIE._LOCK:
            super()._real_initialize()

    def _real_extract(self, url):
        self.report_extraction(url)
        return self.get_playlist_search(url)


class MyVidsterRSSPlaylistIE(MyVidsterBaseIE):
    IE_NAME = 'myvidster:subs:playlist'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?myvidster\.com/subscriptions/Atgarcia/?(\?(?P<query>.+))?'
    _POST_URL = "https://www.myvidster.com/processor.php"
    _RSS_URL = 'https://www.myvidster.com/subscriptions/Atgarcia'
    _SEARCH_URL = "https://www.myvidster.com/search/?%s&filter_by=user_%s"

    _RSS = {}

    def _getter(self, x):

        try:

            _path, _profile = x.groups()
            self.to_screen(f'[getter] {_path}:{_profile}')
            _subs_link = urljoin("https://myvidster.com", _path)
            if not _profile:
                webpage = try_get(self._send_request(_subs_link), lambda x: x.text)
                if not webpage:
                    raise_extractor_error("no webpage")
                else:
                    _profile = try_get(re.findall(r'by <a href="/profile/([^"]+)"', webpage), lambda x: x[0])
            return (_subs_link, _profile)

        except Exception as e:
            self.to_screen(repr(e))

    def _follow_subs_user(self, username):

        webpage = try_get(
            self._send_request(f"https://myvidster.com/profile/{username}"),
            lambda x: html.unescape(x.text))
        if webpage:
            _pattern = r'''(?x)
                name=[\"\']subscribe[\"\']\s+class=[\"\']mybutton[\"\']\s+onClick="window\.location=[\'\"]
                ([^\'\"]+)[\'\"]'''
            adduserurl = try_get(re.findall(_pattern, webpage), lambda x: f'https://myvidster.com/{x[0]}')
            if not adduserurl:
                self.to_screen(f'[follow_subs_user] Already following to {username}')
            else:
                res = self._send_request(adduserurl, headers={'Referer': f'https://myvidster.com/profile/{username}'})
                return (try_get(res, lambda x: 'You are now following this user' in x.text))

    def _get_rss(self):

        info = {
            'action': 'display_subscriptions',
            'disp_name': 'Atgarcia',
            'page': '1',
            'thumb_num': 100,
            'count': 100}

        _headers_post = {
            "Referer": self._SITE_URL,
            "Origin": self._SITE_URL,
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "x-Requested-With": "XMLHttpRequest",
            "Accept": "*/*"}

        try:
            self._send_request(self._POST_URL, _type="POST", data={'action': 'loading'}, headers=_headers_post)
            webpage = try_get(self._send_request(self._POST_URL, _type="POST", data=info, headers=_headers_post), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)))
            if not webpage:
                raise_extractor_error('Couldnt get subscriptions')
            else:
                subwebpages = webpage.split('<div class="vidthumbnail" style="margin-right:6px;margin-bottom:2px;">')
                for sub in subwebpages[1:]:
                    username = try_get(re.findall(r'<a href=[\'\"]/profile/([^\'\"]+)[\'\"]', sub), lambda x: x[0])
                    if username:
                        _subsuser = try_get(self._query_rss(username), lambda x: x.text)
                        assert _subsuser
                        userid = try_get(re.findall(r'/(?:Atgarcia/user|images/profile)/(\d+)', _subsuser), lambda x: x[0])
                        channels = re.findall(r'/Atgarcia/channel/(\d+)', _subsuser)
                        collections = re.findall(r'/Atgarcia/gallery/(\d+)', _subsuser)
                        MyVidsterRSSPlaylistIE._RSS.update({
                            username: {
                                'userid': userid,
                                'channels': channels,
                                'collections': collections}})

        except Exception as e:
            self.report_warning(f'[getrss] error when fetching rss info {repr(e)}')

    def _query_rss(self, q):
        info = {
            'action': 'query_subscriptions',
            'disp_name': 'Atgarcia',
            'q': q
        }

        _headers_post = {
            "Referer": self._SITE_URL,
            "Origin": self._SITE_URL,
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "x-Requested-With": "XMLHttpRequest",
            "Accept": "*/*"
        }

        self._send_request(self._POST_URL, _type="POST", data={'action': 'loading'}, headers=_headers_post)
        res = self._send_request(self._POST_URL, _type="POST", data=info, headers=_headers_post)
        return res

    def get_playlist_rss_search(self, url):

        try:
            query = try_get(re.search(self._VALID_URL, url), lambda x: x.group('query'))

            params = {}
            if query:
                params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&')}

            if not params or list(params.keys()) == ['pages']:

                npages = int(params.get('pages', 1))
                _list_urls_rss_search = [self._RSS_URL + f'&page={i}' for i in range(1, npages + 1)]

                entries = []

                if (list_videos := self._get_videos_pages(_list_urls_rss_search, 'ex_rsspl')):

                    if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

                        # MyVidsterBaseIE._NUM_VIDS_PL[url] = len(list_videos)
                        iemv = self._get_extractor("MyVidster")

                        with ThreadPoolExecutor(thread_name_prefix='ex_rsspl2') as ex:
                            futures = {ex.submit(iemv._get_entry, _url): _url for _url in list_videos}

                        for fut in futures:
                            try:
                                _res = fut.result()
                                if _res:
                                    entries.append(_res)
                            except Exception as e:
                                self.logger_debug(f"[get_entries][{futures[fut]}] error - {repr(e)}")

                    else:
                        entries = [{
                            '_type': 'url',
                            'url': video,
                            'ie_key': 'MyVidster',
                            'original_url': url}
                            for video in list_videos]

                if entries:
                    return self.playlist_result(
                        entries, playlist_id='myvidster_rss', playlist_title='myvidster_rss')

                raise_extractor_error("no entries found")

            else:
                results = {}
                assert query

                _list_urls_rss_search = [self._SEARCH_URL % (query, val['userid'])
                                         for user, val in MyVidsterRSSPlaylistIE._RSS.items()]
                with ThreadPoolExecutor(thread_name_prefix='ex_rss3pl') as ex:
                    futures = {ex.submit(self._get_videos, _url): _url for _url in _list_urls_rss_search}

                for fut in futures:
                    try:
                        _res = fut.result()
                        if _res:
                            results[futures[fut]] = _res
                        else:
                            raise_extractor_error("no entries")
                    except Exception:
                        # self.report_warning(f"[get_entries][{futures[fut]}] error - {repr(e)}")
                        pass

                self.to_screen(results)
                if results:

                    if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

                        iemv = self._get_extractor("MyVidster")
                        _list_urls_rss_search = {video: _url for _url, _videos in results.items() for video in _videos}
                        self.to_screen(_list_urls_rss_search)
                        with ThreadPoolExecutor(thread_name_prefix='ex_rss4pl') as ex:
                            futures = {ex.submit(iemv._get_entry, _url): _url for _url in _list_urls_rss_search}

                        entries = []
                        for fut in futures:
                            try:
                                _res = fut.result()
                                if _res:
                                    entries.append(_res)
                            except Exception as e:
                                self.logger_debug(f"[get_entries][{futures[fut]}] error - {repr(e)}")

                    else:

                        entries = [
                            {
                                '_type': 'url',
                                'url': video,
                                'ie_key': 'MyVidster',
                                'original_url': _url
                            } for _url, _videos in results.items()

                            for video in _videos]

                    if entries:

                        return self.playlist_result(
                            entries, playlist_id=query.replace(' ', '_'),
                            playlist_title='SearchMyVidsterRSS')

                raise_extractor_error("no entries found")

        except ExtractorError as e:
            self.to_screen(repr(e))
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise_extractor_error(repr(e))

    def _real_initialize(self):

        with MyVidsterBaseIE._LOCK:

            super()._real_initialize()

            if not MyVidsterRSSPlaylistIE._RSS:
                if not (_rss := self.cache.load(self.ie_key(), 'rss')):
                    self._get_rss()
                    if (_rss := MyVidsterRSSPlaylistIE._RSS):
                        self.cache.store(self.ie_key(), 'rss', _rss)
                else:
                    MyVidsterRSSPlaylistIE._RSS = _rss

    def _real_extract(self, url):

        self.report_extraction(url)

        return self.get_playlist_rss_search(url)
