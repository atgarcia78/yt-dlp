import html
import re

from .commonwebdriver import (
    ConnectError,
    HTTPStatusError,
    SeleniumInfoExtractor,
    dec_on_exception,
    dec_on_exception2,
    dec_on_exception3,
    limiter_1,
)
from ..utils import (
    ExtractorError,
    int_or_none,
    sanitize_filename,
    try_call,
    try_get,
)


class GayStreamBase(SeleniumInfoExtractor):

    _SITE_URL: str

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
        _headers = {'Range': 'bytes=0-', 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
                    'Pragma': 'no-cache', 'Cache-Control': 'no-cache', **kwargs}
        try:
            return self.get_info_for_format(url, headers=_headers)
        except (HTTPStatusError, ConnectError) as e:
            self.logger_debug(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    def _real_initialize(self):
        super()._real_initialize()


class GayStreamPWIE(GayStreamBase):

    _VALID_URL = r'https?://(?:www\.)?gaystream.pw/video/(?P<id>\d+)/?([^$]+)?$'

    def _real_extract(self, url):

        self.report_extraction(url)

        try:
            _url = url.replace('//www.', '//')
            if not (webpage := try_get(self._send_multi_request(_url), lambda x: html.unescape(x.text))):
                raise ExtractorError("404 no video webpage")
            else:
                _urls_embed = re.findall(r'onclick=[\'\"]document\.getElementById\([\"\']ifr[\"\']\)\.src=[\"\'](?P<eurl>[^\"\']+)[\"\']', webpage, flags=re.I)
                if not _urls_embed:
                    raise ExtractorError("no embed urls")
                else:
                    _title = try_call(lambda: self._html_extract_title(webpage).replace('on Gaystream.pw', '').replace('Watch ', '').strip())
                    print('title gs:', _title)
                    _entry = None
                    for _url in _urls_embed:
                        try:
                            ie = self._get_extractor(_url)
                            if ie.IE_NAME in ('filemoon', 'voe'):
                                if (_entry := ie._get_entry(_url)):
                                    break
                        except Exception as e:
                            self.logger_debug(repr(e))

                    if not _entry:
                        raise ExtractorError("no video entry")

                    else:
                        return _entry | {'title': sanitize_filename(_title, restricted=True), 'original_url': _url}

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))


class GayStreamEmbedIE(GayStreamBase):

    _INSTANCES_RE = r'(?:gaystream.online|watchgayporn.online|streamxxx.online|feurl.com)'

    _VALID_URL = r'https?://(www\.)?(?P<host>%s)/(?:v|e|api/source)/(?P<id>.+)' % _INSTANCES_RE

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
                    _info_video = self._get_video_info(_url, headers={'Referer': self._SITE_URL})
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
