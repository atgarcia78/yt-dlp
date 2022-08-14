import time
import sys
import traceback
from urllib.parse import unquote, urlparse
import re

from ..utils import ExtractorError, sanitize_filename, traverse_obj
from .commonwebdriver import (
    dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, 
    limiter_15, limiter_0_07, limiter_5, limiter_0_1, limiter_0_5, By, HTTPStatusError, PriorityLock)

class getvideourl():
    def __call__(self, driver):

        if '404 - Tubeload.co' in driver.title:
            return "error404"
        if (el_overlay:=driver.find_elements(By.CLASS_NAME, "plyr-overlay")):
            try:
                el_overlay[0].click()
                time.sleep(1)
            except Exception as e:
                pass
            
        el_video = driver.find_element(By.ID, "mainvideo")
        if (videourl:=el_video.get_attribute('src')):
            return unquote(videourl)
        else: return False
        

class TubeloadIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://tubeload.co"
    
    IE_NAME = 'tubeload'
    _VALID_URL = r'https?://(?:www\.)?tubeload.co/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?tubeload\.co/e/.+?)\1']
    

    @dec_on_exception3  
    @dec_on_exception2
    @limiter_0_5.ratelimit("tubeload", delay=True)
    def _get_video_info(self, url, msg=None):        
        
        try:
            if msg: pre = f'{msg}[get_video_info]'
            else: pre = '[get_video_info]'
            self.logger_debug(f"{pre} {self._get_url_print(url)}")
            _host = urlparse(url).netloc
            if not (_sem:=traverse_obj(self._downloader.params, ('sem', _host))):  
                self._downloader.sem.update({_host: (_sem:=PriorityLock())})
            _sem.acquire(priority=10)                
            return self.get_info_for_format(url, headers={'Range': 'bytes=0-', 'Referer': self._SITE_URL + "/", 'Origin': self._SITE_URL, 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'})
        except HTTPStatusError as e:
            self.report_warning(f"{pre} {self._get_url_print(url)}: error - {repr(e)}")
        finally:
            if _sem: _sem.release()
            
    
    @dec_on_exception
    @limiter_0_5.ratelimit("tubeload", delay=True)
    def _send_request(self, url, driver, msg=None):        
        
        if msg: pre = f'{msg}[send_req]'
        else: pre = '[send_req]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}") 
        driver.get(url)
        
    
    def _get_entry(self, url, check_active=False, msg=None):
        try:
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}{pre}'
            _videoinfo = None
            driver = self.get_driver()
            videoid = self._match_id(url)
            self._send_request(f"{self._SITE_URL}/e/{videoid}", driver, msg=pre)
            video_url = self.wait_until(driver, 30, getvideourl())
            if not video_url or video_url == "error404": raise ExtractorError("error404")
            title = re.sub(r'(?i)((at )?%s.co$)' % self.IE_NAME, '', driver.title.replace('.mp4','')).strip('[_,-, ]')
                        
            _format = {
                'format_id': 'http-mp4',
                'url': video_url,               
                'http_headers': {'Referer': f'{self._SITE_URL}/', 'Origin': self._SITE_URL},
                'ext': 'mp4'
            }

            if check_active:
                _videoinfo = self._get_video_info(video_url, msg=pre)
                if not _videoinfo: raise ExtractorError("error 404: no video info")
                else:
                    _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})

            _entry_video = {
                'id' : videoid,
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [_format],
                'extractor_key' : self.ie_key(),
                'extractor': self.IE_NAME,
                'ext': 'mp4',
                'webpage_url': url
            } 
            
            return _entry_video
            
        except Exception:

            raise
        finally:
            self.rm_driver(driver)

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):
        
        self.report_extraction(url)

        try:                            

            if self.get_param('external_downloader'): _check_active = True
            else: _check_active = False

            return self._get_entry(url, check_active=_check_active)  
            
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.report_warning(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))

class RedloadIE(TubeloadIE):
    
    _SITE_URL = "https://redload.co"
    
    IE_NAME = 'redload'
    _VALID_URL = r'https?://(?:www\.)?redload.co/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?redload\.co/e/.+?)\1']