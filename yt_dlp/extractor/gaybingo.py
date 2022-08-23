import re
import sys
import traceback

import httpx

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

from ..utils import ExtractorError, int_or_none, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_1, By, ec


class get_videourl():
    def __call__(self, driver):
        elvideo = driver.find_elements(By.CSS_SELECTOR, "video#player")
        if not elvideo: return False
        elsrc = elvideo[0].find_elements(By.TAG_NAME, "source")
        if not elsrc: return False
        videourl = elsrc[0].get_attribute('src')
        if videourl: return videourl
        else: return False
        

class GayBingoIE(SeleniumInfoExtractor):
    
    _SITE_URL = 'https://gay.bingo'    
    IE_NAME = 'gaybingo'
    _VALID_URL = r'https?://(?:www\.)?gay.bingo/video/(?P<id>\d+)(?:\?|$)'


    @dec_on_exception
    @limiter_1.ratelimit("gaybingo1", delay=True)
    def url_request(self, driver, url):        
        
        self.logger_debug(f"[send_request] {url}") 
        driver.get(url)
        
    @dec_on_exception
    @limiter_1.ratelimit("gaybingo2", delay=True)
    def _send_request(self, url, headers=None):
        
        try:
            res = httpx.get(url, follow_redirects=True, headers=headers)
            res.raise_for_status()
            return res
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise            
         

    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        
        driver = self.get_driver()
 
            
        try: 
            self.url_request(driver, url)
            
            m3u8_url = self.wait_until(driver, 60, get_videourl())
            
            if m3u8_url:
                self.to_screen(m3u8_url)
                uagent = driver.execute_script("return navigator.userAgent")
                _headers = {'Origin': self._SITE_URL, 'Referer': f"{self._SITE_URL}/", 'User-Agent': uagent}
                _videoid = self._match_id(url)           
                height =  int_or_none(try_get(re.findall(r'stream/(\d+)p?/', m3u8_url), lambda x: x[0]))
                _title = driver.title.replace(" - Gay.Bingo", "").strip()

                formats = self._extract_m3u8_formats(m3u8_url, _videoid, 'mp4', entry_protocol='m3u8_native', m3u8_id='hls', headers=_headers, fatal=False)
                if formats: 
                    if height and len(formats) == 1:
                        if not formats[0].get('height'): formats[0].update({'height': height})            
                    for f in formats:
                        
                        _httpheaders = self.get_param('http_headers').copy()                        
                        _httpheaders.update(_headers)                        
                        f.update({'http_headers': _httpheaders})                        
                        
                
                    self._sort_formats(formats)
                
        
                    _entry_video = {
                        'id' : _videoid,
                        'title' : sanitize_filename(re.sub(r' - ', r'_', _title.replace("'","").replace("&","and")), restricted=True),
                        'formats' : formats,
                        'ext': 'mp4'
                    }
        
                
                    return _entry_video
                else: raise ExtractorError("no formats")
                
            else: raise ExtractorError("couldnt find any video")   
            
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
