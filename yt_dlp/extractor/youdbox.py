from __future__ import unicode_literals

import threading

from .webdriver import SeleniumInfoExtractor

from ..utils import (
    ExtractorError,
    sanitize_filename,
    int_or_none,
    std_headers

)
import httpx

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


import traceback
import sys

class YoudBoxIE(SeleniumInfoExtractor):

    IE_NAME = 'youdbox'
    _VALID_URL = r'https?://(?:www\.)?youdbox\.net/(embed-)?(?P<id>[^\.]+).html'
    

 
    _LOCK = threading.Lock()



    
    def _get_info(self, url):
        
        count = 0
        try:
            
            _res = None
            while (count<3):
                
                try:
                    
                    #res = self._send_request(client, url, 'HEAD')
                    res = httpx.head(url, headers=std_headers)
                    if res.status_code >= 400:
                        
                        count += 1
                    else: 
                        _filesize = int_or_none(res.headers.get('content-length'))
                        _url = str(res.url)
                        if _filesize and _url:
                            break
                        else:
                            count += 1
                        
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass

        if count < 3: return ({'url': _url, 'filesize': _filesize}) 
        else: return ({'error': 'max retries'})  
    
    def _real_extract(self, url):
        
   
        self.report_extraction(url)
       
        driver = self.get_driver() 
        
        

        try:
            
            with YoudBoxIE._LOCK:

                driver.get(url.replace("embed-", ""))
            
            el_video = self.wait_until(driver, 30, ec.presence_of_element_located((By.ID, "vjsplayer_html5_api"))) 

            if not el_video: raise ExtractorError("no info")           
            video_url = el_video.get_attribute('src')
              
            
            title = driver.title.replace("mp4", "")
            videoid = self._match_id(url)
            
            info_video = self._get_info(video_url)
            
            _format = {
                    'format_id': 'http-mp4',
                    'url': info_video['url'],
                    'filesize': info_video['filesize'],
                    'ext': 'mp4'
            }
            
            _entry_video = {
                'id' : videoid,
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
            } 
            
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
                self.rm_driver(driver)
            except Exception:
                pass