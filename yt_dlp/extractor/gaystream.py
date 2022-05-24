from __future__ import unicode_literals

import sys
import time
import traceback
from random import randint
from threading import Lock

import httpx
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

from ..utils import ExtractorError, int_or_none, sanitize_filename
from .commonwebdriver import SeleniumInfoExtractor


class GayStreamIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://gaystream.pw"
    
    IE_NAME = 'gaystream'
    _VALID_URL = r'https?://(?:www\.)?gaystream.pw/video/(?P<id>\d+)/?([^$]+)?$'

 
    
    _LOCK =  Lock()
    
 
    
    def get_info_video(self, url, url_post, data_post, headers_post, driver):
        
        count = 0
        while count < 5:
            try:
                res = httpx.post(url_post, data=data_post, headers=headers_post)
                self.to_screen(f'{count}:{url}:{url_post}:{res}')
                if res.status_code > 400:
                    count += 1
                    self.wait_until(driver, randint(10,15))                                        
                else:
                    info_video = res.json()                    
                    return info_video
            except Exception as e:
                count += 1
                    
                
     


    def _real_extract(self, url):
        
        self.report_extraction(url)
 
        driver = self.get_driver(usequeue=True)            
   
                            
        try: 
            
           
            with GayStreamIE._LOCK: 
                
                driver.get(url)
            
            el_over =  self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "a.boner")))
            if el_over:
                el_over.click()
            
            el_ifr = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID, "ifr")))
            _entry_video = {}
            
            if el_ifr:
                url_ifr = el_ifr.get_attribute("src")
                _url_ifr = httpx.URL(url_ifr)
                url_post = url_ifr.replace('/v/', '/api/source/') 
                data_post = {'r': "https://gaystream.pw/", 'd': _url_ifr.host}
                headers_post = {'Referer': url_ifr, 'Origin': f'{_url_ifr.scheme}://{_url_ifr.host}'}
                self.wait_until(driver, randint(3,5))
                info = self.get_info_video(url, url_post, data_post, headers_post, driver)
                self.to_screen(f'{url}:{url_post}\n{info}')
                _formats = []
                if info:
                    for vid in info.get('data'):
                        _url = vid.get('file')
                        _info_video = self.get_info_for_format(_url)
                        if not _info_video: raise ExtractorError(f"[{_url}] no video info")
                        _formats.append({
                                'format_id': vid.get('label'),
                                'url': _info_video.get('url'),
                                'resolution' : vid.get('label'),
                                'height': int_or_none(vid.get('label')[:-1]),                                
                                'filesize': _info_video.get('filesize'),
                                'ext': 'mp4'
                            })
            
                    if _formats: self._sort_formats(_formats)
                    _videoid = self._match_id(url)
                    _title = driver.title.replace("Watch","").replace("on Gaystream.pw","").strip()        
    
                
                
                    _entry_video = {
                        'id' : _videoid,
                        'title' : sanitize_filename(_title, restricted=True),
                        'formats' : _formats,
                        'ext': 'mp4'
                    } 
                    
                    self.to_screen(f'{url}\n{_entry_video}') 
                    
                    if not _entry_video: raise ExtractorError("no video info")
                    else:
                        return _entry_video      
         
        except ExtractorError as e:
            raise        
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e))
        finally:
            try:
                self.put_in_queue(driver)
            except Exception:
                pass
