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



import re

from backoff import constant, on_exception

class get_videourl():
    
    def __init__(self, _type):
        self.id = "player-1" if _type == 'embed' else "videoplayer"
    def __call__(self, driver):
        el_player = driver.find_elements(by=By.ID, value=self.id)
        if not el_player: return False
        else:
            el_video = el_player[0].find_elements(by=By.TAG_NAME, value="video")
            if not el_video: return False
            video_url = el_video[0].get_attribute('src')
            if video_url: 
                return video_url
            else: return False

class TheGayIE(SeleniumInfoExtractor):

    IE_NAME = 'thegayx'
    _VALID_URL = r'https?://(?:www\.)?thegay\.com/(?P<type>(?:embed|videos))/(?P<id>[^\./]+)[\./]'
    

    def _get_video_info(self, url):        
        self.logger_info(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
            

    def _send_request(self, driver, url):
        self.logger_info(f"[send_request] {url}")   
        driver.get(url)
    
    
    @on_exception(constant, Exception, max_tries=5, interval=1)    
    @limiter_1.ratelimit("thegay", delay=True)
    def request_to_host(self, _type, *args):
    
        if _type == "video_info":
            return self._get_video_info(*args)
        elif _type == "url_request":
            self._send_request(*args)

    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):        
        self.report_extraction(url)
               
        _type, _videoid = re.search(self._VALID_URL, url).groups()

        driver = self.get_driver(usequeue=True) 
        
        try:

            self.request_to_host("url_request", driver, url)

            video_url = self.wait_until(driver, 30, get_videourl(_type)) 

            if not video_url: raise ExtractorError("no video url")            
            _title = driver.title.replace(" - TheGay.com", "").strip()
            _videoinfo = self.request_to_host("video_info", video_url)
            if not _videoinfo: raise Exception(f"error video info")

            _format = {
                    'format_id': 'http-mp4',
                    'url': _videoinfo['url'],
                    'filesize': _videoinfo['filesize'],
                    'ext': 'mp4'
            }
            
            _entry_video = {
                'id' : _videoid,
                'title' : sanitize_filename(_title, restricted=True),
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
                self.put_in_queue(driver)
            except Exception:
                pass