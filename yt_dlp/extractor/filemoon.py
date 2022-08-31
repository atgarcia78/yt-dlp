import sys
import traceback
import re
import time

from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_2, By, ec


class gettitle_trigger_m3u8():
    def __call__(self, driver):
        
        vdiv = driver.find_elements(By.CSS_SELECTOR, "div")

        try:
            
            while True:
                try:
                    vdiv[-1].click()
                    time.sleep(1)
                except Exception:
                    break
            
            while True:
                try:
                    vdiv[-2].click()
                    time.sleep(1)
                except Exception:
                    break
            
            vpl = driver.find_element(By.ID, "vplayer")
            vpl.click()            
            vpl.click()

            return driver.find_element(By.TAG_NAME, "h3").get_attribute('innerText')

        except Exception as e:
            return False


class FilemoonIE(SeleniumInfoExtractor):

    IE_NAME = "filemoon"
    _SITE_URL = "https://filemoon.sx/"
    _VALID_URL = r'https?://filemoon\.\w\w/[e,d]/(?P<id>[^&]+)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https://filemoon\.\w\w/[e,d]/.+?)\1']
    
   
    
    # @staticmethod
    # def _extract_urls(webpage):
       
    #     return [mobj.group('url') for mobj in re.finditer(r'<iframe[^>]+?src=([\"\'])(?P<url>https://filemoon\.\w\w/[e,d]/.+?)\1',webpage)]

    @dec_on_exception
    @limiter_2.ratelimit("filemoon", delay=True)
    def send_multi_request(self, url, driver=None, _type=None, headers=None):
        
        if driver:
            driver.get(url)
        else:
            if not _type:
                res = self.send_http_request(url, headers=headers)                
                return res
            else:
                return self.get_info_for_format(url, headers=headers)       


    def _real_initialize(self):

        super()._real_initialize()        

                
    def _real_extract(self, url):

        try:
            
            self.report_extraction(url) 
                
            videoid = self._match_id(url)

            driver = self.get_driver(devtools=True)
            
            _formats = None            
            
            self.send_multi_request(_wurl:=(url.replace('/e/', '/d/').replace('filemoon.to', 'filemoon.sx')), driver)

            title = self.wait_until(driver, 60, gettitle_trigger_m3u8())
            
            _headers = {'Referer': self._SITE_URL, 'Origin': self._SITE_URL.strip("/")}
                                
            m3u8_url, m3u8_doc = self.scan_for_request(driver, f"master.m3u8")
            if m3u8_url and m3u8_doc:
                _formats, _ = self._parse_m3u8_formats_and_subtitles(m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")

            if _formats: self._sort_formats(_formats)
            else:
                raise ExtractorError(f"[{url}] Couldnt find any video format")

                
            for _format in _formats:
                if (_head:=_format.get('http_headers')):
                    _head.update(_headers)
                else:
                    _format.update({'http_headers': _headers})   

            return({ 
                "id": videoid,
                "title": sanitize_filename(title, restricted=True),                    
                "formats": _formats,
                "webpage_url": _wurl,                             
                "ext": "mp4"})
            

        
        except ExtractorError as e:
            raise
        except Exception as e:                
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(repr(e))
        finally:
            self.rm_driver(driver)

                    
