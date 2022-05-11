# coding: utf-8
from __future__ import unicode_literals

import hashlib
import html
import re

from backoff import constant, on_exception

from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import SeleniumInfoExtractor, limiter_5, limiter_10


class Mat6TubeIE(SeleniumInfoExtractor):
    IE_NAME = 'mat6tube'
    IE_DESC = 'mat6tube'
    _VALID_URL = r"https?://(?:www\.)?(?:adult\.)?mat6tube\.com/(?:watch|player)/(?P<id>\d+\_\d+)"
    _SITE_URL = "https://adult.mat6tube.com"

    @on_exception(constant, Exception, max_tries=5, interval=10)
    @limiter_5.ratelimit("mat6tube2", delay=True)  
    def _get_video_info(self, *args, **kwargs):
        
        return super().get_info_for_format(*args, **kwargs)
    
    @on_exception(constant, Exception, max_tries=5, interval=10)
    @limiter_10.ratelimit("mat6tube", delay=True)
    def _send_request(self, url, headers=None):        
        
        self.logger_info(f"[send_request] {url}") 
        res = self.send_request(url, headers=headers)
        res.raise_for_status()
        return res
    
    def _real_initialize(self):
        super()._real_initialize()
        
    

    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        video_id = self._match_id(url)
        _url = f'{self._SITE_URL}/watch/{video_id}'
                   
        webpage = try_get(self._send_request(_url), lambda x: html.unescape(x.text))
        if not webpage: raise ExtractorError("couldnt get video webpage")
            
        if not '/player/' in url:
            iplayer = try_get(re.findall(r'iplayer["\'] src=["\']([^"\']+)["\']', webpage), lambda x: x[0])
            if not iplayer: raise ExtractorError()            
            _url_player = f'{self._SITE_URL}{iplayer}'
        else: 
            _url_player = url
            if not 'adult.mat6tube.com' in _url_player: _url_player = _url_player.replace('mat6tube.com', 'adult.mat6tube.com')
                
        webpage2, urlh2 = try_get(self._send_request(_url_player, headers={'Referer': _url}), lambda x: (html.unescape(x.text), str(x.url)))
        if not webpage2: raise ExtractorError("couldnt get iplayer webpage")
        
        playlisturl = try_get(re.findall(r'playlistUrl=["\']([^"\']+)["\']', webpage2), lambda x: x[0])
        if not playlisturl: raise ExtractorError()
        
        data = try_get(self._send_request(f'{self._SITE_URL}{playlisturl}', headers={'Referer': urlh2}), lambda x: x.json())        
                
        if not data or not data.get('sources'): raise ExtractorError()
        
        _videoid = str(int(hashlib.sha256(video_id.encode('utf-8')).hexdigest(),16) % 10**8)
        
        _title = self._search_regex((r'\"name_\": "(?P<title>[^\"]+)\"', r'<h1>(?P<title>[^\<]+)\<', r'\"og:title\" content=\"(?P<title>[^\"]+)\"'), webpage, "title", fatal=False, default="no_title", group="title")
        
        _title = sanitize_filename(_title, restricted=True)
        
        _formats = [{
            'url': (_info:=(self._get_video_info(_el['file']) or {})).get('file') or _el['file'],
            'height': int(_el['label']),
            'ext': _el['type'],
            'filesize': _info.get('filesize'),
            'format_id': f"http{_el['label']}"
            
        } for _el in data['sources']]
        
        
        self._sort_formats(_formats)

        return {
            "id": _videoid,
            "title": _title,
            "formats": _formats
        }

        
