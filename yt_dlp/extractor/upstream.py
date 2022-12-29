import sys
import traceback


from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_2, By, ec, HTTPStatusError, ConnectError
import time


class trigger_m3u8:
    def __call__(self, driver):
        
        el_poster = driver.find_element(By.CSS_SELECTOR, 'div.player-poster.clickable')
        try:
            el_poster.click()
            time.sleep(3)
        except Exception:
            return False
        
        el_video = driver.find_element(By.TAG_NAME, 'video')
        
        try:  
            el_video.click()                  
            return True
        except Exception:
            return False
        

class HLSStream(SeleniumInfoExtractor):
    

    def _get_entry(self, url, **kwargs):
        
        @dec_on_exception
        @dec_on_exception2
        @dec_on_exception3
        @limiter_2.ratelimit(self.IE_NAME, delay=True)
        def _send_multi_request(_url, **_kwargs):
            
            _driver = _kwargs.get('driver', None)
            _hdrs = _kwargs.get('headers', None)
            
            if _driver:
                _driver.execute_script("window.stop();")
                _driver.get(_url)
            else:
                try:
                                    
                    return self.send_http_request(_url, headers=_hdrs)
            
                except (HTTPStatusError, ConnectError) as e:
                    self.report_warning(f"[get_video_info] {self._get_url_print(_url)}: error - {repr(e)}")
        
        try:
            
            videoid = self._match_id(url)
            
            driver = self.get_driver(devtools=True)
            
            _send_multi_request(url, driver=driver)

            title = try_get(self.wait_until(driver, 60, ec.presence_of_element_located((By.TAG_NAME, "h1"))), lambda x: x.text)

            if self.IE_NAME == 'videobin':
                self.wait_until(driver, 60, trigger_m3u8())
            
            _headers = {'Referer': self._SITE_URL, 'Origin': self._SITE_URL.strip("/")}
            
            _formats = None             
            
            m3u8_url, m3u8_doc  = try_get(self.scan_for_request(driver, r"master.m3u8$"), lambda x: (x.get('url'), x,get('content')) if x else (None, None))
            if m3u8_url:
                if not m3u8_doc:
                    m3u8_doc = try_get(_send_multi_request(m3u8_url, headers=_headers), lambda x: (x.content).decode('utf-8', 'replace'))
                
                if m3u8_doc:                                                                
                    _formats, _ = self._parse_m3u8_formats_and_subtitles(
                        m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")

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
                "extractor": self.IE_NAME,               
                "extractor_key": self.ie_key(),
                "formats": _formats,
                "webpage_url": url,                             
                "ext": "mp4"})
            

        
        except ExtractorError as e:

            raise
        except Exception as e:                
            
            raise ExtractorError(repr(e))
        finally:
            self.rm_driver(driver)
            


    def _real_initialize(self):

        super()._real_initialize()        

                
    def _real_extract(self, url):
        
        self.report_extraction(url)

        try:                            

            if not self.get_param('embed'): _check = True
            else: _check = False

            return self._get_entry(url, check=_check)  
            
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
                


class UpstreamIE(HLSStream):

    _SITE_URL = "https://upstream.to/"
    _VALID_URL = r'https?://upstream.to/(?P<id>.+)'
    
class VideobinIE(HLSStream):
    
    _SITE_URL = "https://videobin.co/"
    _VALID_URL = r'https://videobin.co/(?P<id>.+)'
    
    

                    
