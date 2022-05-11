from __future__ import unicode_literals

import re
import sys
import time
import traceback

from backoff import constant, on_exception
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import SeleniumInfoExtractor, limiter_15


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
                        driver.find_elements(By.CLASS_NAME, "img"), lambda x: x[1].get_attribute('innerText').replace('\n','').strip()
                    )
                    or ""
                )
                if errormsg:
                    self.logger(f'[evoload_url][{driver.current_url[26:]}] error - {errormsg}')
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
                                f"[evoload_url][{driver.current_url[26:]}] error - preloader"
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
            text = el[0].get_attribute('innerText')
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
    _VALID_URL = r'https?://(?:www\.)?evoload.io/(?:e|v)/(?P<id>[^\/$/?]+)'

    @on_exception(constant, Exception, max_tries=5, interval=15)    
    @limiter_15.ratelimit("evoload", delay=True)
    def _get_video_info(self, url):        
        self.logger_info(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
            
    @on_exception(constant, Exception, max_tries=5, interval=15)    
    @limiter_15.ratelimit("evoload", delay=True)
    def _send_request(self, url, driver):
        self.logger_info(f"[send_request] {url}")   
        driver.get(url)

    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
        
        self.report_extraction(url)

        driver = self.get_driver(usequeue=True)
 
            
        try:             

            self._send_request(url.split('?')[0].replace('/v/', '/e/'), driver)

            video_url = self.wait_until(driver, 30, video_or_error_evoload(self.to_screen))
            if not video_url or video_url == 'error': raise ExtractorError("404 not video found")
            
            _format = {
                'format_id': 'http-mp4',
                'url': video_url,
                'ext': 'mp4'
            }
            
            self._send_request(url.split('?')[0].replace('/e/', '/v/'), driver)
            _title =  self.wait_until(driver, 30, get_title())            
            
            if self._downloader.params.get('external_downloader'):
                _videoinfo = self._get_video_info(video_url)
                if _videoinfo:
                    _format.update({'url': _videoinfo['url'],'filesize': _videoinfo['filesize'] })
            
            return({
                'id' : self._match_id(url.split('?')[0]),
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
            
