from __future__ import unicode_literals

import re
import sys
import threading
import traceback

from backoff import constant, on_exception

from ..utils import ExtractorError, sanitize_filename
from .commonwebdriver import SeleniumInfoExtractor, limiter_1, By


class get_videourl():
    
    def __init__(self, _type):
        self.id = "player-1" if _type == "embed" else "videoplayer"
    def __call__(self, driver):
        el_player = driver.find_elements(By.ID, self.id)
        if not el_player: return False
        else:
            el_video = el_player[0].find_elements(By.TAG_NAME, "video")
            if not el_video: return False
            video_url = el_video[0].get_attribute('src')
            if video_url: 
                return video_url
            else: return False

class TheGayIE(SeleniumInfoExtractor):

    IE_NAME = 'thegay'
    _VALID_URL = r'https?://(?:www\.)?thegay\.com/(?P<type>(?:embed|videos))/(?P<id>[^\./]+)[\./]'
    _LOCK = threading.Lock()


    def _get_video_info(self, url, headers):        
        self.logger_info(f"[get_video_info] {url}")
        return self.get_info_for_format(url, headers=headers)       
            

    def _send_request(self,url, driver):
        self.logger_info(f"[send_request] {url}")   
        driver.get(url)
    
    
    @on_exception(constant, Exception, max_tries=5, interval=1)    
    @limiter_1.ratelimit("thegay", delay=True)
    def request_to_host(self, _type, url, driver=None, headers=None):
    
        if _type == "video_info":
            return self._get_video_info(url, headers)
        elif _type == "url_request":
            self._send_request(url, driver)
        elif _type == "client_request":
            res = self._CLIENT.get(url, headers = {'Referer': 'https://thegay.com/', 'Origin':'https://thegay.com' })
            res.raise_for_status()
            return res
            
    def scan_for_request(self, _har, _ref, _link):
                          
        for entry in _har['log']['entries']:
                            
            if entry['pageref'] == _ref:
                
                if _link in (_url:=entry['request']['url']):
                    
                    #self.write_debug(_url)
                    #self.write_debug(entry['request']['headers'])                   
                    
                    return _url            


    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):        
        self.report_extraction(url)
               
        _type, videoid = re.search(self._VALID_URL, url).groups()

        try:

            driver  = self.get_driver(usequeue=True)

            try:

                self.request_to_host("url_request", url, driver)
                videourl = self.wait_until(driver, 30, get_videourl(_type))
                _title = driver.title.replace(" - TheGay.com", "").strip()
                
                if not videourl: raise ExtractorError("couldnt find videourl")
                headers = {'Referer': url}
                _info_video = self.request_to_host("video_info", videourl, headers)
                if not _info_video: raise ExtractorError
                _format = {
                    'url': _info_video['url'],
                    'filesize': _info_video['filesize'],
                    'format_id': 'http',
                    'ext': 'mp4',
                    'http_headers': headers
                }
                return ({ 
                    "id": videoid,
                    "title": sanitize_filename(_title, restricted=True),                    
                    "formats": [_format],
                    "ext": "mp4"})
            
            except ExtractorError as e:
                raise
            except Exception as e:                
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
                raise ExtractorError(repr(e))
            finally:
                self.put_in_queue(driver)                    
                    
        except Exception as e:                
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(repr(e))