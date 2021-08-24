from __future__ import unicode_literals



from .common import InfoExtractor, ExtractorError
from ..utils import (
    
    sanitize_filename,
    int_or_none

)
import httpx


from selenium.webdriver import Firefox, FirefoxProfile
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import time

import traceback
import sys


class UserLoadIE(InfoExtractor):

    IE_NAME = 'userload'
    _VALID_URL = r'https?://(?:www\.)?userload\.co/(?:embed|e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    
    _FF_PROF = ['/Users/antoniotorres/Library/Application Support/Firefox/Profiles/cs2cluq5.selenium5_sin_proxy',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/7mt9y40a.selenium4',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/yhlzl1xp.selenium3',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/wajv55x1.selenium2',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/xxy6gx94.selenium',
                '/Users/antoniotorres/Library/Application Support/Firefox/Profiles/0khfuzdw.selenium0']

 


    def wait_until(self, _driver, time, method):
        try:
            el = WebDriverWait(_driver, time).until(method)
        except Exception as e:
            el = None
            
        return el  
    
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
        prof = self._FF_PROF.pop()
        self._FF_PROF.insert(0, prof)
            
        opts = Options()
        opts.headless = True
            
        try:                            
                            
            driver = Firefox(firefox_binary="/Applications/Firefox Nightly.app/Contents/MacOS/firefox", options=opts, firefox_profile=FirefoxProfile(prof))
 
            self.to_screen(f"ffprof[{prof}]")
            
            driver.set_window_size(1920,575)
            
            _url = url.replace('/e/', '/f/').replace('/embed/', '/f/')
            
            driver.get(_url)
            el = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID,"videooverlay")))
            if el: el.click()
            res = driver.find_elements_by_id("olvideo_html5_api")
            if not res: raise ExtractorError("no info")
            video_url = res[0].get_attribute("src")
            if not video_url: raise ExtractorError("no video url") 
            
            title = driver.title.replace(" | userload","").replace(".mp4","").strip()
            videoid = self._match_id(url)
            
            _entry_video = None
            
            _format = {
                    'format_id': 'http-mp4',
                    'url': video_url,
                    'filesize': self._get_filesize(video_url),
                    'ext': 'mp4'
            }
            
            _entry_video = {
                'id' : videoid,
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
            }   
            
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))
        finally:
            driver.quit()
        
        if not _entry_video: raise ExtractorError("no video info")
        else:
            return _entry_video    



       


