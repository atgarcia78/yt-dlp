import html
import re
import json
from typing import cast

from .commonwebdriver import (
    ConnectError,
    HTTPStatusError,
    SeleniumInfoExtractor,
    dec_on_exception3,
    limiter_1,
    my_dec_on_exception,
    ReExtractInfo
)
from ..utils import (
    ExtractorError,
    get_element_text_and_html_by_tag,
    sanitize_filename,
    try_call,
    try_get,
    js_to_json,
    determine_ext,
    get_domain,
)

on_exception_vinfo = my_dec_on_exception(
    (TimeoutError, ExtractorError), raise_on_giveup=False, max_tries=5, jitter="my_jitter", interval=1)

on_retry_vinfo = my_dec_on_exception(
    ReExtractInfo, raise_on_giveup=False, max_tries=5, jitter="my_jitter", interval=1)


class StreamHideIE(SeleniumInfoExtractor):

    IE_NAME = "streamhide"  # type: ignore
    _DOMAINS = r'(?:guccihide\.com|vflix\.top)'
    _VALID_URL = r'''(?x)https?://(?:.+?\.)?(?P<domain>%s)/(?:d|w|e)/(?P<id>[\dA-Za-z]+)''' % _DOMAINS

    @on_exception_vinfo
    def _get_video_info(self, url, **kwargs):

        msg = kwargs.get('msg')
        pre = f'[get_video_info][{self._get_url_print(url)}]'
        if msg:
            pre = f'{msg}{pre}'

        _headers = kwargs.get('headers', {})
        headers = {'Range': 'bytes=0-', 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors',
                   'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}

        headers.update(_headers)
        with limiter_1.ratelimit(f'{self.IE_NAME}', delay=True):
            try:
                return self.get_info_for_format(url, headers=headers)
            except (HTTPStatusError, ConnectError) as e:
                self.logger_debug(f"{pre}: error - {repr(e)}")
            except ReExtractInfo as e:
                self.logger_debug(f"{pre}: error - {repr(e)}, will retry")
                raise

    @dec_on_exception3
    def _send_request(self, url, **kwargs):
        pre = '[send_req]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}[send_req]'
        headers = kwargs.get('headers', None)

        with limiter_1.ratelimit(f'{self.IE_NAME}2', delay=True):

            self.logger_debug(f"{pre} {self._get_url_print(url)}")

            try:
                return self.send_http_request(url, headers=headers)
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"{pre} {self._get_url_print(url)}: error - {repr(e)}")

    def _real_initialize(self):
        super()._real_initialize()

    @on_retry_vinfo
    def _get_entry(self, url, **kwargs):

        _check = kwargs.get('check', True)
        pre = f'[get_entry][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'

        try:

            videoid, dom = try_get(re.search(self._VALID_URL, url), lambda x: x.group('id', 'domain') if x else (None, None))  # type: ignore
            _wurl = f"https://{dom}/w/{videoid}"
            webpage = try_get(self._send_request(_wurl), lambda x: html.unescape(re.sub('[\t\n]', '', x.text)))

            if not webpage:
                raise ExtractorError("no webpage")

            jwplayer_data = try_get(self._search_regex(
                [r'jwplayer\("[^"]+"\)\.load\(\[({.+?})\]\);', r'jwplayer\("[^"]+"\)\.setup\(({.+?})\);'],
                webpage, 'jwplayer data', default=None),
                lambda x: json.loads(js_to_json(x).replace(' //', '')) if x else None)

            formats = []
            subtitles = {}
            duration = None

            if jwplayer_data and (_entry := self._parse_jwplayer_data(jwplayer_data, videoid, False, m3u8_id='hls', mpd_id='dash')):
                formats, subtitles, duration = _entry.get('formats', []), _entry.get('subtitles', {}), _entry.get('duration')

            if not formats:
                raise ExtractorError(f"[{url}] Couldnt find any video format")

            _headers = {'Origin': f"https://{dom}", 'Referer': f"https://{dom}/"}

            for _format in formats:
                _format.update({'http_headers': _headers})
                if not _format.get('filesize') and _check and determine_ext(_format['url']) == 'mp4':
                    _host = get_domain(_format['url'])

                    _videoinfo = {}
                    with self.get_ytdl_sem(_host):
                        _videoinfo = self._get_video_info(_format['url'], headers=_headers)

                    if not _videoinfo:
                        raise ReExtractInfo(f"{pre} error 404: no video info")

                    _videoinfo = cast(dict, _videoinfo)
                    if _videoinfo['filesize'] >= 1000000:
                        _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize'], 'accept_ranges': _videoinfo['accept_ranges']})
                    else:
                        raise ReExtractInfo(f"{pre} error filesize[{_videoinfo['filesize']}] < 1MB")

            title = try_get(try_call(lambda: get_element_text_and_html_by_tag('h1', webpage)[0]), lambda x: re.sub(r'(\s+)?download(\s+)?|\.mp4|\.mkv', '', x, flags=re.IGNORECASE).strip())

            _entry = {
                "id": videoid,
                "title": sanitize_filename(title, restricted=True).replace("Watch_", ""),
                "formats": formats,
                "subtitles": subtitles,
                "webpage_url": _wurl,
                "ext": "mp4",
                "duration": duration}

            return _entry

        except Exception as e:
            self.LOGGER.exception(repr(e))

    def _real_extract(self, url):

        self.report_extraction(url)

        try:
            return self._get_entry(url)

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))
