from __future__ import unicode_literals


import re

from ..utils import (
    ExtractorError,   
    sanitize_filename,


)


import html



from concurrent.futures import ThreadPoolExecutor

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_15
)


from backoff import constant, on_exception

class get_videourl():
    
    def __call__(self, driver):
        
        el_player = driver.find_elements(by=By.ID, value="kt_player")
        if not el_player: return False
        else:
            try:
                el_player[0].click()
                el_fp = driver.find_elements(by=By.CSS_SELECTOR, value="video.fp-engine")
                if not el_fp: return False
                else:            
                    video_url = el_fp[0].get_attribute('src')
                    if video_url: return video_url
                    else: return False
            except Exception:
                return False
                    

class YourPornGodIE(SeleniumInfoExtractor):
    
    IE_NAME = 'yourporngod'
    _VALID_URL = r'https?://(?:www\.)?yourporngod\.com/videos/(?P<id>\d+)/(?P<title>[^\/\$]+)'
    
    def _get_video_info(self, url):        
        self.logger_info(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
        

    def _send_request(self, driver, url):
        self.logger_info(f"[send_request] {url}")   
        driver.get(url)
    
   
    @on_exception(constant, Exception, max_tries=5, interval=15)    
    @limiter_15.ratelimit("yourporngod", delay=True)
    def request_to_host(self, _type, *args):
    
        if _type == "video_info":
            return self._get_video_info(*args)
        elif _type == "url_request":
            self._send_request(*args)
        
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
        
              
        self.report_extraction(url)
        
        driver = self.get_driver()
        try:
                    
            #self._send_request(driver, url)
            self.request_to_host("url_request", driver, url)
            
            video_url = self.wait_until(driver, 30, get_videourl())                
                
            if not video_url: raise ExtractorError("No video url")
            
            #info_video = self._get_video_info(video_url)
            info_video = self.request_to_host("video_info", video_url)
            
            if not info_video: raise Exception(f"error video info")
            
            formats = [{'format_id': 'http', 'url': info_video.get('url'), 'filesize': info_video.get('filesize'), 'ext': 'mp4'}]
            if not formats: raise ExtractorError("No formats found")
            else:
                self._sort_formats(formats)
                video_id = self._match_id(url)
                title = driver.title        
                entry = {
                        'id' : video_id,
                        'title' : sanitize_filename(title, restricted=True),
                        'formats' : formats,
                        'ext': 'mp4'
                    }            
                return entry
        
        
        except Exception as e:
            self.to_screen(e)
            raise
        finally:
            try:
                self.rm_driver(driver)
            except Exception:
                pass
            
        
class YourPornGodPlayListIE(SeleniumInfoExtractor):
    
    IE_NAME = 'yourporngod:playlist'
    _VALID_URL = r'https?://(?:www\.)?yourporngod\.com/(?:((?P<type1>playlists)/(?P<id>\d+)/(?P<title>[^\/\$]+))|((?P<type3>models)/(?P<model>[^\/\$]+))|((?P<type2>categories)/(?P<categorie>[^\/\$]+)))'
    _SEARCH_URL = {"playlists" : "?mode=async&function=get_block&block_id=playlist_view_playlist_view&sort_by=added2fav_date&from=",
                   "models" : "?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed&from=",
                   "categories": "?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed&from="}
    _REGEX_ENTRIES = {"playlists": r'data-playlist-item\=[\"\']([^\'\"]+)[\'\"]',
                      "models": r'item  [\"\']><a href=["\']([^\'\"]+)[\'\"]',
                      "categories": r'item  [\"\']><a href=["\']([^\'\"]+)[\'\"]'}
    
    
    @on_exception(constant, Exception, max_tries=5, interval=15)    
    @limiter_15.ratelimit("yourporngod", delay=True)
    def _send_request(self, url):
        self.logger_info(f"[send_request] {url}")   
        res = YourPornGodPlayListIE._CLIENT.get(url)
        res.raise_for_status()
        return res

    def _get_entries(self, url, _type):
        res = self._send_request(url)
        if res:
            webpage = re.sub('[\t\n]', '', html.unescape(res.text))
            entries = re.findall(self._REGEX_ENTRIES[_type],webpage)
            return entries
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
        
        self.report_extraction(url)
        #playlist_id = self._match_id(url)
        _type1, _type2, _type3, _id, _title, _model, _categorie = re.search(self._VALID_URL, url).group('type1','type2','type3','id','title','model','categorie')
        
        _type = _type1 or _type2 or _type3
                      
        self.report_extraction(url)
        
        res = self._send_request(url)        
        if not res: raise ExtractorError("couldnt download webpage")
        webpage = re.sub('[\t\n]', '', html.unescape(res.text))
        
        mobj = re.findall(r"<title>([^<]+)<", webpage)
        title = mobj[0] if mobj else _title or _model or _categorie
        
        playlist_id = _id or _model or _categorie

        mobj = re.findall(r'\:(\d+)[\"\']>Last', webpage)        
        last_page = int(mobj[0]) if mobj else 1
        
        base_url = url + self._SEARCH_URL[_type]        
        
        with ThreadPoolExecutor(max_workers=16) as ex:        
            
            futures = [ex.submit(self._get_entries, base_url + str(i), _type) for i in range(1,last_page+1)]
                
        res = []
        
        for fut in futures:
            try:
                res += fut.result()
            except Exception as e:
                pass
            
        entries = [self.url_result(_url, ie="YourPornGod") for _url in res]
        
        return {
            '_type': 'playlist',
            'id': playlist_id,
            'title': sanitize_filename(title,restricted=True),
            'entries': entries,
            
        }
