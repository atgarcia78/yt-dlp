import html
import json
import random
import re
import string
import time
from hashlib import sha256
from typing import cast

from .commonwebdriver import (
    ConnectError,
    ExtractorError,
    HTTPStatusError,
    ReExtractInfo,
    SeleniumInfoExtractor,
    dec_on_exception3,
    limiter_0_1,
    my_dec_on_exception,
    raise_extractor_error,
    raise_reextract_info,
)
from ..utils import get_domain, js_to_json, sanitize_url, try_get

on_exception_vinfo = my_dec_on_exception(
    (TimeoutError, ExtractorError), raise_on_giveup=False, max_tries=5, jitter="my_jitter", interval=1)

on_retry_vinfo = my_dec_on_exception(
    ReExtractInfo, raise_on_giveup=False, max_tries=10, jitter="my_jitter", interval=1)


class DoodStreamIE(SeleniumInfoExtractor):

    IE_NAME = 'doodstream'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?(?:ds2play|(d(oo)+d(?:s|stream)?))\.[^/]+/[ed]/(?P<id>[a-z0-9]+)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(?:www\.)?(?:ds2play|(d(oo)+d(?:s|stream)?))\.[^/]+/[ed]/(?P<id>[a-z0-9]+))\1']

    @on_exception_vinfo
    @limiter_0_1.ratelimit("doodstream", delay=True)
    def _get_video_info(self, url, **kwargs) -> dict:

        msg = kwargs.get('msg')
        pre = f'[get_video_info][{self._get_url_print(url)}]'
        if msg:
            pre = f'{msg}{pre}'

        _headers = kwargs.get('headers', {})
        headers = {'Range': 'bytes=0-', 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors',
                   'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}

        headers.update(_headers)

        try:
            return self.get_info_for_format(url, headers=headers)
        except (HTTPStatusError, ConnectError) as e:
            self.logger_debug(f"{pre}: error - {repr(e)}")
        except ReExtractInfo as e:
            self.logger_debug(f"{pre}: error - {repr(e)}, will retry")
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
        domain = get_domain(url)
        url = f'https://{domain}/e/{video_id}'
        webpage = try_get(self._send_request(url), lambda x: html.unescape(x.text))
        if not webpage or any([_ in webpage for _ in ('<title>Server maintenance', '<title>Video not found')]):
            raise_extractor_error("error 404 no webpage")
        webpage = cast(str, webpage)

        title = self._html_search_meta(('og:title', 'twitter:title'), webpage, default=None)
        if not title:
            title = try_get(self._html_extract_title(webpage, default=None), lambda x: x.replace(' - DoodStream', ''))
        if not title:
            raise_extractor_error("error with title")
        title = cast(str, title)
        mobj = re.findall(r'(1080p|720p|480p)', title)
        if mobj:
            title = title.split(mobj[0])[0]
        title = re.sub(r'(\s*-\s*202)', ' 202', title)

        return {'id': str(int(sha256(video_id.encode('utf-8')).hexdigest(), 16) % 10**12) if len(video_id) > 12 else video_id,
                'title': title.replace(' - DoodStream', '').replace('mp4', '').replace('mkv', '').strip(' \t\n\r\f\v-_')}

    @on_retry_vinfo
    def _get_entry(self, url, **kwargs):

        video_id = cast(str, self._match_id(url))
        domain = get_domain(url)
        url = f'https://{domain}/e/{video_id}'
        pre = f'[get_entry][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'
        webpage = cast(str, try_get(self._send_request(url), lambda x: html.unescape(x.text)))
        if not webpage:
            raise_extractor_error(f"{pre} error 404 no webpage")
        if any([_ in webpage for _ in ('<title>Server maintenance', '<title>Video not found')]):
            raise_extractor_error(f"{pre} error 404 webpage")
        title = self._og_search_title(webpage, default=None) or self._html_extract_title(webpage, default=None)
        if not title:
            raise_extractor_error(f"{pre} error with title")
        title = cast(str, title)
        mobj = re.findall(r'(1080p|720p|480p)', title)
        if mobj:
            title = title.split(mobj[0])[0]
        title = re.sub(r'(\s*-\s*202)', ' 202', title)
        title = title.replace(' - DoodStream', '').replace('mp4', '').replace('mkv', '').strip(' \t\n\r\f\v-_')

        thumbnail = self._og_search_thumbnail(webpage, default=None)

        token = self._html_search_regex(r"[?&]token=([a-z0-9]+)[&']", webpage, 'token')

        headers = {'Referer': f'https://{domain}/'}

        pass_md5 = self._html_search_regex(r"(/pass_md5.*?)'", webpage, 'pass_md5')
        video_url = ''.join([
            try_get(self._send_request(f'https://{domain}{pass_md5}', headers=headers), lambda x: html.unescape(x.text)),  # type: ignore
            *(random.choice(string.ascii_letters + string.digits) for _ in range(10)),
            f'?token={token}&expiry={int(time.time() * 1000)}']
        )
        if not video_url:
            raise_extractor_error(f"{pre} couldnt get videourl")

        _format = {
            'format_id': 'http-mp4',
            'url': video_url,
            'http_headers': headers,
            'ext': 'mp4'
        }

        with self.get_ytdl_sem(get_domain(video_url)):
            _videoinfo = cast(dict, self._get_video_info(video_url, msg=pre, headers=headers))

        if not _videoinfo:
            self._count += 1
            raise_reextract_info(f"{pre} error 404: no video info")

        if _videoinfo['filesize'] >= 25000000 or self._count >= 9:
            _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize'], 'accept_ranges': _videoinfo['accept_ranges']})
        else:
            self._count += 1
            raise_reextract_info(f"{pre} error filesize[{_videoinfo['filesize']}] < 25MB")

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
            'title': title,
            'formats': [_format],
            'subtitles': _subtitles,
            'thumbnail': thumbnail,
            'ext': 'mp4',
            'extractor_key': 'DoodStream',
            'extractor': 'doodstream',
            'webpage_url': url
        }

        return _entry

    def _real_initialize(self):
        super()._real_initialize()
        self._count = 0

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
            raise_extractor_error(repr(e))
