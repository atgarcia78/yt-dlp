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

from .commonwebdriver import SeleniumInfoExtractor

from ratelimit import (
    sleep_and_retry,
    limits
)

from backoff import constant, on_exception

class get_videourl():
    def __call__(self, driver):
        elvideo = driver.find_elements(By.CSS_SELECTOR, "video.jw-video.jw-reset")
        if not elvideo: return False
        videourl = elvideo[0].get_attribute('src')
        if not videourl: return False
        else: return videourl
        

class ExPornToonsIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://hot.exporntoons.net/"
    
    IE_NAME = 'exporntoons'
    _VALID_URL = r'https?://(hot\.)?exporntoons\.net/watch/-(?P<id>\d+_\d+)'

    @on_exception(constant, Exception, max_tries=5, interval=1)
    @sleep_and_retry
    @limits(calls=1, period=0.1)
    def _send_request(self, driver, url):        
        
        self.logger_info(f"[send_request] {url}") 
        driver.get(url)
        
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @sleep_and_retry
    @limits(calls=1, period=5)    
    def get_info_for_format(self, *args, **kwargs):
        return super().get_info_for_format(*args, **kwargs)
         

    def _real_extract(self, url):
        
        self.report_extraction(url)

        driver = self.get_driver()
 
            
        try: 
            self._send_request(driver, url)
            _title = driver.title
            self.wait_until(driver, 30, ec.frame_to_be_available_and_switch_to_it((By.ID, "iplayer")))
            video_url = self.wait_until(driver, 60, get_videourl())
            if video_url:
                _videoinfo = self.get_info_for_format(video_url, headers={'Referer': self._SITE_URL})
                if not _videoinfo: raise ExtractorError("no video info")            
                _videoid = self._match_id(url).replace("_", "")
                          
        
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
