from __future__ import unicode_literals



from ..utils import (
    ExtractorError,
    sanitize_filename,
    try_get
    

)


from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_15
)

from .openload import PhantomJSwrapper


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


import traceback
import sys
import re
import json




from backoff import constant, on_exception
class get_video_url():
    
    def __call__(self, driver):
        
        el = driver.find_elements(by=By.ID, value="videooverlay")        
        if el:            
            try:
                el[0].click()
            except Exception:                
                el_video = driver.find_elements(by=By.ID, value="olvideo_html5_api")
                if el_video:
                    video_url = el_video[0].get_attribute('src')
                    if video_url: return video_url
                    else: return False
                else: return False
        else:
            return False

class UserLoadIE(SeleniumInfoExtractor):

    IE_NAME = 'userload'
    _VALID_URL = r'https?://(?:www\.)?userload\.co/(?P<type>(?:embed|e|f))/(?P<id>[^\/$]+)(?:\/(?P<title>.+)?|$)'

    @on_exception(constant, Exception, max_tries=5, interval=15)    
    @limiter_15.ratelimit("userload2", delay=True)
    def _get_video_info(self, url):        
        self.write_debug(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
        

    # def _send_request(self, driver, url):
    #     self.logger_info(f"[send_request] {url}")   
    #     driver.get(url)
    
    
    # @on_exception(constant, Exception, max_tries=5, interval=15)    
    # @limiter_15.ratelimit("userload", delay=True)
    # def request_to_host(self, _type, *args):
    
    #     if _type == "video_info":
    #         return self._get_video_info(*args)
    #     elif _type == "url_request":
    #         self._send_request(*args)
    
    @on_exception(constant, Exception, max_tries=5, interval=15)    
    @limiter_15.ratelimit("userload", delay=True)   
    def post_api(self, ref):
        
        try:
            res1 = UserLoadIE._CLIENT.get(ref)
            res1.raise_for_status()
            if 'class=\"image-blocked\"' in res1.text:
                return {'error': '404 not found'}
            jscode = try_get(
                re.findall(r"(function\(p,a,c,k,e,d\)[^<]+)</script>", res1.text.replace("\n", "")),
                lambda x: rf"const eljscode = {x[0][:-1]}; console.log(eljscode); saveAndExit();")

            self.write_debug(jscode)
            phantom =  PhantomJSwrapper(self, required_version="2.0")
            res = phantom.get(ref, jscode=jscode)
            
            info = json.loads('{' + res[1].replace(";\n", "}").replace("var ", '"').replace("=", '": ').replace(";", ","))
            #self.to_screen(info)
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded', 
                'Referer': ref
            }
            
            data = {
                "morocco": info['beebcfba'], 
                "mycountry": info['fbbcbfdaedcf']
            }
            
            self.write_debug(f'{info}\n{data}')
            
            res2 = UserLoadIE._CLIENT.post("https://userload.co/api/request/", headers=headers, data=data)
            res2.raise_for_status()
            _vidurl = res2.text.strip() if res2 else ""            
            _vidinfo = self._get_video_info(_vidurl) if _vidurl.startswith("http") else {}
            if _vidinfo:
                _entry = {'title': info['afafbecddafa'].split('/')[-1].split('.')[0], 'url': _vidinfo.get('url'), 'filesize': _vidinfo.get('filesize')}
                self.write_debug(_entry)
                return _entry
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"[postapi] {repr(e)}\n{'!!'.join(lines)}")
            raise
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):

        self.report_extraction(url)
        
        try:

            _videoinfo = self.post_api(url.replace('/f/', '/e/'))

            if not _videoinfo:
                raise ExtractorError("error video info")
            
            if (msg:=_videoinfo.get('error')):
                raise ExtractorError(msg)
            
            _format = {
                'format_id': 'http-mp4',
                'url': _videoinfo['url'],
                'filesize': _videoinfo['filesize'],
                'ext': 'mp4'
            }

            _entry_video = {
                'id' : self._match_id(url),
                'title' : sanitize_filename(_videoinfo['title'], restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
            } 
        
            
            return _entry_video 
    
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        