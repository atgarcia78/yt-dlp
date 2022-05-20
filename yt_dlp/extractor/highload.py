from __future__ import unicode_literals

import sys
import traceback
import time

from backoff import constant, on_exception
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

from ..utils import ExtractorError, sanitize_filename
from .commonwebdriver import SeleniumInfoExtractor, limiter_15


class getvideourl():
    def __call__(self, driver):

        el_video = driver.find_element(By.ID, "faststream_html5_api")
        videourl = el_video.get_attribute('src')
        if not videourl:
            el_overlay = driver.find_element(By.ID, "videerlay")
            try:
                el_overlay.click()
                time.sleep(3)
            except Exception as e:
                pass
            return False
        else: return videourl

class HighloadIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://highload.to"
    
    IE_NAME = 'highload'
    _VALID_URL = r'https?://(?:www\.)?highload.to/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'

    def _get_video_info(self, url):        
        self.logger_info(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
        

    def _send_request(self, driver, url):
        self.logger_info(f"[send_request] {url}")   
        driver.get(url)
    
   
    @on_exception(constant, Exception, max_tries=5, interval=15, raise_on_giveup=False)    
    @limiter_15.ratelimit("highload", delay=True)
    def request_to_host(self, _type, *args):
    
        if _type == "video_info":
            return self._get_video_info(*args)
        elif _type == "url_request":
            self._send_request(*args)


    def _video_active(self, url):
        
        try:
            _videoinfo = None
            driver = self.get_driver(usequeue=True)
            self.request_to_host("url_request", driver, url)
            video_url = self.wait_until(driver, 60, getvideourl())
            _videoinfo = self.request_to_host("video_info", video_url)
            
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
        finally:
            self.put_in_queue(driver)
        
        if _videoinfo: return True


    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        driver = self.get_driver(usequeue=True) 
           
            
        try:                            

            #_url = url.replace('/e/', '/f/')

            self.request_to_host("url_request", driver, url)
            
            video_url = self.wait_until(driver, 30, getvideourl())
            if not video_url: raise ExtractorError("no video url") 
            
            title = driver.title.replace(" - Highload.to","").replace(".mp4","").strip()
            videoid = self._match_id(url)
            
            _format = {
                'format_id': 'http-mp4',
                #'url': _videoinfo['url'],
                'url': video_url,
                #'filesize': _videoinfo['filesize'],
                'ext': 'mp4'
            }
            
            if self._downloader.params.get('external_downloader'):
                _videoinfo = self.request_to_host("video_info", video_url)
                if _videoinfo:
                    _format.update({'url': _videoinfo['url'],'filesize': _videoinfo['filesize'] })

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
                self.put_in_queue(driver)
            except Exception:
                pass
