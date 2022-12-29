import re
import sys
import time
import traceback
from urllib.parse import unquote

from .commonwebdriver import (
    By,
    ConnectError,
    HTTPStatusError,
    Lock,
    SeleniumInfoExtractor,
    dec_on_exception,
    dec_on_exception2,
    dec_on_exception3,
    dec_on_driver_timeout,
    limiter_5,
    TimeoutException,
    WebDriverException
)
from ..utils import (
    ExtractorError,
    get_domain,
    sanitize_filename,
    traverse_obj,
    try_get,
)


class video_or_error_evoload:
    def __init__(self, logger):
        self.logger = logger
        self.init = True
    def __call__(self, driver):
        try:
            elvid = driver.find_elements(By.ID, "EvoVid_html5_api")
            if not elvid:
                errormsg = (
                    try_get(
                        driver.find_elements(By.CLASS_NAME, "img"), lambda x: x[1].get_attribute('innerText').replace('\n','').strip()
                    )
                    or ""
                )
                if errormsg:
                    self.logger(f'[evoload_url][{driver.current_url[26:]}] error - {errormsg}')
                    return "error"
                else:
                    elpreload = driver.find_elements(By.ID, "preloader")
                    if elpreload:
                        if self.init:
                            self.init = False
                            time.sleep(5)                            
                            return False
                        else:
                            
                            self.logger(
                                f"[evoload_url][{driver.current_url[26:]}] error - preloader"
                            )
                        return "error"
                    else:
                        return False

            else:
                if _src:=elvid[0].get_attribute("src"):
                    return unquote(_src)
                else:
                    return False
        except Exception as e:
            return False

class get_title:
    def __call__(self, driver):
        
        el = driver.find_elements(by=By.CSS_SELECTOR, value="h3")        
        if el:            
            text = el[0].get_attribute('innerText')
            if text:
                text = re.sub(r"evoload|Evoload|\.mp4", "", text)                
                subtext = text[0:int(len(text) / 2 * 0.9)]
                if text.count(subtext) > 1:
                    text = text[0:text.rindex(subtext) - 1]
                text = text.replace("-","_").replace(".", "_").strip('_ ')
                return text
            else:
                return False                       
        else:       
            return False
        
       
class EvoLoadIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://evoload.io"
    
    IE_NAME = 'evoload'
    _VALID_URL = r'https?://(?:www\.)?evoload.io/(?:e|v)/(?P<id>[^\/$/?]+)'
    
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https://evoload\.io/e/.+?)\1']

    @dec_on_exception2
    @dec_on_exception3
    @limiter_5.ratelimit("evoload", delay=True)
    def _get_video_info(self, url, **kwargs):        
         
        try:            
            self.logger_debug(f"[get_video_info] {url}")
            
            _headers = {'Range': 'bytes=0-', 'Sec-Fetch-Dest': 'video', 
                        'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site',
                        'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
                        
            _host = get_domain(url)
            
            with self.get_param('lock'):
                if not (_sem:=traverse_obj(self.get_param('sem'), _host)): 
                    _sem = Lock()
                    self.get_param('sem').update({_host: _sem})
                
            with _sem:
                return self.get_info_for_format(url, headers=_headers, **kwargs)    
        
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
         
            
    @dec_on_driver_timeout
    @limiter_5.ratelimit("evoload2", delay=True)
    def _send_request(self, url, driver):
        
        self.logger_debug(f"[send_request] {url}")   
        driver.execute_script("window.stop();")
        driver.get(url)
        
    
    def _get_entry(self, url, check=False, msg=None):
        
        try:
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}{pre}'
            
            driver = self.get_driver()
            driver.set_page_load_timeout(10)
            self._send_request(url.split('?')[0].replace('/v/', '/e/'), driver)
            video_url = self.wait_until(driver, 30, video_or_error_evoload(self.to_screen))
            if not video_url or video_url == 'error': raise ExtractorError("404 not video found")
            
            _format = {
                'format_id': 'http-mp4',
                'url': video_url,
                'ext': 'mp4'
            }
            
            self._send_request(url.split('?')[0].replace('/e/', '/v/'), driver)
            _title =  self.wait_until(driver, 30, get_title()) 
            videoid = self._match_id(url.split('?')[0])        

            if check:
                _videoinfo = self._get_video_info(video_url, msg=pre)
                if not _videoinfo: raise ExtractorError("error 404: no video info")
                else:
                    _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})
            
            _entry_video = {
                'id' : videoid,
                'title' : sanitize_filename(_title, restricted=True),
                'formats' : [_format],
                'extractor_key' : 'EvoLoad',
                'extractor': 'evoload',
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

            if not self.get_param('embed'): _check = True
            else: _check = False

            return self._get_entry(url, check=_check)  
            
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.report_warning(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
            
