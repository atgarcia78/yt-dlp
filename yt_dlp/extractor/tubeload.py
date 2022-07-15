from __future__ import unicode_literals

import re
import sys
import traceback
from urllib.parse import unquote

from ..utils import ExtractorError, sanitize_filename
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_15, limiter_0_07, limiter_2, limiter_0_1, limiter_0_05, By, HTTPStatusError

class getvideourl():
    def __call__(self, driver):

        if '404 - Tubeload.co' in driver.title:
            return "error404"
        el_video = driver.find_element(By.ID, "mainvideo")
        videourl = el_video.get_attribute('src')
        if not videourl:
            el_overlay = driver.find_element(By.CLASS_NAME, "plyr-overlay")
            try:
                el_overlay.click()
            except Exception as e:
                pass
            return False
        else: return unquote(videourl)
        
        

class TubeloadIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://tubeload.co"
    
    IE_NAME = 'tubeload'
    _VALID_URL = r'https?://(?:www\.)?tubeload.co/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    
    @staticmethod
    def _extract_urls(webpage):
        #return try_get(re.search(r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?streamtape\.(?:com|net)/(?:e|v|d)/.+?)\1',webpage), lambda x: x.group('url'))
        return [mobj.group('url') for mobj in re.finditer(r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?tubeload\.co/e/.+?)\1',webpage)]

        
    @dec_on_exception
    @limiter_0_05.ratelimit("tubeload", delay=True)
    def _get_video_info(self, url, msg=None):        
        
        try:
            if msg: pre = f'{msg}[get_video_info]'
            else: pre = '[get_video_info]'
            self.to_screen(f"{pre} {self._get_url_print(url)}")
            return self.get_info_for_format(url, headers={'Range': 'bytes=0-', 'Referer': self._SITE_URL + "/", 'Origin': self._SITE_URL, 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}, verify=False)
        except HTTPStatusError as e:
            self.report_warning(f"{pre} {self._get_url_print(url)}: error - {repr(e)}")
            
    
    @dec_on_exception
    @limiter_0_05.ratelimit("tubeload", delay=True)
    def _send_request(self, url, driver, msg=None):        
        
        if msg: pre = f'{msg}[_send_request]'
        else: pre = '[_send_request]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}") 
        driver.get(url)
        
    
    def _get_entry(self, url, check_active=False, msg=None):
        try:
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}{pre}'
            _videoinfo = None
            driver = self.get_driver()
            self._send_request(url, driver, msg=pre)
            video_url = self.wait_until(driver, 30, getvideourl())
            if not video_url or video_url == "error404": raise ExtractorError("error404")
            title = driver.title.replace(" at Tubeload.co","").strip()
            videoid = self._match_id(url)
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
                'extractor_key' : 'Tubeload',
                'extractor': 'tubeload',
                'ext': 'mp4',
                'webpage_url': url
            } 
            
            return _entry_video
            
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{pre}{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            self.rm_driver(driver)
        
    
       


    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):
        
        self.report_extraction(url)

        try:                            

            if self._downloader.params.get('external_downloader'): _check_active = True
            else: _check_active = False

            return self._get_entry(url, check_active=_check_active)  
            
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.report_warning(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))

