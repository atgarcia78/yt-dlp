from __future__ import unicode_literals

import json
import re
import sys
import traceback

from backoff import constant, on_exception

from ..utils import ExtractorError, js_to_json, sanitize_filename, try_get
from .commonwebdriver import SeleniumInfoExtractor, limiter_1


class Gay0DayIE(SeleniumInfoExtractor):
    
    IE_NAME = 'gay0day'
    _VALID_URL = r'https?://(www\.)?gay0day\.com/(.+/)?(?:videos|embed)/(?P<id>\d+)/?(?P<title>[^$/]*)'
    
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @limiter_1.ratelimit("gay0day", delay=True)
    def _send_request(self, url, _type="GET", data=None, headers=None):        
        
        res = None
        try:
            self.logger_info(f"[_send_request] {url}") 
            res = self.send_request(url, _type=_type, data=data, headers=headers)
            res.raise_for_status()
            return res
        except Exception as e:
            if res: 
                msg_error = f'{res} - {res.request} \n{res.request.headers}'
            else: msg_error = ""
            self.logger_info(f"[_send_request][{url}] error {repr(e)} - {msg_error}")
            raise
        
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @limiter_1.ratelimit("gay0day", delay=True)   
    def _get_info_for_format(self, *args, **kwargs):
        return super().get_info_for_format(*args, **kwargs)
    
    
    def _real_initialize(self):
        super()._real_initialize()   

    def _real_extract(self, url):        
                       
        self.report_extraction(url)
        
        try:
            
            webpage = try_get(self._send_request(url), lambda x: x.text)
            if not webpage: raise ExtractorError("couldnt download webpage")
            _info_flashvars = try_get(re.findall(r'(?ms)<script.*?>.*?var\s+flashvars\s*=\s*(\{.*?\});.*?</script>', webpage), lambda x: json.loads(js_to_json(x[0])))
            _entry_video = {}            
            if _info_flashvars: 
            
                _url = _info_flashvars.get("video_url")
                _res = _info_flashvars.get("postfix").replace("_","").replace(".mp4","")
                _headers = {'Referer': url}
                _info_video = self._get_info_for_format(_url, headers=_headers)
                if not _info_video: raise ExtractorError('couldnt get info video')           
                _format = {
                    'format_id': _res,
                    'resolution': _res,
                    'url': _info_video.get('url'),
                    'ext': 'mp4',
                    'filesize': _info_video.get('filesize'),
                    'http_headers': _headers
                }
                _videoid = _info_video.get("video_id")
                if not _videoid: _videoid = self._match_id(url)
                _title = try_get(re.findall(r"<title>([^<]+)<", webpage), lambda x: x[0].replace("Video:","").replace("at Gay0Day","").replace("en Gay0Day","").strip()) 
                if not _title:
                    _title = try_get(re.search(self._VALID_URL, url), lambda x: x.group('title').replace('-', '_'))
                _entry_video = {
                    'id' : _videoid,
                    'title' : sanitize_filename(_title, restricted=True),
                    'formats' : [_format],
                    'ext': 'mp4'}
                
                return _entry_video
        
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e))

            
                        

    
