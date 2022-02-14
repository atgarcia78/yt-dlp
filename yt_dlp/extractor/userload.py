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



from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


import traceback
import sys
import time

from backoff import constant, on_exception

class video_or_error_userload():
    def __init__(self, logger):
        self.logger = logger
    def __call__(self, driver):
        try:
            elimg = driver.find_elements(By.CSS_SELECTOR, "img.image-blocked")
            if elimg:
                self.logger(f'[video_or_error_wait][{driver.current_url}] error - video doesnt exist')
                return "error"
            elover = driver.find_elements(By.ID, "videooverlay")
            if elover:
                for _ in range(5):
                    try:
                        elover[0].click()
                        time.sleep(1)
                    except Exception as e:
                        break
            el_vid = driver.find_elements(By.ID, "olvideo_html5_api")
            if el_vid:
                if _src:=el_vid[0].get_attribute('src'):
                    return _src
                else:
                    return False
            else: return False
        except Exception as e:
            return False

class UserLoadIE(SeleniumInfoExtractor):

    IE_NAME = 'userload'
    _VALID_URL = r'https?://(?:www\.)?userload\.co/(?P<type>(?:embed|e|f))/(?P<id>[^\/$]+)(?:\/(?P<title>.+)?|$)'

    @on_exception(constant, Exception, max_tries=5, interval=15)    
    @limiter_15.ratelimit("userload2", delay=True)
    def _get_video_info(self, url):        
        self.write_debug(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
        

    # @on_exception(constant, Exception, max_tries=5, interval=15)    
    # @limiter_15.ratelimit("userload", delay=True)   
    # def post_api(self, ref):
        
    #     try:
    #         res1 = UserLoadIE._CLIENT.get(ref)
    #         res1.raise_for_status()
    #         if 'class=\"image-blocked\"' in res1.text:
    #             return {'error': '404 not found'}
    #         jscode = try_get(
    #             re.findall(r"(function\(p,a,c,k,e,d\)[^<]+)</script>", res1.text.replace("\n", "")),
    #             lambda x: rf"const eljscode = {x[0][:-1]}; console.log(eljscode); saveAndExit();")

            
    #         self.write_debug(jscode)
    #         self.write_debug(res1.text)
            
    #         if not jscode: return {'error': 'jscode not found'}
    #         phantom =  PhantomJSwrapper(self, required_version="2.0")
    #         res = phantom.get(ref, jscode=jscode)
            
    #         info = json.loads('{' + res[1].replace(";\n", "}").replace("var ", '"').replace("=", '": ').replace(";", ","))
    #         #self.to_screen(info)
            
    #         self.write_debug(info)
            
    #         headers = {
    #             'Content-Type': 'application/x-www-form-urlencoded', 
    #             'Referer': ref
    #         }
            
    #         data = {
    #             "morocco": info.get('beebcfba') or info.get('deeacafd'),
    #             "mycountry": info['fbbcbfdaedcf']
    #         }
            
    #         self.write_debug(f'{data}')
            
    #         res2 = UserLoadIE._CLIENT.post("https://userload.co/api/request/", headers=headers, data=data)
    #         res2.raise_for_status()
    #         _vidurl = res2.text.strip() if res2 else ""            
    #         _vidinfo = self._get_video_info(_vidurl) if _vidurl.startswith("http") else {}
    #         if _vidinfo:
    #             _entry = {'title': info['afafbecddafa'].split('/')[-1].split('.')[0], 'url': _vidinfo.get('url'), 'filesize': _vidinfo.get('filesize')}
    #             self.write_debug(_entry)
    #             return _entry
    #     except Exception as e:
    #         lines = traceback.format_exception(*sys.exc_info())
    #         self.to_screen(f"[postapi] {repr(e)}\n{'!!'.join(lines)}")
    #         raise
        
    @on_exception(constant, Exception, max_tries=5, interval=15)
    @limiter_15.ratelimit("userload", delay=True)
    def _send_request(self, url, driver):        
        
        self.logger_info(f"[send_request] {url}") 
        driver.get(url)
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):

        self.report_extraction(url)
        driver = self.get_driver(usequeue=True)
        
        try:

            #_videoinfo = self.post_api(url.replace('/f/', '/e/'))
            self._send_request(url, driver)
            video_url = self.wait_until(driver, 30, video_or_error_userload(self.to_screen))
            if not video_url or video_url == 'error': raise ExtractorError('404 video not found')
            _info_video = self._get_video_info(video_url)
            if not _info_video: raise ExtractorError("error info video")
            title = driver.title.replace(".mp4", "").split("|")[0].strip()
            
            _format = {
                'format_id': 'http-mp4',
                'url': _info_video['url'],
                'filesize': _info_video['filesize'],
                'ext': 'mp4'
            }

            return({
                'id' : self._match_id(url),
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
            })

    
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            self.put_in_queue(driver)
        