import hashlib
import re
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote


from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import By, ec, dec_on_exception, dec_on_exception2, dec_on_exception3, dec_retry_raise, SeleniumInfoExtractor, limiter_0_5, limiter_1, HTTPStatusError, ConnectError


class fast_forward:
    def __init__(self, orig, logger):
        self.url_orig = orig
        self.logger = logger
        self.pers_error = False
        self.init = True

    def __call__(self, driver):
        _curl = driver.current_url
        self.logger(f"{unquote(_curl)}:{unquote(self.url_orig)}")
        if "netdna-storage.com/download/" in _curl:
            return "OK"

        if self.init is True:
            self.url_orig = _curl
            self.init = False
            return False

        if unquote(_curl) != unquote(self.url_orig):
            self.url_orig = _curl
            return False

        elif "netdna-storage.com" in _curl:

            if 'file not found' in (_title := driver.title.lower()):
                return "Error 404"
            elif 'error' in _title:
                driver.refresh()
                return False
            else:
                if self.pers_error:
                    return "Error addon fast forward"
                else:
                    self.pers_error = True
                    driver.refresh()
                    return False

        else:
            return False


class NetDNAIE(SeleniumInfoExtractor):
    IE_NAME = "netdna"
    _VALID_URL = r'https?://(www\.)?netdna-storage\.com/f/[^/]+/(?P<title_url>[^\.]+)\.(?P<ext>[^\.]+)\..*'
    _DICT_BYTES = {'KB': 1024, 'MB': 1024 * 1024, 'GB': 1024 * 1024 * 1024}

    @dec_on_exception3
    @dec_on_exception2
    @limiter_0_5.ratelimit("netdna1", delay=True)
    def _send_request(self, url):

        try:
            res = self.send_http_request(url)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
            return

        if "internal server error" in res.text.lower():
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - internal server error")
        else:
            return res

    @dec_on_exception3
    @dec_on_exception2
    @limiter_1.ratelimit("netdna", delay=True)
    def _get_video_info(self, url):

        try:
            return self.get_info_for_format(url, headers={'referer': 'https://netdna-storage.com/'})
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    @dec_on_exception
    @limiter_1.ratelimit("netdna2", delay=True)
    def url_request(self, driver, url):

        driver.execute_script("window.stop();")
        driver.get(url)

    @dec_on_exception
    def get_format(self, formatid, ext, url, get_info):

        def getter(x):
            _url = x.group('file')
            if _url:
                res = {'url': _url}
                if get_info:
                    if (_info := self._get_video_info(_url)):
                        res = _info
                return res

        try:
            _info = try_get(
                self._send_request(url),
                lambda x: try_get(
                    re.search(r'file: \"(?P<file>[^\"]+)\"', x.text),
                    # lambda y: self._send_request(y.group('file'), "GET_INFO")
                    getter
                )
            )
            if not _info:
                raise ExtractorError('no video info')
            _format = {'format_id': formatid, 'url': _info.get('url'), 'ext': ext, 'http_headers': {'Referer': 'https://netdna-storage.com/'}}
            if (_filesize := _info.get('filesize')):
                _format.update({'filesize': _filesize})
            return _format

        except Exception as e:
            self.write_debug(repr(e))
            raise

    def get_video_info_url(self, url):

        title = None
        _num = None
        _unit = None

        try:

            webpage = try_get(self._send_request(url), lambda x: x.text if x else None)
            if not webpage:
                return ({'error': 'webpage nok 404'})

            _num_list = re.findall(r'File size: <strong>([^\ ]+)\ ([^\<]+)<', webpage)
            if _num_list:
                _num = _num_list[0][0].replace(',', '.')
                if _num.count('.') == 2:
                    _num = _num.replace('.', '', 1)
                _num = f"{float(_num):.2f}"
                _unit = _num_list[0][1]
            _title_list = re.findall(r'h1 class="h2">([^\.]+).([^\<]+)<', webpage)
            if _title_list:
                title = _title_list[0][0].upper().replace("-", "_")
                ext = _title_list[0][1].lower()

            if any((not title, not _num, not _unit)):
                return ({'error': 'no video info'})

            str_id = f"{title}{_num}"
            videoid = int(hashlib.sha256(str_id.encode('utf-8')).hexdigest(), 16) % 10**8

            return ({'id': str(videoid), 'url': url, 'title': title, 'ext': ext,
                    'name': f"{videoid}_{title}.{ext}", 'filesize': float(_num) * NetDNAIE._DICT_BYTES[_unit]})

        except Exception as e:
            return ({'error': repr(e)})

    def get_entry(self, url, **kwargs):

        _info_video = self.get_video_info_url(url)
        if (_error := _info_video.get('error')):
            raise ExtractorError(_error)
        _title_search = _info_video.get('title', '').replace("_", ",")
        _id = _info_video.get('id')

        _info = self._downloader.extract_info(f"https://gaybeeg.info/?s={_title_search}")

        _entries = _info.get('entries')
        for _entry in _entries:
            if _entry['id'] == _id:
                res = _entry  # devuelve el más antiguo

        return res

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        info_video = self.get_video_info_url(url)
        if (_error := info_video.get('error')):
            raise ExtractorError(_error)

        self.report_extraction(url)

        @dec_retry_raise
        def _get_entry_video():

            driver = self.get_driver()

            try:

                self.url_request(driver, url)  # using firefox extension universal bypass to get video straight forward

                el_res = self.wait_until(driver, 60, fast_forward(url, self.logger_debug), poll_freq=4)

                if el_res != 'OK':
                    if not el_res:
                        msg_error = f"[{url}] Bypass stopped at: {driver.current_url}"
                        self.to_screen(msg_error)
                    elif el_res in ["Error 404", "Error addon fast forward"]:
                        msg_error = f"[{url}] {el_res}"
                        self.to_screen(msg_error)
                    else:
                        msg_error = f"[{url}] Bypass stopped at: {driver.current_url}"
                        self.to_screen(msg_error)

                    raise ExtractorError(msg_error)

                else:

                    entry = None
                    try:

                        el_formats = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CSS_SELECTOR, "a.btn.btn--small")))

                        if el_formats:
                            if len(el_formats) > 1:
                                _get_info_video = True
                            else:
                                if not self.get_param('embed'):
                                    _get_info_video = True
                                else:
                                    _get_info_video = False

                            with ThreadPoolExecutor(thread_name_prefix='fmt_netdna', max_workers=len(el_formats)) as ex:
                                futures = [ex.submit(self.get_format, _el.text, info_video.get('ext'), _el.get_attribute('href'), _get_info_video) for _el in el_formats]

                            _formats = []

                            for fut in futures:
                                try:
                                    _res = fut.result()
                                    if _res:
                                        _formats.append(_res)

                                except Exception as e:
                                    msg_error = f"[{url}] error when getting formats {repr(e)}"
                                    self.to_screen(msg_error)

                            if _formats:
                                self._sort_formats(_formats)

                                entry = {
                                    'id': info_video.get('id'),
                                    'title': sanitize_filename(info_video.get('title'), restricted=True),
                                    'formats': _formats,
                                    'ext': info_video.get('ext'),
                                    'webpage_url': url,
                                    'extractor': 'netdna',
                                    'extractor_key': 'NetDNA',

                                }

                        else:
                            el_download = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "btn.btn--xLarge")))
                            if el_download:
                                try:
                                    _video_url = el_download.get_attribute('href')
                                    _formats = {'format_id': 'ORIGINAL',
                                                'url': _video_url,
                                                'ext': info_video.get('ext'),
                                                'http_headers': {'Referer': 'https://netdna-storage.com/'}}
                                    if not self.get_param('embed'):
                                        _info = self._get_video_info(_video_url)
                                        if _info:
                                            _formats.update({'url': _info['url'], 'filesize': _info['filesize']})

                                except Exception:
                                    msg_error = f"[{url}] error when getting formats"
                                    self.to_screen(msg_error)

                                entry = {
                                    'id': info_video.get('id'),
                                    'title': sanitize_filename(info_video.get('title'), restricted=True),
                                    'formats': [_formats],
                                    'ext': info_video.get('ext'),
                                    'webpage_url': url,
                                    'extractor': 'netdna',
                                    'extractor_key': 'NetDNA',
                                }

                        if not entry:
                            raise ExtractorError("no video info")
                        else:
                            return entry

                    except Exception as e:
                        lines = traceback.format_exception(*sys.exc_info())
                        self.logger_debug(f"{repr(e)}, \n{'!!'.join(lines)}")
                        raise

            except ExtractorError:
                raise
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.logger_debug(f"{repr(e)}\n{'!!'.join(lines)}")
                raise ExtractorError(repr(e))
            finally:
                self.rm_driver(driver)

        return _get_entry_video()
