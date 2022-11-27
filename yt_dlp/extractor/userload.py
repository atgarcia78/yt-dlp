import sys
import time
import traceback
from urllib.parse import unquote

from ..utils import ExtractorError, sanitize_filename, traverse_obj, get_domain
from .commonwebdriver import (
    dec_on_exception, dec_on_exception2, dec_on_exception3, 
    SeleniumInfoExtractor, limiter_15, limiter_5, limiter_10, By, ec, HTTPStatusError, ConnectError,
    Lock, TimeoutException, WebDriverException, dec_on_driver_timeout)




class video_or_error_userload:
    
    def __call__(self, driver):
        try:
            elimg = driver.find_elements(By.CSS_SELECTOR, "img.image-blocked")
            if elimg:
                
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
                    return unquote(_src)
                else:
                    return False
            else: return False
        except Exception as e:
            return False

class UserLoadIE(SeleniumInfoExtractor):

    IE_NAME = 'userload'
    _VALID_URL = r'https?://(?:www\.)?userload\.co/(?:embed|e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    _SITE_URL = 'https://userload.co/'
    
    @dec_on_exception2
    @dec_on_exception3
    @limiter_5.ratelimit("userload", delay=True)
    def _get_video_info(self, url, msg=None):        
        try:
            pre = '[get_video_info]'
            if msg: pre = f'{msg}{pre}'
            self.logger_debug(f"{pre} {self._get_url_print(url)}")
            _headers = {'Range': 'bytes=0-', 'Referer': self._SITE_URL,
                        'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
                        'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
            _host = get_domain(url)
            
            with self.get_param('lock'):
                if not (_sem:=traverse_obj(self.get_param('sem'), _host)): 
                    _sem = Lock()
                    self.get_param('sem').update({_host: _sem})
                
            with _sem:   
                return self.get_info_for_format(url, headers=_headers)       
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
        
        
        
    @dec_on_driver_timeout
    @dec_on_exception3
    @dec_on_exception2    
    def _send_request(self, url, **kwargs):        
        
        driver = kwargs.get('driver', None)
         
        if driver:
            with limiter_5.ratelimit("userload2", delay=True):
                self.logger_debug(f"[send_request] {url}")
                driver.get(url)
        else:
            with limiter_5.ratelimit("userload2", delay=True):
                self.logger_debug(f"[send_request] {url}")
                try:
                    return self.send_http_request(url)
                except (HTTPStatusError, ConnectError) as e:
                    self.report_warning(f"[send_request] {self._get_url_print(url)}: error - {repr(e)}")
    
    def _get_entry(self, url, **kwargs):
        
        check_active = kwargs.get('check_active', False)
        msg = kwargs.get('msg', None)
        
        try:
            
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}{pre}'
            
            driver = self.get_driver()
            self._send_request(url.replace('userload.co/embed/', 'userload.co/f/').replace('userload.co/e/', 'userload.co/f/'), driver=driver)
            video_url = self.wait_until(driver, 30, video_or_error_userload())
            if not video_url or video_url == 'error': raise ExtractorError('404 video not found')
            title = driver.title.replace(".mp4", "").split("|")[0].strip()
            videoid = self._match_id(url)
            
            _format = {
                'format_id': 'http-mp4',
                'url': video_url,
                'ext': 'mp4',
                'http_headers': {'Referer': self._SITE_URL}
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
            
        except (WebDriverException, TimeoutException) as e:
            raise ExtractorError(f"no webpage - error 404 - {e.msg}")
        except ExtractorError as e:
            raise
        except Exception as e:                
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(f"{repr(e)} {str(e)}")
        finally:
            self.rm_driver(driver)
        
        
    
    def _real_initialize(self):
        super()._real_initialize()
    
    
    def _real_extract(self, url):

        self.report_extraction(url)
            
        try:

            if not self.get_param('embed'): _check_active = True
            else: _check_active = False

            return self._get_entry(url, check_active=_check_active)  
    
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))

        