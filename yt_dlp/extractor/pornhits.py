import sys
import traceback

from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_2, By, ec, HTTPStatusError



class PornhitsIE(SeleniumInfoExtractor):

    IE_NAME = "pornhits"
    _SITE_URL = "https://www.pornhits.com/"
    _VALID_URL = r'https?://www.pornhits.com/video/(?P<id>\d+)'

    @dec_on_exception
    @dec_on_exception2
    @dec_on_exception3
    @limiter_2.ratelimit("pornhits", delay=True)
    def send_multi_request(self, url, driver=None, _type=None, headers=None):
        
        if driver:
            driver.execute_script("window.stop();")
            driver.get(url)
        else:
            try:
                if not _type:                
                    return self.send_http_request(url, headers=headers)
                else:
                    return self.get_info_for_format(url, headers=headers)
            except HTTPStatusError as e:
                self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")


    def _real_initialize(self):

        super()._real_initialize()        

                
    def _real_extract(self, url):

        try:
            
            self.report_extraction(url)
            videoid = self._match_id(url)
            driver = self.get_driver(devtools=True)
            
                      
            
            self.send_multi_request(url, driver)

            title = try_get(self.wait_until(driver, 60, ec.presence_of_element_located((By.TAG_NAME, "h1"))), lambda x: x.text)

            #video_url = self.wait_until(driver, 60, getvideourl())
            
            _headers = {'Referer': self._SITE_URL, 'Origin': self._SITE_URL.strip("/")}
            
            _formats = None             
            m3u8_url, m3u8_doc = self.scan_for_request(driver, r".mp4$")
            if m3u8_url:
                if not m3u8_doc:
                    m3u8_doc = try_get(self.send_multi_request(m3u8_url, headers=_headers), lambda x: (x.content).decode('utf-8', 'replace'))
                
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
                "formats": _formats,
                "webpage_url": url,                             
                "ext": "mp4"})
            

        
        except ExtractorError as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise
        except Exception as e:                
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(repr(e))
        finally:
            self.rm_driver(driver)

                    
