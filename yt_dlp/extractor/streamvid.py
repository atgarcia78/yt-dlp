import html
import json
import logging
import re

from yt_dlp_plugins.extractor.commonwebdriver import (
    ConnectError,
    ExtractorError,
    HTTPStatusError,
    ReExtractInfo,
    SeleniumInfoExtractor,
    dec_on_exception2,
    limiter_1,
    my_dec_on_exception,
    raise_extractor_error,
    raise_reextract_info,
)

from ..utils import (
    decode_packed_codes,
    get_elements_html_by_attribute,
    js_to_json,
    sanitize_filename,
    try_get,
)

on_exception = my_dec_on_exception(
    (TimeoutError, ExtractorError), raise_on_giveup=False, max_tries=3, jitter="my_jitter", interval=1)

on_retry = my_dec_on_exception(
    ReExtractInfo, raise_on_giveup=True, max_tries=3, jitter="my_jitter", interval=1)

logger = logging.getLogger('streamvid')


class StreamVidIE(SeleniumInfoExtractor):

    _SITE_URL = "https://streamvid.net"

    IE_NAME = 'streamvid'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?streamvid\.[^/]+/(embed-)?(?P<id>[^\/$]+)(?:\/|$)'

    ERROR_WEB = ['<title>Server maintenance', '<title>Video not found']

    @dec_on_exception2
    @on_exception
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
                return
            except Exception as e:
                self.logger_debug(f"{pre}: {repr(e)}")
                raise

    def _get_m3u8url(self, webpage):
        _filter_func = lambda x: 'function(p,a,c,k,e,d)' in x
        ofuscated_code = try_get(
            list(filter(
                _filter_func,
                get_elements_html_by_attribute('type', 'text/javascript', webpage))),
            lambda x: x[0])
        sources = json.loads(js_to_json(try_get(
            re.search(r'sources:(?P<sources>[^;]+);', decode_packed_codes(ofuscated_code)),
            lambda x: x.group('sources')[:-2] if x else '{}')))
        m3u8_url = try_get(sources, lambda x: x[0]['src'] if x else None)
        poster_url = try_get(
            re.search(
                r'poster\([^\'"][\'"](?P<poster>[^\\\'"]+)[\\\'"]',
                decode_packed_codes(ofuscated_code)),
            lambda x: x.group('poster') if x else None)
        return (m3u8_url, poster_url)

    @on_retry
    def _get_entry(self, url, **kwargs):

        url = url.replace('embed-', '')
        video_id = self._match_id(url)
        pre = f'[get_entry][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'

        try:
            webpage = try_get(
                self._send_request(url), lambda x: html.unescape(re.sub('[\t\n]', '', x.text)))

            if not webpage or any(_ in webpage for _ in self.ERROR_WEB):
                raise_extractor_error(f"{pre} error 404 no webpage")

            title = try_get(
                self._html_extract_title(webpage, default=None),
                lambda x: x.replace('Watch ', ''))

            m3u8_url, poster_url = self._get_m3u8url(webpage)

            self.logger_debug(f'{pre} {m3u8_url}\n{poster_url}')

            if not m3u8_url:
                raise_extractor_error(f"{pre} couldnt get m3u8 url")

            headers = {'Referer': self._SITE_URL + '/'}
            base_headers = {
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'cross-site',
                'TE': 'trailers'}
            m3u8_doc = None
            try:
                m3u8_doc = try_get(
                    self._send_request(m3u8_url, headers={**base_headers, **headers}, timeout=60),
                    lambda x: x.text if x else None)
            except ReExtractInfo as e:
                raise_extractor_error(f"{pre} Error M3U8 doc {str(e)}", _from=e)

            self.logger_debug(f'{pre} m3u8_doc\n{m3u8_doc}')
            if not m3u8_doc:
                if poster_url:
                    _res = self._send_request(poster_url, headers=headers)
                    if not _res:
                        raise_extractor_error(f"{pre} error video")
                else:
                    raise_reextract_info(f"{pre} couldnt get m3u8 doc")

            _formats, _subtitles = self._parse_m3u8_formats_and_subtitles(
                m3u8_doc, m3u8_url, ext="mp4", m3u8_id="hls", headers=headers)

            if not _formats:
                raise_extractor_error(f"{pre} couldnt get video info")

            for _format in _formats:
                if (_head := _format.get('http_headers')):
                    _head.update(headers)
                else:
                    _format.update({'http_headers': headers})

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
                _entry.update({'duration': self._extract_m3u8_vod_duration(
                    _formats[0]['url'], video_id, headers=_formats[0].get('http_headers', {}))})
            except Exception as e:
                self.logger_debug(f"{pre}: error trying to get vod {repr(e)}")
            return _entry
        except Exception as e:
            self.logger_debug(f"{pre}: {repr(e)}")
            raise

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        try:
            if not self.get_param('embed'):
                _check = True
            else:
                _check = False

            return self._get_entry(url, check=_check)

        except ExtractorError:
            raise
        except Exception as e:
            raise_extractor_error(_from=e)


class FilelionsIE(StreamVidIE):

    _SITE_URL = "https://filelions.to"

    IE_NAME = 'filelions'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?filelions\.[^/]+/(?:f|v)/(?P<id>[^\/$]+)(?:\/|$)'

    def _get_m3u8url(self, webpage):
        ofuscated_code = try_get(list(filter(lambda x: 'function(p,a,c,k,e,d)' in x, get_elements_html_by_attribute('type', 'text/javascript', webpage))), lambda x: x[0])
        sources = json.loads(js_to_json(try_get(re.search(r'sources:\[(?P<sources>[^\]]+)\],', decode_packed_codes(ofuscated_code)), lambda x: x.group('sources') if x else '{}')))
        m3u8_url = sources.get('file')
        poster_url = try_get(re.search(r'image\:[^\'"][\'"](?P<poster>[^\'"]+)[\'"]', decode_packed_codes(ofuscated_code)), lambda x: x.group('poster') if x else None)
        return (m3u8_url, poster_url)

    def _get_entry(self, url, **kwargs):
        return super()._get_entry(url.replace('/v/', '/f/'), **kwargs)
