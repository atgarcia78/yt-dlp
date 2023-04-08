import re
import html
import time
import atexit
from .commonwebdriver import (
    SeleniumInfoExtractor,
    dec_on_exception2,
    dec_on_exception3,
    HTTPStatusError,
    ConnectError,
    limiter_1,
    ReExtractInfo,
    By,
    ec
)
from ..utils import (
    ExtractorError,
    sanitize_filename,
    try_get,
    try_call,
    traverse_obj,
    get_element_text_and_html_by_tag,
    get_elements_html_by_class)

import functools
from threading import Lock

import logging
logger = logging.getLogger('streamsb')


class getvideourl:
    def __call__(self, driver):
        el_rct = driver.find_elements(By.CLASS_NAME, 'g-recaptcha')
        if el_rct:
            el_rct[0].click()
            time.sleep(0.5)
            _el_a = driver.find_element(By.CLASS_NAME, 'mb-5').find_element(By.TAG_NAME, 'a')
            if (_vurl := _el_a.get_attribute('href')) and 'sbbrisk.com/dl?op=download_orig' not in _vurl:
                return _vurl
            else:
                return False
        else:
            return False


class StreamSBIE(SeleniumInfoExtractor):

    _DOMAINS = r'(?:gaymovies\.top|sbanh\.com|sbbrisk\.com|watchonlinehd\.top)'
    _VALID_URL = r'''(?x)https?://(?:.+?\.)?(?P<domain>%s)/((?:d|e|v)/)?(?P<id>[\dA-Za-z]+)(\.html)?''' % _DOMAINS
    IE_NAME = 'streamsb'  # type: ignore
    _LOCK = Lock()
    _DRIVER = None

    @dec_on_exception3
    @dec_on_exception2
    def _get_video_info(self, url, **kwargs):

        pre = f'[get_video_info][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'
        _headers = kwargs.get('headers', {})

        _headers = {'Range': 'bytes=0-', 'Referer': _headers.get('Referer'),
                    'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors',
                    'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache',
                    'Cache-Control': 'no-cache'}

        with limiter_1.ratelimit(self.IE_NAME, delay=True):
            try:
                self.logger_debug(pre)
                return self.get_info_for_format(url, headers=_headers)
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
                with StreamSBIE._LOCK:
                    return func(*args, **kwargs)
            return wrapper

    def close(self):
        if StreamSBIE._DRIVER:
            self.rm_driver(StreamSBIE._DRIVER)

    @synchronized()
    def _get_entry(self, url, **kwargs):

        pre = f'[get_entry_by_har][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'

        videoid, dom = try_get(re.search(self._VALID_URL, url), lambda x: x.group('id', 'domain'))  # type: ignore
        url_dl = f"https://{dom}/e/{videoid}.html"

        if not StreamSBIE._DRIVER:
            StreamSBIE._DRIVER = self.get_driver(host='127.0.0.1', port='8080')
            atexit.register(self.close)

        try:

            with self.get_har_logs('streamsb', videoid, msg=pre) as harlogs:

                _har_file = harlogs.har_file
                self._send_request(url_dl, driver=StreamSBIE._DRIVER)
                self.wait_until(StreamSBIE._DRIVER, 30, ec.presence_of_element_located((By.TAG_NAME, "video")))
                self.wait_until(StreamSBIE._DRIVER, 5)

            _headers = {'Accept': '*/*', 'Accept-Encoding': 'gzip, deflate, br', 'Accept-Language': 'en-US,en;q=0.5', 'Origin': f"https://{dom}", 'Referer': f"https://{dom}/"}
            m3u8_url, m3u8_doc = try_get(
                self.scan_for_request(r"master.m3u8.+$", har=_har_file),  # type: ignore
                lambda x: (x.get('url'), x.get('content')) if x else (None, None))

            _formats = []
            if m3u8_doc and m3u8_url:
                _formats, _ = self._parse_m3u8_formats_and_subtitles(m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")

            if not _formats:
                raise ExtractorError('Couldnt get video formats')

            for _format in _formats:
                if (_head := _format.get('http_headers')):
                    _head.update(_headers)
                else:
                    _format.update({'http_headers': _headers})

            _title = traverse_obj(self.scan_for_json(r'/sources.+$', har=_har_file), ('stream_data', 'title'))

            _entry = {
                'id': videoid,
                'title': sanitize_filename(_title, restricted=True),
                'formats': _formats,
                'ext': 'mp4',
                'extractor_key': 'StreamSB',
                'extractor': 'streamsb',
                'webpage_url': url}

            return _entry

        except Exception as e:
            self.report_warning(f"{pre} {repr(e)}")
            raise ExtractorError(f"Couldnt get video entry - {repr(e)}")

    def _old_get_entry(self, url, **kwargs):

        check = kwargs.get('check', False)
        msg = kwargs.get('msg', None)
        videoid, dom = try_get(re.search(self._VALID_URL, url), lambda x: x.group('id', 'domain'))  # type: ignore

        pre = f'[get_entry][{self._get_url_print(url)}]'
        if msg:
            pre = f'{msg}{pre}'

        driver = None

        try:

            url_dl = f"https://{dom}/{videoid}.html"
            webpage = try_get(self._send_request(url_dl, msg=pre), lambda x: html.unescape(x.text) if not isinstance(x, dict) else x)
            if not webpage:
                raise ReExtractInfo("error to get webpage")
            _title = try_get(try_call(lambda: get_element_text_and_html_by_tag('h1', webpage)[0]), lambda x: re.sub(r'\[?\d+p\]?', '', x.replace('Download ', '')).strip())
            _sources = get_elements_html_by_class("block py-3 rounded-3 mb-3 text-reset d-block", webpage)
            if 'File owner disabled downloads' in webpage or not _title or not _sources:
                raise ReExtractInfo("video without download page, lets get HAR")

            _data = [try_get(re.findall(r'download_video\(([^\)]+)\)', _source), lambda x: {key: val for key, val in zip(['code', 'mode', 'hash'], x[0].replace("'", "").split(","))}) for _source in _sources]
            _res = [try_get(re.findall(r'(\d+)p', try_get(get_element_text_and_html_by_tag("span", _source), lambda y: y[0])), lambda x: x[0])  # type: ignore
                    for _source in _sources]

            if not _data or not _res:
                ExtractorError("error to get video details")

            for res, data in zip(_res, _data):
                if data and res:
                    data['res'] = int(res)
                    data['url'] = f"https://{dom}/dl?op=download_orig&id={data['code']}&mode={data['mode']}&hash={data['hash']}"

            _formats = []

            driver = self.get_driver()

            try:

                for data in _data:
                    if data:
                        self._send_request(data['url'], driver=driver)
                        _videourl = self.wait_until(driver, 30, getvideourl())

                        _format = {
                            'format_id': f"http-mp4-{data['res']}",
                            'url': _videourl,
                            'http_headers': {'Referer': f"https://{dom}/"},
                            'ext': 'mp4',
                            'height': data['res']
                        }

                        if check:
                            _video_info = self._get_video_info(_videourl, headers={'Referer': f"https://{dom}/"})
                            self.raise_from_res(_video_info, "no video info")
                            _format.update(_video_info)

                        _formats.append(_format)

            except Exception as e:
                logger.exception(f"[get_entry] {repr(e)}")
            finally:
                self.rm_driver(driver)

            if not _formats:
                raise ExtractorError("no formats")

            _entry = {
                'id': videoid,
                'title': sanitize_filename(_title, restricted=True),
                'formats': _formats,
                'ext': 'mp4',
                'extractor_key': 'StreamSB',
                'extractor': 'streamsb',
                'webpage_url': url}

            return _entry

        except ReExtractInfo as e:
            self.logger_info(f"{pre} {repr(e)}")
            # return self._get_entry_by_har(url, msg=msg)
        except Exception as e:
            logger.exception(repr(e))

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
