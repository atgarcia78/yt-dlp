import json
import re
import time
from threading import Lock
import sys, traceback

import httpx

from ..utils import ExtractorError, int_or_none, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_5, By, ec


class GayForFansIE(SeleniumInfoExtractor):
    IE_NAME = 'gayforfans'
    IE_DESC = 'gayforfans'
    _VALID_URL = r'https://gayforfans\.com/video/(?P<video>[a-zA-Z0-9_-]+)'
    _SITE_URL = 'https://gayforfans.com/'
    
   
    
    @dec_on_exception
    @limiter_5.ratelimit("gayforfans", delay=True)
    def _get_video_info(self, url, headers=None, msg=None):        
        
        
        pre = '[get_video_info]'
        if msg: pre = f'{msg}[get_video_info]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}")
        return self.get_info_for_format(url, headers={'Range': 'bytes=0-', 'Referer': self._SITE_URL, 'Sec-Fetch-Dest': 'video', 
                                                    'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'same-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'})      
    
    @dec_on_exception
    @limiter_5.ratelimit("gayforfans", delay=True)
    def _send_request(self, url, driver, msg=None):        
        
        
        pre = '[send_req]'
        if msg: pre = f'{msg}[send_req]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}")
        driver.get(url)
        
        
    def _get_entry(self, url, check_active=False, msg=None):
        

        try:
            
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}{pre}'
            driver = self.get_driver()
            self._send_request(url, driver)
                
            _videourl = try_get(self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME,'video'))), 
                               lambda x: try_get(x.find_elements(By.TAG_NAME, 'source'), lambda y: y[0].get_attribute('src') if y else None) if x else None)
            
            
            if not _videourl:
                raise ExtractorError('No url')
            
            _title = driver.title.strip().replace(' - Gay for Fans', '').replace(' - gayforfans.com', '')
            
            _info = try_get(re.findall(r'wpdiscuzAjaxObj = (\{[^\;]+)\;',driver.page_source), lambda x: json.loads(x[0]) if x else None)
            if _info:
                _videoid = f"POST{_info.get('wc_post_id')}"
            else: _videoid = "POST"    

            _format = {
                'format_id': 'http-mp4',
                'url': _videourl,
                'ext': 'mp4',
                'http_headers': {'Referer': self._SITE_URL}
            }
            
            if check_active:
                _videoinfo = self._get_video_info(_videourl, msg=pre)
                if not _videoinfo: raise ExtractorError("error 404: no video info")
                if _videoinfo:
                    _format.update({'url': _videoinfo['url'],'filesize': _videoinfo['filesize'] })
            
            _entry_video = {
                'id' : _videoid,
                'title' : sanitize_filename(_title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4',
                'extractor_key': 'GayForFans',
                'extractor': 'gayforfans',
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
        
        
class GayForFansPlayListIE(SeleniumInfoExtractor):
    IE_NAME = 'gayforfans:playlist'
    IE_DESC = 'gayforfans'
    _VALID_URL = r'https?://(www\.)?gayforfans\.com(?:(/(?P<type>(?:popular-videos|performer|categories))(?:/?$|(/(?P<name>[^\/$\?]+))))(?:/?$|/?\?(?P<search>[^$]+)$)|/?\?(?P<search2>[^$]+)$)'
    


    def _real_extract(self, url):

 
        self.report_extraction(url)
        driver = self.get_driver()
        
        try:
            driver.get(url)
            entries = []
            
            while True:
            
                el_videos = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.TAG_NAME,'article')))
                for _el in el_videos:
                    _url = _el.find_element(by=By.TAG_NAME, value='a').get_attribute('href')
                    if _url: entries.append({'_type': 'url', 'url': _url, 'ie_key': 'GayForFans'})

                el_next = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CSS_SELECTOR, 'a.next.page-numbers')))
                if el_next:
                    el_next[0].click()
                else:          
                    break
        
            if not entries:
                raise ExtractorError(f'no videos info')
            
            return{
                '_type': "playlist",
                'id': "gayforfans",
                'title': "gayforfans",
                'entries': entries
            }     
        
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
