from ..utils import (
    parse_duration,
    parse_count,
    traverse_obj,
    unified_strdate,
    ExtractorError,
    sanitize_filename,
    try_get
)
import html
from .commonwebdriver import dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_5, HTTPStatusError, ConnectError


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

    @dec_on_exception2
    @dec_on_exception3
    @limiter_5.ratelimit("noodlemagazine", delay=True)
    def _send_request(self, url, **kwargs):

        _type = kwargs.get('_type', None)
        headers = kwargs.get('headers', None)

        if not _type:

            try:
                self.logger_debug(f"[send_req] {self._get_url_print(url)}")
                return (self.send_http_request(url, headers=headers))
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

        elif _type == 'json':

            try:
                self.logger_debug(f"[send_req] {self._get_url_print(url)}")
                self._CLIENT.cookies.clear(domain=".noodlemagazine.com", path="/")
                res = self.send_http_request(url, headers=headers)
                info_json = res.json()
                _file = traverse_obj(info_json, ('sources', 0, 'file'))
                if not _file.startswith('http'):
                    raise ExtractorError('not valid url')
                else:
                    return info_json
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    def _real_extract(self, url):
        video_id = self._match_id(url)
        # webpage = self._download_webpage(url, video_id)
        webpage = try_get(self._send_request(url), lambda x: html.unescape(x.text))
        title = self._og_search_title(webpage)
        duration = parse_duration(self._html_search_meta('video:duration', webpage, 'duration', default=None))
        description = self._og_search_property('description', webpage, default='').replace(' watch online hight quality video', '')
        tags = self._html_search_meta('video:tag', webpage, default='').split(', ')
        view_count = parse_count(self._html_search_meta('ya:ovs:views_total', webpage, default=None))
        like_count = parse_count(self._html_search_meta('ya:ovs:likes', webpage, default=None))
        upload_date = unified_strdate(self._html_search_meta('ya:ovs:upload_date', webpage, default=''))

        key = self._html_search_regex(rf'/{video_id}\?(?:.*&)?m=([^&"\'\s,]+)', webpage, 'key')

        # playlist_info = self._download_json(f'https://noodlemagazine.com/playlist/{video_id}?m={key}', video_id, headers={'Referer': f'https://noodlemagazine.com/player/{video_id}?m={key}&a=1'})

        playlist_info = self._send_request(f'https://noodlemagazine.com/playlist/{video_id}?m={key}', _type="json", headers={'Referer': f'https://noodlemagazine.com/player/{video_id}?m={key}&a=1'})

        self.logger_debug(playlist_info)

        thumbnail = self._og_search_property('image', webpage, default=None) or playlist_info.get('image')

        formats = [{
            'format_id': source.get('label'),
            'url': source.get('file'),
            'height': int(source.get('label')),
            'ext': source.get('type'),
        } for source in playlist_info.get('sources')]

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
