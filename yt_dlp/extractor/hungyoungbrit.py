import hashlib
import html
import json
import re
import sys
import threading
import traceback


from ..utils import ExtractorError, int_or_none, sanitize_filename, get_elements_html_by_attribute, traverse_obj
from .commonwebdriver import (
    By, ec, SeleniumInfoExtractor,
    limiter_1, dec_on_exception2,
    dec_on_exception3, HTTPStatusError, ConnectError,
    try_get, my_dec_on_exception, ReExtractInfo)

on_exception_vinfo = my_dec_on_exception(
    (TimeoutError, ExtractorError, HTTPStatusError), raise_on_giveup=False, max_tries=3, interval=1)

dec_on_reextract = my_dec_on_exception(
    ReExtractInfo, max_tries=3, raise_on_giveup=True, interval=5)


class HungYoungBritBaseIE(SeleniumInfoExtractor):

    _SITE_URL = 'https://www.hungyoungbrit.com'
    _NETRC_MACHINE = 'hungyoungbrit'

    _LOCK = threading.Lock()

    _COOKIES = []

    @on_exception_vinfo
    def _get_info_video(self, url):

        try:
            with HungYoungBritBaseIE._LOCK:
                res = self._CLIENT.head(url)
                res.raise_for_status()

                _filesize = int_or_none(res.headers.get('content-length'))
                _url = str(res.url)
                if _filesize:
                    res = {'url': _url, 'filesize': _filesize}
                    return res
                else:
                    raise ExtractorError('no filesize')

        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise

    @dec_on_exception3
    @dec_on_exception2
    @limiter_1.ratelimit("hungyoungbrit", delay=True)
    def _send_request(self, url, **kwargs):

        pre = f'[send_request][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'

        driver = kwargs.pop('driver', None)

        # with HungYoungBritBaseIE._LOCK:
        self.logger_debug(pre)
        if driver:
            driver.get(url)
        else:
            try:
                return self.send_http_request(url, **kwargs)
            except (HTTPStatusError, ConnectError) as e:
                _msg_error = f"{repr(e)}"
                self.logger_debug(f"{pre}: {_msg_error}")
                return {"error_res": _msg_error}

    def get_auth(self):

        _home_url = "https://www.hungyoungbrit.com/members/category.php?id=5"

        with HungYoungBritBaseIE._LOCK:

            _login_ok = try_get(self._send_request(_home_url), lambda x: _home_url in str(x.url) if x else None)
            if _login_ok:
                self.to_screen("[login] login ok with no actions")
                return

            _cookies = None
            if not HungYoungBritBaseIE._COOKIES:

                try:
                    with open("/Users/antoniotorres/Projects/common/logs/HYB_cookies.json", "r") as f:
                        _cookies = json.load(f)
                    self.to_screen("[login] cookies from file")
                except Exception as e:
                    self.to_screen(str(e))
            else:
                _cookies = HungYoungBritBaseIE._COOKIES.copy()
                self.to_screen("[login] cookies from class")

            if _cookies:

                for cookie in _cookies:
                    self._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])

                _login_ok = try_get(self._send_request(_home_url), lambda x: _home_url in str(x.url) if x else False)
                if _login_ok:
                    self.to_screen("[login] cookies valid for login")
                    HungYoungBritBaseIE._COOKIES = _cookies.copy()
                    return
                else:
                    self.to_screen("[login] login failed with current cookies")

            self.to_screen("[login] start new login with driver")
            self.report_login()

            with SeleniumInfoExtractor._SEMAPHORE:
                driver = self.get_driver()

                try:

                    self._send_request(self._SITE_URL, driver=driver)
                    driver.add_cookie({"name": "warn", "value": "1", "domain": "www.hungyoungbrit.com", "secure": False, "httpOnly": False, "sameSite": "Lax"})

                    self._send_request(_home_url, driver=driver)
                    self.wait_until(driver, 30, ec.url_changes(""))
                    self.to_screen(f"[login] current url: {driver.current_url}")
                    if _home_url not in driver.current_url:

                        el = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a.dropdown-toggle.londrina")))
                        assert el
                        el.click()
                        el_username = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "input#username.form-control")))
                        el_password = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "input#password.form-control")))
                        button_login = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "button#btnLogin.btn.btn-primary.btn-sm.btn-block")))
                        username, password = self._get_login_info()
                        assert el_username and el_password and button_login
                        el_username.send_keys(username)
                        self.wait_until(driver, 2)
                        el_password.send_keys(password)
                        self.wait_until(driver, 2)
                        button_login.click()
                        self.wait_until(driver, 300, ec.invisibility_of_element(button_login))
                        el = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a.dropdown-toggle.londrina")))
                        assert el
                        if el.text != 'ACCOUNT':
                            raise ExtractorError("log in error")

                    self.to_screen("[login] success with driver")

                    HungYoungBritBaseIE._COOKIES = driver.get_cookies()

                    with open("/Users/antoniotorres/Projects/common/logs/HYB_cookies.json", "w") as f:
                        json.dump(HungYoungBritBaseIE._COOKIES, f)

                    for cookie in HungYoungBritBaseIE._COOKIES:
                        self._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])

                    _login_ok = try_get(self._send_request(_home_url), lambda x: _home_url in str(x.url) if x else None)
                    if _login_ok:
                        self.to_screen("[login] login valid for http client")
                    else:
                        raise ExtractorError("Error cookies")

                except ExtractorError:
                    raise
                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
                    raise ExtractorError(repr(e))
                finally:
                    self.rm_driver(driver)

    def _real_initialize(self):
        super()._real_initialize()

        self.get_auth()


class HungYoungBritIE(HungYoungBritBaseIE):

    IE_NAME = "hungyoungbrit"  # type: ignore
    _VALID_URL = r'https?://(www\.)?hungyoungbrit\.com/members/gallery\.php\?id=(?P<id>\d+)&type=vids'

    def _real_initialize(self):
        super()._real_initialize()
        self._done = 0
        self._total = 0

    @dec_on_reextract
    def _get_entry(self, url, **kwargs):

        progress_bar = kwargs.get('progress_bar')

        try:
            webpage = try_get(self._send_request(url), lambda x: re.sub('[\n\t]', '', html.unescape(x.text)))

            if not webpage:
                raise ExtractorError("fails getting webpage")

            title = self._html_extract_title(webpage)

            if isinstance(title, str) and 'Members Only' in title:
                raise ReExtractInfo("members only in title")

            mobj = re.findall(r'movie\[\"(?:1080|720|480)p\"\]\[\"([^\"]+)\"\]=\{path:\"([^\"]+)\"[^\}]+movie_width:\'(\d+)\',movie_height:\'(\d+)\'[^\}]+\}', webpage.replace(' ', ''))
            if not mobj:
                self.write_debug(webpage)
                raise ExtractorError("no video formats")

            #  video_id = str(int(hashlib.sha256((mobj[0][0]).encode('utf-8')).hexdigest(), 16) % 10**8)

            video_id = str(int(hashlib.sha256(f'HYB{self._match_id(url)}'.encode('utf-8')).hexdigest(), 16) % 10**8)

            formats = []

            for pos, el in enumerate(mobj):

                _url = el[1]
                _filesize = None

                if pos == 0:
                    _info_video = self._get_info_video(el[1])

                    if _info_video:
                        _url = _info_video['url']
                        _filesize = _info_video['filesize']

                _format = {
                    'url': _url,
                    'width': int(el[2]),
                    'height': int(el[3]),
                    'format_id': f'http{el[3]}',
                    'ext': 'mp4'}

                if _filesize:
                    _format['filesize'] = _filesize

                formats.append(_format)

            return ({
                'id': video_id,
                'title': sanitize_filename(title, restricted=True).upper(),
                'formats': formats,
                'ext': 'mp4',
                'webpage_url': url,
                'extractor_key': 'HungYoungBrit',
                'extractor': 'hungyoungbrit',
            })

        except ReExtractInfo:
            self.get_auth()
            raise
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e))
        finally:
            if progress_bar:
                with HungYoungBritBaseIE._LOCK:
                    self._done += 1
                progress_bar.print(f'Entry OK {self._done}/{self._total}')

    def _real_extract(self, url, **kwargs):

        self.report_extraction(url)

        return self._get_entry(url)


class HungYoungBritPlaylistIE(HungYoungBritBaseIE):

    IE_NAME = "hungyoungbrit:playlist"  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?hungyoungbrit\.com/members/category\.php\?id=5&(?P<query>.+)'
    _PL_LOCK = threading.Lock()

    def _get_last_page(self):
        base_url = 'https://www.hungyoungbrit.com/tour/category.php?id=5&page=%s&s=d'

        _page_target = '1'

        while True:
            webpage = try_get(self._send_request(base_url % _page_target), lambda x: x.text)
            _el = traverse_obj(get_elements_html_by_attribute('aria-label', 'Next Set', webpage), (0))
            if _el:
                _res = try_get(re.search(r'page=(?P<page>\d+)', _el), lambda x: x.groupdict().get('page'))  # type: ignore
                if _res:
                    _page_target = _res
                    continue
            else:
                return int(_page_target)

    def get_pages_search(self, url):

        query = try_get(re.search(self._VALID_URL, url), lambda x: x.group('query'))

        assert query

        params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&')}

        if not params.get('s'):
            params['s'] = 'd'

        npages = params.pop('pages', 1)
        firstpage = params.pop('from', 1)

        query_str = "&".join([f"{_key}={_val}" for _key, _val in params.items()])
        base_url = f'https://www.hungyoungbrit.com/members/category.php?id=5&page=%s&{query_str}'

        last_page = self._get_last_page()

        if npages == 'all':
            _max = last_page
        else:
            _max = int(firstpage) + int(npages) - 1
            if _max > last_page:
                self.logger_debug(
                    f'[{self._get_url_print(url)}] pages requested > max page website: will check up to max page')
                _max = last_page

        return [base_url % i for i in range(int(firstpage), _max + 1)]

    def get_videos_page(self, urlpage):

        webpage = try_get(self._send_request(urlpage), lambda x: html.unescape(x.text))

        if not webpage:
            raise ExtractorError("fails getting webpage")

        mobj = re.findall(r'<a title="([^"]+)" href="gallery\.php\?id=(\d+).+"', webpage)
        if not mobj:
            self.write_debug(webpage)
            raise ExtractorError("no video entries")

        return [{'id': str(int(hashlib.sha256(f'HYB{vid[1]}'.encode('utf-8')).hexdigest(), 16) % 10**8), 'title': sanitize_filename(html.unescape(vid[0]), restricted=True).upper(),
                'url': f"https://www.hungyoungbrit.com/members/gallery.php?id={vid[1]}&type=vids"}
                for vid in mobj]

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        _urls_pages = self.get_pages_search(url)

        _info_videos = []
        for _url in _urls_pages:
            _info_videos.extend(self.get_videos_page(_url))

        if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

            iehung = self._get_extractor("HungYoungBrit")
            iehung._total = len(_info_videos)

            with self.create_progress_bar(msg=f'[get_entries][{url}]') as progress_bar:

                entries = [iehung._get_entry(_vid['url'], progress_bar=progress_bar) for _vid in _info_videos]

            for _ent in entries:
                _ent['original_url'] = url

        else:
            entries = [self.url_result(_vid['url'], ie=HungYoungBritIE.ie_key(), title=_vid['title'], id=_vid['id'], original_url=url) for _vid in _info_videos]

        return self.playlist_result(entries, playlist_id="HYBplaylist", playlist_title="HYBplaylist")
