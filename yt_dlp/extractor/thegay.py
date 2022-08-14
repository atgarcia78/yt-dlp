import time
import sys
import traceback
from urllib.parse import unquote, urlparse
import re

from ..utils import ExtractorError, sanitize_filename, traverse_obj
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_15, limiter_1, limiter_5, limiter_0_1, limiter_0_5, By, HTTPStatusError


class get_videourl():
    
    def __init__(self, _type):
        self.id = "player-1"  if _type == "embed" else "videoplayer"
    def __call__(self, driver):
        el_player = driver.find_element(By.ID, self.id)
        el_video = el_player.find_element(By.TAG_NAME, "video")
        video_url = el_video.get_attribute('src')
        if video_url: 
            return unquote(video_url)
        else: return False

class TheGayIE(SeleniumInfoExtractor):

    IE_NAME = 'thegay'
    _VALID_URL = r'https?://(?:www\.)?thegay\.com/(?P<type>(?:embed|videos))/(?P<id>\d+)/?'
    


    @dec_on_exception3  
    @dec_on_exception2
    @limiter_1.ratelimit("thegay", delay=True)
    def _get_video_info(self, url, **kwargs):        
        
        msg = kwargs.get('msg',None)
        headers = kwargs.get('headers', {})
                
        try:
            if msg: pre = f'{msg}[get_video_info]'
            else: pre = '[get_video_info]'
            self.logger_debug(f"{pre} {self._get_url_print(url)}")
      
            return self.get_info_for_format(url, headers={'Range': 'bytes=0-', 'Referer': headers['Referer'], 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'same-origin', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'})
        except HTTPStatusError as e:
            self.report_warning(f"{pre} {self._get_url_print(url)}: error - {repr(e)}")


    @dec_on_exception
    @limiter_1.ratelimit("thegay", delay=True)
    def _send_request(self, url, **kwargs):        
        
        msg = kwargs.get('msg',None)
        driver = kwargs.get('driver', None)
        
        if msg: pre = f'{msg}[send_req]'
        else: pre = '[send_req]'
        if driver:
            self.logger_debug(f"{pre} {self._get_url_print(url)}") 
            driver.get(url)


    def _get_entry(self, url, **kwargs):
        
        check_active = kwargs.get('check_active', False)
        msg = kwargs.get('msg', None)
         

        try:
            
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}{pre}'
            driver = self.get_driver()

            self._send_request(url, driver=driver)     
            
            _type, videoid = re.search(self._VALID_URL, url).groups()       

            videourl = self.wait_until(driver, 30, get_videourl(_type))
            if not videourl: raise ExtractorError("couldnt find videourl")
            
            _title = re.sub(r'(?i)( - %s\..+$)' % self.IE_NAME, '', driver.title.replace('.mp4','')).strip('[_,-, ]')
            headers = {'Referer': url}
            
            _format = {
                    'url': videourl,                    
                    'format_id': 'http',
                    'ext': 'mp4',
                    'http_headers': headers
            }
            if check_active:
                _videoinfo = self._get_video_info(videourl, headers=headers)
                if not _videoinfo: raise ExtractorError("error 404: no video info")
                else:
                    _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})
            

            return ({ 
                "id": videoid,
                "title": sanitize_filename(_title, restricted=True),                    
                "formats": [_format],
                "ext": "mp4",
                'extractor_key': self.ie_key(),
                'extractor': self.IE_NAME,
                'webpage_url': url})
            
       
            
      
        
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
            
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.report_warning(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        
        
