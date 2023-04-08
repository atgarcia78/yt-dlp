import sys
import traceback
import re
import subprocess
import json
import html

from ..utils import ExtractorError, sanitize_filename, traverse_obj, try_get, js_to_json, decode_packed_codes
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_2, HTTPStatusError, ConnectError


class FilemoonIE(SeleniumInfoExtractor):

    IE_NAME = "filemoon"
    _SITE_URL = "https://filemoon.sx/"
    _VALID_URL = r'https?://filemoon\.\w\w/[e,d]/(?P<id>[^\/$]+)(?:\/|$)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https://filemoon\.\w\w/[e,d]/.+?)\1']

    @dec_on_exception
    @dec_on_exception3
    @dec_on_exception2
    def _send_request(self, url, **kwargs):

        driver = kwargs.get('driver', None)
        msg = kwargs.get('msg', None)
        headers = kwargs.get('headers', None)

        with limiter_2.ratelimit(f'{self.IE_NAME}', delay=True):
            if msg:
                pre = f'{msg}[send_req]'
            else:
                pre = '[send_req]'
            self.logger_debug(f"{pre} {self._get_url_print(url)}")
            if driver:
                driver.get(url)
            else:
                try:
                    return self.send_http_request(url, headers=headers)
                except (HTTPStatusError, ConnectError) as e:
                    self.report_warning(f"{pre} {self._get_url_print(url)}: error - {repr(e)}")

    def _real_initialize(self):

        super()._real_initialize()

    def _get_entry(self, url, **kwargs):

        videoid = self._match_id(url)

        _wurl = f"{self._SITE_URL}d/{videoid}"
        webpage = try_get(self._send_request(_wurl), lambda x: html.unescape(re.sub('[\t\n]', '', x.text)))

        if not webpage:
            raise ExtractorError("no webpage")

        packed = self._search_regex(r'<script data-cfasync=[^>]+>eval\((.+)\)</script>', webpage, 'packed code')
        if not packed:
            raise ExtractorError("couldnt find js function")

        try:
            unpacked = decode_packed_codes(packed)

            m3u8_url = try_get(re.search(r'file:"(?P<url>[^"]+)"', unpacked), lambda x: x.group('url'))

        except Exception:
            self.logger_debug("Change to node")

            sign = try_get(re.findall(r'</main><script data-cfasync=[^>]+>eval\((.+)\)</script>', webpage), lambda x: x[0])
            if not sign:
                raise ExtractorError("couldnt find js function")
            jscode = "var res =" + sign + ";console.log(res)"

            try:
                _webpage = subprocess.run(["node", "-e", jscode], capture_output=True, encoding="utf-8").stdout.strip('\n')
            except Exception as e:
                self.report_warning(repr(e))
                _webpage = None

            if not _webpage:
                raise ExtractorError("error executing js")

            options = try_get(re.search(r'setup\s*\((?P<options>[^;]+);', _webpage), lambda x: json.loads(js_to_json(x.group('options')[:-1].replace('Class()', 'Class'))) if x else None)

            m3u8_url = traverse_obj(options, ('sources', 0, 'file'))

        if not m3u8_url:
            raise ExtractorError("couldnt find m3u8 url")

        _headers = {'Referer': self._SITE_URL, 'Origin': self._SITE_URL.strip("/")}

        formats = self._extract_m3u8_formats(m3u8_url, videoid, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls", headers=_headers)

        if formats:
            self._sort_formats(formats)
        else:
            raise ExtractorError(f"[{url}] Couldnt find any video format")

        for _format in formats:
            _format.update({'http_headers': _headers})

        title = self._html_extract_title(webpage)

        return ({
            "id": videoid,
            "title": sanitize_filename(title, restricted=True).replace("Watch_", ""),
            "formats": formats,
            "webpage_url": _wurl,
            "ext": "mp4"})

    def _real_extract(self, url):

        self.report_extraction(url)

        try:
            return self._get_entry(url)

        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.report_warning(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
