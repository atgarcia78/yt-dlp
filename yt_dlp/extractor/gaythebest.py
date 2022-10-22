import sys
import threading
import time
import traceback

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

from ..utils import ExtractorError, sanitize_filename
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor


class getvideourl:
    def __call__(self, driver):
        try:
            el = driver.find_element(By.CLASS_NAME,"fp-player")
            for _ in range(5):
                try:
                    el.click()
                    time.sleep(1)
                except Exception as e:
                    break
            el_video = driver.find_element(By.CSS_SELECTOR, "video.fp-engine")
            if video_url:=el_video.get_attribute('src'):
                return video_url
            else:
                return False
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            return False
            
                
        
class GayTheBestIE(SeleniumInfoExtractor):

    IE_NAME = 'gaythebest'
    _VALID_URL = r'https?://(?:www\.)?gaythebest\.com/videos/(?P<id>\d+)/.+'
    
    _LOCK = threading.Lock()


    def _real_initialize(self):
        super()._real_initialize()
        
    def _real_extract(self, url):
   
        self.report_extraction(url)
        
        driver = self.get_driver()
        
        try:

            with GayTheBestIE._LOCK:
                driver.get(url)
            
            # el = self.wait_until(driver, 60, ec.presence_of_element_located((By.CLASS_NAME,"fp-player"))) 
            # el.click()
            # el_video = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "video.fp-engine")))
            
                      
            video_url = self.wait_until(driver, 60, getvideourl())
            if not video_url: raise ExtractorError("no video url") 
              
            
            title = driver.title.split(" - ")[0]
            videoid = self._match_id(url)
            
            info_video = self.get_info_for_format(video_url)
            if not info_video: raise ExtractorError("no info video")
            
            _format = {
                    'format_id': 'http-mp4',
                    'url': info_video['url'],
                    'filesize': info_video['filesize'],
                    'ext': 'mp4'
            }
            
            _entry_video = {
                'id' : videoid,
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
            } 
            
            return _entry_video      
            
        
        except ExtractorError as e:
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
