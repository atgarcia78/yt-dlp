from __future__ import unicode_literals

import re
import sys
import traceback

from backoff import constant, on_exception
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

from ..utils import ExtractorError, get_domain, sanitize_filename
from .commonwebdriver import SeleniumInfoExtractor, limiter_1, limiter_5


class get_videourl():
    def __call__(self, driver):
        elvideo = driver.find_element(By.ID, "video_player_html5_api")
        videourl = elvideo.get_attribute('src')
        if not videourl: return False
        else: return videourl
        

class DoodIE(SeleniumInfoExtractor):
    
        
    IE_NAME = 'dood'
    _VALID_URL = r'https?://(?:www\.)?dood\.[a-z]+/(?P<type>[ed])/(?P<id>[^\/$]+)(?:\/|$)'


    @on_exception(constant, Exception, max_tries=5, interval=1)
    @limiter_5.ratelimit("dood1", delay=True)  
    def get_info_for_format(self, *args, **kwargs):
        return super().get_info_for_format(*args, **kwargs)
    
    @limiter_5.ratelimit("dood2", delay=True)
    def _send_request(self, driver, url):        
        
        self.logger_info(f"[send_request] {url}") 
        driver.get(url)
         

    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        driver = self.get_driver(usequeue=True)
 
            
        try: 
            self._send_request(driver, url)
            _type = re.search(self._VALID_URL, url).group('type')
            if _type != 'e': self.wait_until(driver, 30, ec.frame_to_be_available_and_switch_to_it((By.TAG_NAME, "iframe")))
            video_url = self.wait_until(driver, 60, get_videourl())
            if video_url:
                _videoinfo = self.get_info_for_format(video_url, headers={'Referer': url})
                if not _videoinfo: raise ExtractorError("no video info")            
                _videoid = self._match_id(url)
                _title = driver.title.replace(" - DoodStream", "").strip()           
        
                _format = {
                    'format_id': 'http-mp4',
                    'url': _videoinfo['url'],
                    'filesize': _videoinfo['filesize'],
                    'http_headers': {'Referer': url},
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
            self.put_in_queue(driver)
