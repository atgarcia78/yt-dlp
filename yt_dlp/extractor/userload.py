from __future__ import unicode_literals

import sys
import time
import traceback



from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_15, By, ec, HTTPStatusError


class video_or_error_userload():
    def __init__(self, logger):
        self.logger = logger
    def __call__(self, driver):
        try:
            elimg = driver.find_elements(By.CSS_SELECTOR, "img.image-blocked")
            if elimg:
                self.logger(f'[userload_url][{driver.current_url[26:]}] error - video doesnt exist')
                return "error"
            elover = driver.find_elements(By.ID, "videooverlay")
            if elover:
                for _ in range(5):
                    try:
                        elover[0].click()
                        time.sleep(1)
                    except Exception as e:
                        break
            el_vid = driver.find_elements(By.ID, "olvideo_html5_api")
            if el_vid:
                if _src:=el_vid[0].get_attribute('src'):
                    return _src
                else:
                    return False
            else: return False
        except Exception as e:
            return False

class UserLoadIE(SeleniumInfoExtractor):

    IE_NAME = 'userload'
    _VALID_URL = r'https?://(?:www\.)?userload\.co/(?:embed|e|f)/(?P<id>[^\/$]+)(?:\/|$)'

    @dec_on_exception2
    @dec_on_exception3
    @limiter_15.ratelimit("userload", delay=True)
    def _get_video_info(self, url):        
        try:
            self.logger_debug(f"[get_video_info] {url}")
            return self.get_info_for_format(url)       
        except HTTPStatusError as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
        
        
    @dec_on_exception
    @limiter_15.ratelimit("userload", delay=True)
    def _send_request(self, url, driver):        
        
        self.logger_debug(f"[send_request] {url}") 
        driver.get(url)
    
    def _get_entry(self, url, check_active=False, msg=None):
        
        try:
            
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}{pre}'
            _videoinfo = None
            driver = self.get_driver()
            self._send_request(url, driver)
            video_url = self.wait_until(driver, 30, video_or_error_userload(self.to_screen))
            if not video_url or video_url == 'error': raise ExtractorError('404 video not found')
            title = driver.title.replace(".mp4", "").split("|")[0].strip()
            videoid = self._match_id(url)
            
            _format = {
                'format_id': 'http-mp4',
                #'url': _info_video['url'],
                'url': video_url,
                #'filesize': _info_video['filesize'],
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
                'extractor_key' : 'UserLoad',
                'extractor': 'userload',
                'ext': 'mp4',
                'webpage_url': url
            } 
            return _entry_video
            
        except Exception:
            #lines = traceback.format_exception(*sys.exc_info())
            #self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise
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
    
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))

        