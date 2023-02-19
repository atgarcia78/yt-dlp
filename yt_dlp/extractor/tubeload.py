import html
import re
from urllib.parse import unquote
import subprocess
import logging
from concurrent.futures import ThreadPoolExecutor

from .commonwebdriver import (
    ConnectError,
    HTTPStatusError,
    Lock,
    SeleniumInfoExtractor,
    dec_on_exception2,
    dec_on_exception3,
    limiter_0_1,
    limiter_non,
    my_dec_on_exception,
    Tuple
)
from ..utils import (
    ExtractorError,
    get_domain,
    sanitize_filename,
    try_get,
)


on_exception_vinfo = my_dec_on_exception(
    (TimeoutError, ExtractorError), raise_on_giveup=False, max_tries=2, interval=0.1)


class BaseloadIE(SeleniumInfoExtractor):

    _LOCK = Lock()
    _MAINJS = ""
    _SITE_URL = ""
    _JS_SCRIPT = {
        "deofus": "/Users/antoniotorres/.config/yt-dlp/tubeload_deofus.js",
        "getvurl": "/Users/antoniotorres/.config/yt-dlp/tubeload_getvurl.js"}

    @on_exception_vinfo
    @dec_on_exception2
    def _get_video_info(self, url, **kwargs):

        pre = f'[get_video_info][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'

        with limiter_0_1.ratelimit(self.IE_NAME, delay=True):
            _headers = {
                'Range': 'bytes=0-',
                'Referer': self._SITE_URL + "/",
                'Origin': self._SITE_URL,
                'Sec-Fetch-Dest': 'video',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'cross-site',
                'Pragma': 'no-cache',
                'Cache-Control': 'no-cache'}
            try:
                return self.get_info_for_format(url, headers=_headers)
            except (HTTPStatusError, ConnectError) as e:
                self.logger.debug(f"{pre}: inner error sin raise - {repr(e)}")

    @dec_on_exception3
    @dec_on_exception2
    def _send_request(self, url, **kwargs):

        headers = kwargs.get('headers', None)
        max_limit = kwargs.get('max_limit', None)
        pre = f'[send_req][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'

        with limiter_non.ratelimit(f'{self.IE_NAME}2', delay=True):

            self.logger.debug(f"{pre}: start")

            try:
                if not max_limit:
                    return self.send_http_request(url, headers=headers)
                else:
                    return self.stream_http_request(url, truncate='</script><style>', headers=headers)
            except (HTTPStatusError, ConnectError) as e:
                self.logger.warning(f"{pre}: error - {repr(e)}")

    def _get_args(self, webpage, _all=False):

        def getter(x):
            if not x:
                return
            _res = []
            for el in x:
                _args = el.split(',')
                if len(_args) != 6:
                    return
                for i in range(len(_args)):
                    if _args[i].isdecimal():
                        _args[i] = int(_args[i])
                    else:
                        _args[i] = _args[i].strip('"')
                if not _all:
                    return _args
                else:
                    _res.append(_args)
            return _res

        args = try_get(
            re.findall(r'var .+eval\(.+decodeURIComponent\(escape\(r\)\)\}\(([^\)]+)\)', webpage),
            lambda x: getter(x))
        return args

    def get_mainjs(self, url):
        _headers_mainjs = {
            'Referer': url,
            'Sec-Fetch-Dest': 'script',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'same-origin',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
        }

        return (try_get(self._send_request(self._MAINJS, headers=_headers_mainjs), lambda x: x.text))

    def _getres0(self, _url) -> str:
        if (mainjs := self.get_mainjs(_url)) and (argsjs := self._get_args(mainjs)):
            cmd0 = f"node {self._JS_SCRIPT['deofus']} " + " ".join([str(el) for el in argsjs])
            res0 = subprocess.run(cmd0.split(' '), capture_output=True, encoding="utf-8").stdout.strip('\n')
            if res0:
                self.cache.store(self.IE_NAME, f'{self._key}res0', res0)
                return res0
            else:
                raise ExtractorError("couldnt get res0")

        else:
            raise ExtractorError("couldnt get res0")

    def _getinfofromwebpage(self, _url, webpage, max_limit, pre) -> Tuple[str, str]:
        _args = None
        title = None
        if not webpage:
            webpage = try_get(
                self._send_request(_url, max_limit=max_limit),
                lambda x: html.unescape(x) if isinstance(x, str) else html.unescape(x.text))
            if not webpage or '<title>404' in webpage:
                raise ExtractorError("error 404 no webpage")
            self.logger.debug(f'{pre} size webpage dl: {len(webpage)}')

        _title = try_get(
            self._html_extract_title(webpage),
            lambda x: x.replace('.mp4', '').strip('[_,-, ]') if x else None)
        if not _title:
            raise ExtractorError("error no title")
        else:
            title = re.sub(r'(?i)((at )?%s$)' % get_domain(_url), '', _title)
            _args = self._get_args(webpage)
            if not _args:
                raise ExtractorError("error extracting video args")
            cmd1 = f"node {self._JS_SCRIPT['deofus']} " + " ".join([str(el) for el in _args])
            return (subprocess.run(cmd1.split(' '), capture_output=True, encoding="utf-8").stdout.strip('\n'), title)

    def _get_entry(self, url, **kwargs):

        check = kwargs.get('check')
        webpage = kwargs.get('webpage', None)
        max_limit = kwargs.get('max_limit', True)
        pre = f'[get_entry][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'
        videoid = self._match_id(url)
        _url = f"{self._SITE_URL}/e/{videoid}"

        res0 = None
        res1 = None
        title = None

        try:
            res0 = self.cache.load(self.IE_NAME, f'{self._key}res0')
            if not res0:
                with ThreadPoolExecutor(thread_name_prefix="tload") as exe:
                    futures = {
                        exe.submit(self._getinfofromwebpage, _url, webpage, max_limit, pre): 'infowebpage',
                        exe.submit(self._getres0, _url): 'res0'}

                for fut in futures:
                    if (res := fut.result()):
                        if isinstance(res, tuple):
                            res1, title = res
                        else:
                            res0 = res

            else:

                res1, title = self._getinfofromwebpage(_url, webpage, max_limit, pre)

            if not res0 or not res1:
                raise ExtractorError(f"error in res0[{not res0}] or res1[{not res1}]")
            else:
                video_url = subprocess.run(
                    ['node', self._JS_SCRIPT['getvurl'], res0, res1],
                    capture_output=True, encoding="utf-8").stdout.strip('\n')

                _format = {
                    'format_id': 'http-mp4',
                    'url': unquote(video_url),
                    'http_headers': {'Referer': f'{self._SITE_URL}/', 'Origin': self._SITE_URL},
                    'ext': 'mp4'
                }

                if check:
                    _host = get_domain(video_url)

                    _sem = self.get_ytdl_sem(_host)

                    with _sem:
                        _videoinfo = self._get_video_info(video_url, msg=pre)
                    if not _videoinfo:
                        raise ExtractorError("error 404: no video info")
                    else:
                        _format.update({
                            'url': _videoinfo['url'],
                            'filesize': _videoinfo['filesize'],
                            'accept_ranges': _videoinfo['accept_ranges']})

                _entry_video = {
                    'id': videoid,
                    'title': sanitize_filename(title, restricted=True),
                    'formats': [_format],
                    'extractor_key': self.ie_key(),
                    'extractor': self.IE_NAME,
                    'ext': 'mp4',
                    'webpage_url': url
                }

                return _entry_video

        except Exception as e:
            self.logger.debug(f"{pre} error {repr(e)} - {str(e)}")
            raise

    def _real_initialize(self):

        super()._real_initialize()
        self.logger = logging.getLogger(self.IE_NAME)

        _proxy = try_get(self.get_param('proxy'), lambda x: int(x.split(':')[-1]))
        if not _proxy or not self.get_param('routing_table'):
            self._key = self.get_ip_origin()
        else:
            self._key = try_get(self.get_param('routing_table'), lambda x: x.get(_proxy))

    def _real_extract(self, url):

        self.report_extraction(url)

        try:

            # if not self.get_param('embed'): _check = True
            # else: _check = False
            _check = True

            return self._get_entry(url, check=_check)

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))


class TubeloadIE(BaseloadIE):

    IE_NAME = 'tubeload'  # type: ignore
    _SITE_URL = "https://tubeload.co"
    _VALID_URL = r'https?://(?:www\.)?tubeload.co/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?tubeload\.co/e/.+?)\1']
    _MAINJS = 'https://tubeload.co/assets/js/main.min.js'
    _DOMAIN = 'tubeload.co'


class RedloadIE(BaseloadIE):

    _SITE_URL = "https://redload.co"
    IE_NAME = 'redload'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?redload.co/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?redload\.co/e/.+?)\1']
    _MAINJS = 'https://redload.co/assets/js/main.min.js'
    _DOMAIN = 'redload.co'


class HighloadIE(BaseloadIE):

    _SITE_URL = "https://highload.to"
    IE_NAME = 'highload'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?highload.to/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?highload\.to/e/.+?)\1']
    _MAINJS = 'https://highload.to/assets/js/master.js'
    _DOMAIN = 'highload.co'


class EmbedoIE(BaseloadIE):

    _SITE_URL = "https://embedo.co"
    IE_NAME = 'embedo'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?embedo.co/e/(?P<id>[^\/$]+)(?:\/|$)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?embedo\.co/e/.+?)\1']
    _MAINJS = 'https://embedo.co/assets/js/master.js'
    _DOMAIN = 'embedo.co'
