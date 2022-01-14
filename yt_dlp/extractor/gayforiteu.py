# coding: utf-8
from __future__ import unicode_literals

import re

from .commonwebdriver import SeleniumInfoExtractor
from ..utils import (
    ExtractorError, 
    sanitize_filename,
    try_get
    
)

from urllib.parse import unquote
from ratelimit import limits, sleep_and_retry
from backoff import on_exception, constant
import sys, traceback

class GayForITEUIE(SeleniumInfoExtractor):
    
    _VALID_URL = r'https?://(?:www\.)gayforit\.eu/(?:playvideo.php\?vkey\=[^&]+&vid\=(?P<vid>[\w-]+)|video/(?P<id>[\w-]+)|playvideo.php\?vkey\=.+)'

    
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @sleep_and_retry
    @limits(calls=1, period=1)
    def _send_request(self, url):
        
        #lets use the native method of InfoExtractor to download the webpage content. HTTPX doesnt work with this site
        webpage = self._download_webpage(url, None, note=False)
        if not webpage: raise ExtractorError("no video page info")
        else: return webpage
        
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @sleep_and_retry
    @limits(calls=1, period=5)    
    def get_info_for_format(self, *args, **kwargs):
        return super().get_info_for_format(*args, **kwargs)
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
        
        try:
        
            videoid = try_get(re.search(self._VALID_URL, url), lambda x: x.groups()[0] or x.groups()[1])
            
            webpage = self._send_request(url) 
            
            if not webpage or 'this-video-has-been-removed' in webpage.lower(): raise ExtractorError("Error 404: no video page info")

            title = try_get(re.findall(r'<title>GayForIt\.eu - Free Gay Porn Videos - (.+?)</title>', webpage), lambda x: x[0]) 
            
            video_url = try_get(re.findall(r'<source src=\"([^\"]+)\" type=\"video/mp4', webpage), lambda x: x[0])

            if not video_url:
                raise ExtractorError("no video url")
            else: video_url = unquote(video_url)
            
            if not videoid:
                videoid = try_get(re.findall(r'/(\d+)_', video_url), lambda x: x[0]) or 'not_id'
            if not title:
                webpage = self._send_request(f"https://gayforit.eu/video/{videoid}")
                if not webpage or 'this-video-has-been-removed' in webpage.lower(): raise ExtractorError("Error 404: no video page info")
                title = try_get(re.findall(r'<title>GayForIt\.eu - Free Gay Porn Videos - (.+?)</title>', webpage), lambda x: x[0]) 

            self.to_screen(f"[video_url] {video_url}")
            _info_video = self.get_info_for_format(video_url, headers={"Referer" : "https://gayforit.eu/"}, verify=False)
            
            if not _info_video: raise ExtractorError("no video info")

            format_video = {
                'format_id' : "http-mp4",
                'url' : _info_video['url'],
                'filesize' : _info_video['filesize'],
                'ext' : 'mp4'
            }

            entry = {
                'id': videoid,                
                'formats': [format_video],
                'ext': 'mp4'
            }
            
            if title: entry.update({'title': sanitize_filename(title.strip(), restricted=True)})
            
            return entry
        
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}') 
