import html
import json
import logging
import re
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock
import base64
import subprocess
import copy

from .commonwebdriver import (
    ConnectError,
    StatusStop,
    HTTPStatusError,
    ProgressTimer,
    ReExtractInfo,
    dec_on_exception2,
    dec_on_exception3,
    dec_on_reextract,
    dec_retry,
    limiter_0_01,
    limiter_0_1,
    limiter_5,
    SeleniumInfoExtractor,
    Dict,


)
from ..utils import (
    ExtractorError,
    extract_timezone,
    int_or_none,
    sanitize_filename,
    traverse_obj,
    try_get,
    js_to_json
)

logger = logging.getLogger('nakedsword')


class NSAPI:

    def __init__(self):
        self.logger = logging.getLogger("NSAPI")
        self.call_lock = Lock()
        self.headers_api = {}
        self.ready = False

    def init(self, iens):
        self.iens = iens
        self.timer = ProgressTimer()
        self.get_auth()
        self.ready = True

    def logout(self):

        if self.iens._logout_api():
            self.headers_api = {}
            self.logger.info("[logout] OK")
        else:
            self.logger.info("[logout] NOK")

    @dec_retry
    def get_auth(self, **kwargs):

        with self.call_lock:

            try:
                _headers = self.iens._get_api_basic_auth()
                if _headers:
                    self.headers_api = _headers
                    self.logger.info("[get_auth] OK")
                    self.timer.reset()
                    return True
                else:
                    raise ExtractorError("couldnt auth")
            except Exception as e:
                self.logger.exception(f"[get_auth] {str(e)}")
                raise ExtractorError("error get auth")

    @dec_retry
    def get_refresh(self):

        with self.call_lock:

            try:
                if self.iens._refresh_api():
                    self.logger.info("[refresh] OK")
                    self.timer.reset()
                    return True
                else:
                    raise ExtractorError("couldnt refresh")
            except Exception as e:
                self.logger.error(f"[refresh] {str(e)}")
                raise ExtractorError("error refresh")

    def __call__(self):
        if not self.headers_api:
            self.get_auth()
            return self.headers_api

        if not self.timer.has_elapsed(50):
            return self.headers_api
        else:
            self.logger.info("[call] timeout to token refresh")
            if self.get_refresh():
                return self.headers_api


class NakedSwordBaseIE(SeleniumInfoExtractor):

    _SITE_URL = "https://www.nakedsword.com/"
    _NETRC_MACHINE = 'nakedsword'
    _LOCK = Lock()
    _TAGS = {}
    _MAXPAGE_SCENES_LIST = 2
    _APP_DATA = {}
    _API = NSAPI()
    _STATUS: str = 'NORMAL'
    _LIMITERS = {'403': limiter_5.ratelimit("nakedswordscene", delay=True), 'NORMAL': limiter_0_1.ratelimit("nakedswordscene", delay=True)}
    _JS_SCRIPT = '/Users/antoniotorres/.config/yt-dlp/nsword_getxident.js'
    _HEADERS = {"OPTIONS": {"AUTH": {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:108.0) Gecko/20100101 Firefox/108.0',
        'Accept': '*/*',
        'Accept-Language': 'en,es-ES;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'authorization,x-ident',
        'Referer': 'https://www.nakedsword.com/',
        'Origin': 'https://www.nakedsword.com',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache'
    }, "LOGOUT": {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:108.0) Gecko/20100101 Firefox/108.0',
        'Accept': '*/*',
        'Accept-Language': 'en,es-ES;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Access-Control-Request-Method': 'DELETE',
        'Access-Control-Request-Headers': 'authorization,donotrefreshtoken,x-ident',
        'Referer': 'https://www.nakedsword.com/',
        'Origin': 'https://www.nakedsword.com',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache'
    }}, "POST": {"AUTH": {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:108.0) Gecko/20100101 Firefox/108.0',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://www.nakedsword.com',
        'Connection': 'keep-alive',
        'Referer': 'https://www.nakedsword.com/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
        'Content-Length': '0',
        'TE': 'trailers',
    }}, "DELETE": {"LOGOUT": {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:108.0) Gecko/20100101 Firefox/108.0',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'doNotRefreshToken': 'true',
        'Origin': 'https://www.nakedsword.com',
        'Connection': 'keep-alive',
        'Referer': 'https://www.nakedsword.com/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
        'Content-Length': '0',
        'TE': 'trailers',
    }}, "FINAL": {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:108.0) Gecko/20100101 Firefox/108.0',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Authorization': None,
        'x-ident': None,
        'X-CSRF-TOKEN': None,
        'Origin': 'https://www.nakedsword.com',
        'Connection': 'keep-alive',
        'Referer': 'https://www.nakedsword.com/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
        'TE': 'trailers'
    }, "MPD": {
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Origin': 'https://www.nakedsword.com',
        'Connection': 'keep-alive',
        'Referer': 'https://www.nakedsword.com/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'cross-site',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
        'TE': 'trailers'
    }}

    def get_formats(self, _types, _info):

        with NakedSwordBaseIE._LIMITERS[NakedSwordBaseIE._STATUS]:

            logger.debug(f"[get_formats] {_info}")

            m3u8_url = _info.get('m3u8_url')

            formats = []

            for _type in _types:

                self.check_stop()
                try:
                    if _type == "hls":

                        m3u8_doc = try_get(self._send_request(m3u8_url, headers=NakedSwordBaseIE._HEADERS["MPD"]), lambda x: (x.content).decode('utf-8', 'replace'))
                        if not m3u8_doc:
                            raise ReExtractInfo("couldnt get m3u8 doc")

                        formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                            m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")
                        if formats_m3u8:
                            formats.extend(formats_m3u8)

                    elif _type == "dash":

                        mpd_url = m3u8_url.replace('playlist.m3u8', 'manifest.mpd')
                        _doc = try_get(self._send_request(mpd_url, headers=NakedSwordBaseIE._HEADERS["MPD"]), lambda x: (x.content).decode('utf-8', 'replace'))
                        if not _doc:
                            raise ExtractorError("couldnt get mpd doc")
                        mpd_doc = self._parse_xml(_doc, None)

                        formats_dash = self._parse_mpd_formats(mpd_doc, mpd_id="dash", mpd_url=mpd_url, mpd_base_url=(mpd_url.rsplit('/', 1))[0])
                        if formats_dash:
                            formats.extend(formats_dash)

                    elif _type == "ism":

                        ism_url = m3u8_url.replace('playlist.m3u8', 'Manifest')
                        _doc = try_get(self._send_request(ism_url, headers=NakedSwordBaseIE._HEADERS["MPD"]), lambda x: (x.content).decode('utf-8', 'replace'))
                        if _doc:
                            ism_doc = self._parse_xml(_doc, None)
                            formats_ism, _ = self._parse_ism_formats_and_subtitles(ism_doc, ism_url)
                            if formats_ism:
                                formats.extend(formats_ism)

                except ReExtractInfo:
                    raise
                except Exception as e:
                    logger.error(f"[get_formats][{_type}][{_info.get('url')}] {str(e)}")

            if not formats:
                raise ExtractorError("couldnt find any format")
            else:
                return formats

    @dec_on_exception2
    @dec_on_exception3
    @limiter_0_01.ratelimit("nakedsword", delay=True)
    def _send_request(self, url, **kwargs):

        try:
            return (self.send_http_request(url, **kwargs))
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[send_request_http] {self._get_url_print(url)}: error - {repr(e)} - {str(e)}")

    def _logout_api(self):

        self._send_request("https://ns-api.nakedsword.com/frontend/auth/logout", _type="OPTIONS", headers=self._HEADERS["OPTIONS"]["LOGOUT"])
        _headers_del = copy.deepcopy(self._HEADERS["DELETE"]["LOGOUT"])
        if (_headers := self.API_GET_HTTP_HEADERS()):
            _headers_del.update({'x-ident': _headers['x-ident'], 'Authorization': _headers['Authorization']})
            if (resdel := self._send_request("https://ns-api.nakedsword.com/frontend/auth/logout", _type="DELETE", headers=_headers_del)):
                return (resdel.status_code == 204)

    def _get_data_app(self) -> Dict:

        app_data = {'PROPERTY_ID': None, 'PASSPHRASE': None, 'GTM_ID': None, 'GTM_AUTH': None, 'GTM_PREVIEW': None}

        try:

            _app_data = self.cache.load('nakedsword', 'app_data') or {}

            if not _app_data:

                js_content = try_get(self._send_request(try_get(re.findall(r'src="(/static/js/main[^"]+)', try_get(self._send_request(self._SITE_URL), lambda z: html.unescape(z.text))), lambda x: "https://www.nakedsword.com" + x[0])), lambda y: html.unescape(y.text))
                if js_content:
                    data_js = re.findall(r'REACT_APP_([A-Z_]+:"[^"]+")', js_content)
                    data_js_str = "{" + f"{','.join(data_js)}" + "}"
                    data = json.loads(js_to_json(data_js_str))
                    if data:
                        for key in app_data:
                            app_data.update({key: data[key]})

                        self.cache.store('nakedsword', 'app_data', app_data)

            else:
                app_data = _app_data

            return app_data

        except Exception as e:
            logger.exception(str(e))
            return app_data

    def _get_api_basic_auth(self) -> Dict:

        self._send_request("https://ns-api.nakedsword.com/frontend/auth/login", _type="OPTIONS", headers=self._HEADERS["OPTIONS"]["AUTH"])
        username, pwd = self._get_login_info()
        _headers_post = copy.deepcopy(self._HEADERS["POST"]["AUTH"])
        _headers_post['Authorization'] = "Basic " + base64.urlsafe_b64encode(f"{username}:{pwd}".encode()).decode('utf-8')
        xident = subprocess.run(['node', self._JS_SCRIPT, NakedSwordBaseIE._APP_DATA['PASSPHRASE']], capture_output=True, encoding="utf-8").stdout.strip('\n')
        _headers_post['x-ident'] = xident
        token = try_get(self._send_request("https://ns-api.nakedsword.com/frontend/auth/login", _type="POST", headers=_headers_post), lambda x: traverse_obj(x.json(), ('data', 'jwt')))
        if token:
            _final = copy.deepcopy(self._HEADERS["FINAL"])
            _final.update({'x-ident': xident, 'Authorization': f'Bearer {token}', 'X-CSRF-TOKEN': token})

            return _final
        return {}

    def _refresh_api(self) -> bool:

        xident = subprocess.run(['node', self._JS_SCRIPT, NakedSwordBaseIE._APP_DATA['PASSPHRASE']], capture_output=True, encoding="utf-8").stdout.strip('\n')
        if xident:
            NakedSwordBaseIE._API.headers_api['x-ident'] = xident
            return True
        else:
            return False

    def _get_api_details(self, movieid, headers=None):
        return try_get(self._send_request(f"https://ns-api.nakedsword.com/frontend/movies/{movieid}/details", headers=headers or self.API_GET_HTTP_HEADERS()), lambda x: x.json().get('data') if x else None)

    def _get_api_newest_movies(self, pages=2):
        _list_urls = [f"https://ns-api.nakedsword.com/frontend/movies/feed?subset_sort_by=newest&subset_limit=480&page={i}&sort_by=newest" for i in range(1, pages + 1)]
        _movies_info = []
        for _url in _list_urls:
            _movies_info.extend(try_get(self._send_request(_url, headers=self.API_GET_HTTP_HEADERS()), lambda x: traverse_obj(x.json(), ('data', 'movies'), default=[]) if x else []))

        return _movies_info

    def _get_api_tags(self):

        feed = try_get(self._send_request("https://ns-api.nakedsword.com/frontend/tags/feed", headers=self.API_GET_HTTP_HEADERS()), lambda x: x.json().get('data'))
        if feed and feed.get('categories') and feed.get('sex-acts'):
            themes = [el['name'].lower().replace(' ', '-').replace(',', '-') for el in feed['categories']]
            sex_acts = [el['name'].lower().replace(' ', '-').replace(',', '-') for el in feed['sex_acts']]
            NakedSwordBaseIE._TAGS.update({'themes': themes, 'sex_acts': sex_acts})

    def _get_api_most_watched_scenes(self, query, limit=60):

        if query == 'most_watched':
            _query = ""
        else:
            _query = query + '&'
        _limit = limit or 60
        pages = int(_limit) // 30 + 1
        _list_urls = [f"https://ns-api.nakedsword.com/frontend/scenes/feed?{_query}per_page=30&subset_sort_by=most_watched&subset_limit={_limit}&page={i}&sort_by=most_watched" for i in range(1, pages + 1)]
        _scenes_info = []
        for _url in _list_urls:
            _scenes_info.extend(try_get(self._send_request(_url, headers=self.API_GET_HTTP_HEADERS()), lambda x: traverse_obj(x.json(), ('data', 'scenes'), default=[]) if x else []))

        return _scenes_info

    def _get_api_scene_urls(self, details):

        movie_id = details.get('id')
        return [f"https://ns-api.nakedsword.com/frontend/streaming/aebn/movie/{movie_id}?max_bitrate=10500&scenes_id={sc['id']}&start_time={sc['startTimeSeconds']}&duration={sc['endTimeSeconds']-sc['startTimeSeconds']}&format=HLS" for sc in details.get('scenes')]

    def get_streaming_info(self, url, **kwargs):

        premsg = f"[get_streaming_info][{url}]"
        index_scene = int_or_none(kwargs.get('index'))
        headers_api = kwargs.get('headers')

        try:

            _url_movie = try_get(self._send_request(url.split('/scene/')[0]), lambda x: str(x.url))
            movieid = NakedSwordMovieIE._match_id(_url_movie)
            details = None
            details = self._get_api_details(movieid, headers=headers_api)
            if not details:
                raise ReExtractInfo(f"{premsg} no details info")

            _urls_api = self._get_api_scene_urls(details)
            num_scenes = len(details.get('scenes'))

            if index_scene:
                _start_ind = index_scene
                _end_ind = _start_ind + 1
            else:
                _start_ind = 1
                _end_ind = num_scenes + 1

            info_scenes = []
            _urls_sc = []

            m3u8urls_scenes = []

            for ind in range(_start_ind, _end_ind):
                _urls_sc.append(f"{_url_movie}/scene/{ind}")
                _info_scene = try_get(self._send_request(_urls_api[ind - 1], headers=headers_api or self.API_GET_HTTP_HEADERS()), lambda x: x.json().get('data') if x else None)
                if _info_scene:
                    m3u8urls_scenes.append(_info_scene)

            if len(m3u8urls_scenes) != len(_urls_sc):
                logger.error(f"{premsg} number of info scenes {len(m3u8urls_scenes)} doesnt match with number of urls sc {len(_urls_sc)}\n{_urls_sc}\n\n{m3u8urls_scenes}")
                raise ReExtractInfo(f"{premsg} number of info scenes {len(m3u8urls_scenes)} doesnt match with number of urls sc {len(_urls_sc)}")

            if index_scene:
                info_scene = {'index': index_scene, 'url': _urls_sc[0], 'm3u8_url': m3u8urls_scenes[0]}
                return (info_scene, details)

            else:
                for i, (m3u8_url, _url) in enumerate(zip(m3u8urls_scenes, _urls_sc)):

                    if not m3u8_url:
                        raise ReExtractInfo(f"{premsg}[{_url}] couldnt find m3u8 url")

                    info_scenes.append({'index': i + 1, 'url': _url, 'm3u8_url': m3u8_url})

                return (info_scenes, details)

        except Exception as e:
            logger.exception(str(e))
            raise

    def _real_initialize(self):

        try:

            super()._real_initialize()

            _proxy = self._downloader.params.get('proxy')
            if _proxy:
                self.proxy = _proxy
                self._key = _proxy.split(':')[-1]
                self.logger_debug(f"proxy: [{self._key}]")

            else:
                self.proxy = None
                self._key = "noproxy"

            with NakedSwordBaseIE._LOCK:
                if not NakedSwordBaseIE._APP_DATA:
                    NakedSwordBaseIE._APP_DATA = self._get_data_app()
                if not NakedSwordBaseIE._API.ready:
                    NakedSwordBaseIE._API.init(self)

        except Exception as e:
            logger.error(repr(e))

    def API_AUTH(self):
        return NakedSwordBaseIE._API.get_auth()

    def API_REFRESH(self):
        return NakedSwordBaseIE._API.get_refresh()

    def API_LOGOUT(self):
        return NakedSwordBaseIE._API.logout()

    def API_GET_HTTP_HEADERS(self):
        return NakedSwordBaseIE._API()


class NakedSwordSceneIE(NakedSwordBaseIE):
    IE_NAME = 'nakedswordscene'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<movieid>[\d]+)/(?P<title>[^\/]+)/scene/(?P<id>[\d]+)"

    @dec_on_reextract
    def get_entry(self, url, **kwargs):

        _type = kwargs.get('_type', 'all')
        if _type == 'all':
            _types = ['hls', 'dash', 'ism']
        else:
            _types = [_type]
        msg = kwargs.get('msg')
        index_scene = try_get(kwargs.get('index') or try_get(self._match_valid_url(url).groupdict(), lambda x: x.get('id')), lambda x: int(x) if x else 1)
        premsg = f"[get_entry][{self._key}][{url}][{index_scene}]"
        if msg:
            premsg = f"{msg}{premsg}"

        try:

            self.logger_debug(f"{premsg} start to get entry")
            _url_movie = try_get(self._send_request(url.split('/scene/')[0]), lambda x: str(x.url))
            _info, details = self.get_streaming_info(_url_movie, index=index_scene)

            _title = f"{sanitize_filename(details.get('title'), restricted=True)}_scene_{index_scene}"
            scene_id = traverse_obj(details, ('scenes', int(index_scene) - 1, 'id'))

            formats = self.get_formats(_types, _info)

            if formats:

                _entry = {
                    "id": str(scene_id),
                    "title": _title,
                    "formats": formats,
                    "ext": "mp4",
                    "webpage_url": url,
                    "extractor_key": 'NakedSwordScene',
                    "extractor": 'nakedswordscene'
                }

                self.logger_debug(f"{premsg}: OK got entr {_entry}")
                return _entry

            else:
                raise ExtractorError(f'{premsg}: error - no formats')

        except ReExtractInfo as e:
            logger.error(f"[get_entries][{url} {str(e)}")

            raise
        except (StatusStop, ExtractorError):
            raise
        except Exception as e:
            logger.exception(repr(e))
            raise ExtractorError(f'{premsg}: error - {repr(e)}')

    def _real_extract(self, url):

        try:
            self.report_extraction(url)
            nscene = int(self._match_id(url))
            return self.get_entry(url, index=nscene, _type="hls")

        except (ExtractorError, StatusStop):
            raise
        except ReExtractInfo as e:
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')


class NakedSwordMovieIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:movie:playlist'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<id>[\d]+)/(?P<title>[^/?#&]+)"
    _MOVIES_URL = "https://www.nakedsword.com/movies/"

    @dec_on_reextract
    def get_entries(self, url, **kwargs):
        _type = kwargs.get('_type', 'all')
        if _type == 'all':
            _types = ['hls', 'dash', 'ism']
        else:
            _types = [_type]
        msg = kwargs.get('msg')
        premsg = f"[get_entries][{self._key}]"
        if msg:
            premsg = f"{msg}{premsg}"

        _force_list = kwargs.get('force', False)

        self.report_extraction(url)

        _url_movie = try_get(self._send_request(url), lambda x: str(x.url))

        if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

            info_streaming_scenes, details = self.get_streaming_info(_url_movie)

            _entries = []

            sublist = []
            if hasattr(self, 'args_ie'):
                sublist = traverse_obj(self.args_ie, ('nakedswordmovie', 'listreset'), default=[])

            logger.info(f"{premsg} sublist of movie scenes: {sublist}")

            _raise_reextract = []

            for _info in info_streaming_scenes:

                try:
                    i = _info.get('index')

                    self.logger_debug(f"{premsg}[{i}]:\n{_info}")

                    _title = f"{sanitize_filename(details.get('title'), restricted=True)}_scene_{i}"
                    scene_id = traverse_obj(details, ('scenes', i - 1, 'id'))

                    _entry = {
                        "id": str(scene_id),
                        "title": _title,
                        "formats": [],
                        "ext": "mp4",
                        "webpage_url": _info.get('url'),
                        "original": url,
                        "extractor_key": 'NakedSwordScene',
                        "extractor": 'nakedswordscene'
                    }

                    if not sublist or i in sublist:

                        try:
                            formats = self.get_formats(_types, _info)
                            if formats:
                                _entry.update({'formats': formats})
                                self.logger_debug(f"{premsg}[{i}][{_info.get('url')}]: OK got entry")
                                _entries.append(_entry)
                        except ReExtractInfo:
                            _raise_reextract.append(i)

                    else:
                        _entries.append(_entry)

                except ReExtractInfo:
                    raise
                except Exception as e:
                    logger.exception(f"{premsg}[{i}]: info streaming\n{_info} error - {str(e)}")
                    raise

            if _raise_reextract:
                logger.info(f"{premsg} ERROR to get format {_raise_reextract} from sublist of movie scenes: {sublist}")
                self.API_LOGOUT()
                self.API_AUTH()
                raise ReExtractInfo("error in scenes of movie")

            else:
                logger.info(f"{premsg} OK format for sublist of movie scenes: {sublist}")

            if _force_list:
                return _entries
            else:
                playlist_id = str(details.get('id'))
                pl_title = sanitize_filename(details.get('title'), restricted=True)
                return self.playlist_result(_entries, playlist_id=playlist_id, playlist_title=pl_title)

        else:
            details = self._get_api_details(self._match_id(_url_movie))
            if _force_list:
                return [self.url_result(f"{_url_movie.strip('/')}/scene/{x['index']}", ie=NakedSwordSceneIE) for x in traverse_obj(details, 'scenes')]
            else:
                playlist_id = str(details.get('id'))
                pl_title = sanitize_filename(details.get('title'), restricted=True)
                return self.playlist_from_matches(
                    traverse_obj(details, 'scenes'),
                    getter=lambda x: f"{_url_movie.strip('/')}/scene/{x['index']}",
                    ie=NakedSwordSceneIE, playlist_id=playlist_id, playlist_title=pl_title)

    def _real_extract(self, url):

        try:
            return self.get_entries(url, _type="hls")
        except (ExtractorError, StatusStop):
            raise
        except ReExtractInfo as e:
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')


class NakedSwordScenesPlaylistIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:scenes:playlist'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/(?:((studios|stars)/(?P<id>[\d]+)/(?P<name>[^/?#&]+))|(tag/(?P<tagname>[^/?#&]+))|most-watched)(\?limit=(?P<limit>\d+))?"

    @dec_on_reextract
    def get_entries_from_scenes_list(self, url, **kwargs):

        _type = kwargs.get('_type', 'hls')
        msg = kwargs.get('msg')
        premsg = f"[get_entries][{self._key}]"
        if msg:
            premsg = f"{msg}{premsg}"

        try:

            info_url = self._match_valid_url(url).groupdict()

            _tagname = info_url.get('tagname')
            if _tagname:
                with NakedSwordBaseIE._LOCK:
                    if not NakedSwordBaseIE._TAGS:
                        self._get_api_tags()
                _tagname = _tagname.lower().replace(' ', '-').replace(',', '-')
                if _tagname in (NakedSwordBaseIE._TAGS['themes'] + NakedSwordBaseIE._TAGS['sex_acts']):
                    query = f'tags_name={_tagname}'

            elif _id := info_url.get('id'):
                if '/stars/' in url:
                    query = f'stars_id={_id}'
                elif '/studios/' in url:
                    query = f'studios_id={_id}'

            elif 'most-watched' in url:
                query = "most_watched"

            limit = info_url.get('limit')

            _scenes = self._get_api_most_watched_scenes(query, limit=limit)

            def _getter(movie_id, index):
                _movie_url = try_get(self._send_request(f"https://www.nakedsword.com/movies/{movie_id}/_"), lambda x: str(x.url))
                return f'{_movie_url}/scene/{index}'

            _info_scenes = [(_getter(sc['movie']['id'], sc['index']), int(sc['index'])) for sc in _scenes]

            self.logger_debug(f"{premsg} url scenes [{len(_info_scenes)}]\n{_info_scenes}")

            if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

                isc = self._get_extractor('NakedSwordScene')

                _entries = []
                with ThreadPoolExecutor(thread_name_prefix='nsmostwatch') as ex:
                    futures = {ex.submit(isc.get_entry, _info[0], index=_info[1], _type=_type): _info[0] for _info in _info_scenes}

                for fut in futures:
                    if _res := fut.result():
                        _res.update({'original_url': url})
                        _entries.append(_res)

                return self.playlist_result(_entries, playlist_id=query, playlist_title="Search")

            else:
                return self.playlist_from_matches(
                    _info_scenes,
                    getter=lambda x: x[0],
                    ie=NakedSwordMovieIE, playlist_id=query, playlist_title="Search")

        except Exception as e:
            logger.exception(f"{premsg} {str(e)}")
            raise

    def _real_extract(self, url):

        try:
            self.report_extraction(url)
            return self.get_entries_from_scenes_list(url, _type="hls")
        except (ExtractorError, StatusStop):
            raise
        except ReExtractInfo as e:
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')


class NakedSwordJustAddedMoviesPlaylistIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:justaddedmovies:playlist'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/just-added(\?(?P<query>.+))?"

    def get_entries_from_movies_list(self, url, **kwargs):

        premsg = f"[get_entries][{url}]"
        msg = kwargs.get('msg')
        if msg:
            premsg = f"{msg}{premsg}"

        try:

            _movies = sorted(self._get_api_newest_movies(), key=lambda x: datetime.fromisoformat(extract_timezone(x.get('publish_start'))[1]))

            _query = self._match_valid_url(url).groupdict().get('query')
            if _query:
                _params = {el.split('=')[0]: el.split('=')[1] for el in _query.split('&') if el.count('=') == 1}
            else:
                _params = {}
                _query = "noquery"
            if _f := _params.get('from'):
                _from = datetime.fromisoformat(f'{_f}T00:00:00.000001')
            else:
                _from = try_get(_movies[0].get('publish_start'), lambda x: datetime.fromisoformat(extract_timezone(x)[1]))
            _t = _params.get('to')
            if _t:
                _to = datetime.fromisoformat(f'{_t}T23:59:59.999999')
            else:
                _to = try_get(_movies[-1].get('publish_start'), lambda x: datetime.fromisoformat(extract_timezone(x)[1]))

            self.logger_debug(f"{premsg} from {str(_from)} to {str(_to)}")

            _movies_filtered = [_mov for _mov in _movies if _from <= datetime.fromisoformat(extract_timezone(_mov.get('publish_start'))[1]) <= _to]

            _url_movies = list(set([try_get(self._send_request(_url), lambda x: str(x.url)) for _url in [f'https://www.nakedsword.com/movies/{x["id"]}/_' for x in _movies_filtered]]))

            self.logger_debug(f"{premsg} url movies [{len(_url_movies)}]\n{_url_movies}")

            if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

                imov = self._get_extractor('NakedSwordMovie')

                _entries = []
                with ThreadPoolExecutor(thread_name_prefix='nsnewest') as ex:
                    futures = {ex.submit(imov.get_entries, _url, _type="hls", force=True): _url for _url in _url_movies}

                for fut in futures:
                    _res = fut.result()
                    if _res:
                        _entries += [_r for _r in _res if not _r.update({'original_url': url})]

                return self.playlist_result(_entries, playlist_id=f'{sanitize_filename(_query, restricted=True)}', playlist_title="Search")

            else:
                return self.playlist_from_matches(
                    _url_movies,
                    getter=lambda x: x,
                    ie=NakedSwordMovieIE, playlist_id=f'{sanitize_filename(_query, restricted=True)}', playlist_title="Search")

        except Exception as e:
            logger.exception(f"{premsg} {str(e)}")
            raise

    def _real_extract(self, url):

        try:
            self.report_extraction(url)
            return self.get_entries_from_movies_list(url)
        except (ExtractorError, StatusStop):
            raise
        except ReExtractInfo as e:
            raise ExtractorError(str(e))
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')
