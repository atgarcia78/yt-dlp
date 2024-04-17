import logging
import os
import re

from yt_dlp_plugins.extractor.commonwebdriver import (
    By,
    ConnectError,
    HTTPStatusError,
    ReExtractInfo,
    SeleniumInfoExtractor,
    dec_on_driver_timeout,
    ec,
    limiter_1,
    my_dec_on_exception,
    raise_extractor_error,
    raise_reextract_info,
    subnright,
)

from ..utils import (
    ExtractorError,
    get_first,
    sanitize_filename,
    try_call,
    try_get,
)

logger = logging.getLogger('streamsb')

on_exception = my_dec_on_exception(
    (TimeoutError, ExtractorError), raise_on_giveup=False, max_tries=3, jitter="my_jitter", interval=5)

on_retry_vinfo = my_dec_on_exception(
    ReExtractInfo, raise_on_giveup=False, max_tries=3, jitter="my_jitter", interval=5)


class StreamSBIE(SeleniumInfoExtractor):

    _DOMAINS = r'(?:gaymovies\.top|sbanh\.com|sbbrisk\.com|watchonlinehd\.top|realgalaxy\.top)'
    _VALID_URL = r'''(?x)https?://(?:.+?\.)?(?P<domain>%s)/((?:d|e|v)/)?(?P<id>[\dA-Za-z]+)(\.html)?''' % _DOMAINS
    IE_NAME = 'streamsb'  # type: ignore

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
            driver.execute_script("window.stop();")
            driver.get(url)
        else:
            try:
                return self.send_http_request(url)
            except (HTTPStatusError, ConnectError) as e:
                _msg_error = f"{repr(e)}"
                self.logger_debug(f"{pre}: {_msg_error}")
                return {"error_res": _msg_error}

    @SeleniumInfoExtractor.syncsem()
    @on_retry_vinfo
    def _get_entry(self, url, **kwargs):

        pre = f'[get_entry][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'

        videoid, dom = try_get(
            re.search(self._VALID_URL, url),
            lambda x: x.group('id', 'domain'))  # type: ignore
        url_dl = f"https://{dom}/e/{videoid}.html"

        _har_file = None

        if "error" in (_res := self._is_valid(url_dl, inc_error=True)):
            raise_extractor_error(_res['error'])

        try:
            _port = self.find_free_port()
            driver = self.get_driver(host='127.0.0.1', port=_port)
            try:
                with self.get_har_logs('streamsb', videoid, msg=pre, port=_port) as harlogs:  # type: ignore
                    _har_file = harlogs.har_file
                    self._send_request(url_dl, driver=driver)
                    self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "video")))  # type: ignore
                    self.wait_until(driver, 1)  # type: ignore
            except ReExtractInfo:
                raise
            except Exception as e:
                self.logger_debug(f"{pre} {repr(e)}")
                raise_reextract_info(f'{pre} {repr(e)}')
            finally:
                self.rm_driver(driver)

            info = [_el['json'] for _el in self.scan_for_json(StreamSBIE._DOMAINS, har=_har_file, _all=True) or []]
            self.logger_debug(info)
            if (_error := get_first(info, ('error'))):
                raise_reextract_info(f'{pre} {_error}')

            _title = get_first(info, ('stream_data', 'title'), ('title'))
            if not isinstance(_title, str):
                raise ExtractorError('Couldnt get title')
            else:
                if _res := try_get(
                    re.findall(r'(1080p|720p|480p)', _title),  # type: ignore
                    lambda x: x[0]
                ):
                    _title = _title.split(_res)[0]

                _title = try_get(
                    re.sub(r'(\s*-\s*202)', ' 202', _title),
                    lambda x: x.replace('mp4', '').replace('mkv', '').strip(' \t\n\r\f\v-_.'))

            _headers = {
                'Origin': f"https://{dom}",
                'Referer': f"https://{dom}/"
            }

            m3u8_url, m3u8_doc = try_get(
                self.scan_for_request(r"master\.m3u8.+$", har=_har_file),  # type: ignore
                lambda x: (x.get('url'), x.get('content')) if x else (None, None))

            if not m3u8_url and not (m3u8_url := get_first(info, ('stream_data', 'file'))):
                raise_reextract_info(f'{pre} Couldnt get video info')

            if (not m3u8_doc and not (m3u8_doc := try_get(
                self._send_request(m3u8_url, headers=_headers),
                lambda x: x.text)
            )) or '404 not found' in m3u8_doc.lower():
                raise_reextract_info(f'{pre} Couldnt get video info')

            self.logger_debug(m3u8_doc)
            if isinstance(m3u8_doc, str):
                if 'SDR,AUDIO="audio' in m3u8_doc:
                    m3u8_doc = m3u8_doc.replace('SDR,AUDIO="audio0"', 'SDR').replace('SDR,AUDIO="audio1"', 'SDR')
                    m3u8_doc = subnright('index-v1-a1', 'index-v1-a2', m3u8_doc, 3)

                _formats, _subtitles = self._parse_m3u8_formats_and_subtitles(
                    m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")

                if not _formats:
                    raise_reextract_info(f'{pre} Couldnt get video formats')

                for _format in _formats:
                    if _format.setdefault('http_headers', _headers) != _headers:
                        _format['http_headers'].update(**_headers)

                if not _subtitles:
                    list_subt_urls = try_get(
                        self.scan_for_request(r"\.(?:srt|vtt)$", har=_har_file, _all=True),  # type: ignore
                        lambda x: [el.get('url') for el in x] if x else [])
                    if list_subt_urls:
                        def _get_info_subt(subturl):
                            _cc_lang = {'spanish': 'es', 'english': 'en'}
                            if subturl:
                                ext = subturl.rsplit('.', 1)[-1]
                                if (
                                    lang := _cc_lang.get(try_call(
                                        lambda: subturl.rsplit('.', 1)[0].rsplit('_', 1)[-1].lower()) or 'dummy')
                                ):
                                    return {'lang': lang, 'ext': ext}

                        for _url_subt in list_subt_urls:
                            if (_subt := _get_info_subt(_url_subt)):
                                if _lang := _subt.get('lang'):
                                    if _lang not in _subtitles:
                                        _subtitles[_lang] = []
                                    _subtitles[_lang].append({'url': _url_subt, 'ext': _subt.get('ext')})

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
                    if (
                        _duration := self._extract_m3u8_vod_duration(
                            _formats[0]['url'], videoid, headers=_formats[0]['http_headers'])
                    ):
                        _entry.update({'duration': _duration})
                except Exception as e:
                    self.logger_debug(f"{pre}: error trying to get vod {repr(e)}")

                return _entry

        except ReExtractInfo:
            raise
        except ExtractorError:
            raise
        except Exception as e:
            self.logger_debug(f"{pre} {repr(e)}")
            raise ExtractorError(f"Couldnt get video entry - {repr(e)}")
        finally:
            if _har_file:
                try:
                    if os.path.exists(_har_file):
                        os.remove(_har_file)
                except OSError:
                    self.logger_debug(f"{pre}: Unable to remove the har file")

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
