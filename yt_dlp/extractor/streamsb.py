import re
import os
import time
from .commonwebdriver import (
    SeleniumInfoExtractor,
    HTTPStatusError,
    ConnectError,
    dec_on_driver_timeout,
    limiter_1,
    my_dec_on_exception,
    By,
    ec
)
from ..utils import (
    ExtractorError,
    sanitize_filename,
    try_get,
    try_call,
    get_first
)

import functools
from threading import Semaphore

import logging
logger = logging.getLogger('streamsb')

on_exception = my_dec_on_exception(
    (TimeoutError, ExtractorError), raise_on_giveup=False, max_tries=3, jitter="my_jitter", interval=5)


class StreamSBIE(SeleniumInfoExtractor):

    _DOMAINS = r'(?:gaymovies\.top|sbanh\.com|sbbrisk\.com|watchonlinehd\.top)'
    _VALID_URL = r'''(?x)https?://(?:.+?\.)?(?P<domain>%s)/((?:d|e|v)/)?(?P<id>[\dA-Za-z]+)(\.html)?''' % _DOMAINS
    IE_NAME = 'streamsb'  # type: ignore
    _SEM = Semaphore(8)

    @on_exception
    @dec_on_driver_timeout
    @limiter_1.ratelimit("streamsb", delay=True)
    def _send_request(self, url, **kwargs):

        pre = f'[send_request][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'

        driver = kwargs.get('driver', None)

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
                with StreamSBIE._SEM:
                    return func(*args, **kwargs)
            return wrapper

    @synchronized()
    def _get_entry(self, url, **kwargs):

        pre = f'[get_entry_by_har][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'

        videoid, dom = try_get(re.search(self._VALID_URL, url), lambda x: x.group('id', 'domain'))  # type: ignore
        url_dl = f"https://{dom}/e/{videoid}.html"

        _har_file = None
        try:

            for _ in range(3):

                _port = self.find_free_port()
                driver = self.get_driver(host='127.0.0.1', port=_port)
                _cont = True
                m3u8_doc = None
                m3u8_url = None
                try:
                    with self.get_har_logs('streamsb', videoid, msg=pre, port=_port) as harlogs:

                        _har_file = harlogs.har_file
                        self._send_request(url_dl, driver=driver)
                        if self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "video"))):
                            _cont = False
                            self.wait_until(driver, 2)
                finally:
                    self.rm_driver(driver)

                if not _cont:

                    m3u8_url, m3u8_doc = try_get(
                        self.scan_for_request(r"master.m3u8.+$", har=_har_file),  # type: ignore
                        lambda x: (x.get('url'), x.get('content')) if x else (None, None))
                    if not m3u8_url or not m3u8_doc:
                        _cont = True

                if _cont:
                    time.sleep(5)
                else:
                    break

            _headers = {'Accept': '*/*', 'Accept-Encoding': 'gzip, deflate, br', 'Accept-Language': 'en-US,en;q=0.5', 'Origin': f"https://{dom}", 'Referer': f"https://{dom}/"}

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

            info = self.scan_for_json(StreamSBIE._DOMAINS, har=_har_file, _all=True)
            self.logger_debug(info)
            _title = get_first(info, ('stream_data', 'title'), ('title'))
            if not _title:
                raise ExtractorError('Couldnt get title')

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
                'extractor_key': 'StreamSB',
                'extractor': 'streamsb',
                'webpage_url': url}

            try:
                _duration = self._extract_m3u8_vod_duration(_formats[0]['url'], videoid, headers=_formats[0]['http_headers'])
                if _duration:
                    _entry.update({'duration': _duration})
            except Exception as e:
                self.logger_info(f"{pre}: error trying to get vod {repr(e)}")

            return _entry

        except Exception as e:
            logger.exception(f"{pre} {repr(e)}")
            raise ExtractorError(f"Couldnt get video entry - {repr(e)}")
        finally:
            if _har_file:
                try:
                    if os.path.exists(_har_file):
                        os.remove(_har_file)
                except OSError:
                    return self.logger_info(f"{pre}: Unable to remove the har file")

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
