import sys
import traceback
import html
import re

from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_2, By, ec, HTTPStatusError, ConnectError

class get_title():
    def __call__(self, driver):
        if any(_ == driver.title.strip() for _ in  ("TXXX.com", "HotMovs.com")):
            return False
        else:
            return(driver.title)


class PornhitsIE(SeleniumInfoExtractor):

    IE_NAME = "pornhits"
    _SITE_URL = "https://www.pornhits.com/"
    _VALID_URL = r'https?://(?:www)?.pornhits.com/(?:embed\.php\?id=|video/)(?P<id>\d+)'

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
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")


    def _real_initialize(self):

        super()._real_initialize()        

                
    def _real_extract(self, url):

        try:

            videoid = self._match_id(url)
            driver = self.get_driver(devtools=True)

            if self.IE_NAME == 'pornhits' and 'embed.php' in url:
                webpage = try_get(self.send_multi_request(url), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)) if x else None)
                url = try_get(re.findall(r'/video/%s/([^\'\")]+)[\'\"]' % videoid, webpage), lambda x: f'{self._SITE_URL}video/{videoid}/{x[0]}')
                
            
            self.report_extraction(url)    
            
            self.send_multi_request(url, driver)

            if self.IE_NAME == "pornhits" or ((self.IE_NAME == 'txxx' or self.IE_NAME == 'hotmovs') and '/videos/' in url):
                title = try_get(self.wait_until(driver, 60, ec.presence_of_element_located((By.TAG_NAME, "h1"))), lambda x: x.text)
            
            else:
                title = self.wait_until(driver, 60, get_title()).replace('Porn Video | HotMovs.com', '').strip()
                
                
            
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
            
class TxxxIE(PornhitsIE):
    IE_NAME = "txxx"
    _SITE_URL = "https://txxx.com/"
    _VALID_URL = r'https?://txxx.com/(?:embed|videos)/(?P<id>\d+)'
    
class HotMovsIE(PornhitsIE):
    IE_NAME = "hotmovs"
    _SITE_URL = "https://hotmovs.com/"
    _VALID_URL = r'https?://hotmovs.com/(?:embed|videos)/(?P<id>\d+)'
    

                    
