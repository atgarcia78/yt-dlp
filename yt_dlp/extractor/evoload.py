from __future__ import unicode_literals

from ..utils import (
    ExtractorError,
    sanitize_filename,
    block_exceptions
)


import traceback
import sys


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

from .webdriver import SeleniumInfoExtractor

from ratelimit import (
    sleep_and_retry,
    limits
)


from backoff import constant, on_exception


class get_title():
    def __call__(self, driver):
        
        el = driver.find_elements(by=By.CSS_SELECTOR, value="h3")        
        if el:            
            text = el[0].text
            if text:
                return text.replace(".mp4", "").replace("evo", "").replace("-","_")
            else:
                return False
                       
        else:       
            return False

class EvoloadIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://evoload.io"
    
    IE_NAME = 'evoload'
    _VALID_URL = r'https?://(?:www\.)?evoload.io/(?:e|v)/(?P<id>[^\/$]+)(?:\/|$)'


    def _get_video_info(self, url):        
        self.logger_info(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
            

    def _send_request(self, driver, url):
        self.logger_info(f"[send_request] {url}")   
        driver.get(url)
        
    @block_exceptions
    @on_exception(constant, Exception, max_tries=5, interval=15)    
    @sleep_and_retry
    @limits(calls=1, period=15)
    def request_to_host(self, _type, *args):
    
        if _type == "video_info":
            return self._get_video_info(*args)
        elif _type == "url_request":
            self._send_request(*args)
         

    def _real_extract(self, url):
        
        self.report_extraction(url)

        driver = self.get_driver()
 
            
        try:            
            
            _url = url.replace('/e/', '/v/')

            #self._send_request(driver, _url)
            self.request_to_host("url_request", driver, url)
            
            
            _title =  self.wait_until(driver, 60, get_title())
           

            el_fr = self.wait_until(driver, 60, ec.frame_to_be_available_and_switch_to_it((By.CSS_SELECTOR, "iframe#videoplayer")))
            if not el_fr: raise ExtractorError("no videoframe")
            
                
            el_video = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID, "EvoVid_html5_api")))
            if not el_video: raise ExtractorError("no info")
            try:
                el_video.click()
                self.wait_until(driver, 3, ec.title_is("DUMMYWAIT"))
            except Exception:
                pass                        
            video_url = el_video.get_attribute("src")
            if not video_url: raise ExtractorError("no video url") 
            _videoid = self._match_id(url)
            
            #_videoinfo = self._get_video_info(video_url)
            _videoinfo = self.request_to_host("video_info", video_url)
            
            if not _videoinfo: raise Exception(f"error video info")
            
            _format = {
                    'format_id': 'http-mp4',
                    'url': _videoinfo['url'],
                    'filesize': _videoinfo['filesize'],
                    'ext': 'mp4'
            }
            
            _entry_video = {
                'id' : _videoid,
                'title' : sanitize_filename(_title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
            }
            
            if not _entry_video: raise ExtractorError("no video info")
            else:  return _entry_video   
            
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
