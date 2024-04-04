import html
import json
import random
import re
import string
import time
from hashlib import sha256

from .commonwebdriver import (
    ConnectError,
    ExtractorError,
    HTTPStatusError,
    ReExtractInfo,
    SeleniumInfoExtractor,
    limiter_0_1,
    limiter_0_05,
    my_dec_on_exception,
    raise_extractor_error,
    raise_reextract_info,
)
from ..utils import (
    get_domain,
    js_to_json,
    parse_qs,
    sanitize_filename,
    sanitize_url,
    traverse_obj,
    try_get,
    update_url,
)

on_exception_vinfo = my_dec_on_exception(
    (TimeoutError, ExtractorError), raise_on_giveup=False, max_tries=5, jitter="my_jitter", interval=1)

on_exception_req = my_dec_on_exception(
    (TimeoutError, ExtractorError), raise_on_giveup=False, max_tries=3, interval=0.1)

on_retry_vinfo = my_dec_on_exception(
    ReExtractInfo, raise_on_giveup=False, max_tries=10, jitter="my_jitter", interval=1)


class DoodStreamIE(SeleniumInfoExtractor):

    IE_NAME = 'doodstream'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?(?:d[0oO]+d|ds2play|ds2video|(d(oo)+d(?:s|stream)?))\.[^/]+/[ed]/(?P<id>[a-z0-9]+)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>%s)\1' % _VALID_URL]

    @on_exception_vinfo
    def _get_video_info(self, url, **kwargs):

        with kwargs.get('limiter', limiter_0_1).ratelimit("doodstream", delay=True):
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

    @on_exception_req
    def _send_request(self, url, **kwargs):

        _kwargs = kwargs.copy()
        pre = f'[send_req][{self._get_url_print(url)}]'
        if (msg := _kwargs.pop('msg', None)):
            pre = f'{msg}{pre}'
        with _kwargs.pop('limiter', limiter_0_1).ratelimit("doodstream2", delay=True):
            try:
                return self.send_http_request(url, **_kwargs)
            except (HTTPStatusError, ConnectError) as e:
                _msg_error = f"{repr(e)}"
                self.logger_debug(f"{pre}: {_msg_error}")

    @on_retry_vinfo
    def _get_entry(self, url, **kwargs):

        video_id = self._match_id(url)
        # domain = get_domain(url)
        domain = 'dood.to'
        url = f'https://{domain}/e/{video_id}'
        pre = f'[get_entry][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'
        check = kwargs.get('check', True)
        _kwargs = {'limiter': limiter_0_05 if check else limiter_0_1}
        _urlh, webpage = try_get(
            self._send_request(url, **_kwargs),
            lambda x: (x.url, html.unescape(x.text))) or (None, None)
        if not webpage:
            raise_extractor_error(f"{pre} error 404 no webpage")
        elif any([_ in webpage for _ in ('<title>Server maintenance', '<title>Video not found')]):
            raise_extractor_error(f"{pre} error 404 webpage")

        token = self._html_search_regex(r"[?&]token=([a-z0-9]+)[&']", webpage, 'token')

        if _urlh:
            domain = _urlh.host

        headers = {'Referer': f'https://{domain}/'}

        pass_md5 = self._html_search_regex(r"(/pass_md5.*?)'", webpage, 'pass_md5')

        def _getter(x):
            return ''.join([
                html.unescape(x.text),  # type: ignore
                *(random.choice(string.ascii_letters + string.digits) for _ in range(10)),
                f'?token={token}&expiry={int(time.time() * 1000)}'])

        video_url = try_get(
            self._send_request(f'https://{domain}{pass_md5}', headers=headers, **_kwargs), lambda x: _getter(x) if x else None)

        if not video_url:
            raise_extractor_error(f"{pre} couldnt get videourl")

        _format = {
            'format_id': 'http-mp4',
            'url': video_url,
            'http_headers': headers,
            'ext': 'mp4'
        }

        if check:
            with self.get_ytdl_sem(get_domain(video_url)):
                _videoinfo = self._get_video_info(video_url, msg=pre, headers=headers, **_kwargs)

            if not _videoinfo:
                self._count += 1
                self.report_warning(f"{pre} error 404: no video info")
                raise_reextract_info(f"{pre} error 404: no video info")

            elif _videoinfo['filesize'] >= 5000000 or self._count >= 9:
                _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize'], 'accept_ranges': _videoinfo['accept_ranges']})
            else:
                self._count += 1
                self.report_warning(f"{pre} error filesize[{_videoinfo['filesize']}] < 5MB")
                raise_reextract_info(f"{pre} error filesize[{_videoinfo['filesize']}] < 5MB")

        _subtitles = {}
        list_subts = [subt for subt in [
            json.loads(js_to_json(el)) for el in re.findall(r'addRemoteTextTrack\((\{[^\}]+\})', webpage)]  # type: ignore
            if subt.get('label', '').lower() in ('spanish', 'english')]

        if list_subts:

            def _get_info_subt(subt):
                _cc_lang = {'spanish': 'es', 'english': 'en'}
                if subt:
                    ext = subt.get('src').rsplit('.', 1)[-1]
                    lang = _cc_lang.get(subt.get('label').lower())
                    if lang:
                        return {'lang': lang, 'ext': ext, 'url': sanitize_url(subt.get('src'), scheme='https')}

            for _subt in list_subts:
                _subtinfo = _get_info_subt(_subt)
                if not _subtinfo:
                    continue
                _subtitles.setdefault(_subtinfo.get('lang'), []).append({'url': _subtinfo.get('url'), 'ext': _subtinfo.get('ext')})

        if not (title := self._og_search_title(webpage, default=None) or self._html_extract_title(webpage, default=None)):
            raise_extractor_error(f"{pre} error with title")

        title = try_get(re.findall(r'(1080p|720p|480p)', title), lambda x: title.split(x[0])[0] if x else title)  # type: ignore
        title = re.sub(r'(\s*-\s*202)', ' 202', title)  # type: ignore
        title = title.replace(' - DoodStream', '').replace('mp4', '').replace('mkv', '').strip(' \t\n\r\f\v-_')

        thumbnail = self._og_search_thumbnail(webpage, default=None)

        _entry = {
            'id': str(int(sha256(video_id.encode('utf-8')).hexdigest(), 16) % 10**12) if len(video_id) > 12 else video_id,
            'title': sanitize_filename(title, restricted=True),
            'formats': [_format],
            'subtitles': _subtitles,
            'thumbnail': thumbnail,
            'ext': 'mp4',
            'extractor_key': 'DoodStream',
            'extractor': 'doodstream',
            'webpage_url': str(_urlh)
        }

        if title[:6].replace('-', '').isdecimal():
            _entry['_try_title'] = True

        return _entry

    def _real_initialize(self):
        super()._real_initialize()
        self._count = 0

    def _real_extract(self, url):

        try:
            _check = traverse_obj(parse_qs(url), ("check", 0, {lambda x: x.lower() == 'yes'}), default=True)  # type: ignore
            return self._get_entry(update_url(url, query=''), check=_check)

        except ExtractorError:
            raise
        except Exception as e:
            raise_extractor_error(repr(e))
