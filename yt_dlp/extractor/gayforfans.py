# coding: utf-8
from __future__ import unicode_literals

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
import re
import json

from .webdriver import SeleniumInfoExtractor

from ..utils import (
    ExtractorError,
    int_or_none,
    sanitize_filename,

)

import httpx
import time
from threading import Lock


class GayForFansIE(SeleniumInfoExtractor):
    IE_NAME = 'gayforfans'
    IE_DESC = 'gayforfans'
    _VALID_URL = r'https://gayforfans\.com/video/(?P<video>[a-zA-Z0-9_-]+)'
    
   

    _LOCK = Lock()
    
    def _get_filesize(self, url):
        
        count = 0
        try:
            
            _res = None
            while (count<3):
                
                try:
                    
                    res = httpx.head(url)
                    if res.status_code > 400:
                        time.sleep(1)
                        count += 1
                    else: 
                        _res = int_or_none(res.headers.get('content-length'))
                       
                        break
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass

        
        return _res


    def _real_extract(self, url):

 
        self.report_extraction(url)
            
        driver = self.get_driver()
        
        try:
            
            with GayForFansIE._LOCK:
                driver.get(url)
                
            el_video = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.TAG_NAME,'video')))
            
            _url = el_video[0].find_element(by=By.TAG_NAME, value='source').get_attribute('src') if el_video else None
            
            
            _title = driver.title.replace(' – Gay for Fans – gayforfans.com', '')
            
            mobj = re.findall(r'wpdiscuzAjaxObj = (\{[^\;]+)\;',driver.page_source)
            if mobj:
                _info = json.loads(mobj[0])
                _videoid = f"POST{_info.get('wc_post_id')}"
            else: _videoid = "POST"    
            if not _url:
                raise ExtractorError('No url')
            
            filesize = self._get_filesize(_url)
            format_video = {
                'format_id' : 'http-mp4',
                'url' : _url,
                'filesize' : filesize,
                'ext' : 'mp4'
            }
            return {
                'id': _videoid,
                'title': sanitize_filename(_title, restricted=True),
                'formats': [format_video],
                'ext': 'mp4'
            
            }          


        except Exception as e:
            raise 
        finally:
            try:
                self.rm_driver(driver)
            except Exception:
                pass
            
        

        
        
class GayForFansPlayListIE(SeleniumInfoExtractor):
    IE_NAME = 'gayforfans:playlist'
    IE_DESC = 'gayforfans'
    _VALID_URL = r'https?://(www\.)?gayforfans\.com(?:(/(?P<type>(?:popular-videos|performer|categories))(?:/?$|(/(?P<name>[^\/$\?]+))))(?:/?$|/?\?(?P<search>[^$]+)$)|/?\?(?P<search2>[^$]+)$)'
    
     

    def _get_filesize(self, url):
        
        count = 0
        try:
            
            _res = None
            while (count<3):
                
                try:
                    
                    res = httpx.head(url)
                    if res.status_code > 400:
                        time.sleep(1)
                        count += 1
                    else: 
                        _res = int_or_none(res.headers.get('content-length'))
                       
                        break
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass

        
        return _res


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
        
        except Exception as e:
            self.to_screen(str(e))
            raise

        finally:
            try:
                self.rm_driver(driver)
            except Exception:
                pass
            
        
        
        
               