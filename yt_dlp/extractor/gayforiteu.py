# coding: utf-8
from __future__ import unicode_literals

import re

from .commonwebdriver import SeleniumInfoExtractor
from ..utils import (
    ExtractorError, 
    sanitize_filename,
    
)

from urllib.parse import unquote
from ratelimit import limits, sleep_and_retry
from backoff import on_exception, constant


class GayForITEUIE(SeleniumInfoExtractor):
    
    _VALID_URL = r'https?://(?:www\.)gayforit\.eu/(?:playvideo.php\?vkey\=[^&]+&vid\=(?P<vid>[\w-]+)|video/(?P<id>[\w-]+))'

    
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @sleep_and_retry
    @limits(calls=1, period=1)
    def _send_request(self, url, videoid):
        
        webpage = self._download_webpage(url, videoid, "Downloading video webpage", fatal=True)
        if not webpage: raise ExtractorError("no video page info")
        else: return webpage
        
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @sleep_and_retry
    @limits(calls=1, period=5)    
    def get_info_for_format(self, *args, **kwargs):
        return super().get_info_for_format(*args, **kwargs)
    
    
    def _real_extract(self, url):
        
        mobj = re.search(self._VALID_URL, url)
        if mobj:
            videoid = mobj.group('id') or mobj.group('vid')

        webpage = self._send_request(url, videoid) 
        
        if not webpage: raise ExtractorError("no video page info")

        title = self._html_search_regex((r'<title>GayForIt\.eu - Free Gay Porn Videos - (.+?)</title>'), webpage, 'title')
        
        if title: title=title.strip()
        else: title="GayForIt_eu"
        
        video_url = self._search_regex(r'<source src=\"([^\"]+)\" type=\"video/mp4', webpage, 'videourl', default=None, fatal=False)

        if not video_url:
            raise ExtractorError("no video url")
        else: video_url = unquote(video_url)
        
        if not videoid:
            videoid = self._search_regex(r'content/(\d+)/mp4', video_url, 'videoid', default="no_id")
  
        self.to_screen(f"[video_url] {video_url}")
        _info_video = self.get_info_for_format(video_url, headers={"Referer" : "https://gayforit.eu/"}, verify=False)
        
        if not _info_video: raise ExtractorError("no video info")

        format_video = {
            'format_id' : "http-mp4",
            'url' : _info_video['url'],
            'filesize' : _info_video['filesize'],
            'ext' : 'mp4'
         }

        return {
            'id': videoid,
            'title': sanitize_filename(title, restricted=True),
            'formats': [format_video],
            'ext': 'mp4'
        }
