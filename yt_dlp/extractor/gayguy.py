from __future__ import unicode_literals

from ..utils import (
    ExtractorError,
    sanitize_filename,
    try_get
)

from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_5
)

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import traceback
import sys

from backoff import constant, on_exception

class getvideourl():
    def __init__(self, logger):
        self.logger = logger
        self.init = True

    def __call__(self, driver):
        try:
            if self.init:    
                cont = driver.find_elements(By.CLASS_NAME, "loading-container.faplbu")
                self.logger(f'[wait] cont: {cont}')
                if cont:
                    for _ in range(5):
                        try:
                            cont[0].click()
                        except Exception as e:
                            break
                self.init = False
            vid = driver.find_element(By.TAG_NAME, "video")
            self.logger(f'[wait] vid: {vid}')
            if _src := vid.get_attribute("src"):
                return _src
            else: return False
        except Exception as e:
            return False


class GayGuyTopIE(SeleniumInfoExtractor):

    IE_NAME = 'gayguytop'
    _VALID_URL = r'https?://(?:www\.)?gayguy\.top/'

    @on_exception(constant, Exception, max_tries=5, interval=5)    
    @limiter_5.ratelimit("gayguytop2", delay=True)
    def _get_video_info(self, url):        
        self.write_debug(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
        
        
    @on_exception(constant, Exception, max_tries=5, interval=5)
    @limiter_5.ratelimit("gayguytop", delay=True)
    def _send_request(self, url, driver):        
        
        self.logger_info(f"[send_request] {url}") 
        driver.get(url)
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):

        self.report_extraction(url)
        driver = self.get_driver(usequeue=True)
        
        try:
            videoid = url.split("/")[-1]
            self._send_request(url, driver)
            el_art = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.TAG_NAME, "article")))
            if el_art:
                videoid = try_get(el_art[0].get_attribute('id'), lambda x: x.split("-")[-1])
            title = driver.title.replace("| GayGuy.Top", "").strip()
            el_ifr = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.TAG_NAME, "iframe")))
            for el in el_ifr:
                if not 'viewsb.com' in (_ifrsrc:=el.get_attribute('data-src')):
                    for _ in range(5):
                        try:
                            el.click()
                            #self.wait_until(driver, 1)
                        except Exception as e:
                            break
                    self.to_screen(f"[iframe] {_ifrsrc}")                    
                    driver.switch_to.frame(el)
                    break
            
            video_url = self.wait_until(driver, 60, getvideourl(self.to_screen))
            if not video_url: raise ExtractorError('404 video not found')
            _info_video = self._get_video_info(video_url)
            if not _info_video: raise ExtractorError("error info video")
            
           
            
            _format = {
                'format_id': 'http-mp4',
                'url': _info_video['url'],
                'filesize': _info_video['filesize'],
                'ext': 'mp4'
            }

            return({
                'id' : videoid,
                'title': sanitize_filename(title, restricted=True),             
                'formats' : [_format],                
                'ext': 'mp4'
            })

    
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            self.put_in_queue(driver)