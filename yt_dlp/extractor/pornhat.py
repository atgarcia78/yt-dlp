from __future__ import unicode_literals

import json
import re
import sys
import traceback
import datetime



from ..utils import ExtractorError, js_to_json, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_1


class PornHatIE(SeleniumInfoExtractor):
    
    IE_NAME = 'pornhat'
    _VALID_URL = r'https?://(www\.)?pornhat\.com/(?:video|embed)/?(?P<title>[^$/]*)'
    
    @dec_on_exception
    @limiter_1.ratelimit("pornhat", delay=True)
    def _send_request(self, url, _type="GET", data=None, headers=None):        
        
        self.logger_debug(f"[send_req] {self._get_url_print(url)}") 
        return(self.send_http_request(url, _type=_type, data=data, headers=headers))
        
    @dec_on_exception
    @limiter_1.ratelimit("pornhat", delay=True)   
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
            
                     
            if _info_flashvars: 
                
                _new_tokens = re.findall(r'download-link[\"\'] href=[\"\']https://www\.pornhat\.com/get_file/[^/]+/([^/]+)/', webpage)
                _keys = [_key for _key in ['video_url', 'video_alt_url'] if _key in _info_flashvars.keys()]
                _keys_text = [_key for _key in ['video_url_text', 'video_alt_url_text'] if _key in _info_flashvars.keys()]
                self.to_screen(f"tokens={_new_tokens} keys={_keys} keys_text={_keys_text}")
                _formats = [{'url':  re.sub(r'(get_file/[^/]+)/([^/]+)/', fr'\1/{_token}/', _info_flashvars.get(_key).replace('function/0/','')), 
                             'height': try_get(_info_flashvars.get(_key_text), lambda x: int(x.replace('p',''))), 'http_headers': {'Referer': url},
                             'ext': 'mp4', 'format_id': try_get(_info_flashvars.get(_key_text), lambda x: f'http-{x}' if x else 'http')} 
                                for (_token, _key, _key_text) in zip(_new_tokens, _keys, _keys_text)]            
                
                _headers = {'Referer': url}
                
                for _f in _formats:
                    _url = f"{_f['url']}&rnd={int(datetime.datetime.now().timestamp() * 1000)}"
                    _info_video = self._get_info_for_format(_url ,headers=_headers)
                    if _info_video:
                        _f.update({'url': _info_video['url'], 'filesize': _info_video['filesize']})
                    else:
                        _f.update({'url': _url})
                
          
                _videoid = _info_flashvars.get('video_id')
                _title = try_get(re.findall(r"<h1>([^<]+)<", webpage) or re.findall(r'og:title[\'\"] content=[\'\"]([^\'\"]+)[\'\"]'), lambda x: x[0]) 

                _entry_video = {
                    'id' : _videoid,
                    'title' : sanitize_filename(_title, restricted=True),
                    'formats' : _formats,
                    'ext': 'mp4'}
                
                return _entry_video
        
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e))

            
                        

    
