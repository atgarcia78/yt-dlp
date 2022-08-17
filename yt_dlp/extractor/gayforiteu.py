import html
import re
import sys
import traceback
from lzma import PRESET_DEFAULT
from urllib.parse import unquote


from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, HTTPStatusError, ConnectError, SeleniumInfoExtractor, limiter_5, By

class getvideourl():
    def __call__(self, driver):
        el_video = driver.find_element(By.CSS_SELECTOR, 'video')
        if (video_url:=el_video.get_attribute('src')):
            return unquote(video_url).replace("medialatest-cdn.gayforit.eu", "media.gayforit.eu")
        else: return False
        

class GayForITEUIE(SeleniumInfoExtractor):
    
    _VALID_URL = r'https?://(?:www\.)gayforit\.eu/(?:playvideo.php\?vkey\=[^&]+&vid\=(?P<vid>[\w-]+)|video/(?P<id>[\w-]+)|playvideo.php\?vkey\=.+)'

    
    @dec_on_exception
    @limiter_5.ratelimit("gayforiteu", delay=True)
    def _send_request(self, url, **kwargs):        

        if (driver:=kwargs.get('driver')):
            driver.get(url)
        

    @dec_on_exception3
    @dec_on_exception2
    @limiter_5.ratelimit("gayforiteu", delay=True)
    def _get_video_info(self, url, **kwargs):        

        try:
            return self.get_info_for_format(url, **kwargs)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
            

    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
        
        self.report_extraction(url)
        driver = self.get_driver()
        try:
            videoid = try_get(re.search(self._VALID_URL, url), lambda x: x.groups()[0] or x.groups()[1])
            self._send_request(url, driver=driver)
            video_url = self.wait_until(driver, 30, getvideourl())
            if not video_url:
                raise ExtractorError("no video url")
           

            title = try_get(driver.find_elements(By.XPATH, "//li[label[text()='Title:']]"), lambda x: x[0].text.split('\n')[1].strip('[ ,_-]'))
            
            if not title:
                title = try_get(re.findall(r'GayForIt\.eu - Free Gay Porn Videos - (.+)', driver.title, re.IGNORECASE), lambda x: x[0])         

 
            self.logger_debug(f"[video_url] {video_url}")
            
            _headers = {"Referer" : "https://www.gayforit.eu/"}
            
            _info_video = self._get_video_info(video_url, headers=_headers)
            
            if not _info_video: 
                raise ExtractorError("no video info")

            format_video = {
                'format_id' : "http-mp4",
                'url' : _info_video['url'].replace("medialatest-cdn.gayforit.eu", "media.gayforit.eu"),
                'filesize' : _info_video['filesize'],
                'http_headers': _headers,
                'ext' : 'mp4'
            }

            entry = {
                'id': videoid,
                'title': sanitize_filename(title.strip(), restricted=True).replace('-',''),
                'formats': [format_video],
                'ext': 'mp4',
                'webpage_url': url,
                'extractor': self.IE_NAME,
                'extractor_key': self.ie_key()
            }
            
                        
            return entry
        
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}') 
            raise ExtractorError({repr(e)})
        finally:
            self.rm_driver(driver)
