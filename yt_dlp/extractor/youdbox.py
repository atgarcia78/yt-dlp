from __future__ import unicode_literals


from .webdriver import SeleniumInfoExtractor

from ..utils import (
    ExtractorError,
    sanitize_filename,

)


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


import traceback
import sys

from ratelimit import (
    sleep_and_retry,
    limits
)

class YoudBoxIE(SeleniumInfoExtractor):

    IE_NAME = 'youdbox'
    _VALID_URL = r'https?://(?:www\.)?youdbox\.(?:net|org|com)/(embed-)?(?P<id>[^\./]+)[\./]'
    

    @sleep_and_retry
    @limits(calls=1, period=10)
    def _get_video_info(self, url):
        
        self.logger_info(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
        

    
    @sleep_and_retry
    @limits(calls=1, period=10)
    def _send_request(self, driver, url):


        self.logger_info(f"[send_request] {url}")   
        driver.get(url)

    def _real_extract(self, url):
        
   
        self.report_extraction(url)
       
        driver = self.get_driver() 
        
        try:
            
            _url = url.replace("embed-", "")

            self._send_request(driver, _url)
            
            
            el_video = self.wait_until(driver, 30, ec.presence_of_element_located((By.ID, "vjsplayer_html5_api"))) 

            if not el_video: raise ExtractorError("no info")           
            video_url = el_video.get_attribute('src')
            if not video_url: raise ExtractorError("no video url")            
            title = driver.title.replace("mp4", "").replace("Download", "").replace("download", "").strip()
            videoid = self._match_id(url)            
            
            _videoinfo = self._get_video_info(video_url)
            
            
            if _videoinfo.get('error'): raise ExtractorError("error video info")
            
            
            _format = {
                    'format_id': 'http-mp4',
                    'url': _videoinfo['url'],
                    'filesize': _videoinfo['filesize'],
                    'ext': 'mp4'
            }
            
            _entry_video = {
                'id' : videoid,
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
            } 
            
            if not _entry_video: raise ExtractorError("no video info")
            else:
                return _entry_video      
            
        
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            try:
                self.rm_driver(driver)
            except Exception:
                pass