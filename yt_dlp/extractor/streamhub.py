import os
import atexit
from .commonwebdriver import (
    SeleniumInfoExtractor,
    dec_on_exception2,
    dec_on_exception3,
    HTTPStatusError,
    ConnectError,
    limiter_1,
    By,
    ec
)
from ..utils import (
    ExtractorError,
    sanitize_filename,
    try_get,
    try_call,
    find_available_port
)

import functools
from threading import Lock

import logging
logger = logging.getLogger('streamhub')


class StreamHubIE(SeleniumInfoExtractor):

    _VALID_URL = r'https?://(?:www\.)?streamhub\.[^/]+/(?:e/)?(?P<id>[a-z0-9]+)'
    IE_NAME = 'streamhub'  # type: ignore
    _LOCK = Lock()
    _DRIVER = None

    @dec_on_exception3
    @dec_on_exception2
    def _get_video_info(self, url, **kwargs):

        pre = f'[get_video_info][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'

        _headers = kwargs.get('headers', {})
        headers = {
            'Range': 'bytes=0-', 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache',
            'Cache-Control': 'no-cache'}
        headers.update(_headers)

        with limiter_1.ratelimit(self.IE_NAME, delay=True):
            try:
                self.logger_debug(pre)
                return self.get_info_for_format(url, headers=headers)
            except (HTTPStatusError, ConnectError) as e:
                _msg_error = f"{repr(e)}"
                self.logger_debug(f"{pre}: {_msg_error}")
                return {"error_res": _msg_error}

    @dec_on_exception3
    @dec_on_exception2
    def _send_request(self, url, **kwargs):

        pre = f'[send_request][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'

        driver = kwargs.get('driver', None)

        with limiter_1.ratelimit(f"{self.IE_NAME}2", delay=True):
            self.logger_debug(pre)
            if driver:
                driver.get(url)
            else:
                try:
                    return self.send_http_request(url)
                except (HTTPStatusError, ConnectError) as e:
                    _msg_error = f"{repr(e)}"
                    self.logger_debug(f"{pre}: {_msg_error}")
                    return {"error_res": _msg_error}

    class synchronized:

        def __call__(self, func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with StreamHubIE._LOCK:
                    return func(*args, **kwargs)
            return wrapper

    def close(self):
        if StreamHubIE._DRIVER:
            self.rm_driver(StreamHubIE._DRIVER)
            StreamHubIE._DRIVER = None
        super().close()

    @synchronized()
    def _get_entry(self, url, **kwargs):

        pre = f'[get_entry_by_har][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'

        videoid = self._match_id(url)  # type: ignore
        url_dl = f"https://streamhub.to/{videoid}"

        _port = find_available_port() or 8080
        if not StreamHubIE._DRIVER:
            StreamHubIE._DRIVER = self.get_driver(host='127.0.0.1', port=_port)
            atexit.register(self.close)
        else:
            self.set_driver_proxy_port(StreamHubIE._DRIVER, _port)
        try:

            with self.get_har_logs('streamhub', videoid, msg=pre, port=_port) as harlogs:

                _har_file = harlogs.har_file
                self._send_request(url_dl, driver=StreamHubIE._DRIVER)
                self.wait_until(StreamHubIE._DRIVER, 30, ec.presence_of_element_located((By.TAG_NAME, "video")))
                self.wait_until(StreamHubIE._DRIVER, 5)
                _title = try_get(self.wait_until(StreamHubIE._DRIVER, 5, ec.presence_of_element_located((By.TAG_NAME, "h4"))), lambda x: x.text)

            _headers = {'Accept': '*/*', 'Accept-Encoding': 'gzip, deflate, br', 'Accept-Language': 'en-US,en;q=0.5', 'Origin': "https://streamhub.to", 'Referer': "https://streamhub.to/"}
            m3u8_url, m3u8_doc = try_get(
                self.scan_for_request(r"master.m3u8+$", har=_har_file),  # type: ignore
                lambda x: (x.get('url'), x.get('content')) if x else (None, None))

            _formats = []
            _subtitles = {}
            if m3u8_doc and m3u8_url:
                _formats, _subtitles = self._parse_m3u8_formats_and_subtitles(m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")

            if not _formats:
                raise ExtractorError('Couldnt get video formats')

            for _format in _formats:
                if (_head := _format.get('http_headers')):
                    _head.update(_headers)
                else:
                    _format.update({'http_headers': _headers})

            if not _subtitles:
                list_subt_urls = try_get(
                    self.scan_for_request(r"\.(?:srt|vtt)$", har=_har_file, _all=True),  # type: ignore
                    lambda x: [el.get('url') for el in x] if x else [])
                if list_subt_urls:
                    def _get_info_subt(subturl):
                        _cc_lang = {'spanish': 'es', 'english': 'en'}
                        if subturl:
                            ext = subturl.rsplit('.', 1)[-1]
                            lang = _cc_lang.get(try_call(lambda: subturl.rsplit('.', 1)[0].rsplit('_', 1)[-1].lower()) or 'dummy')
                            if lang:
                                return {'lang': lang, 'ext': ext}

                    for _url_subt in list_subt_urls:
                        _subt = _get_info_subt(_url_subt)
                        if not _subt:
                            continue
                        _subtitles.setdefault(_subt.get('lang'), []).append({'url': _url_subt, 'ext': _subt.get('ext')})

            _entry = {
                'id': videoid,
                'title': sanitize_filename(_title, restricted=True),
                'formats': _formats,
                'subtitles': _subtitles,
                'ext': 'mp4',
                'extractor_key': 'StreamHub',
                'extractor': 'streamhub',
                'webpage_url': url}

            try:
                _entry.update({'duration': self._extract_m3u8_vod_duration(_formats[0]['url'], videoid, headers=_formats[0].get('http_headers', {}))})
            except Exception as e:
                self.logger_info(f"{pre}: error trying to get vod {repr(e)}")

            try:
                if os.path.exists(_har_file):
                    os.remove(_har_file)
            except OSError:
                return self.logger_info(f"{pre}: Unable to remove the har file")

            return _entry

        except Exception as e:
            logger.exception(f"{pre} {repr(e)}")
            raise ExtractorError(f"Couldnt get video entry - {repr(e)}")

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
            self.to_screen(f"{repr(e)}")
            raise ExtractorError(repr(e))
