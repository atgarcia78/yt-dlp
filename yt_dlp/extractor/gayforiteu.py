# coding: utf-8
from __future__ import unicode_literals

import html
import re
import sys
import traceback
from lzma import PRESET_DEFAULT
from urllib.parse import unquote



from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_5, By, ec

class getvideourl():
    def __call__(self, driver):
        el_video = driver.find_elements(By.TAG_NAME, 'video')
        if not el_video: return False
        if (video_url:=el_video[0].get_attribute('src')):
            return video_url
        else: return False
        

class GayForITEUIE(SeleniumInfoExtractor):
    
    _VALID_URL = r'https?://(?:www\.)gayforit\.eu/(?:playvideo.php\?vkey\=[^&]+&vid\=(?P<vid>[\w-]+)|video/(?P<id>[\w-]+)|playvideo.php\?vkey\=.+)'

    
    @dec_on_exception
    @limiter_5.ratelimit("gayforiteu1", delay=True)
    def _send_request(self, url, driver):
        
        #lets use the native method of InfoExtractor to download the webpage content. HTTPX doesnt work with this site
        #webpage = self._download_webpage(url, None, note=False)
        driver.get(url)
      
            
    @dec_on_exception
    @limiter_5.ratelimit("gayforiteu2", delay=True)   
    def get_info_for_format(self, *args, **kwargs):
        return super().get_info_for_format(*args, **kwargs)
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
        
        self.report_extraction(url)
        driver = self.get_driver(noheadless=True)
        try:
            videoid = try_get(re.search(self._VALID_URL, url), lambda x: x.groups()[0] or x.groups()[1])
            self._send_request(url, driver)
            video_url = self.wait_until(driver, 30, getvideourl())
            title = try_get(re.findall(r'GayForIt\.eu - Free Gay Porn Videos - (.+)', driver.title), lambda x: x[0]) 
            
            webpage = html.unescape(driver.page_source)
            if not webpage or 'this video has been removed' in webpage.lower() or 'this video does not exist' in webpage.lower() : raise ExtractorError("Error 404: no video page info")


            if not video_url:
                raise ExtractorError("no video url")
            else: video_url = unquote(video_url)
            
            if not videoid:
                videoid = try_get(re.findall(r'/(\d+)_', video_url), lambda x: x[0]) or 'not_id'
            if not title:
                self._send_request(f"https://www.gayforit.eu/video/{videoid}", driver)
                webpage = html.unescape(driver.page_source)
                if not webpage or 'this video has been removed' in webpage.lower() or 'this video does not exist' in webpage.lower() : raise ExtractorError("Error 404: no video page info")
                title = try_get(re.findall(r'<title>GayForIt\.eu - Free Gay Porn Videos - (.+)', driver.title), lambda x: x[0]) 

            self.to_screen(f"[video_url] {video_url}")
            
            _headers = {"Referer" : "https://www.gayforit.eu/"}
            
            _info_video = self.get_info_for_format(video_url, headers=_headers, verify=False)
            
            if not _info_video: raise ExtractorError("no video info")

            format_video = {
                'format_id' : "http-mp4",
                'url' : _info_video['url'],
                'filesize' : _info_video['filesize'],
                'http_headers': _headers,
                'ext' : 'mp4'
            }

            entry = {
                'id': videoid,                
                'formats': [format_video],
                'ext': 'mp4'
            }
            
            if title: entry.update({'title': sanitize_filename(title.strip(), restricted=True)})
            
            return entry
        
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}') 
        finally:
            self.rm_driver(driver)
