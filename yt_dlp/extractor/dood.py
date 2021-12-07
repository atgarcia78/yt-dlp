from __future__ import unicode_literals

from ..utils import (
    ExtractorError,
    sanitize_filename
)

import traceback
import sys
import re

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

from .webdriver import SeleniumInfoExtractor

from ratelimit import (
    sleep_and_retry,
    limits
)

class get_videourl():
    def __call__(self, driver):
        elvideo = driver.find_elements(By.ID, "video_player_html5_api")
        if not elvideo: return False
        videourl = elvideo[0].get_attribute('src')
        if not videourl: return False
        else: return videourl
        

class DoodIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://dood.ws/"
    
    IE_NAME = 'dood'
    _VALID_URL = r'https?://(?:www\.)?dood.ws/(?P<type>(?:e|d))/(?P<id>[^\/$]+)(?:\/|$)'


    @sleep_and_retry
    @limits(calls=1, period=0.1)
    def _send_request(self, driver, url):        
        
        self.logger_info(f"[send_request] {url}") 
        driver.get(url)
         

    def _real_extract(self, url):
        
        self.report_extraction(url)

        driver = self.get_driver()
 
            
        try: 
            self._send_request(driver, url)
            _type = re.search(self._VALID_URL, url).group('type')
            if _type != 'e': self.wait_until(driver, 30, ec.frame_to_be_available_and_switch_to_it((By.TAG_NAME, "iframe")))
            video_url = self.wait_until(driver, 60, get_videourl())
            if video_url:
                _videoinfo = self.get_info_for_format(video_url, headers={'Referer': self._SITE_URL})
                if not _videoinfo: raise ExtractorError("no video info")            
                _videoid = self._match_id(url)
                _title = driver.title.replace(" - DoodStream", "").strip()           
        
                _format = {
                    'format_id': 'http-mp4',
                    'url': _videoinfo['url'],
                    'filesize': _videoinfo['filesize'],
                    'http_headers': {'Referer': self._SITE_URL},
                    'ext': 'mp4'
                    
                }
        
                _entry_video = {
                    'id' : _videoid,
                    'title' : sanitize_filename(re.sub(r' - ', r'_', _title.replace("'","").replace("&","and")), restricted=True),
                    'formats' : [_format],
                    'ext': 'mp4'
                }
        
                
                return _entry_video
                
            raise ExtractorError("couldnt find any video")   
            
        except ExtractorError:
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
