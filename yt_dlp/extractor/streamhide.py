import html
import re

from .commonwebdriver import (
    ConnectError,
    HTTPStatusError,
    SeleniumInfoExtractor,
    dec_on_exception3,
    dec_on_exception2,
    limiter_1,
)
from ..utils import (
    ExtractorError,
    decode_packed_codes,
    get_element_text_and_html_by_tag,
    sanitize_filename,
    try_call,
    try_get,
)


class StreamHideIE(SeleniumInfoExtractor):

    IE_NAME = "streamhide"  # type: ignore
    _DOMAINS = r'(?:guccihide\.com)'
    _VALID_URL = r'''(?x)https?://(?:.+?\.)?(?P<domain>%s)/(?:d|w|e)/(?P<id>[\dA-Za-z]+)''' % _DOMAINS

    @dec_on_exception2
    @dec_on_exception3
    def _send_request(self, url, **kwargs):

        pre = '[send_req]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}[send_req]'

        headers = kwargs.get('headers', None)

        with limiter_1.ratelimit(f'{self.IE_NAME}', delay=True):

            self.logger_debug(f"{pre} {self._get_url_print(url)}")

            try:
                return self.send_http_request(url, headers=headers)
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"{pre} {self._get_url_print(url)}: error - {repr(e)}")

    def _real_initialize(self):

        super()._real_initialize()

    def _get_entry(self, url, **kwargs):

        videoid, dom = try_get(re.search(self._VALID_URL, url), lambda x: x.group('id', 'domain'))  # type: ignore
        _wurl = f"https://{dom}/e/{videoid}"
        webpage = try_get(self._send_request(_wurl), lambda x: html.unescape(re.sub('[\t\n]', '', x.text)))

        if not webpage:
            raise ExtractorError("no webpage")

        unpacked = decode_packed_codes(webpage)

        m3u8_url = try_get(re.search(r'file:"(?P<url>[^"]+)"', unpacked), lambda x: x.group('url'))

        if not m3u8_url:
            raise ExtractorError("couldnt find m3u8 url")

        _headers = {'Origin': f"https://{dom}", 'Referer': f"https://{dom}/"}

        formats, subtitles = self._extract_m3u8_formats_and_subtitles(m3u8_url, videoid, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls", headers=_headers)

        if not formats:
            raise ExtractorError(f"[{url}] Couldnt find any video format")

        for _format in formats:
            _format.update({'http_headers': _headers})

        _vurl = f"https://{dom}/w/{videoid}"
        webpage = try_get(self._send_request(_vurl), lambda x: html.unescape(re.sub('[\t\n]', '', x.text)))
        if not webpage:
            _vurl = f"https://{dom}/d/{videoid}"
            webpage = try_get(self._send_request(_vurl), lambda x: html.unescape(re.sub('[\t\n]', '', x.text)))
            if not webpage:
                raise ExtractorError("no webpage d/w")
            title = try_get(try_call(lambda: get_element_text_and_html_by_tag('h4', webpage)[0]), lambda x: re.sub(r'(\s+)?download(\s+)?|\.mp4|\.mkv', '', x, flags=re.IGNORECASE).strip())
        else:
            title = try_get(try_call(lambda: get_element_text_and_html_by_tag('h1', webpage)[0]), lambda x: re.sub(r'(\s+)?download(\s+)?|\.mp4|\.mkv', '', x, flags=re.IGNORECASE).strip())

        return ({
            "id": videoid,
            "title": sanitize_filename(title, restricted=True).replace("Watch_", ""),
            "formats": formats,
            "subtitles": subtitles,
            "webpage_url": _wurl,
            "ext": "mp4"})

    def _real_extract(self, url):

        self.report_extraction(url)

        try:
            return self._get_entry(url)

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))
