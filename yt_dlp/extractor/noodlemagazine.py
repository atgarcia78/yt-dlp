import time

from .common import InfoExtractor
from ..utils import (
    int_or_none,
    parse_count,
    parse_duration,
    unified_strdate,
)
from ..utils.traversal import traverse_obj


class NoodleMagazineIE(InfoExtractor):
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
            'age_limit': 18,
        },
    }

    def _real_extract(self, url):
        video_id = self._match_id(url)
        webpage = self._download_webpage(url, video_id)
        title = self._og_search_title(webpage)
        duration = parse_duration(self._html_search_meta('video:duration', webpage, 'duration', default=None))
        description = self._og_search_property('description', webpage, default='').replace(' watch online hight quality video', '')
        tags = self._html_search_meta('video:tag', webpage, default='').split(', ')
        view_count = parse_count(self._html_search_meta('ya:ovs:views_total', webpage, default=None))
        like_count = parse_count(self._html_search_meta('ya:ovs:likes', webpage, default=None))
        upload_date = unified_strdate(self._html_search_meta('ya:ovs:upload_date', webpage, default=''))


        for _ in range(10):
            try:
                playlist_info = self._parse_json(
                    self._search_regex(
                        r'window.playlist\s*=\s*([^;]+);', webpage, 'playlist',
                        default='{}'),
                    video_id, fatal=False)

                formats = []
                for source in traverse_obj(playlist_info, ('sources', lambda _, v: v['file'])):
                    if 'srcIp=' in source['file']:
                        raise ValueError('url incorrect')
                    if source.get('type') == 'hls':
                        formats.extend(self._extract_m3u8_formats(
                            source['file'], video_id, 'mp4', fatal=False, m3u8_id='hls'))
                    else:
                        formats.append(traverse_obj(source, {
                            'url': ('file', {str}),
                            'format_id': 'label',
                            'height': ('label', {int_or_none}),
                            'ext': 'type',
                        }))
                break
            except ValueError:
                time.sleep(2)
                self._downloader.cookiejar.clear('.noodlemagazine.com')
                self._downloader.cookiejar.clear('noodlemagazine.com')
                self._download_webpage('https://noodlemagazine.com/new-video', video_id)
                webpage = self._download_webpage(url, video_id)


        return {
            'id': video_id,
            'formats': formats,
            'title': title,
            'thumbnail': self._og_search_property('image', webpage, default=None) or playlist_info.get('image'),
            'duration': duration,
            'description': description,
            'tags': tags,
            'view_count': view_count,
            'like_count': like_count,
            'upload_date': upload_date,
            'age_limit': 18,
        }
