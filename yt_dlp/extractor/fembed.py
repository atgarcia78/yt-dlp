from __future__ import unicode_literals

from ..utils import (
    ExtractorError,
    sanitize_filename,
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

class FembedIE(SeleniumInfoExtractor):

    IE_NAME = 'fembed'
    _VALID_URL = r'https?://(?:www\.)?fembed\.com/v/(?P<id>.+)'

    @on_exception(constant, Exception, max_tries=5, interval=5)    
    def _get_video_info(self, url):        
        self.write_debug(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
        
        
    @on_exception(constant, Exception, max_tries=5, interval=5)
    @limiter_5.ratelimit("fembed", delay=True)
    def _send_request(self, url, driver):        
        self.logger_info(f"[send_request] {url}") 
        driver.get(url)
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
        self.report_extraction(url)
        driver = self.get_driver(usequeue=True)
        
        try:
            videoid = self._match_id(url)
            self._send_request(url, driver)
            
            
            cont = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "loading-container.faplbu")))
            if cont:
                cont.click()
            else:
                elobs = self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, 'svg')))
                if elobs:
                    elobs.click()
            title = driver.title.replace("Video ", "").replace(".mp4", "").strip().lower()
            vstr = self.wait_until(driver, 30, ec.presence_of_element_located((By.ID, "vstr")))
            vstr.click()            
            setb = self.wait_until(driver, 30, ec.presence_of_element_located((
                By.CSS_SELECTOR,
                "div.jw-icon.jw-icon-inline.jw-button-color.jw-reset.jw-icon-settings.jw-settings-submenu-button",
            )))
            setb.click()
            qbmenu = self.wait_until(driver, 30, ec.presence_of_element_located((
                    By.CSS_SELECTOR, "div.jw-reset.jw-settings-submenu.jw-settings-submenu-active"
            )))
            qbmenubut = qbmenu.find_elements(By.TAG_NAME, "button")
            nquality = len(qbmenubut)
            setb.click()
            vid = self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "video")))
            _formats = []
            for i in range(nquality):
                vstr.click()
                setb.click()
                qbmenu = self.wait_until(driver, 30, ec.presence_of_element_located((
                    By.CSS_SELECTOR, "div.jw-reset.jw-settings-submenu.jw-settings-submenu-active"
                )))
                qbmenubut = qbmenu.find_elements(By.TAG_NAME, "button")
                _formatid = qbmenubut[i].text
                qbmenubut[i].click()                
                _videourl = vid.get_attribute("src")
                _info_video = self._get_video_info(_videourl)
                _formats.append({
                    'format_id': f'http-mp4-{_formatid}',
                    'height': int(_formatid[:-1]),
                    'url': _info_video['url'],
                    'filesize': _info_video['filesize'],
                    'ext': 'mp4'
                })
            vstr.click()

            if _formats: 
                self._sort_formats(_formats)
            return({
                'id' : videoid,
                'title': sanitize_filename(title, restricted=True),             
                'formats' : _formats,                
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