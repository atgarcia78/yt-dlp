from __future__ import unicode_literals

import sys
import traceback



from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_0_1, By, ec


class GayGuyTopIE(SeleniumInfoExtractor):

    IE_NAME = 'gayguytop'
    _VALID_URL = r'https?://(?:www\.)?gayguy\.top/'


    @dec_on_exception
    @limiter_0_1.ratelimit("gayguytop", delay=True)
    def _send_request(self, url, driver):        
        self.logger_debug(f"[send_request] {url}") 
        driver.get(url)
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
        self.report_extraction(url)
        driver = self.get_driver()
        
        try:
            
            self._send_request(url, driver) 
            title = driver.title.replace("| GayGuy.Top", "").strip().lower()
            el_ifr = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.TAG_NAME, "iframe")))
            _ifrsrc = None
            for el in el_ifr:
                if 'fembed.com' in (_ifrsrc:=(el.get_attribute('src') or "")):
                    self.to_screen(f"[iframe] {_ifrsrc}")
                    break
            if not _ifrsrc: raise ExtractorError("iframe fembed.com not found")
            ie, _ = try_get(self._downloader.get_info_extractor('Fembed'), lambda x: (x, x._real_initialize()))
            
            return ie._get_entry(_ifrsrc)
    
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            self.rm_driver(driver)
