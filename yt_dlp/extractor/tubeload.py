from __future__ import unicode_literals

from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_15
)

from ..utils import (
    ExtractorError,
    sanitize_filename,
    
)


import traceback
import sys
import re


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


from backoff import constant, on_exception

class getvideourl():
    def __call__(self, driver):

        el_video = driver.find_element(By.ID, "mainvideo")
        videourl = el_video.get_attribute('src')
        if not videourl:
            el_overlay = driver.find_element(By.CLASS_NAME, "plyr-overlay")
            try:
                el_overlay.click()
            except Exception as e:
                pass
            return False
        else: return videourl

        
        

class TubeloadIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://tubeload.co"
    
    IE_NAME = 'tubeload'
    _VALID_URL = r'https?://(?:www\.)?tubeload.co/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    
    @staticmethod
    def _extract_urls(webpage):
        #return try_get(re.search(r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?streamtape\.(?:com|net)/(?:e|v|d)/.+?)\1',webpage), lambda x: x.group('url'))
        return [mobj.group('url') for mobj in re.finditer(r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?tubeload\.co/e/.+?)\1',webpage)]

        
    @on_exception(constant, Exception, max_tries=5, interval=5)
    @limiter_15.ratelimit("tubeload1", delay=True)
    def _get_video_info(self, url):        
        
        self.logger_info(f"[get_video_info] {url}")
        return self.get_info_for_format(url, verify=False)     
    
    @on_exception(constant, Exception, max_tries=5, interval=5)
    @limiter_15.ratelimit("tubeload", delay=True)
    def _send_request(self, url, driver):        
        
        self.logger_info(f"[send_request] {url}") 
        driver.get(url)
    
   
 

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        driver = self.get_driver(usequeue=True) 
           
            
        try:                            

            self._send_request(url.replace('/e/', '/f/'), driver)
            
            video_url = self.wait_until(driver, 60, getvideourl())
            
            if not video_url: raise ExtractorError("no video url") 
            
            title = driver.title.replace(" at Tubeload.co","").strip()
            videoid = self._match_id(url)
            
                       
            
            
            #if not _videoinfo: raise Exception(f"error video info")
            
            _format = {
                    'format_id': 'http-mp4',
                    #'url': _videoinfo['url'],
                    'url': video_url,
                    #'filesize': _videoinfo['filesize'],
                    'ext': 'mp4'
            }
            
            if self._downloader.params.get('external_downloader'):
                _videoinfo = self._get_video_info(video_url)
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
