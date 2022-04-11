# coding: utf-8
from __future__ import unicode_literals

from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_1
)

from ..utils import (
    ExtractorError,
    sanitize_filename,
)

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By




import traceback
import sys




from backoff import constant, on_exception

class get_videourl():
    def __call__(self, driver):
        elvideo = driver.find_elements(By.TAG_NAME, "video")
        if not elvideo: return False
        videourl = elvideo[0].get_attribute('src')
        if not videourl: return False
        else: return videourl
        

class ThatGVideoIE(SeleniumInfoExtractor):
    IE_NAME = 'thatgvideo'
    _VALID_URL = r'https?://thatgvideo\.com/videos/(?P<id>\d+).*'

    def _get_video_info(self, url):        
        self.logger_info(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
        

    def _send_request(self, driver, url):
        self.logger_info(f"[send_request] {url}")   
        driver.get(url)
    
    
    @on_exception(constant, Exception, max_tries=5, interval=1)    
    @limiter_1.ratelimit("thatgvideo", delay=True)
    def request_to_host(self, _type, *args):
    
        if _type == "video_info":
            return self._get_video_info(*args)
        elif _type == "url_request":
            self._send_request(*args)     
    
    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        
        self.report_extraction(url)
        
        driver = self.get_driver(usequeue=True)
 
        try:
            
  
            self.request_to_host("url_request", driver, url) 

            video_url = self.wait_until(driver, 30, get_videourl())

            if video_url:
                self.to_screen(video_url)
                _info = self.request_to_host("video_info", video_url)
                
                if _info:

                    _format_video = {
                            'format_id' : "http-mp4",
                            'url' : _info.get('url'),
                            'filesize' : _info.get('filesize'),
                            'http_headers': SeleniumInfoExtractor._CLIENT_CONFIG['headers'],
                            'ext': "mp4"
                        }
                    
                    _entry_video = {
                        'id' : self._match_id(url),
                        'title' : sanitize_filename(driver.title,restricted=True),
                        'formats' : [_format_video],
                        'ext': "mp4"
                    }
                
                    return _entry_video
                else: raise ExtractorError("couldnt get video info")
            else: raise ExtractorError("no video url found")    
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            try:
                self.put_in_queue(driver)
            except Exception:
                pass