from __future__ import unicode_literals

import re
import sys
import traceback

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

from ..utils import ExtractorError, sanitize_filename
from .commonwebdriver import SeleniumInfoExtractor, limiter_10


class get_videourl_title():
    
    def __call__(self, driver):

        el_player = driver.find_elements(by=By.ID, value="player")
        if not el_player: return False
        else:

            video_url = el_player[0].get_attribute('src')
            if video_url: 
                return (video_url, driver.title)
            else: return False
        
class CockHeroIE(SeleniumInfoExtractor):
    
    IE_NAME = 'cockhero'
    _VALID_URL = r'https?://(?:www\.)?cockhero\.win/(?P<title>.+)-(?P<id>\d+).html'
    
    @limiter_10.ratelimit("cockhero1", delay=True)
    def _get_video_info(self, url):
        
        self.logger_info(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
        

    
    @limiter_10.ratelimit("cockhero2", delay=True)
    def _send_request(self, driver, url):

        
        self.logger_info(f"[send_request] {url}")   
        driver.get(url)
        
   
    def _real_extract(self, url):
        
              
        self.report_extraction(url)
        
        driver = self.get_driver()
        try:
            video_id = self._match_id(url) 
            self._send_request(driver, url)
            
            el = self.wait_until(driver, 30, get_videourl_title())                
                
            if not el: raise ExtractorError("No video url")
            
            video_url, _title = el[0], el[1]
            
            title = re.sub(" - Cockhero.win","", _title, re.IGNORECASE)
            
            info_video = self._get_video_info(video_url)
            
            if not info_video: raise ExtractorError(f"error video info")
            
            formats = [{'format_id': 'http', 'url': info_video.get('url'), 'filesize': info_video.get('filesize'), 'ext': 'mp4'}]
            if not formats: raise ExtractorError("No formats found")
            else:
                self._sort_formats(formats)
                        
                entry = {
                        'id' : video_id,
                        'title' : sanitize_filename(title, restricted=True),
                        'formats' : formats,
                        'ext': 'mp4'
                    }            
                return entry
        
        
        except Exception as e:            
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise
        finally:
            try:
                self.rm_driver(driver)
            except Exception:
                pass
            
        





