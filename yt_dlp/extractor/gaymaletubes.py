from __future__ import unicode_literals

import re
import sys
import traceback



from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_1


class GayMaleTubesIE(SeleniumInfoExtractor):
    IE_NAME = "gaymaletubes"
    _VALID_URL = r'https?://(www\.)?gaymaletubes\.ga/[^\?]+$'
    
            
    
    @dec_on_exception
    @limiter_1.ratelimit("gaymaletubes", delay=True)
    def _send_request(self, url):        
        
        _url_str = self._get_url_print(url)
        self.logger_info(f"[send_request] {_url_str}") 
        res = self._CLIENT.get(url)
        return res
    
    @dec_on_exception
    @limiter_1.ratelimit("gaymaletubes", delay=True)  
    def _get_info_video(self, url):
        
        return super().get_info_for_format(url, headers={'Referer': 'https://gaymaletubes.ga/'})
    
    
    def _real_initialize(self):
        super()._real_initialize()
               
    def _real_extract(self, url):        
        
        
        self.report_extraction(url)

        try:

            webpage = try_get(self._send_request(url), lambda x: x.text.replace("\n", ""))
            if not webpage: raise ExtractorError("couldnt download webpage")
           
            title, videoid, videourl = try_get(re.search(r'og:title["\'] content=["\']([^"\']+)["\'].*gaymaletubes\.ga/\?p=([^"\']+)["\'].*contentURL["\'] content=["\']([^"\']+)["\']', webpage), lambda x: x.groups()) or ("", "", "")
            
            if not videourl: raise ExtractorError("no video url")
            
            self.to_screen(videourl)
            
            _entry = {
                'id': videoid,
                'title': sanitize_filename(title.split(' - GayMaleTubes')[0], restricted=True),                
                'url': videourl,
                'http_headers': {'Referer': 'https://gaymaletubes.ga/'},
                'ext': 'mp4'}
            
            if (_video_info:=self._get_info_video(videourl)):
                _entry.update({'url': _video_info['url'], 'filesize': _video_info['filesize']})                       

                        
            return _entry
                
        
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e))
        