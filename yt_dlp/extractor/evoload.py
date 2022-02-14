from __future__ import unicode_literals

from ..utils import (
    ExtractorError,
    sanitize_filename,
    try_get
)


import traceback
import sys
import time
import re


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_15
)


from backoff import constant, on_exception

class video_or_error_evoload():
    def __init__(self, logger):
        self.logger = logger
        self.init = True
    def __call__(self, driver):
        try:
            elvid = driver.find_elements(By.ID, "EvoVid_html5_api")
            if not elvid:
                errormsg = (
                    try_get(
                        driver.find_elements(By.CLASS_NAME, "img"), lambda x: x[1].text
                    )
                    or ""
                )
                if errormsg:
                    self.logger(f'[video_or_error_wait][{driver.current_url}] error - {errormsg}')
                    return "error"
                else:
                    elpreload = driver.find_elements(By.ID, "preloader")
                    if elpreload:
                        if self.init:
                            self.init = False
                            time.sleep(5)                            
                            return False
                        else:
                            
                            self.logger(
                                f"[video_or_error_wait][{driver.current_url}] error - preloader"
                            )
                        return "error"
                    else:
                        return False

            else:
                if _src:=elvid[0].get_attribute("src"):
                    return _src
                else:
                    return False
        except Exception as e:
            return False

class get_title():
    def __call__(self, driver):
        
        el = driver.find_elements(by=By.CSS_SELECTOR, value="h3")        
        if el:            
            text = el[0].text
            if text:
                text = re.sub(r"evoload|Evoload|\.mp4", "", text)                
                subtext = text[0:int(len(text) / 2 * 0.9)]
                if text.count(subtext) > 1:
                    text = text[0:text.rindex(subtext) - 1]
                text = text.replace("-","_").replace(".", "_").strip('_ ')
                return text
            else:
                return False                       
        else:       
            return False
        
       
        

class EvoLoadIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://evoload.io"
    
    IE_NAME = 'evoload'
    _VALID_URL = r'https?://(?:www\.)?evoload.io/(?:e|v)/(?P<id>[^\/$]+)(?:\/|$)'


    def _get_video_info(self, url):        
        self.logger_info(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
            

    def _send_request(self, driver, url):
        self.logger_info(f"[send_request] {url}")   
        driver.get(url)
        
     
    @on_exception(constant, Exception, max_tries=5, interval=15)    
    @limiter_15.ratelimit("evoload", delay=True)
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
            
            

            self.request_to_host("url_request", driver, url.replace('/v/', '/e/'))

            video_url = self.wait_until(driver, 30, video_or_error_evoload(self.to_screen))
            if not video_url or video_url == 'error': raise ExtractorError("404 not video found") 
            _videoinfo = self.request_to_host("video_info", video_url)            
            if not _videoinfo: raise ExtractorError("error video info")
            
            self.request_to_host("url_request", driver, url.replace('/e/', '/v/'))
            _title =  self.wait_until(driver, 30, get_title())
            
            
            _format = {
                    'format_id': 'http-mp4',
                    'url': _videoinfo['url'],
                    'filesize': _videoinfo['filesize'],
                    'ext': 'mp4'
            }
            
            return({
                'id' : self._match_id(url),
                'title' : sanitize_filename(_title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
            })
            

            
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")            
            raise ExtractorError(repr(e))
        finally:
            self.put_in_queue(driver)
            
