from .common import InfoExtractor
from ..compat import compat_b64decode
from ..utils import (
    int_or_none,
    js_to_json,
    parse_count,
    parse_duration,
    traverse_obj,
    try_get,
    unified_timestamp,
)


class DaftsexIE(InfoExtractor):
    _VALID_URL = r'https?://(?:www\.)?daftsex\.com/watch/(?P<id>-?\d+_\d+)'
    _TESTS = [{
        'url': 'https://daftsex.com/watch/-35370899_456246186',
        'md5': 'd95135e6cea2d905bea20dbe82cda64a',
        'info_dict': {
            'id': '-35370899_456246186',
            'ext': 'mp4',
            'title': 'just relaxing',
            'description': 'just relaxing - Watch video Watch video in high quality',
            'upload_date': '20201113',
            'timestamp': 1605261911,
            'thumbnail': r're:https://[^/]+/impf/-43BuMDIawmBGr3GLcZ93CYwWf2PBv_tVWoS1A/dnu41DnARU4\.jpg\?size=800x450&quality=96&keep_aspect_ratio=1&background=000000&sign=6af2c26ff4a45e55334189301c867384&type=video_thumb',
        },
    }, {
        'url': 'https://daftsex.com/watch/-156601359_456242791',
        'info_dict': {
            'id': '-156601359_456242791',
            'ext': 'mp4',
            'title': 'Skye Blue - Dinner And A Show',
            'description': 'Skye Blue - Dinner And A Show - Watch video Watch video in high quality',
            'upload_date': '20200916',
            'timestamp': 1600250735,
            'thumbnail': 'https://psv153-1.crazycloud.ru/videos/-156601359/456242791/thumb.jpg?extra=i3D32KaBbBFf9TqDRMAVmQ',
        },
    }]

    def _real_extract(self, url):
        video_id = self._match_id(url)
        webpage = self._download_webpage(url, video_id)
        title = self._html_search_meta('name', webpage, 'title')
        timestamp = unified_timestamp(self._html_search_meta('uploadDate', webpage, 'Upload Date', default=None))
        description = self._html_search_meta('description', webpage, 'Description', default=None)

        duration = parse_duration(self._search_regex(
            r'Duration: ((?:[0-9]{2}:){0,2}[0-9]{2})',
            webpage, 'duration', fatal=False))
        views = parse_count(self._search_regex(
            r'Views: ([0-9 ]+)',
            webpage, 'views', fatal=False))

        player_hash = self._search_regex(
            r'DaxabPlayer\.Init\({[\s\S]*hash:\s*"([0-9a-zA-Z_\-]+)"[\s\S]*}',
            webpage, 'player hash')
        player_color = self._search_regex(
            r'DaxabPlayer\.Init\({[\s\S]*color:\s*"([0-9a-z]+)"[\s\S]*}',
            webpage, 'player color', fatal=False) or ''

        embed_page = self._download_webpage(
            'https://daxab.com/player/%s?color=%s' % (player_hash, player_color),
            video_id, headers={'Referer': url})
        video_params = self._parse_json(
            self._search_regex(
                r'window\.globParams\s*=\s*({[\S\s]+})\s*;\s*<\/script>',
                embed_page, 'video parameters'),
            video_id, transform_source=js_to_json)

        server_domain = 'https://%s' % compat_b64decode(video_params['server'][::-1]).decode('utf-8')

        cdn_files = traverse_obj(video_params, ('video', 'cdn_files')) or {}
        if cdn_files:
            formats = []
            for format_id, format_data in cdn_files.items():
                ext, height = format_id.split('_')
                formats.append({
                    'format_id': format_id,
                    'url': f'{server_domain}/videos/{video_id.replace("_", "/")}/{height}.mp4?extra={format_data.split(".")[-1]}',
                    'height': int_or_none(height),
                    'ext': ext,
                })

            return {
                'id': video_id,
                'title': title,
                'formats': formats,
                'description': description,
                'duration': duration,
                'thumbnail': try_get(video_params, lambda vi: 'https:' + compat_b64decode(vi['video']['thumb']).decode('utf-8')),
                'timestamp': timestamp,
                'view_count': views,
                'age_limit': 18,
            }

        item = self._download_json(
            f'{server_domain}/method/video.get/{video_id}', video_id,
            headers={'Referer': url}, query={
                'token': video_params['video']['access_token'],
                'videos': video_id,
                'ckey': video_params['c_key'],
                'credentials': video_params['video']['credentials'],
            })['response']['items'][0]

        formats = []
        for f_id, f_url in item.get('files', {}).items():
            if f_id == 'external':
                return self.url_result(f_url)
            ext, height = f_id.split('_')
            height_extra_key = traverse_obj(video_params, ('video', 'partial', 'quality', height))
            if height_extra_key:
                formats.append({
                    'format_id': f'{height}p',
                    'url': f'{server_domain}/{f_url[8:]}&videos={video_id}&extra_key={height_extra_key}',
                    'height': int_or_none(height),
                    'ext': ext,
                })

        thumbnails = []
        for k, v in item.items():
            if k.startswith('photo_') and v:
                width = k.replace('photo_', '')
                thumbnails.append({
                    'id': width,
                    'url': v,
                    'width': int_or_none(width),
                })

        return {
            'id': video_id,
            'title': title,
            'formats': formats,
            'comment_count': int_or_none(item.get('comments')),
            'description': description,
            'duration': duration,
            'thumbnails': thumbnails,
            'timestamp': timestamp,
            'view_count': views,
            'age_limit': 18,
        }
'''
import re

from .common import InfoExtractor
from ..utils import (
    ExtractorError, int_or_none, 
    std_headers,
    sanitize_filename,
    js_to_json
)


import httpx
import time
from urllib.parse import unquote
import base64
import hashlib
import json


class DaftSexIE(InfoExtractor):
    IE_NAME = 'daftsex'
    _VALID_URL = r'https?://(www.)?daftsex\.com/watch/(?P<id>[a-zA-Z0-9_-]+)(?:$|/)'
    

    def _get_info(self, url, client):
        
        count = 0
        try:
            
            _res = None
            while (count<3):
                
                try:
                    
                    res = client.head(url)
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

        
        
        try:
        
            
            _timeout = httpx.Timeout(15, connect=15)        
            _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
            client = httpx.Client(timeout=_timeout, limits=_limits, headers=std_headers, follow_redirects=True, verify=(not self.get_param('nocheckcertificate')))            
            
            self.report_extraction(url)
            
            webpage = client.get(url).text
            mobj = re.findall(r'(hash|color):\"([^\"]+)\"',webpage.replace(" ",""))
            if not mobj: raise ExtractorError("no info about embed url")
            
            _data = dict(mobj)
            
            #self.to_screen(_data)
            
            mobj = re.findall(r'og:title\" +content=\"([^\"]+)\"', webpage)
            if mobj:
                _title = sanitize_filename(mobj[0],restricted=True)
            else:
                _title = "video"
            
            _url = f"https://daxab.com/player/{_data['hash']}?color={_data['color']}"
            
            webpage2 = client.get(_url,headers={'referer': 'https://daftsex.com/'}).text       
            #mobj = re.findall(r'(id|server|c_key|access_token|credentials):\"([^\"]+)"',webpage2.replace(" ",""))
            mobj = re.findall(r'window.globParams = ({[^\;]+);',webpage2)
            if not mobj: raise ExtractorError("no video info")
            #_data2 = dict(mobj)
            _data2 = json.loads(js_to_json(mobj[0]))
            #self.to_screen(_data2)
            
            _host = base64.b64decode(_data2['server'][::-1]).decode('utf-8')
            _videoid = str(int(hashlib.sha256(_data2['video']['id'].encode('utf-8')).hexdigest(),16) % 10**8)
            _formats = []
            if _data2['video'].get('credentials'):
                _url2 = f"https://{_host}/method/video.get/{_data2['video']['id']}?token={_data2['video']['access_token']}&videos={_data2['video']['id']}&ckey={_data2['c_key']}&credentials={_data2['video']['credentials']}"
                _data3 = client.get(_url2, headers={'referer':'https://dabax.com/', 'origin':'https://dabax.com'}).json()
                
                if not _data3: raise ExtractorError("no info video json")
                
                #self.to_screen(_data3)
                
                
                try:
                    _info_formats = _data3.get('response').get('items')[0].get('files')
                
                except Exception as e:
                    raise ExtractorError(e)
                
                if not _info_formats: raise ExtractorError("no info video")
                
                #self.to_screen(_info_formats)
            
               
                
                for _fid, _furl in _info_formats.items():
                    _info = self._get_info(_furl.replace("https://",f"https://{_host}/"), client)
                    _formats.append({
                        'format_id': _fid,
                        'ext' : 'mp4',
                        'url': _info.get('url'),
                        'filesize': _info.get('filesize')
                        
                    })
            else:
                _info_formats = _data2['video'].get('cdn_files')
                if not _info_formats: raise ExtractorError("no info video")
                
                
                for _fid, _furl in _info_formats.items():
                    _info = self._get_info(f"https://{_host}/videos/{_data2['video']['id'].split('_')[0]}/{_data2['video']['id'].split('_')[1]}/{_furl.replace('.','?extra=')}", client)
                    _formats.append({
                        'format_id': _fid,
                        'ext' : 'mp4',
                        'url': _info.get('url'),
                        'filesize': _info.get('filesize')
                        
                    })
                
            
            if not _formats: raise ExtractorError("no formats")
            self._sort_formats(_formats)
        except Exception as e:
            self.to_screen(e)
            raise
            
        finally:
            client.close()

        return {
            'id': _videoid,
            'title': _title,
            'formats': _formats,
            'ext': 'mp4'
        }
'''


