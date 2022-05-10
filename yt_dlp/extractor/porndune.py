from __future__ import unicode_literals
from concurrent.futures import ThreadPoolExecutor

import re

import sys
import traceback

from httpx import HTTPStatusError

from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_1
)

from ..utils import (
    ExtractorError,
    sanitize_filename,
    try_get,
    urljoin,
    datetime_from_str,
    get_elements_by_class)

from urllib.parse import unquote
import html
from threading import Lock

from backoff import on_exception, constant

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

from datetime import datetime

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


 
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @limiter_1.ratelimit("porndune", delay=True)
    def _send_request(self, url, _type="GET", data=None, headers=None):        
        
        try:
            if len(url) > 150:
                _url_str = f'{url[:140]}...{url[-10:]}'
            else: _url_str = url
            #self.logger_info(f"[send_request] {_url_str}") 
            res = self.send_request(url, _type=_type, data=data, headers=headers)
            res.raise_for_status()
            return res
        except HTTPStatusError as e:
            return
        
            

    @on_exception(constant, Exception, max_tries=5, interval=1)
    @limiter_1.ratelimit("porndune", delay=True)
    def _get_infovideo(self, url):       
        
        return self.get_info_for_format(url)

    def _real_initialize(self):
           
        super()._real_initialize()
        
    def _real_extract(self, url):

        self.report_extraction(url)
        #video_id = self._match_id(url)
        try:
        
            driver = self.get_driver(usequeue=True)
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
            
                    
            ie_traff = self._downloader.get_info_extractor('TrafficDePot')
            ie_traff._real_initialize()
            if ie_traff.suitable(ifr_url):
                _entry = ie_traff._get_video_entry(ifr_url)
                _entry.update({'title': title})
                return _entry
        
        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))
        finally:
            self.put_in_queue(driver)
        
 