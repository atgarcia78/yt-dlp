# coding: utf-8
from __future__ import unicode_literals


from .webdriver import SeleniumInfoExtractor
from ..utils import (
    ExtractorError,
    sanitize_filename,
    int_or_none,
    std_headers   
)

import time
import traceback
import sys
from random import randint

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


from threading import Lock

import httpx


class GayStreamIE(SeleniumInfoExtractor):
    
    _SITE_URL = "https://gaystream.pw"
    
    IE_NAME = 'gaystream'
    _VALID_URL = r'https?://(?:www\.)?gaystream.pw/video/(?P<id>\d+)/?([^$]+)?$'

 
    
    _LOCK =  Lock()
    

    
    def _get_filesize(self, url):
        
        count = 0
        try:
            
            _res = None
            while (count<3):
                
                try:
                    
                    res = httpx.head(url, headers=std_headers)
                    if res.status_code > 400:
                        time.sleep(10)
                        count += 1
                    else: 
                        _res = int_or_none(res.headers.get('content-length')) 
                        break
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass

        
        return _res
    
    def get_info_video(self, url, url_post, data_post, headers_post, driver):
        
        count = 0
        while count < 5:
            try:
                res = httpx.post(url_post, data=data_post, headers=headers_post)
                self.to_screen(f'{count}:{url}:{url_post}:{res}')
                if res.status_code > 400:
                    count += 1
                    self.wait_until(driver, randint(10,15), ec.title_is("DUMMYFORWAIT"))                                        
                else:
                    info_video = res.json()                    
                    return info_video
            except Exception as e:
                count += 1
                    
                
     


    def _real_extract(self, url):
        
        self.report_extraction(url)
 
        driver = self.get_driver()            
   
                            
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
                self.wait_until(driver, randint(3,5), ec.title_is("DUMMYFORWAIT"))
                info_video = self.get_info_video(url, url_post, data_post, headers_post, driver)
                self.to_screen(f'{url}:{url_post}\n{info_video}')
                _formats = []
                if info_video:
                    for vid in info_video.get('data'):
                        _formats.append({
                                'format_id': vid.get('label'),
                                'url': (_url:=vid.get('file')),
                                'resolution' : vid.get('label'),
                                'height': int_or_none(vid.get('label')[:-1]),                                
                                'filesize': self._get_filesize(_url),
                                'ext': "mp4"
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
            raise ExtractorError(str(e)) from e
        finally:
            try:
                self.rm_driver(driver)
            except Exception:
                pass
        
 

