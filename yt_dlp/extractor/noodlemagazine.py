from ..utils import (
    parse_duration,
    parse_count,
    unified_strdate,
    ExtractorError,
    sanitize_filename,
    try_get,
    get_domain
)
import html
from .commonwebdriver import cast, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_5, HTTPStatusError, ConnectError


class NoodleMagazineIE(SeleniumInfoExtractor):
    _VALID_URL = r'https?://(?:www|adult\.)?noodlemagazine\.com/watch/(?P<id>[0-9-_]+)'
    _TEST = {
        'url': 'https://adult.noodlemagazine.com/watch/-67421364_456239604',
        'md5': '9e02aa763612929d0b4b850591a9248b',
        'info_dict': {
            'id': '-67421364_456239604',
            'title': 'Aria alexander manojob',
            'thumbnail': r're:^https://.*\.jpg',
            'ext': 'mp4',
            'duration': 903,
            'view_count': int,
            'like_count': int,
            'description': 'Aria alexander manojob',
            'tags': ['aria', 'alexander', 'manojob'],
            'upload_date': '20190218',
            'age_limit': 18
        }
    }

    @dec_on_exception3
    @dec_on_exception2
    @limiter_5.ratelimit("noodlemagazine", delay=True)
    def _get_info_for_format(self, url, **kwargs):

        _headers = kwargs.get('headers', {})
        _headers.update({'Accept': 'video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5',
                         'Range': 'bytes=0-', 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors',
                         'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'})
        self.logger_debug(f"[get_video_info] {url}")

        try:
            return self.get_info_for_format(url, headers=_headers)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
            return {"error_res": f"{repr(e)}"}

    @dec_on_exception3
    @dec_on_exception2
    @limiter_5.ratelimit("noodlemagazine2", delay=True)
    def _send_request(self, url, **kwargs):

        try:
            return self.send_http_request(url, **kwargs)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[send_request] {self._get_url_print(url)}: error - {repr(e)}")

    def _get_entry(self, url, **kwargs):

        video_id = self._match_id(url)
        webpage = try_get(self._send_request(url), lambda x: html.unescape(x.text))
        if not webpage:
            raise ExtractorError("no webpage")

        key = try_get(self._og_search_video_url(webpage), lambda x: x.split('m=')[1])
        if not key:
            key = self._html_search_regex(rf'/{video_id}\?(?:.*&)?m=([^&"\'\s,]+)', webpage, 'key')

        _headers = {'Referer': f'https://noodlemagazine.com/player/{video_id}?m={key}&a=1'}
        try:
            self._CLIENT.cookies.clear(domain='.noodlemagazine.com')
        except Exception:
            pass

        video_info = try_get(self._send_request(f'https://noodlemagazine.com/playlist/{video_id}?m={key}', headers=_headers), lambda x: x.json())

        if not video_info:
            ExtractorError("no video info")

        assert isinstance(video_info, dict)

        formats = []

        if (sources := video_info.get('sources')):
            sources = sorted(sources, key=lambda x: int(x.get('label', "0")), reverse=True)

            for i, source in enumerate(sources):

                _url = source.get('file')
                _format_id = source.get('label')
                _format = {
                    'format_id': _format_id,
                    'url': _url,
                    'height': int(source.get('label')),
                    'ext': source.get('type'),
                    'http_headers': {'Referer': 'https://noodlemagazine.com/'}}

                if i == 0:
                    _host = get_domain(_url)
                    _sem = self.get_ytdl_sem(_host)

                    with _sem:
                        _info_video = self._get_info_for_format(_url, headers={'Referer': 'https://noodlemagazine.com/'})
                    if _info_video:
                        _info_video = cast(dict, _info_video)

                    if not _info_video or 'error' in _info_video:
                        self.logger_debug(f"[{url}][{_format_id}] no video info")
                    else:
                        _format.update({'url': _info_video.get('url'), 'filesize': _info_video.get('filesize')})

                formats.append(_format)

        if not formats:
            raise ExtractorError("no formats")

        title = self._og_search_title(webpage)
        duration = parse_duration(self._html_search_meta('video:duration', webpage, 'duration', default=None))
        description = try_get(self._og_search_property('description', webpage, default=''), lambda x: x.replace(' watch online hight quality video', ''))
        tags = try_get(self._html_search_meta('video:tag', webpage, default=''), lambda x: x.split(', '))
        view_count = parse_count(self._html_search_meta('ya:ovs:views_total', webpage, default=None))
        like_count = parse_count(self._html_search_meta('ya:ovs:likes', webpage, default=None))
        upload_date = unified_strdate(self._html_search_meta('ya:ovs:upload_date', webpage, default=''))
        thumbnail = self._og_search_property('image', webpage, default=None) or video_info.get('image')

        return {
            'id': video_id.replace('-', '').replace('_', ''),
            'formats': formats,
            'title': sanitize_filename(title, restricted=True),
            'thumbnail': thumbnail,
            'duration': duration,
            'description': description,
            'tags': tags,
            'view_count': view_count,
            'like_count': like_count,
            'upload_date': upload_date,
            'age_limit': 18
        }

    def _real_extract(self, url):

        self.report_extraction(url)
        return self._get_entry(url)
