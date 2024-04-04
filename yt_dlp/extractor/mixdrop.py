import html
import json
import re

from .commonwebdriver import (
    ConnectError,
    ExtractorError,
    HTTPStatusError,
    ReExtractInfo,
    SeleniumInfoExtractor,
    dec_on_exception3,
    limiter_1,
    my_dec_on_exception,
    raise_extractor_error,
)
from ..utils import (
    decode_packed_codes,
    get_domain,
    js_to_json,
    sanitize_filename,
    sanitize_url,
    try_get,
)

on_exception_vinfo = my_dec_on_exception(
    (TimeoutError, ExtractorError), raise_on_giveup=False, max_tries=5, jitter="my_jitter", interval=1)

on_retry_vinfo = my_dec_on_exception(
    ReExtractInfo, raise_on_giveup=False, max_tries=10, jitter="my_jitter", interval=1)


class MixDropIE(SeleniumInfoExtractor):

    _SITE_URL = "https://mixdrop.to"

    IE_NAME = 'mixdrop'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?mixdrop\.[^/]+/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'

    @on_exception_vinfo
    def _get_video_info(self, url, **kwargs):
        with limiter_1.ratelimit("mixdrop", delay=True):
            msg = kwargs.get('msg')
            pre = f'[get_video_info][{self._get_url_print(url)}]'
            if msg:
                pre = f'{msg}{pre}'

            _headers = kwargs.get('headers', {})
            headers = {
                'Range': 'bytes=0-', 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}

            headers.update(_headers)

            try:
                return self.get_info_for_format(url, headers=headers)
            except HTTPStatusError as e:
                self.logger_debug(f"{pre}: error - {repr(e)}")
            except ReExtractInfo as e:
                self.logger_debug(f"{pre}: error - {repr(e)}, will retry")
                raise

    @dec_on_exception3
    @limiter_1.ratelimit("mixdrop", delay=True)
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

    @on_retry_vinfo
    def _get_entry(self, url, check=False, msg=None):

        video_id = self._match_id(url)
        url = f'https://mixdrop.to/e/{video_id}'
        pre = f'[get_entry][{self._get_url_print(url)}]'
        if msg:
            pre = f'{msg}{pre}'
        webpage = try_get(self._send_request(url), lambda x: html.unescape(re.sub('[\t\n]', '', x.text)))
        if not webpage or any([_ in webpage for _ in ('<title>Server maintenance', '<title>Video not found')]):
            raise_extractor_error(f"{pre} error 404 no webpage")
        else:
            ofuscated_code = try_get(re.search(r'<script>(MD.*)</script><video', webpage), lambda x: x.group())
            info_video = json.loads('{' + js_to_json(decode_packed_codes(ofuscated_code)).replace(';', ',').replace('"=', '":').strip(',') + '}')

        _urlf = f'https://mixdrop.to/f/{video_id}'
        _webpagef = try_get(self._send_request(_urlf), lambda x: html.unescape(re.sub('[\t\n]', '', x.text)))
        if not _webpagef or any([_ in _webpagef for _ in ('<title>Server maintenance', '<title>Video not found')]):
            raise_extractor_error(f"{pre} error 404 no webpage")
        else:
            if (
                (title := (self._og_search_title(_webpagef, default=None) or self._html_extract_title(_webpagef, default=None)))
                and isinstance(title, str)
            ):
                title = re.sub(r'(\s+-+\s+)?mixdrop(\s+-+\s+watch\s+)?|\.mp4', '', title, flags=re.IGNORECASE)
            else:
                raise_extractor_error(f"{pre} error no title")

        headers = {'Referer': self._SITE_URL + '/', 'Origin': self._SITE_URL}

        if not (video_url := try_get(info_video.get('MDCore.wurl'), lambda x: sanitize_url(x, scheme='https'))):
            raise_extractor_error(f"{pre} couldnt get videourl")

        _format = {
            'format_id': 'http-mp4',
            'url': video_url,
            'http_headers': headers,
            'ext': 'mp4'
        }

        if check:
            with self.get_ytdl_sem(get_domain(video_url)):
                _videoinfo = self._get_video_info(video_url, msg=pre, headers=headers)

            if not _videoinfo:
                raise ReExtractInfo(f"{pre} error 404: no video info")

            elif ((_size := _videoinfo.get('filesize')) and _size >= 1000000):
                _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize'], 'accept_ranges': _videoinfo['accept_ranges']})
            else:
                raise ReExtractInfo(f"{pre} error filesize[{_size}]{' < 1MB' if _size else ''}")

        _entry = {
            'id': video_id,
            'title': sanitize_filename(title, restricted=True),
            'formats': [_format],
            'ext': 'mp4',
            'extractor_key': 'MixDrop',
            'extractor': 'mixdrop',
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
            raise_extractor_error(repr(e))
