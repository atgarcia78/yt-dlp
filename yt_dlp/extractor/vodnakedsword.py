import html
import json
import logging
import re
from threading import Lock

from .commonwebdriver import (
    ConnectError,
    HTTPStatusError,
    ReExtractInfo,
    Response,
    SeleniumInfoExtractor,
    dec_on_driver_timeout,
    dec_on_exception3,
    limiter_0_1,
    my_dec_on_exception,
    raise_extractor_error,
)
from ..utils import (
    get_element_html_by_id,
    get_element_text_and_html_by_tag,
    sanitize_filename,
    traverse_obj,
    try_get,
)

logger = logging.getLogger('vodnakedsword')

dec_on_reextract = my_dec_on_exception(
    ReExtractInfo, max_time=300, jitter='my_jitter', raise_on_giveup=True, interval=30)

dec_on_reextract_1 = my_dec_on_exception(
    ReExtractInfo, max_time=300, jitter='my_jitter', raise_on_giveup=True, interval=1)

dec_on_reextract_3 = my_dec_on_exception(
    ReExtractInfo, max_tries=3, jitter='my_jitter', raise_on_giveup=True, interval=2)


class VODNakedSwordBaseIE(SeleniumInfoExtractor):
    _SITE_URL = "https://vod.nakedsword.com/gay"
    _LOGIN_URL = "https://vod.nakedsword.com/gay/login?f=%2Fgay"
    _POST_URL = "https://vod.nakedsword.com/gay/deliver"
    _NETRC_MACHINE = 'vodnakedsword'

    _LOCK = Lock()
    _COOKIES = []
    _NSINIT = False

    headers_post = {
        'Accept': '*/*',
        'Accept-Language': 'en,es-ES;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Origin': 'https://vod.nakedsword.com',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'TE': 'trailers',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
    }

    data_post = {
        'movieId': None,
        'sceneId': None,
        'embedHLS': 'true',
        'consumptionRate': '1',
        'popoutTitle': 'Watching',
        'format': 'HLS',
        'maxBitrate': '100000',
        'trickPlayImgPrefix': 'https://pic.aebn.net/dis/t/',
        'isEmbedded': 'false',
        'popoutHtmlUrl': '/resources/unified-player/player/fullframe.html',
    }

    @classmethod
    @dec_on_driver_timeout
    @dec_on_exception3
    @limiter_0_1.ratelimit("nakedsword", delay=True)
    def _send_request(cls, url, **kwargs) -> None | Response:

        pre = f'[send_request][{cls._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'

        driver = kwargs.get('driver', None)

        if driver:
            driver.get(url)
        else:
            try:
                return (cls._send_http_request(url, client=VODNakedSwordBaseIE._CLIENT, **kwargs))
            except (HTTPStatusError, ConnectError) as e:
                logger.warning(f"[send_request_http] {cls._get_url_print(url)}: error - {repr(e)} - {str(e)}")

    def _get_api_info(self, url, movieid, sceneid=None):
        def data_upt():
            data_copy = VODNakedSwordBaseIE.data_post.copy()
            data_copy['movieId'] = movieid
            if not sceneid:
                data_copy.pop('sceneId')
            else:
                data_copy['sceneid'] = sceneid
            return data_copy
        params = {
            'movieId': '282670',
            'isPreview': 'false'
        }
        if sceneid:
            params['sceneId'] = sceneid

        check = try_get(
            VODNakedSwordBaseIE._send_request(
                'https://vod.nakedsword.com/gay/play-check', _type="POST",
                headers=VODNakedSwordBaseIE.headers_post | {'Referer': url.split('#')[0]}, data=params),
            lambda x: x.json() if x else None)

        if check == "can play":
            return try_get(
                VODNakedSwordBaseIE._send_request(
                    VODNakedSwordBaseIE._POST_URL, _type="POST",
                    headers=VODNakedSwordBaseIE.headers_post | {'Referer': url.split('#')[0]}, data=data_upt()),
                lambda x: x.json() if x else None)

    def _login(self):
        pass

    def _real_initialize(self):

        super()._real_initialize()

        with VODNakedSwordBaseIE._LOCK:
            if not VODNakedSwordBaseIE._NSINIT:
                VODNakedSwordBaseIE._CLIENT = self._CLIENT
                if not VODNakedSwordBaseIE._COOKIES:
                    try:
                        with open("/Users/antoniotorres/Projects/common/logs/VODNSWORD_COOKIES.json", "r") as f:
                            VODNakedSwordBaseIE._COOKIES = json.load(f)

                    except Exception as e:
                        self.to_screen(f"{repr(e)}")
                        raise

                for cookie in VODNakedSwordBaseIE._COOKIES:
                    VODNakedSwordBaseIE._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])

                VODNakedSwordBaseIE._NSINIT = True


class VODNakedSwordSceneIE(VODNakedSwordBaseIE):
    IE_NAME = 'vodnakedsword:scene'  # type: ignore
    _VALID_URL = r"https?://(?:www\.)?vod.nakedsword.com/gay/movies/(?P<movieid>[\d]+)(/(?P<title>[a-zA-Z\d_-]+))?#scene-(?P<sceneid>[\d]+)"

    def _real_initialize(self):
        return super()._real_initialize()

    def _real_extract(self, url):
        movieid, sceneid = try_get(self._match_valid_url(url), lambda x: x.group('movieid', 'sceneid') if x else (None, None))  # type: ignore
        webpage = try_get(self._send_request(url), lambda x: html.unescape(re.sub('[\t\n]', '', x.text)))
        _scene_str = try_get(re.search(r'(Scene\s+\d+)', get_element_html_by_id(f'scene-{sceneid}', webpage), flags=re.I), lambda x: x.group() if x else "scene")  # type: ignore
        _title = try_get(re.search(r'(?P<san_title>[^<]+)<?', traverse_obj(get_element_text_and_html_by_tag('h1', webpage), 0)),  # type: ignore
                         lambda x: try_get(x.group('san_title'), lambda y: y.strip()) if x else None)
        _info_streaming = self._get_api_info(url, movieid, sceneid=sceneid)
        _headers = {'Referer': url.split('#')[0], 'Origin': 'https://vod.nakedsword.com'}
        _formats, _subtitles = self._extract_m3u8_formats_and_subtitles(_info_streaming['url'], sceneid, ext="mp4", entry_protocol="m3u8_native", headers=_headers)

        if not _formats:
            raise_extractor_error('Couldnt get video formats')

        for _format in _formats:
            if (_head := _format.get('http_headers')):
                _head.update(_headers)
            else:
                _format.update({'http_headers': _headers})

        _entry = {
            'id': sceneid,
            'title': sanitize_filename(f'{_title}_{_scene_str}'.replace('-', '_'), restricted=True),
            'formats': _formats,
            'subtitles': _subtitles,
            'ext': 'mp4',
            'extractor_key': self._get_ie_key(),
            'extractor': self.IE_NAME,
            'webpage_url': url}

        try:
            _entry.update({'duration': self._extract_m3u8_vod_duration(_formats[0]['url'], sceneid, headers=_formats[0].get('http_headers', {}))})
        except Exception as e:
            self.logger_info(f"error trying to get vod {repr(e)}")

        return _entry
