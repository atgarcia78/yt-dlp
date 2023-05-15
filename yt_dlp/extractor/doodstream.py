import html
import json
import random
import re
import string
import sys
import time
import traceback
from hashlib import sha256
from typing import cast

from .commonwebdriver import (
    ConnectError,
    ExtractorError,
    HTTPStatusError,
    LimitContextDecorator,
    ReExtractInfo,
    SeleniumInfoExtractor,
    dec_on_exception3,
    limiter_0_1,
    my_dec_on_exception,
)
from ..utils import (
    get_domain,
    js_to_json,
    sanitize_filename,
    sanitize_url,
    try_get,
)

on_exception_vinfo = my_dec_on_exception(
    (TimeoutError, ExtractorError), raise_on_giveup=False, max_tries=5, jitter="my_jitter", interval=1)

on_retry_vinfo = my_dec_on_exception(
    ReExtractInfo, raise_on_giveup=False, max_tries=5, jitter="my_jitter", interval=1)


class DoodStreamIE(SeleniumInfoExtractor):

    IE_NAME = 'doodstream'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?d(oo)+d(?:stream)?\.[^/]+/[ed]/(?P<id>[a-z0-9]+)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(?:www\.)?d(oo)*d(?:stream)?\.[^/]+/[ed]/[a-z0-9]+)\1']
    _SITE_URL = 'https://dood.to/'

    _TESTS = [{
        'url': 'http://dood.to/e/5s1wmbdacezb',
        'md5': '4568b83b31e13242b3f1ff96c55f0595',
        'info_dict': {
            'id': '5s1wmbdacezb',
            'ext': 'mp4',
            'title': 'Kat Wonders - Monthly May 2020',
            'description': 'Kat Wonders - Monthly May 2020 | DoodStream.com',
            'thumbnail': 'https://img.doodcdn.com/snaps/flyus84qgl2fsk4g.jpg',
        }
    }, {
        'url': 'http://dood.watch/d/5s1wmbdacezb',
        'md5': '4568b83b31e13242b3f1ff96c55f0595',
        'info_dict': {
            'id': '5s1wmbdacezb',
            'ext': 'mp4',
            'title': 'Kat Wonders - Monthly May 2020',
            'description': 'Kat Wonders - Monthly May 2020 | DoodStream.com',
            'thumbnail': 'https://img.doodcdn.com/snaps/flyus84qgl2fsk4g.jpg',
        }
    }, {
        'url': 'https://dood.to/d/jzrxn12t2s7n',
        'md5': '3207e199426eca7c2aa23c2872e6728a',
        'info_dict': {
            'id': 'jzrxn12t2s7n',
            'ext': 'mp4',
            'title': 'Stacy Cruz Cute ALLWAYSWELL',
            'description': 'Stacy Cruz Cute ALLWAYSWELL | DoodStream.com',
            'thumbnail': 'https://img.doodcdn.com/snaps/8edqd5nppkac3x8u.jpg',
        }
    }]

    @on_exception_vinfo
    def _get_video_info(self, url, **kwargs):

        msg = kwargs.get('msg')
        pre = f'[get_video_info][{self._get_url_print(url)}]'
        if msg:
            pre = f'{msg}{pre}'

        _headers = kwargs.get('headers', {})
        headers = {'Range': 'bytes=0-', 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}

        headers.update(_headers)

        limiter = cast(LimitContextDecorator, DoodStreamIE.IE_LIMITER)
        with limiter:
            try:
                return self.get_info_for_format(url, headers=headers)
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"{pre}: error - {repr(e)}")
            except ReExtractInfo as e:
                self.report_warning(f"{pre}: error - {repr(e)}, will retry")
                raise

    @dec_on_exception3
    @limiter_0_1.ratelimit("doodstream2", delay=True)
    def _send_request(self, url, **kwargs):

        _kwargs = kwargs.copy()
        pre = f'[send_req][{self._get_url_print(url)}]'
        if (msg := _kwargs.pop('msg', None)):
            pre = f'{msg}{pre}'

        try:
            return self.send_http_request(url, **_kwargs)
        except (HTTPStatusError, ConnectError) as e:
            _msg_error = f"{repr(e)}"
            self.logger_debug(f"{pre}: {_msg_error}")

    def _get_metadata(self, url):
        video_id = self._match_id(url)
        url = f'https://dood.to/e/{video_id}'
        webpage = try_get(self._send_request(url), lambda x: html.unescape(x.text))
        if not webpage or '<title>Video not found' in webpage:
            raise ExtractorError("error 404 no webpage")

        title = self._html_search_meta(('og:title', 'twitter:title'), webpage, default=None)
        if not title:
            title = try_get(self._html_extract_title(webpage, default=None), lambda x: x.replace(' - DoodStream', ''))
        if not title or not isinstance(title, str):
            raise ExtractorError("error with title")

        mobj = re.findall(r'(1080p|720p|480p)', title)
        if mobj:
            title = title.split(mobj[0])[0]

        title = re.sub(r'(\s*-\s*202)', ' 202', title)

        return {'id': str(int(sha256(video_id.encode('utf-8')).hexdigest(), 16) % 10**12) if len(video_id) > 12 else video_id,
                'title': sanitize_filename(title.replace('mp4', '').replace('mkv', '').strip().strip('-'), restricted=True)}

    @on_retry_vinfo
    def _get_entry(self, url, check=False, msg=None):

        video_id = cast(str, self._match_id(url))
        url = f'https://dood.to/e/{video_id}'
        pre = f'[get_entry][{self._get_url_print(url)}]'
        if msg:
            pre = f'{msg}{pre}'
        webpage = try_get(self._send_request(url), lambda x: html.unescape(x.text))
        if not webpage or '<title>Video not found' in webpage:
            raise ExtractorError("error 404 no webpage")
        title = self._html_search_meta(('og:title', 'twitter:title'), webpage, default=None)
        if not title:
            title = try_get(self._html_extract_title(webpage, default=None), lambda x: x.replace(' - DoodStream', ''))
        if not title or not isinstance(title, str):
            raise ExtractorError("error with title")

        mobj = re.findall(r'(1080p|720p|480p)', title)
        if mobj:
            title = title.split(mobj[0])[0]
        title = re.sub(r'(\s*-\s*202)', ' 202', title)
        title = title.replace('mp4', '').replace('mkv', '').strip(' \t\n\r\f\v-_')

        token = self._html_search_regex(r"[?&]token=([a-z0-9]+)[&']", webpage, 'token')

        headers = {'Referer': self._SITE_URL}

        pass_md5 = self._html_search_regex(r"(/pass_md5.*?)'", webpage, 'pass_md5')
        video_url = ''.join((try_get(self._send_request(f'https://dood.to{pass_md5}', headers=headers), lambda x: html.unescape(x.text)),  # type: ignore
                            *(random.choice(string.ascii_letters + string.digits) for _ in range(10)),
                            f'?token={token}&expiry={int(time.time() * 1000)}'))
        if not video_url:
            raise ExtractorError("couldnt get videourl")

        _format = {
            'format_id': 'http-mp4',
            'url': video_url,
            'http_headers': headers,
            'ext': 'mp4'
        }

        if check:
            _host = get_domain(video_url)
            _sem = self.get_ytdl_sem(_host)

            with _sem:
                _videoinfo = self._get_video_info(video_url, msg=pre, headers=headers)

            if not _videoinfo:
                raise ExtractorError("error 404: no video info")
            if _videoinfo and _videoinfo['filesize'] > 20:

                _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize'], 'accept_ranges': _videoinfo['accept_ranges']})
            else:
                raise ExtractorError(f"error filesize[{_videoinfo['filesize']}] < 20 bytes")

        _subtitles = {}
        list_subts = [subt for subt in [
            json.loads(js_to_json(el)) for el in re.findall(r'addRemoteTextTrack\((\{[^\}]+\})', webpage)]
            if subt.get('label', '').lower() in ('spanish', 'english')]

        if list_subts:

            def _get_info_subt(subt):
                _cc_lang = {'spanish': 'es', 'english': 'en'}
                if subt:
                    ext = subt.get('src').rsplit('.', 1)[-1]
                    lang = _cc_lang.get(subt.get('label').lower())
                    if lang:
                        return {'lang': lang, 'ext': ext, 'url': sanitize_url(subt.get('src'), scheme='https')}

            for _subt in list_subts:
                _subtinfo = _get_info_subt(_subt)
                if not _subtinfo:
                    continue
                _subtitles.setdefault(_subtinfo.get('lang'), []).append({'url': _subtinfo.get('url'), 'ext': _subtinfo.get('ext')})

        _entry = {
            'id': str(int(sha256(video_id.encode('utf-8')).hexdigest(), 16) % 10**12) if len(video_id) > 12 else video_id,
            'title': sanitize_filename(title, restricted=True),
            'formats': [_format],
            'subtitles': _subtitles,
            'ext': 'mp4',
            'extractor_key': 'DoodStream',
            'extractor': 'doodstream',
            'webpage_url': url
        }

        return _entry

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        try:

            if not self.get_param('embed'):
                _check = True
            else:
                _check = False

            return self._get_entry(url, check=_check)

        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.report_warning(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
