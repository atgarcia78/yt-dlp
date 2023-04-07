import re
from urllib.parse import unquote

from ..utils import ExtractorError, sanitize_filename, try_get, js_to_json, get_domain
from .commonwebdriver import (
    dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor,
    limiter_1, HTTPStatusError, ConnectError)

import html
import json


class VoeIE(SeleniumInfoExtractor):
    IE_NAME = 'gaymoviestop'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?gaymovies\.top/(e/)?(?P<id>[^.]+)'
    _SITE_URL = 'https://gaymovies.top/'

    @dec_on_exception2
    @dec_on_exception3
    @limiter_1.ratelimit("voe", delay=True)
    def _get_video_info(self, url, **kwargs):

        try:
            msg = kwargs.get('msg', None)
            pre = '[get_video_info]'
            if msg:
                pre = f'{msg}{pre}'
            self.logger_debug(f"{pre} {self._get_url_print(url)}")
            _headers = {'Range': 'bytes=0-', 'Referer': self._SITE_URL,
                        'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site',
                        'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}

            return self.get_info_for_format(url, headers=_headers, **kwargs)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    @dec_on_exception2
    @dec_on_exception3
    @limiter_1.ratelimit("voe2", delay=True)
    def _send_request(self, url, **kwargs):

        try:
            self.logger_debug(f"[send_req] {self._get_url_print(url)}")
            return (self.send_http_request(url, **kwargs))
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    def _get_entry(self, url, **kwargs):

        try:
            check = kwargs.get('check', False)
            msg = kwargs.get('msg', None)
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg:
                pre = f'{msg}{pre}'
            webpage = try_get(self._send_request(url.replace('/e/', '/')), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)))
            if not webpage:
                raise ExtractorError("no video webpage")
            sources = try_get(re.findall(r'sources\s+=\s+(\{[^\}]+\})', webpage), lambda x: json.loads(js_to_json(x[0])))

            if not sources:
                raise ExtractorError(f"{pre} no video sources")

            _formats = []
            _headers = {'Referer': self._SITE_URL}

            res = sources.get('video_height', '')

            videoid = self._match_id(url)

            if 'mp4' in sources:
                video_url = unquote(sources.get('mp4'))

                _format = {
                    'format-id': f'http{res}',
                    'url': video_url,
                    'ext': 'mp4',
                    'http_headers': _headers

                }
                if res:
                    _format.update({'height': int(res)})
                if check:
                    _host = get_domain(video_url)
                    _sem = self.get_ytdl_sem(_host)
                    with _sem:
                        _videoinfo = self._get_video_info(video_url, msg=pre)
                    if not _videoinfo:
                        self.report_warning(f"{pre}[{_format['format-id']}] {video_url} - error 404: no video info")
                    else:
                        assert isinstance(_videoinfo, dict)
                        _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})
                        _formats.append(_format)
                else:
                    _formats.append(_format)

            if 'hls' in sources:
                m3u8_url = unquote(sources.get('hls'))
                fmts = self._extract_m3u8_formats(m3u8_url, videoid, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls", headers=_headers)

                if fmts:
                    _formats.extend(fmts)

            if not _formats:
                raise ExtractorError(f"{pre} No formats found")

            # self._sort_formats(_formats)

            _title = try_get(self._html_extract_title(webpage), lambda x: x.replace('Watch OFS -', '').replace(' - VOE | Content Delivery Network (CDN) & Video Cloud', '').replace('.mp4', ''))

            entry_video = {
                'id': videoid,
                'title': sanitize_filename(_title, restricted=True),
                'formats': _formats,
                'extractor_key': 'Voe',
                'extractor': 'voe',
                'ext': 'mp4',
                'webpage_url': url
            }

            return entry_video

        except Exception as e:
            self.to_screen(e)
            raise

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        try:

            _check = True

            return self._get_entry(url, check=_check)

        except ExtractorError:
            raise
        except Exception as e:

            self.to_screen(f"{repr(e)}")
            raise ExtractorError(repr(e))
