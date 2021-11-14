from __future__ import unicode_literals

import re

from .common import InfoExtractor
from ..utils import (
  
    ExtractorError,
    int_or_none,
    url_or_none,
    sanitize_filename,
    std_headers,
    determine_ext
)

import demjson
import httpx
import time
from urllib.parse import unquote

class RedTubeIE(InfoExtractor):
    _VALID_URL = r'https?://(?:.+?\.)?redtube\.com/(\?id=)?(?P<id>(\d+))'
    _TESTS = [{
        'url': 'http://www.redtube.com/66418',
        'md5': 'fc08071233725f26b8f014dba9590005',
        'info_dict': {
            'id': '66418',
            'ext': 'mp4',
            'title': 'Sucked on a toilet',
            'upload_date': '20110811',
            'duration': 596,
            'view_count': int,
            'age_limit': 18,
        }
    }, {
        'url': 'http://embed.redtube.com/?bgcolor=000000&id=1443286',
        'only_matching': True,
    }, {
        'url': 'http://it.redtube.com/66418',
        'only_matching': True,
    }]

    @staticmethod
    def _extract_urls(webpage):
        return re.findall(
            r'<iframe[^>]+?src=["\'](?P<url>(?:https?:)?//embed\.redtube\.com/\?.*?\bid=\d+)',
            webpage)
        
        
    def _get_info(self, url):
        
        count = 0
        try:
            
            _res = None
            while (count<3):
                
                try:
                    
                    res = httpx.head(url, headers=std_headers)
                    if res.status_code > 400:
                        time.sleep(1)
                        count += 1
                    else: 
                        _size = int_or_none(res.headers.get('content-length'))
                        _url = unquote(str(res.url))
                        if _size and _url:
                            _res = {'url': _url, 'filesize': _size}                         
                            break
                        else: count += 1
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass
                
        return _res

    def _real_extract(self, url):
        video_id = self._match_id(url)
        
        _url = f'https://www.redtube.com/{video_id}'
        #_url = f'https://embed.redtube.com/?id={video_id}'
        webpage = self._download_webpage(_url, video_id)

        ERRORS = (
            (('video-deleted-info', '>This video has been removed'), 'has been removed'),
            (('private_video_text', '>This video is private', '>Send a friend request to its owner to be able to view it'), 'is private'),
        )

        for patterns, message in ERRORS:
            if any(p in webpage for p in patterns):
                raise ExtractorError(
                    'Video %s %s' % (video_id, message), expected=True)




        formats = []
        sources = self._parse_json(
            self._search_regex(
                r'sources\s*:\s*({.+?})', webpage, 'source', default='{}'),
            video_id, fatal=False)
        if sources and isinstance(sources, dict):
            for format_id, format_url in sources.items():
                if format_url:
                    formats.append({
                        'url': format_url,
                        'format_id': format_id,
                        'height': int_or_none(format_id),
                    })
        medias = self._parse_json(
            self._search_regex(
                r'mediaDefinition["\']?\s*:\s*(\[.+?}\s*\])', webpage,
                'media definitions', default='{}'),
            video_id, fatal=False)
        if medias and isinstance(medias, list):
            for media in medias:
                format_url = url_or_none(media.get('videoUrl'))
                if not format_url:
                    continue
                if media.get('format') == 'hls' or determine_ext(format_url) == 'm3u8':
                    formats.extend(self._extract_m3u8_formats(
                        format_url, video_id, 'mp4',
                        entry_protocol='m3u8_native', m3u8_id='hls',
                        fatal=False))
                    continue
                format_id = media.get('quality')
                formats.append({
                    'url': format_url,
                    'ext': 'mp4',
                    'format_id': format_id,
                    'height': int_or_none(format_id),
                })
        if not formats:
            video_url = self._html_search_regex(
                r'<source src="(.+?)" type="video/mp4">', webpage, 'video URL')
            formats.append({'url': video_url, 'ext': 'mp4'})
        self._sort_formats(formats)

                
        mobj = re.findall(r'playervars: (\{.+?\}),\n',webpage)
        info_desc = demjson.decode(mobj[0]) if mobj else None
        if info_desc:
            
            _formats = []
            
            _desc_list = info_desc.get('mediaDefinitions')
            
            for _desc in _desc_list:
                if  _desc['format'] == 'mp4':
                    std_headers['Referer'] = _url
                    res = httpx.get(_desc.get('videoUrl'), headers=std_headers)
                    _media_list = res.json()
                    for _media in _media_list:                   
                        _info_video = self._get_info(_media.get('videoUrl'))
                        _formats.append({'format_id' : f'http_{_media.get("quality")}', 'url' : _info_video.get('url'), 'resolution': f'{_media.get("quality")}p', 'filesize': _info_video.get('filesize'), 'ext': 'mp4'}) 
                        
            self._sort_formats(_formats)
            
            
            return({
                'id' : video_id,
                'title' : sanitize_filename(info_desc.get('video_title'), restricted=True),
                'formats' : _formats,
                'ext': 'mp4'
            })
            
            
  
        

        
