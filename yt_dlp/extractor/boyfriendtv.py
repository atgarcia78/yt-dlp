import html
import json
import logging
import re
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote, urlparse


from .commonwebdriver import (
    By,
    ConnectError,
    HTTPStatusError,
    SeleniumInfoExtractor,
    dec_on_exception,
    dec_on_exception2,
    dec_on_exception3,
    ec,
    limiter_0_1,
    cast
)
from ..utils import (
    ExtractorError,
    get_domain,
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

    _LOCK = threading.Lock()
    _COOKIES = {}

    @dec_on_exception3
    @dec_on_exception2
    @limiter_0_1.ratelimit("boyfriendtv", delay=True)
    def _get_info_for_format(self, url, **kwargs):

        _headers = kwargs.get('headers', {})
        _headers.update({'Range': 'bytes=0-', 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'})
        self.logger_debug(f"[get_video_info] {url}")

        try:
            return self.get_info_for_format(url, headers=_headers)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
            return {"error_res": f"{repr(e)}"}

    @dec_on_exception
    @dec_on_exception3
    @dec_on_exception2
    @limiter_0_1.ratelimit("boyfriendtv2", delay=True)
    def _send_request(self, url, driver=None, **kwargs):

        if driver:
            driver.get(url)
        else:
            try:
                return self.send_http_request(url, **kwargs)
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"[send_request] {self._get_url_print(url)}: error - {repr(e)}")

    def _login(self, driver):

        username, password = self._get_login_info()

        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)

        self.report_login()

        self._send_request(self._SITE_URL, driver)
        el_menu = self.wait_until(driver, 10, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))
        if el_menu:
            self.logger_debug("Login already")
            return

        el_login = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a#login-url")))
        if el_login:
            el_login.click()
        el_username = self.wait_until(driver, 30, ec.presence_of_element_located(
            (By.CSS_SELECTOR, "input#login.form-control")))
        el_password = self.wait_until(driver, 30, ec.presence_of_element_located(
            (By.CSS_SELECTOR, "input#password.form-control")))
        el_login = self.wait_until(driver, 30, ec.presence_of_element_located(
            (By.CSS_SELECTOR, "input.btn.btn-submit")))
        if el_username and el_password and el_login:
            el_username.send_keys(username)
            self.wait_until(driver, 2)
            el_password.send_keys(password)
            self.wait_until(driver, 2)
            el_login.submit()
            el_menu = self.wait_until(driver, 10, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))

            if not el_menu:
                self.raise_login_required("Invalid username/password")
            else:
                self.logger_debug("Login OK")

    def _real_initialize(self):

        super()._real_initialize()

        with BoyFriendTVBaseIE._LOCK:
            if not BoyFriendTVBaseIE._COOKIES:
                driver = self.get_driver()
                try:
                    self._send_request(self._SITE_URL, driver)
                    driver.add_cookie({'name': 'rta_terms_accepted', 'value': 'true', 'domain': '.boyfriendtv.com'})
                    driver.add_cookie({'name': 'videosPerRow', 'value': '5', 'domain': '.boyfriendtv.com'})
                    self._login(driver)
                    BoyFriendTVBaseIE._COOKIES = driver.get_cookies()
                except Exception:
                    self.to_screen("error when login")
                    raise
                finally:
                    self.rm_driver(driver)

            for cookie in BoyFriendTVBaseIE._COOKIES:
                self._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])


class BoyFriendTVIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtv'  # type: ignore
    _VALID_URL = r'https?://(?:(?P<prefix>m|www|es|ru|de)\.)?(?P<url>boyfriendtv\.com/(?:videos|embed)/(?P<id>[0-9]+)/?(?:([0-9a-zA-z_-]+/?)|$))'

    def _get_entry(self, url, **kwargs):

        check = kwargs.get('check', True)
        videoid = self._match_id(url)

        _san_url = urljoin(self._SITE_URL, f'videos/{videoid}')

        try:
            webpage = try_get(self._send_request(_san_url), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)))
            if not webpage:
                raise ExtractorError("no webpage")

            _title = try_get(self._html_extract_title(webpage), lambda x: x.replace(" - BoyFriendTV.com", "").strip())
            if _title and any(_ in _title.lower() for _ in ("deleted", "removed", "page not found")):
                raise ExtractorError("Page not found 404")

            _rating = try_get(re.search(r'class="progress-big js-rating-title" title="(?P<rat>\d+)%"', webpage), lambda x: int(x.group('rat')))

            info_sources = try_get(re.findall(r'sources:\s+(\[\{.*\}\])\,\s+poster', webpage), lambda x: json.loads(js_to_json(x[0])))

            if not info_sources:
                raise ExtractorError("no video sources")

            sources_mp4 = [source for source in info_sources if source.get('format') == 'mp4']

            if not sources_mp4:
                raise ExtractorError("no mp4 video sources")

            sources_mp4 = sorted(sources_mp4, key=lambda x: int(x.get('desc', "0p")[:-1]), reverse=True)

            urlp = urlparse(_san_url)
            _headers = {'Referer': f"{urlp.scheme}//{urlp.netloc}/"}

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

                    if i == 0 and check:
                        _host = get_domain(_url)
                        _sem = self.get_ytdl_sem(_host)

                        with _sem:
                            _info_video = self._get_info_for_format(_url, headers=_headers)
                        if _info_video:
                            _info_video = cast(dict, _info_video)

                        if not _info_video or 'error' in _info_video:
                            self.logger_debug(f"[{url}][{_format_id}] no video info")
                        else:
                            _format.update({'url': _info_video.get('url'), 'filesize': _info_video.get('filesize')})

                    _formats.append(_format)
                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.logger_debug(f"{repr(e)}\n{'!!'.join(lines)}")

            if not _formats:

                raise ExtractorError('404 no formats')

            return ({
                'id': videoid,
                'title': sanitize_filename(_title, restricted=True),
                'formats': _formats,
                'ext': 'mp4',
                'webpage_url': _san_url,
                'average_rating': _rating,
                'extractor_key': self.ie_key(),
                'extractor': self.IE_NAME})

        except ExtractorError as e:
            self.logger_debug(f"[{url}] error {repr(e)}")
            raise
        except Exception as e:
            self.logger_debug(f"[{url}] error {repr(e)}")
            raise ExtractorError(repr(e))

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
        try:
            return self._get_entry(url)
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}  \n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))


class BoyFriendTVPLBaseIE(BoyFriendTVBaseIE):

    def _get_last_page(self, webpage):
        last_page_url = try_get(re.findall(r'class="rightKey" href="([^"]+)"', webpage), lambda x: x[-1] if x else "")

        assert last_page_url

        last_page = try_get(re.search(r'(?P<last>\d+)/?(?:$|\?)', last_page_url), lambda x: int(x.group('last'))) or 1
        return last_page

    def _get_entries_page(self, url_page, _min_rating, _q, page, orig_url):

        try:
            logger.debug(f"page: {url_page}")
            webpage = try_get(self._send_request(url_page), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)))

            assert webpage

            el_videos = try_get(webpage.split(self._CSS_SEL), lambda x: x[1:])
            entries = []
            urls = []
            if el_videos:
                for el in el_videos:
                    try:
                        thumb, title, url, rating = try_get(re.search(r'href="(?P<url>[^"]+)".*src="(?P<thumb>[^"]+)" alt="(?P<title>[^"]+)".*green" title="(?P<rat>\d+)%', el), lambda x: (x.group('thumb'), x.group('title'), urljoin(self._SITE_URL, x.group('url').rsplit("/", 1)[0]), try_get(x.group('rat'), lambda y: int(y) if y.isdecimal() else 0)) if x else ("", "", "", ""))  # type: ignore
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
                            if (_ent := fut.result()):
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

    def _get_playlist(self, url):

        playlist_id, query = try_get(re.match(self._VALID_URL, url), lambda x: x.group('playlist_id', 'query'))  # type: ignore
        if query:
            params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
        else:
            params = {}

        _sq = try_get(params.get('sort'), lambda x: f'?sort={x}' if x else "")
        self.to_screen(f'{self._BASE_URL}{_sq}' % (playlist_id, 1))
        self.to_screen(params)
        webpage = try_get(self._send_request(f'{self._BASE_URL}{_sq}' % (playlist_id, 1)), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)))
        _title = self._html_search_regex(r'<h1[^>]*>([^<]+)<', webpage, 'title')
        _min_rating = int(params.get('rating', 0))
        _q = try_get(params.get('q'), lambda x: x.split(','))

        last_page = self._get_last_page(webpage)

        self.to_screen(f"last_page: {last_page}, minrating: {_min_rating}")

        with ThreadPoolExecutor(thread_name_prefix='bftvlist') as ex:
            futures = {ex.submit(self._get_entries_page, f'{self._BASE_URL}{_sq}' % (playlist_id, (page + 1)), _min_rating, _q, page, url): page for page in range(last_page)}

        _entries = []

        for fut in futures:
            try:
                if (_ent := fut.result()):
                    _entries.extend(_ent)
                else:
                    self.report_warning(f"[{url}][page {futures[fut]}] no entries")
            except Exception as e:
                self.report_warning(f"[{url}][page {futures[fut]}] {repr(e)}")

        if not _entries:
            raise ExtractorError("cant find any video")

        return self.playlist_result(_entries, playlist_id, sanitize_filename(_title, restricted=True))

    def _real_initialize(self):
        super()._real_initialize()
        self._CSS_SEL: str
        self._BASE_URL: str

    def _real_extract(self, url):

        self.report_extraction(url)

        try:
            return self._get_playlist(url)
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}  \n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))


class BoyFriendTVSearchIE(BoyFriendTVPLBaseIE):
    IE_NAME = 'boyfriendtv:playlist:search'  # type: ignore
    IE_DESC = 'boyfriendtv:playlist:search'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/search/(?P<playlist_id>[^/?$]*)/?(\?(?P<query>.+))?'
    _BASE_URL = f'{BoyFriendTVBaseIE._SITE_URL}search/%s/%d'
    _CSS_SEL = "js-pop thumb-item videospot inrow5"


class BoyFriendTVProfileFavIE(BoyFriendTVPLBaseIE):
    IE_NAME = 'boyfriendtv:playlist:profilefav'  # type: ignore
    IE_DESC = 'boyfriendtv:playlist:profilefav'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/profiles/(?P<playlist_id>\d*)/?(\?(?P<query>.+))?'
    _BASE_URL = f'{BoyFriendTVBaseIE._SITE_URL}profiles/%s/videos/favorites/?page=%d'
    _CSS_SEL = "js-pop thumb-item videospot"


class BoyFriendTVPlayListIE(BoyFriendTVPLBaseIE):
    IE_NAME = 'boyfriendtv:playlist'  # type: ignore
    IE_DESC = 'boyfriendtv:playlist'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/playlists/(?P<playlist_id>\d*)/?(\?(?P<query>.+))?'
    _BASE_URL = f'{BoyFriendTVBaseIE._SITE_URL}playlists/%s/%d'
    _CSS_SEL = "playlist-video-thumb thumb-item videospot"
