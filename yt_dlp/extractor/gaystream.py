import html
import re
import sys
import traceback

from .commonwebdriver import (
    ConnectError,
    HTTPStatusError,
    SeleniumInfoExtractor,
    dec_on_exception,
    dec_on_exception2,
    dec_on_exception3,
    limiter_1,
)
from ..utils import ExtractorError, int_or_none, sanitize_filename, try_get


class GayStreamBase(SeleniumInfoExtractor):

    @dec_on_exception
    @dec_on_exception2
    @dec_on_exception3
    @limiter_1.ratelimit("gaystream", delay=True)
    def _send_multi_request(self, url, **kwargs):

        driver = kwargs.get('driver', None)

        if driver:
            driver.execute_script("window.stop();")
            driver.get(url)
        else:
            try:
                return self.send_http_request(url, **kwargs)
            except (HTTPStatusError, ConnectError) as e:
                self.logger_debug(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    @dec_on_exception3
    @dec_on_exception2
    @limiter_1.ratelimit("gaystream", delay=True)
    def _get_video_info(self, url, **kwargs):

        self.logger_debug(f"[get_video_info] {url}")
        _headers = {'Range': 'bytes=0-', 'Referer': self._SITE_URL,
                    'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
                    'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
        try:
            return self.get_info_for_format(url, headers=_headers)
        except (HTTPStatusError, ConnectError) as e:
            self.logger_debug(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    def _real_initialize(self):
        super()._real_initialize()


class GayStreamPWIE(GayStreamBase):

    _SITE_URL = 'https://gaystream.pw/'
    _VALID_URL = r'https?://(?:www\.)?gaystream.pw/video/(?P<id>\d+)/?([^$]+)?$'

    def _get_entry(self, url, **kwargs):

        try:

            webpage = try_get(self._send_multi_request(url), lambda x: html.unescape(x.text) if x else None)
            if not webpage:
                raise ExtractorError("no video webpage")
            _url_embed = try_get(re.search(r'onclick=[\'\"]document\.getElementById\([\"\']ifr[\"\']\)\.src=[\"\'](?P<eurl>[^\"\']+)[\"\']', webpage), lambda x: x.group('eurl'))
            if not _url_embed:
                raise ExtractorError("no embed url")
            ie_embed = self._get_extractor('GayStreamEmbed')
            _entry_video = ie_embed._get_entry(_url_embed)
            if not _entry_video:
                raise ExtractorError("no entry video")
            return _entry_video

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))

    def _real_initialize(self):

        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        try:
            _url = url.replace('//www.', '//')
            return self._get_entry(_url)

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))


class GayStreamEmbedIE(GayStreamBase):

    _INSTANCES_RE = r'(?:watchgayporn.online|streamxxx.online|feurl.com)'

    _VALID_URL = r'https?://(www\.)?(?P<host>%s)/(?:v|api/source)/(?P<id>.+)' % _INSTANCES_RE

    def _get_entry(self, url, **kwargs):

        _host = try_get(re.search(self._VALID_URL, url), lambda x: x.group('host'))
        _videoid = self._match_id(url)
        self._SITE_URL = f"https://{_host}/"
        try:

            _headers_post = {
                'Referer': url,
                'Origin': self._SITE_URL.strip('/'),
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest'
            }

            _data = {
                'r': '',
                'd': _host
            }

            _post_url = f"{self._SITE_URL}api/source/{_videoid}"

            info = try_get(self._send_multi_request(_post_url, _type="POST", headers=_headers_post, data=_data), lambda x: x.json() if x else None)
            _formats = []
            if info:
                for vid in info.get('data'):
                    _url = vid.get('file')
                    _info_video = self._get_video_info(_url)
                    if not isinstance(_info_video, dict):
                        self.report_warning(f"[{_url}] no video info")
                    else:
                        _formats.append({
                            'format_id': vid.get('label'),
                            'url': _info_video.get('url'),
                            'resolution': vid.get('label'),
                            'height': int_or_none(vid.get('label')[:-1]),
                            'filesize': _info_video.get('filesize'),
                            'ext': 'mp4',
                            'http_headers': {'Referer': self._SITE_URL}
                        })

            if _formats:
                self._sort_formats(_formats)

                webpage = try_get(self._send_multi_request(url), lambda x: x.text if x else None)
                _title = try_get(self._html_extract_title(webpage), lambda x: x.replace('Video ', '').replace('.mp4', '').replace('.', '_').replace(' ', '_'))

                _entry_video = {
                    'id': _videoid,
                    'title': sanitize_filename(_title, restricted=True).replace('___', '_').replace('__', '_'),
                    'formats': _formats,
                    'extractor': self.IE_NAME,
                    'extractor_key': self.ie_key(),
                    'ext': 'mp4',
                    'webpage_url': url
                }

                return _entry_video
            else:
                raise ExtractorError("couldn find video formats")

        except Exception as e:
            self.logger_debug(f"[{url}] error {repr(e)}")
            return {'error': e, '_all_urls': [
                f'https://{_host}/v/{_videoid}', f'https://www.{_host}/v/{_videoid}',
                f'https://{_host}/api/source/{_videoid}', f'https://www.{_host}/api/source/{_videoid}']}

    def _real_initialize(self):

        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        try:
            _url = url.replace('//www.', '//')
            if 'error' in (_info := self._get_entry(_url)):
                raise _info['error']
            else:
                return _info

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))
