import html
import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote, urlparse

from .commonwebdriver import (
    By,
    ConnectError,
    HTTPStatusError,
    SeleniumInfoExtractor,
    WebElement,
    dec_on_driver_timeout,
    dec_on_exception2,
    dec_on_exception3,
    ec,
    get_host,
    limiter_1,
)
from ..utils import (
    ExtractorError,
    int_or_none,
    js_to_json,
    sanitize_filename,
    try_get,
    urljoin,
)

logger = logging.getLogger('bftv')


class BoyFriendTVBaseIE(SeleniumInfoExtractor):
    _LOGIN_URL = 'https://www.boyfriendtv.com/login/'
    _SITE_URL = 'https://www.boyfriendtv.com/'
    _NETRC_MACHINE = 'boyfriendtv'
    _LOGOUT_URL = 'https://www.boyfriendtv.com/logout'
    _COOKIES = {}
    _LOCK = threading.Lock()
    _BFINIT = False

    @dec_on_exception3
    @dec_on_exception2
    @limiter_1.ratelimit("boyfriendtv", delay=True)
    def _get_info_for_format(self, url, **kwargs) -> dict:

        _headers = kwargs.get('headers', {})
        headers = {
            'Range': 'bytes=0-', 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
        headers.update(_headers)
        self.logger_debug(f"[get_video_info] {url}")

        try:
            return self.get_info_for_format(url, client=BoyFriendTVBaseIE._CLIENT, headers=headers)
        except (HTTPStatusError, ConnectError) as e:
            self.logger_debug(
                f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
            return {"error_res": f"{repr(e)}"}

    @classmethod
    @dec_on_exception3
    @dec_on_exception2
    @dec_on_driver_timeout
    @limiter_1.ratelimit("boyfriendtv2", delay=True)
    def _send_request(cls, url, driver=None, **kwargs):

        if driver:
            driver.get(url)
        else:
            try:
                return cls._send_http_request(url, client=BoyFriendTVBaseIE._CLIENT, **kwargs)
            except (HTTPStatusError, ConnectError) as e:
                logger.debug(f"[send_request] {cls._get_url_print(url)}: error - {repr(e)}")

    def _login(self, driver):

        username, password = self._get_login_info()

        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)

        self.report_login()

        BoyFriendTVBaseIE._send_request(self._SITE_URL, driver)
        el_menu = self.wait_until(
            driver, 10, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))
        if el_menu:
            self.logger_debug("Login already")
            return

        el_login = self.wait_until(
            driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a#login-url")))
        if isinstance(el_login, WebElement):
            el_login.click()
        el_username = self.wait_until(driver, 30, ec.presence_of_element_located(
            (By.CSS_SELECTOR, "input#login.form-control")))
        el_password = self.wait_until(driver, 30, ec.presence_of_element_located(
            (By.CSS_SELECTOR, "input#password.form-control")))
        el_login = self.wait_until(driver, 30, ec.presence_of_element_located(
            (By.CSS_SELECTOR, "input.btn.btn-submit")))
        if el_username and el_password and el_login:
            el_username.send_keys(username)  # type: ignore
            self.wait_until(driver, 2)
            el_password.send_keys(password)  # type: ignore
            self.wait_until(driver, 2)
            el_login.submit()  # type: ignore
            el_menu = self.wait_until(
                driver, 10, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))

            if not el_menu:
                self.raise_login_required("Invalid username/password")
            else:
                self.logger_debug("Login OK")

    def _real_initialize(self):

        super()._real_initialize()

        with BoyFriendTVBaseIE._LOCK:
            if not BoyFriendTVBaseIE._BFINIT:
                BoyFriendTVBaseIE._CLIENT = self._CLIENT
                BoyFriendTVBaseIE._send_request(self._SITE_URL)
                for cookie in self._FF_COOKIES_JAR.get_cookies_for_url(self._SITE_URL):
                    BoyFriendTVBaseIE._CLIENT.cookies.jar.set_cookie(cookie)
                if try_get(
                    BoyFriendTVBaseIE._send_request(self._SITE_URL),
                    lambda x: 'atgarcia' in x.text
                ):
                    self.logger_debug("Already logged with cookies")
                    BoyFriendTVBaseIE._BFINIT = True

                else:

                    with SeleniumInfoExtractor._SEMAPHORE:
                        driver = self.get_driver()
                        try:
                            if not driver:
                                raise ExtractorError('error driver init')
                            else:
                                BoyFriendTVBaseIE._send_request(self._SITE_URL, driver)
                                driver.add_cookie({
                                    'name': 'rta_terms_accepted',
                                    'value': 'true',
                                    'domain': '.boyfriendtv.com'})
                                driver.add_cookie({
                                    'name': 'videosPerRow',
                                    'value': '5',
                                    'domain': '.boyfriendtv.com'})
                                self._login(driver)
                                BoyFriendTVBaseIE._COOKIES = driver.get_cookies()
                                for cookie in BoyFriendTVBaseIE._COOKIES:
                                    BoyFriendTVBaseIE._CLIENT.cookies.jar.set_cookie(cookie)
                                if try_get(
                                    BoyFriendTVBaseIE._send_request(self._SITE_URL),
                                    lambda x: 'atgarcia' in x.text
                                ):
                                    self.logger_debug("Already logged with cookies")
                                    BoyFriendTVBaseIE._BFINIT = True
                        except Exception:
                            self.to_screen("error when login")
                            raise
                        finally:
                            if driver:
                                self.rm_driver(driver)


class BoyFriendTVIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtv'  # type: ignore
    _VALID_URL = r'https?://(?:(?P<prefix>m|www|es|ru|de)\.)?(?P<url>boyfriendtv\.com/(?:es/)?(?:videos|embed)/(?P<id>[0-9]+)/?(?:([0-9a-zA-z_-]+/?)|$))'

    def _get_entry(self, url, **kwargs):

        check = kwargs.get('check', True)
        videoid = self._match_id(url)

        _san_url = urljoin(self._SITE_URL, f'videos/{videoid}')

        try:
            webpage = try_get(
                BoyFriendTVBaseIE._send_request(_san_url),
                lambda x: re.sub('[\t\n]', '', html.unescape(x.text)))
            if not webpage:
                raise ExtractorError("error 404 no webpage", expected=True)

            _title = try_get(
                self._html_extract_title(webpage),
                lambda x: x.replace(" - BoyFriendTV.com", "").strip())
            if _title and any(_ in _title.lower() for _ in ("deleted", "removed", "page not found")):
                raise ExtractorError("Page not found 404", expected=True)

            _rating = try_get(
                re.search(r'class="progress-big js-rating-title" title="(?P<rat>\d+)%"', webpage),
                lambda x: int(x.group('rat')))

            info_sources = try_get(
                re.findall(r'sources:\s+(\[\{.*\}\])\,\s+poster', webpage),
                lambda x: json.loads(js_to_json(x[0])))

            if not info_sources:
                raise ExtractorError("no video sources")

            sources_mp4 = [source for source in info_sources if source.get('format') == 'mp4']

            if not sources_mp4:
                raise ExtractorError("no mp4 video sources")

            sources_mp4 = sorted(
                sources_mp4, key=lambda x: int(x.get('desc', "0p")[:-1]), reverse=True)

            urlp = urlparse(_san_url)
            _headers = {
                'Referer': f"{urlp.scheme}://{urlp.netloc}/",
                'Accept': 'video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5',
                'Accept-Encoding': 'identity'
            }

            _formats = []

            for i, _src in enumerate(sources_mp4):

                try:

                    _format_id = f"http-{_src.get('desc')}"
                    _url = unquote(_src.get('src'))

                    _format = {
                        'url': _url,
                        'ext': 'mp4',
                        'format_id': _format_id,
                        'height': int_or_none(_src.get('desc').lower().replace('p', '')),
                        'http_headers': _headers,
                    }

                    if i == 0:
                        _host = get_host(_url)
                        _sem = self.get_ytdl_sem(_host)
                        if check:
                            with _sem:
                                _info_video = self._get_info_for_format(_url, headers=_headers)

                            if not isinstance(_info_video, dict) or 'error' in _info_video:
                                self.logger_debug(f"[{url}][{_format_id}] no video info")
                            else:
                                _format.update(_info_video)
                                self.get_ytdl_sem(get_host(_info_video.get('url')) or 'boyfriendtv.com')

                    _formats.append(_format)
                except Exception as e:
                    self.logger_debug(repr(e))

            if not _formats:

                raise ExtractorError('404 no formats', expected=True)

            return ({
                'id': videoid,
                'title': sanitize_filename(_title, restricted=True),
                'formats': _formats,
                'ext': 'mp4',
                'webpage_url': _san_url,
                'average_rating': _rating,
                'extractor_key': self.ie_key(),
                'extractor': self.IE_NAME})

        except Exception as e:
            self.logger_debug(f"[{url}] error {repr(e)}")
            return {'error': e, '_all_urls': [f'https://{get_host(url)}/videos/{videoid}', f'https://{get_host(url)}/embed/{videoid}']}

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
        try:
            if 'error' in (_info := self._get_entry(url)):
                raise _info['error']
            else:
                return _info
        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(repr(e), expected=True)


class BoyFriendTVPLBaseIE(BoyFriendTVBaseIE):

    def _get_last_page(self, webpage):
        last_page_url = try_get(re.findall(r'class="rightKey" href="([^"]+)"', webpage), lambda x: x[-1] if x else "")

        if not last_page_url:
            return 1

        last_page = try_get(re.search(r'(?P<last>\d+)/?(?:$|\?)', last_page_url), lambda x: int(x.group('last'))) or 1
        return last_page

    def _get_entries_page(self, url_page, _min_rating, _q, page, orig_url):

        _pattern = r'href="(?P<url>[^"]+)".*src="(?P<thumb>[^"]+)" alt="(?P<title>[^"]+)".*green" title="(?P<rat>\d+)%'
        try:
            logger.debug(f"page: {url_page}")
            webpage = try_get(
                BoyFriendTVBaseIE._send_request(url_page),
                lambda x: re.sub('[\t\n]', '', html.unescape(x.text)))

            if not webpage:
                raise ExtractorError("error 404 no webpage", expected=True)

            el_videos = try_get(webpage.split(self._CSS_SEL), lambda x: x[1:])
            entries = []
            urls = []
            if el_videos:
                for el in el_videos:
                    try:
                        thumb, title, url, rating = try_get(
                            re.search(_pattern, el),
                            lambda x: (
                                x.group('thumb'), x.group('title'),
                                urljoin(self._SITE_URL, x.group('url').rsplit("/", 1)[0]),
                                try_get(
                                    x.group('rat'),
                                    lambda y: int(y) if y.isdecimal() else 0) or 0)
                        ) or ("", "", "", "")
                        if 'img/removed-video' in thumb or not url:
                            continue

                        if rating and (rating < _min_rating):
                            continue
                        if title and _q:
                            if not any(_.lower() in title.lower() for _ in _q):
                                continue

                        urls.append(url)
                    except Exception as e:
                        logger.exception(repr(e))
            if urls:

                if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):
                    ie_bf = self._get_extractor("BoyFriendTV")
                    with ThreadPoolExecutor(thread_name_prefix=f'bftventries{page}') as ex:
                        futures = {ex.submit(ie_bf._get_entry, _url): _url for _url in urls}
                    for fut in futures:
                        try:
                            if (_ent := fut.result()) and "error" not in _ent:
                                _ent.update({'original_url': orig_url})
                                entries.append(_ent)
                            else:
                                self.report_warning(f"[{url_page}][{futures[fut]}] no entry")
                        except Exception as e:
                            self.report_warning(f"[{url_page}][{futures[fut]}] {repr(e)}")
                    if entries:
                        return (entries)
                else:
                    entries = [self.url_result(_url, ie=BoyFriendTVIE.ie_key()) for _url in urls]
                    return entries
        except Exception as e:
            logger.exception(repr(e))

    def _get_playlist(self, url, playlist_id, query):

        if query:
            params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
        else:
            params = {}

        _sq = try_get(params.get('sort'), lambda x: f'?sort={x}' if x else "")
        self.to_screen(f'{self._BASE_URL}{_sq}' % (playlist_id, 1))
        self.to_screen(params)
        webpage = try_get(
            BoyFriendTVBaseIE._send_request(f'{self._BASE_URL}{_sq}' % (playlist_id, 1)),
            lambda x: re.sub('[\t\n]', '', html.unescape(x.text)))
        if not webpage:
            raise ExtractorError("error 404 no webpage", expected=True)
        _title = self._html_search_regex(r'<h1[^>]*>([^<]+)<', webpage, 'title')
        _min_rating = int(params.get('rating', 0))
        _q = try_get(params.get('q'), lambda x: x.split(','))

        last_page = self._get_last_page(webpage)

        self.to_screen(f"last_page: {last_page}, minrating: {_min_rating}")

        with ThreadPoolExecutor(thread_name_prefix='bftvlist') as ex:
            futures = {ex.submit(
                self._get_entries_page, f'{self._BASE_URL}{_sq}' % (playlist_id, (page + 1)),
                _min_rating, _q, page, url): page for page in range(last_page)}

        _entries = []

        for fut in futures:
            try:
                if (_ent := fut.result()):
                    _entries.extend(_ent)
                else:
                    self.report_warning(
                        f"[{url}][page {futures[fut]}] no entries")
            except Exception as e:
                self.report_warning(
                    f"[{url}][page {futures[fut]}] {repr(e)}")

        if not _entries:
            raise ExtractorError("cant find any video", expected=True)

        return self.playlist_result(
            _entries, playlist_id, sanitize_filename(_title, restricted=True))

    def _real_initialize(self):
        super()._real_initialize()
        self._CSS_SEL: str
        self._BASE_URL: str


class BoyFriendTVSearchIE(BoyFriendTVPLBaseIE):
    IE_NAME = 'boyfriendtv:playlist:search'  # type: ignore
    IE_DESC = 'boyfriendtv:playlist:search'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/search/(?P<playlist_id>[^/?$]*)/?(\?(?P<query>.+))?'
    _BASE_URL = f'{BoyFriendTVBaseIE._SITE_URL}search/%s/%d'
    _CSS_SEL = "js-pop thumb-item videospot inrow5"

    def _real_extract(self, url):

        self.report_extraction(url)
        playlist_id, query = try_get(
            re.match(self._VALID_URL, url),
            lambda x: x.group('playlist_id', 'query')) or (None, None)

        try:
            return self._get_playlist(url, playlist_id, query)
        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(repr(e), expected=True)


class BoyFriendTVProfileFavIE(BoyFriendTVPLBaseIE):
    IE_NAME = 'boyfriendtv:playlist:profilefav'  # type: ignore
    IE_DESC = 'boyfriendtv:playlist:profilefav'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/profiles/(?P<playlist_id>\d*)/?(\?(?P<query>.+))?'
    _BASE_URL = f'{BoyFriendTVBaseIE._SITE_URL}profiles/%s/videos/favorites/?page=%d'
    _CSS_SEL = "js-pop thumb-item videospot"

    def _real_extract(self, url):

        self.report_extraction(url)
        playlist_id, query = try_get(
            re.match(self._VALID_URL, url),
            lambda x: x.group('playlist_id', 'query')) or (None, None)

        try:
            return self._get_playlist(url, playlist_id, query)
        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(repr(e), expected=True)


class BoyFriendTVPlayListIE(BoyFriendTVPLBaseIE):
    IE_NAME = 'boyfriendtv:playlist'  # type: ignore
    IE_DESC = 'boyfriendtv:playlist'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/playlists/(?P<playlist_id>\d*)/?(\?(?P<query>.+))?'
    _BASE_URL = f'{BoyFriendTVBaseIE._SITE_URL}playlists/%s/%d'
    _CSS_SEL = "playlist-video-thumb thumb-item videospot"

    def _real_extract(self, url):

        self.report_extraction(url)
        playlist_id, query = try_get(
            re.match(self._VALID_URL, url),
            lambda x: x.group('playlist_id', 'query')) or (None, None)

        try:
            return self._get_playlist(url, playlist_id, query)
        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(repr(e), expected=True)
