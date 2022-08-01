from __future__ import unicode_literals

import html
import re
from threading import Lock


from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_1, By, ec


class ifr_or_captcha():
    def __call__(self, driver):
        el_capt = driver.find_elements(By.ID, 'stream-encrypt-bot')
        if el_capt: return {'error': 'capt'}
        ifr_url = try_get(driver.find_elements(By.TAG_NAME, 'iframe'), lambda x: x[0].get_attribute('src'))
        if ifr_url: return {'iframe': ifr_url}
        else: return False
        
        
class PornDuneIE(SeleniumInfoExtractor):

    IE_NAME = 'porndune'
    _SITE_URL = "https://porndune.com"
    _VALID_URL = r'https?://porndune\.com/en/watch\?v\=(?P<id>\w+)'
    
    _LOCK = Lock()
    _COOKIES = {}
    
    @dec_on_exception
    @limiter_1.ratelimit("porndune", delay=True)
    def _send_request(self, url, _type="GET", data=None, headers=None):        
        
        self.logger_debug(f"[send_req] {self._get_url_print(url)}") 
        return(self.send_http_request(url, _type=_type, data=data, headers=headers))

    @dec_on_exception
    @limiter_1.ratelimit("porndune", delay=True)
    def _get_infovideo(self, url):       
        
        return self.get_info_for_format(url)

    
    def _get_video_entry(self, video_url, title=None):
        
        ie_traff = self._downloader.get_info_extractor('TrafficDePot')
        ie_traff._real_initialize()
        if ie_traff.suitable(video_url):
            _entry = ie_traff._get_video_entry(video_url)
            if title: _entry.update({'title': title})
            return _entry
        
        
    
    def _real_initialize(self): 
        
                  
        super()._real_initialize()
        
    def _real_extract(self, url):        

        self.report_extraction(url)
        #video_id = self._match_id(url)
        try:
        
            driver = self.get_driver()
            driver.get(url)
            ifr_url = try_get(self.wait_until(driver, 30, ifr_or_captcha()), lambda x: x.get('iframe'))
            title = try_get(re.findall(r'og:title" content="([^"]+)"', html.unescape(driver.page_source)), lambda x: sanitize_filename(x[0], restricted=True))
            if not ifr_url:
                
                _driver = self.get_driver(noheadless=True)
                _driver.get(url)
                ifr_url = try_get(self.wait_until(_driver, 60, ec.presence_of_element_located((By.TAG_NAME, 'iframe'))), lambda x: x.get_attribute('src'))
                PornDuneIE._COOKIES = _driver.get_cookies()
                self.rm_driver(_driver)
            
            else: PornDuneIE._COOKIES = driver.get_cookies()

            for cookie in PornDuneIE._COOKIES:
                PornDuneIE._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])

            if not (_entry:= self._get_video_entry(ifr_url, title)):
                raise ExtractorError('No entry video')
            else:
                return _entry
        
        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))
        finally:
            self.rm_driver(driver)
        
 