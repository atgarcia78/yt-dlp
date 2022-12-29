import sys
import traceback

from ..utils import ExtractorError, sanitize_filename
from .commonwebdriver import (
    dec_on_exception, dec_on_exception2, dec_on_exception3, 
    SeleniumInfoExtractor, limiter_5, By, HTTPStatusError, ConnectError)


class video_or_error_eplayvid:
    
    def __call__(self, driver):
        try:
                        
            el_vid = driver.find_elements(By.ID, "player_html5_api")
            if el_vid:
                el_src = el_vid[0].find_elements(By.TAG_NAME, "source")
                if el_src:
                    if _src := el_src[0].get_attribute("src"):
                        return _src
            return False
        except Exception as e:
            return False


class EPlayVidIE(SeleniumInfoExtractor):

    IE_NAME = 'eplayvid'
    _VALID_URL = r'https?://(?:www\.)?eplayvid\.net/watch/[^\/$]+'

    @dec_on_exception2
    @dec_on_exception3
    @limiter_5.ratelimit("eplayvid", delay=True)
    def _get_video_info(self, url):
        
        pre = '[get_video_info]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}")
        _headers = {'Range': 'bytes=0-', 'Referer': 'https://eplayvid.net/',
                        'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
                        'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
        try:
            return self.get_info_for_format(url, headers=_headers)
            #return self.get_info_for_format(url, headers={'Referer': 'https://eplayvid.net/'})
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")        
        

    @dec_on_exception
    @limiter_5.ratelimit("eplayvid", delay=True)
    def _send_request(self, url, driver):        
        
        self.logger_debug(f"[send_request] {url}") 
        driver.get(url)
    
    def _get_entry(self, url, check=False, msg=None):
        
        try:
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}{pre}'
           
            driver = self.get_driver()
            self._send_request(url, driver)
            video_url = self.wait_until(driver, 30, video_or_error_eplayvid())
            if not video_url or video_url == 'error': raise ExtractorError('404 video not found')
            
            _format = {
                'format_id': 'http-mp4',
                'url': video_url,
                'ext': 'mp4'
            }

            if check:
                _videoinfo = self._get_video_info(video_url)
                if not _videoinfo: raise ExtractorError("error 404: no video info")
                else:
                    _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})

            video_id = video_url.split("___")[-1].replace(".mp4", "")
            title = video_url.split('/')[-1].replace(".mp4", "").replace(video_id, "").strip()

            _entry_video = {
                'id' : video_id,
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [_format],
                'extractor_key' : 'EplayVid',
                'extractor': 'eplayvid',
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

            if not self.get_param('embed'): _check = True
            else: _check = False

            return self._get_entry(url, check=_check)  
            
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.report_warning(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        