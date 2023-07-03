import html
import json
import re
from typing import cast

from .commonwebdriver import (
    ConnectError,
    ExtractorError,
    HTTPStatusError,
    ReExtractInfo,
    SeleniumInfoExtractor,
    dec_on_exception3,
    dec_on_exception2,
    limiter_1,
    my_dec_on_exception,
    raise_extractor_error
)
from ..utils import (
    js_to_json,
    sanitize_filename,
    try_get,
    decode_packed_codes,
    get_elements_html_by_attribute
)

on_exception_vinfo = my_dec_on_exception(
    (TimeoutError, ExtractorError), raise_on_giveup=False, max_tries=5, jitter="my_jitter", interval=1)

on_retry_vinfo = my_dec_on_exception(
    ReExtractInfo, raise_on_giveup=False, max_tries=5, jitter="my_jitter", interval=1)


class StreamVidIE(SeleniumInfoExtractor):

    _SITE_URL = "https://streamvid.net"

    IE_NAME = 'streamvid'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?streamvid\.[^/]+/(embed-)?(?P<id>[^\/$]+)(?:\/|$)'

    @dec_on_exception2
    @dec_on_exception3
    def _send_request(self, url, **kwargs):

        _kwargs = kwargs.copy()
        pre = f'[send_req][{self._get_url_print(url)}]'
        if (msg := _kwargs.pop('msg', None)):
            pre = f'{msg}{pre}'

        with limiter_1.ratelimit(self.IE_NAME, delay=True):
            try:
                return self.send_http_request(url, **_kwargs)
            except (HTTPStatusError, ConnectError) as e:
                _msg_error = f"{repr(e)}"
                self.logger_debug(f"{pre}: {_msg_error}")

    def _get_m3u8url(self, webpage):
        ofuscated_code = try_get(list(filter(lambda x: 'function(p,a,c,k,e,d)' in x, get_elements_html_by_attribute('type', 'text/javascript', webpage))), lambda x: x[0])
        sources = json.loads(js_to_json(try_get(re.search(r'sources:(?P<sources>[^;]+);', decode_packed_codes(ofuscated_code)), lambda x: x.group('sources')[:-2] if x else '{}')))
        if not (m3u8_url := try_get(sources, lambda x: x[0]['src'])):
            raise_extractor_error("couldnt get videourl")
        return m3u8_url

    def _get_entry(self, url, **kwargs):

        url = url.replace('embed-', '')
        video_id = cast(str, self._match_id(url))
        pre = f'[get_entry][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'
        webpage = try_get(self._send_request(url), lambda x: html.unescape(re.sub('[\t\n]', '', x.text)))
        if not webpage or any([_ in webpage for _ in ('<title>Server maintenance', '<title>Video not found')]):
            raise_extractor_error(f"{pre} error 404 no webpage")
        webpage = cast(str, webpage)

        m3u8_url = self._get_m3u8url(webpage)

        title = cast(str, self._html_extract_title(webpage, default=None))
        title = title.replace('Watch ', '')

        headers = {'Referer': self._SITE_URL + '/', 'Origin': self._SITE_URL}

        _formats, _subtitles = self._extract_m3u8_formats_and_subtitles(m3u8_url, video_id, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls", headers=headers)

        if not _formats:
            raise_extractor_error(f"{pre} couldnt get video info")

        _entry = {
            'id': video_id,
            'title': sanitize_filename(title, restricted=True),
            'formats': _formats,
            'subtitles': _subtitles,
            'ext': 'mp4',
            'extractor_key': self.ie_key(),
            'extractor': self.IE_NAME,
            'webpage_url': url
        }

        try:
            _entry.update({'duration': self._extract_m3u8_vod_duration(_formats[0]['url'], video_id, headers=_formats[0].get('http_headers', {}))})
        except Exception as e:
            self.logger_info(f"{pre}: error trying to get vod {repr(e)}")

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


class FilelionsIE(StreamVidIE):

    _SITE_URL = "https://filelions.to"

    IE_NAME = 'filelions'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?filelions\.[^/]+/(?:f|v)/(?P<id>[^\/$]+)(?:\/|$)'

    def _get_m3u8url(self, webpage):
        ofuscated_code = try_get(list(filter(lambda x: 'function(p,a,c,k,e,d)' in x, get_elements_html_by_attribute('type', 'text/javascript', webpage))), lambda x: x[0])
        sources = json.loads(js_to_json(try_get(re.search(r'sources:(?P<sources>[^,]+),', decode_packed_codes(ofuscated_code)), lambda x: x.group('sources') if x else '{}')))
        if not (m3u8_url := try_get(sources, lambda x: x[0]['file'])):
            raise_extractor_error("couldnt get videourl")
        return m3u8_url

    def _get_entry(self, url, **kwargs):

        return super()._get_entry(url.replace('/v/', '/f/'), **kwargs)
