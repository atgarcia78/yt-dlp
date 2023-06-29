import re
import json
import html
from typing import cast

from ..utils import (
    ExtractorError,
    sanitize_filename,
    try_get,
    js_to_json,
    decode_packed_codes,
    get_domain, determine_ext)

from .commonwebdriver import (
    dec_on_exception3,
    SeleniumInfoExtractor,
    limiter_2,
    HTTPStatusError,
    ConnectError)


class FilemoonIE(SeleniumInfoExtractor):

    IE_NAME = "filemoon"  # type: ignore
    _SITE_URL = "https://filemoon.sx"
    _VALID_URL = r'https?://filemoon\.\w\w/[e,d]/(?P<id>[^\/$]+)(?:\/|$)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https://filemoon\.\w\w/[e,d]/.+?)\1']

    @dec_on_exception3
    @limiter_2.ratelimit("mixdrop", delay=True)
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

    def _real_initialize(self):
        super()._real_initialize()

    def _get_entry(self, url, **kwargs):

        videoid = self._match_id(url)

        _wurl = f"{self._SITE_URL}/d/{videoid}"
        webpage = try_get(self._send_request(_wurl), lambda x: html.unescape(x.text))

        if not webpage:
            raise ExtractorError("no webpage")

        info_video = {}
        for ofcode in re.finditer(r'<script data-cfasync=[^>]+>(eval[^\n]+)\n', webpage, flags=re.MULTILINE):
            plaincode = decode_packed_codes(ofcode.group())
            if 'jwplayer' and 'setup' in plaincode:
                info_video = try_get(try_get(re.search(r'setup\((?P<code>.*)\);var vvplay', plaincode), lambda x: x.group('code').replace('\\', '')), lambda y: json.loads(js_to_json(y)))
                break

        formats = []
        subtitles = {}
        duration = None

        if info_video and (_entry := cast(dict, self._parse_jwplayer_data(info_video, videoid, False, m3u8_id='hls', mpd_id='dash'))):
            formats, subtitles, duration = _entry.get('formats', []), _entry.get('subtitles', {}), _entry.get('duration')

        if not formats:
            raise ExtractorError(f"[{url}] Couldnt find any video format")

        dom = get_domain(_wurl)
        _headers = {'Origin': f"https://{dom}", 'Referer': f"https://{dom}/"}

        for _format in formats:
            _format.update({'http_headers': _headers})
            if not duration and determine_ext(_format['url']):
                try:
                    duration = self._extract_m3u8_vod_duration(_format['url'], videoid, headers=_format.get('http_headers', {}))
                except Exception as e:
                    self.logger_info(f"error trying to get vod {repr(e)}")

        title = self._html_extract_title(webpage)

        _entry = {
            "id": videoid,
            "title": sanitize_filename(title, restricted=True),
            "formats": formats,
            "subtitles": subtitles,
            "webpage_url": _wurl,
            "ext": "mp4",
            "extractor": "filemoon",
            "extractor_key": "Filemoon",
            "duration": duration}

        return _entry

    def _real_extract(self, url):

        self.report_extraction(url)

        try:
            return self._get_entry(url)

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))
