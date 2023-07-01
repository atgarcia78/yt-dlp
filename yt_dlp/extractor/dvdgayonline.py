import re
import os
import html
from .commonwebdriver import (
    SeleniumInfoExtractor,
    HTTPStatusError,
    ConnectError,
    ReExtractInfo,
    dec_on_driver_timeout,
    limiter_1,
    limiter_5,
    my_dec_on_exception,
    By,
    ec,
    cast,
    subnright,
    get_host,
    raise_extractor_error,
    raise_reextract_info,
    WebElement
)
from ..utils import (
    ExtractorError,
    sanitize_filename,
    try_get,
    try_call,
    get_first,
    traverse_obj,
    get_elements_by_class
)

import functools
from threading import Semaphore

import logging
logger = logging.getLogger('dvdgayonline')

on_exception = my_dec_on_exception(
    (TimeoutError, ExtractorError), raise_on_giveup=False, max_tries=3, jitter="my_jitter", interval=5)

on_retry_vinfo = my_dec_on_exception(
    ReExtractInfo, raise_on_giveup=False, max_tries=3, jitter="my_jitter", interval=5)


class error_or_video:
    def __call__(self, driver):
        elvideo = driver.find_elements(By.TAG_NAME, 'video')
        if not elvideo:
            _alert = driver.find_element(By.TAG_NAME, 'html').text.lower()
            if any([_ in _alert for _ in ['video was deleted', 'doesn\'t exist']]):
                return {'error': _alert.replace('\n', ' ')}
            else:
                return False
        else:
            return {'video': elvideo[0]}


class DVDGayOnlineIE(SeleniumInfoExtractor):

    _VALID_URL = r'https?://dvdgayonline.com/movies/.*'
    IE_NAME = 'dvdgayonline'  # type: ignore
    _SEM = Semaphore(8)
    _POST_URL = 'https://dvdgayonline.com/wp-admin/admin-ajax.php'
    KEYS_ORDER = ['realgalaxy', 'vflix', 'dood', 'streamtape']

    @on_exception
    @dec_on_driver_timeout
    @limiter_5.ratelimit("dvdgayonline", delay=True)
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

    @on_exception
    @limiter_1.ratelimit("dvdgayonline2", delay=True)
    def get_url_player(self, url, postid, nplayer):
        data = {
            'action': 'doo_player_ajax',
            'post': str(postid),
            'nume': str(nplayer),
            'type': 'movie'}
        headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Referer': url,
            'Origin': 'https://dvdgayonline.com'}

        return try_get(self.send_http_request(self._POST_URL, _type="POST", headers=headers, data=data),
                       lambda x: traverse_obj(x.json(), 'embed_url') if x else None)

    @on_retry_vinfo
    def _get_entry_realgalaxy(self, url, postid, nplayer, _pre):
        '''
        embed videos of realgalaxy only can be watched within dvdgsayonline domain
        '''
        pre = f'{_pre}[realgalaxy]'
        _har_file = None

        try:
            _port = self.find_free_port()
            driver = self.get_driver(host='127.0.0.1', port=_port)
            _har_file = None

            try:
                with self.get_har_logs('gvdgayonline', videoid=postid, msg=pre, port=_port) as harlogs:

                    _har_file = harlogs.har_file
                    self._send_request(url, driver=driver)
                    self.wait_until(driver, 1)
                    _players = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CLASS_NAME, 'server')))
                    if not _players or not (_player := cast(WebElement, traverse_obj(_players, nplayer - 1))) or 'realgalaxy' not in _player.text:
                        raise_extractor_error(f'{pre} cant find realgalaxy player')
                    else:
                        _player.click()

                    self.wait_until(driver, 1)
                    ifr = self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "iframe")))
                    driver.switch_to.frame(ifr)
                    self.wait_until(driver, 1)
                    _res = cast(dict, self.wait_until(driver, 30, error_or_video()))
                    if _res and (_error := _res.get('error')):
                        raise_extractor_error(f'{pre} {_error}')

                    self.wait_until(driver, 2)

            except ReExtractInfo:
                raise
            except Exception as e:
                self.report_warning(f"{pre} {repr(e)}")
                raise
            finally:
                self.rm_driver(driver)

            m3u8_doc = None
            m3u8_url = None
            urlembed = None

            urlembed = cast(str, try_get(self.scan_for_json(r'admin-ajax.php$', har=_har_file, _method="POST"), lambda x: x.get('embed_url') if x else None))
            if not urlembed or 'realgalaxy' not in urlembed:
                raise_reextract_info(f"{pre} couldnt get urlembed")

            dom = get_host(urlembed)
            videoid = traverse_obj(try_get(re.search(r'https?://%s/e/(?P<id>[\dA-Za-z]+)(\.html)?' % dom, urlembed), lambda x: x.groupdict()), 'id')
            if not videoid:
                raise_reextract_info(f'{pre} Couldnt get videoid')

            info = self.scan_for_json(r'%s/' % dom, har=_har_file, _all=True)
            self.logger_debug(info)
            if (_error := get_first(info, ('error'))):
                raise_reextract_info(f'{pre} {_error}')
            _title = cast(str, get_first(info, ('stream_data', 'title'), ('title')))
            if not _title:
                raise_reextract_info(f'{pre} Couldnt get title')

            _title = try_get(re.findall(r'(1080p|720p|480p)', _title), lambda x: _title.split(x[0])[0]) or _title
            _title = re.sub(r'(\s*-\s*202)', ' 202', _title)
            _title = _title.replace('mp4', '').replace('mkv', '').strip(' \t\n\r\f\v-_')

            m3u8_url, m3u8_doc = try_get(
                self.scan_for_request(r"master.m3u8.+$", har=_har_file),  # type: ignore
                lambda x: (x.get('url'), x.get('content')) if x else (None, None))
            if (m3u8_doc and '404 Not Found' in m3u8_doc):
                m3u8_doc = None

            _headers = {'Accept': '*/*', 'Accept-Encoding': 'gzip, deflate, br', 'Accept-Language': 'en-US,en;q=0.5',
                        'Origin': f"https://{dom}", 'Referer': f"https://{dom}/"}

            if not m3u8_url:
                if not (m3u8_url := cast(str, get_first(info, ('stream_data', 'file')))):
                    raise_reextract_info(f'{pre} Couldnt get video info')

            if not m3u8_doc:
                if not (m3u8_doc := try_get(self._send_request(m3u8_url, headers=_headers), lambda x: x.text)):
                    raise_reextract_info(f'{pre} Couldnt get video info')

            m3u8_url, m3u8_doc = cast(str, m3u8_url), cast(str, m3u8_doc)

            _formats = []
            _subtitles = {}

            if 'SDR,AUDIO="audio' in m3u8_doc:
                m3u8_doc = m3u8_doc.replace('SDR,AUDIO="audio0"', 'SDR').replace('SDR,AUDIO="audio1"', 'SDR')
                m3u8_doc = subnright('index-v1-a1', 'index-v1-a2', m3u8_doc, 3)

            _formats, _subtitles = self._parse_m3u8_formats_and_subtitles(
                m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")

            if not _formats:
                raise_reextract_info(f'{pre} Couldnt get video formats')

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
                'extractor_key': 'DVDGayOnline',
                'extractor': 'dvdgayonline',
                'webpage_url': url}

            try:
                _duration = self._extract_m3u8_vod_duration(_formats[0]['url'], videoid, headers=_formats[0]['http_headers'])
                if _duration:
                    _entry.update({'duration': _duration})
            except Exception as e:
                self.logger_debug(f"{pre}: error trying to get vod {repr(e)}")

            return _entry

        except ReExtractInfo:
            raise
        except ExtractorError:
            raise
        except Exception as e:
            logger.exception(f"{pre} {repr(e)}")
            raise ExtractorError(f"{pre} Couldnt get video entry - {repr(e)}")
        finally:
            if _har_file:
                try:
                    if os.path.exists(_har_file):
                        os.remove(_har_file)
                except OSError:
                    self.logger_debug(f"{pre}: Unable to remove the har file")

    class syncsem:
        def __call__(self, func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with DVDGayOnlineIE._SEM:
                    return func(*args, **kwargs)
            return wrapper

    @syncsem()
    def _get_entry(self, url, **kwargs):

        pre = f'[get_entry][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'

        _check = kwargs.get('check', True)

        webpage = cast(str, try_get(self._send_request(url), lambda x: html.unescape(re.sub('[\t\n]', '', x.text))))
        if not webpage or any([_ in webpage for _ in ('<title>Server maintenance', '<title>Video not found')]):
            raise_extractor_error(f"{pre} error 404 no webpage")
        postid = try_get(re.search(r'data-post=[\'"](?P<id>\d+)[\'"]', webpage), lambda x: x.group('id'))
        players = {el: i + 1 for i, el in enumerate(map(lambda x: x.split('.')[0], cast(list[str], get_elements_by_class('server', webpage))))}
        if not players:
            raise_extractor_error(f"{pre} couldnt find players")

        for _key in DVDGayOnlineIE.KEYS_ORDER:
            try:
                if _key in players and (urlembed := self.get_url_player(url, postid, players[_key])):
                    self.logger_info(f'{pre}[{_key}] {urlembed}')
                    if _key == 'realgalaxy':
                        _entry = self._get_entry_realgalaxy(url, postid, players[_key], pre)
                        if _entry:
                            self.logger_debug(f"{pre}[{_key}] OK got entry video")
                            return _entry
                        else:
                            self.logger_debug(f"{pre}[{_key}] WARNING not entry video")
                    else:
                        ie = self._get_extractor(urlembed)
                        _entry = ie._get_entry(urlembed, check=_check, msg=pre)
                        if _entry:
                            self.logger_debug(f"{pre}[{_key}] OK got entry video")
                            return _entry
                        else:
                            self.logger_debug(f"{pre}[{_key}] WARNING not entry video")
            except Exception as e:
                self.logger_debug(f"{pre}[{_key}] WARNING error entry video {repr(e)}")
            finally:
                players.pop(_key, None)

        if players:
            for _key, nplayer in players.items():
                if (urlembed := self.get_url_player(url, postid, nplayer)):
                    self.logger_info(f'{pre}[{_key}] {urlembed}')
                    if (_valid := self._is_valid(urlembed, msg=pre, inc_error=True)) and (_valid is True):
                        return self.url_result(urlembed, original_url=url)
                    else:
                        self.report_warning(f"{pre}[{_key}] {_valid.get('error')}")

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
