from __future__ import unicode_literals

import html
import re
import sys
import time
import traceback
from urllib.parse import urlparse



from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_5, By, ec, Keys


class video_or_error_streamtape():
    def __init__(self, logger):
        self.logger = logger
    def __call__(self, driver):
        try:

            elover = driver.find_elements(By.CLASS_NAME, "play-overlay")
            if elover:
                for _ in range(5):
                    try:
                        elover[0].click()
                        time.sleep(1)
                    except Exception as e:
                        break
            el_vid = driver.find_elements(By.ID, "mainvideo")
            if el_vid:
                if _src:=el_vid[0].get_attribute('src'):
                    return _src
                else:
                    return False
            else: 
                elbutton = driver.find_elements(By.CSS_SELECTOR, "button.plyr__controls__item")
                if elbutton:
                    for _ in range(5):
                        try:
                            elbutton[0].click()
                            time.sleep(1)
                        except Exception as e:
                            break
                elh1 = driver.find_elements(By.TAG_NAME, "h1")
                if elh1:
                    errormsg = elh1[0].get_attribute('innerText').strip("!")
                    self.logger(f'[streamtape_url][{driver.current_url[26:]}] error - {errormsg}')
                    return "error"
                    
                return False
        except Exception as e:
            return False


class StreamtapeIE(SeleniumInfoExtractor):

    IE_NAME = 'streamtape'
    _VALID_URL = r'https?://(www.)?streamtape\.(?:com|net)/(?:d|e|v)/(?P<id>[a-zA-Z0-9_-]+)/?((?P<title>.+)\.mp4)?'
    
    
    @staticmethod
    def _extract_urls(webpage):
        #return try_get(re.search(r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?streamtape\.(?:com|net)/(?:e|v|d)/.+?)\1',webpage), lambda x: x.group('url'))
        return [mobj.group('url') for mobj in re.finditer(r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?streamtape\.(?:com|net)/(?:e|v|d)/.+?)\1',webpage)]

    @dec_on_exception
    @limiter_5.ratelimit("streamtape", delay=True)
    def _get_video_info(self, url, headers=None, msg=None):        
        
        if msg: pre = f'{msg}[get_video_info]'
        else: pre = '[get_video_info]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}")
        return self.get_info_for_format(url, headers={'Range': 'bytes=0-', 'Referer': headers['Referer'], 'Sec-Fetch-Dest': 'video', 
                                                    'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}, verify=False)      
    
    @dec_on_exception
    @limiter_5.ratelimit("tubeload", delay=True)
    def _send_request(self, url, driver, msg=None):        
        
        if msg: pre = f'{msg}[_send_request]'
        else: pre = '[_send_request]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}")
        driver.get(url)
        

    def _get_entry(self, url, check_active=False, msg=None):
        try:
            if msg: pre = f'{msg}[get_entry][{self._get_url_print(url)}]'
            else: pre = f'[get_entry][{self._get_url_print(url)}]'
            _videoinfo = None
            driver = self.get_driver(msg=pre)
            self._send_request(url, driver, msg=pre)
            video_url = self.wait_until(driver, 30, video_or_error_streamtape(self.to_screen))
            if not video_url or video_url == 'error': raise ExtractorError('404 video not found')

            
            title = try_get(driver.title, lambda x: re.sub(r'\.mp4| at Streamtape\.com|amp;', '', x[0], re.IGNORECASE))
                                        
             
            _format = {
                'format_id': 'http-mp4',
                'url': video_url,
                'ext': 'mp4',
                'http_headers': {'Referer': url}
            }
            
            
            if check_active:
                _videoinfo = self._get_video_info(video_url, headers= {'Referer': url}, msg=pre)
                if _videoinfo:
                    _format.update({'url': _videoinfo['url'],'filesize': _videoinfo['filesize'] })
                
            _entry_video = {
                'id' : self._match_id(url),
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4',
                'extractor_key': 'Streamtape',
                'extractor': 'streamtape',
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
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))