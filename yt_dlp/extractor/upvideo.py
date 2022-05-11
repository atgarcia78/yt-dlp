from __future__ import unicode_literals

import sys
import traceback

from backoff import constant, on_exception
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

from ..utils import ExtractorError, sanitize_filename
from .commonwebdriver import SeleniumInfoExtractor, limiter_15


class UpVideoIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://upvideo.to"
    
    IE_NAME = 'upvideo'
    _VALID_URL = r'https?://(?:www\.)?upvideo.to/[ev]/(?P<id>[^\/$]+)(?:\/|$)'


    def _get_video_info(self, url):        
        self.logger_info(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
        

    def _send_request(self, driver, url):
        self.logger_info(f"[send_request] {url}")   
        driver.get(url)
    
    
    @on_exception(constant, Exception, max_tries=5, interval=15)    
    @limiter_15.ratelimit("upvideo", delay=True)
    def request_to_host(self, _type, *args):
    
        if _type == "video_info":
            return self._get_video_info(*args)
        elif _type == "url_request":
            self._send_request(*args)


    def _real_extract(self, url):
        
        self.report_extraction(url)

        driver = self.get_driver()

        try:                            

            
            #self._send_request(driver, url)
            self.request_to_host("url_request", driver, url)
            
            el = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID,"overlay")))
            if el: 
                try:
                    el.click()
                except Exception:
                    pass
            
            res = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID, "vplayer_html5_api")))
            if not res: raise ExtractorError("no info")
            video_url = res.get_attribute("src")
            if not video_url: raise ExtractorError("no video url") 
            
            title = driver.title.replace(" | upvideo","").replace(".mp4","")
            videoid = self._match_id(url)
            
            #info_video = self._get_video_info(video_url)
            
            info_video = self.request_to_host("video_info", video_url)
            
            if not info_video: raise Exception(f"error video info")            
            
            _format = {
                    'format_id': 'http-mp4',
                    'url': info_video.get('url', video_url),
                    'filesize': info_video.get('filesize'),
                    'ext': 'mp4'
            }
            
            _entry_video = {
                'id' : videoid,
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
            } 
            
            return _entry_video  
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
