from __future__ import unicode_literals

import re

from ..utils import ExtractorError, sanitize_filename, try_get, js_to_json, int_or_none
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_2, By, ec, HTTPStatusError

import html
import time
import json



class VidozaIE(SeleniumInfoExtractor):
    IE_NAME = 'vidoza'
    _VALID_URL = r'https?://(?:www\.)?vidoza\.net/(?P<id>[^.]+).html'
    _SITE_URL = 'https://vidoza.net/'
   
    @dec_on_exception2
    @dec_on_exception3
    @limiter_2.ratelimit("vidoza", delay=True)
    def _get_video_info(self, url, **kwargs):        
        try:
            self.logger_debug(f"[get_video_info] {url}")
            return self.get_info_for_format(url, **kwargs)       
        except HTTPStatusError as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
            
    @dec_on_exception2
    @dec_on_exception3
    @limiter_2.ratelimit("vidoza", delay=True)
    def _send_request(self, url, **kwargs):        
        
        try:
            self.logger_debug(f"[send_req] {self._get_url_print(url)}") 
            return(self.send_http_request(url, **kwargs))
        except HTTPStatusError as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
        

       
    def _get_entry(self, url, check_active=False, msg=None):
        
        try:
            
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}{pre}'
            webpage = try_get(self._send_request(url), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)))
            if not webpage: raise ExtractorError("no video webpage")          
            info_sources = try_get(re.findall(r'sourcesCode: (\[\{.*\}\])\,', webpage), lambda x: json.loads(js_to_json(x[0])))
            _formats = []
            _headers = {'Referer': self._SITE_URL}
            for source in info_sources:
                video_url = source.get('src')
                res = source.get('res','')
                _format = {
                    'format-id': f'http{res}',
                    'url' : video_url,
                    'ext': 'mp4',
                    'http_headers': _headers
                    
                }
                if res:
                    _format.update({'height': int(res)})
                if check_active:
                    _videoinfo = self._get_video_info(video_url, headers=_headers, msg=pre)
                    if not _videoinfo: 
                        self.report_warning(f"{pre} {video_url} - error 404: no video info")
                    else:
                        _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})
                        _formats.append(_format)
                else: _formats.append(_format)
                    
            if not _formats: raise ExtractorError("No formats found")
            
            self._sort_formats(_formats)
                      
            _videoid = self._match_id(url)
            _title = try_get(re.findall(r'<h1>([^\<]+)\<', webpage), lambda x: x[0])
                  
            entry_video = {
                'id' : _videoid,
                'title' : sanitize_filename(_title, restricted=True),
                'formats' : _formats,
                'extractor_key' : 'Vidoza',
                'extractor': 'vidoza',
                'ext': 'mp4',
                'webpage_url': url
            } 
            
            return entry_video
        
        except Exception as e:
            self.to_screen(e)
            raise
        
    def _real_initialize(self):
        super()._real_initialize()
    
    
    def _real_extract(self, url):

        self.report_extraction(url)
            
        try:

            #if self._downloader.params.get('external_downloader'): _check_active = True
            #else: _check_active = False
            
            _check_active = True

            return self._get_entry(url, check_active=_check_active)  
    
        except ExtractorError as e:
            raise
        except Exception as e:
            
            self.to_screen(f"{repr(e)}")
            raise ExtractorError(repr(e))
        
        


