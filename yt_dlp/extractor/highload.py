import sys
import traceback
import time
from urllib.parse import unquote


from ..utils import ExtractorError, sanitize_filename, traverse_obj, get_domain
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_2, limiter_0_1, HTTPStatusError, ConnectError, By, Lock


class getvideourl():
    def __call__(self, driver):

        el_video = driver.find_element(By.ID, "faststream_html5_api")
        videourl = el_video.get_attribute('src')
        if not videourl:
            el_overlay = driver.find_element(By.ID, "videerlay")
            try:
                el_overlay.click()
                time.sleep(3)
            except Exception as e:
                pass
            return False
        else: return unquote(videourl)

class FastStreamIE(SeleniumInfoExtractor):
    


    def _get_entry(self, url, check_active=False, **kwargs):
        
        @dec_on_exception3 
        @dec_on_exception2
        @limiter_0_1.ratelimit(self.IE_NAME, delay=True)
        def _get_video_info(_url):        
        
            try:
                
                _headers = {'Range': 'bytes=0-', 'Referer': self._SITE_URL + "/", 'Origin': self._SITE_URL,
                            'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site',
                            'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
            
                
                self.logger_debug(f"[get_video_info] {self._get_url_print(_url)}")
                _host = get_domain(url)                
                
                with self.get_param('lock'):
                    if not (_sem:=traverse_obj(self.get_param('sem'), _host)): 
                        _sem = Lock()
                        self.get_param('sem').update({_host: _sem})
                    
                with _sem:   
                    return self.get_info_for_format(_url, headers=_headers)
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    
   
        @dec_on_exception
        @limiter_0_1.ratelimit(self.IE_NAME, delay=True)
        def _send_request(_url, _driver):        
        
            self.logger_debug(f"[send_request] {_url}") 
            _driver.get(_url)
        
        
        
        _videoinfo = None
        driver = self.get_driver()
        
        try:
            _send_request(url, driver)
            video_url = self.wait_until(driver, 30, getvideourl())
            if not video_url or video_url == "error404": raise ExtractorError("error404")
            title = driver.title.replace(self._SUBS_TITLE,"").replace(".mp4","").strip('[_,-, ]')
            videoid = self._match_id(url)
            
            _format = {
                'format_id': 'http-mp4',                
                'url': video_url,
                'http_headers': {'Referer': f'{self._SITE_URL}/', 'Origin': self._SITE_URL},               
                'ext': 'mp4'
            }
            
            if check_active:
                _videoinfo = _get_video_info(video_url)
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

            if not self.get_param('embed'): _check_active = True
            else: _check_active = False

            return self._get_entry(url, check_active=_check_active)  
            
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        
class EmbedoIE(FastStreamIE):
    
    _SITE_URL = "https://embedo.co"
    
    IE_NAME = 'embedo'
    _VALID_URL = r'https?://(?:www\.)?embedo.co/e/(?P<id>[^\/$]+)(?:\/|$)'
    _SUBS_TITLE = " - embedo.co"
    
class HighloadIE(FastStreamIE):
    
    _SITE_URL = "https://highload.to"
    
    IE_NAME = 'highload'
    _VALID_URL = r'https?://(?:www\.)?highload.to/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    _SUBS_TITLE = " - Highload.to"