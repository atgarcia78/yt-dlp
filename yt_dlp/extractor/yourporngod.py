from __future__ import unicode_literals

import html
import re
import time
from concurrent.futures import ThreadPoolExecutor



from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_15, By, ec


class get_title_videourl:
    def __init__(self, name, logger):
        self.logger = logger
        self.init = True
        self.title = None
        self.name = name

    def __call__(self, driver):
        try:
            if self.init:
                elembed = driver.find_elements(By.CLASS_NAME, "embed-wrap")
                self.title = driver.title
                if elembed:
                    elifr = elembed[0].find_element(By.TAG_NAME, "iframe")
                    driver.switch_to.frame(elifr)
                    self.init = False
                    elifr2_url = try_get(driver.find_elements(By.TAG_NAME, "iframe"), lambda x: x[0].get_attribute('src')) or ""
                    if '/deleted' in elifr2_url: return "error404"


            elplayer = driver.find_element(By.ID, "kt_player")
            try:
                elplayer.click()
                time.sleep(1)
                video_url = try_get(driver.find_element(By.CSS_SELECTOR, "video.fp-engine"), lambda x: x.get_attribute('src'))
                if video_url:
                    return ({'title': self.title, 'url': video_url})
                else: return False
            except Exception as e:
                self.logger(repr(e))
            finally:
                if self.name == 'yourporngod':
                    time.sleep(8)
                    elplayer.click()
                else: 
                    time.sleep(5)
                    elplayer.click()

        except Exception as e:
            self.logger(repr(e))
            raise

class YourPornGodIE(SeleniumInfoExtractor):
    
    IE_NAME = 'yourporngod'
    _VALID_URL = r'https?://(?:www\.)?yourporngod\.com/videos/(?P<id>\d+)/(?P<title>[^\/\$]+)'
    _SITE_URL = 'https://yourporngod.com'
    
    @dec_on_exception
    @limiter_15.ratelimit("yourporngod", delay=True)   
    def _get_video_info(self, url):        
        self.logger_debug(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
        
    @dec_on_exception
    @limiter_15.ratelimit("yourporngod", delay=True)
    def _send_request(self, url, driver):
        self.logger_debug(f"[send_request] {url}")   
        driver.get(url)

    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):        
              
        self.report_extraction(url)
        
        driver = self.get_driver()
        try:
                    
            self._send_request(url, driver)
 
            title, video_url = try_get(self.wait_until(driver, 60, get_title_videourl(self.IE_NAME, self.to_screen)), lambda x: (x['title'], x['url']) if isinstance(x, dict) else ("error", x)) or ("","")                
            self.to_screen(f"{title} : {video_url}")    
            if not video_url: raise ExtractorError("No video url")
            if video_url == "error404": raise ExtractorError("not found 404")
            
            _format = {
                'format_id': 'http', 
                'url': video_url,
                'http_headers': {'Referer': self._SITE_URL}, 
                'ext': 'mp4'}
            
            if self._downloader.params.get('external_downloader'):
                _videoinfo = self._get_video_info(video_url)
                _format.update({'url': _videoinfo['url'],'filesize': _videoinfo['filesize'] })
            
            
            video_id = self._match_id(url)
            if not title: title = try_get(re.search(self._VALID_URL, url), lambda x: x.group('title').replace("-","_"))
                    
            entry = {
                'id' : video_id,
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
                }            
            return entry
        
        
        except Exception as e:
            self.to_screen(e)
            raise
        finally:
            self.rm_driver(driver)
                        
        
class YourPornGodPlayListIE(SeleniumInfoExtractor):
    
    IE_NAME = 'yourporngod:playlist'
    _VALID_URL = r'https?://(?:www\.)?yourporngod\.com/(?:((?P<type1>playlists)/(?P<id>\d+)/(?P<title>[^\/\$]+))|((?P<type3>models)/(?P<model>[^\/\$]+))|((?P<type2>categories)/(?P<categorie>[^\/\$]+)))'
    _SEARCH_URL = {"playlists" : "?mode=async&function=get_block&block_id=playlist_view_playlist_view&sort_by=added2fav_date&from=",
                   "models" : "?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed&from=",
                   "categories": "?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed&from="}
    _REGEX_ENTRIES = {"playlists": r'data-playlist-item\=[\"\']([^\'\"]+)[\'\"]',
                      "models": r'item  [\"\']><a href=["\']([^\'\"]+)[\'\"]',
                      "categories": r'item  [\"\']><a href=["\']([^\'\"]+)[\'\"]'}
    
    
    @dec_on_exception
    @limiter_15.ratelimit("yourporngod", delay=True)
    def _send_request(self, url):
        self.logger_debug(f"[send_request] {url}")   
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
        
class OnlyGayVideoIE(YourPornGodIE):
    IE_NAME = 'onlygayvideo'
    _VALID_URL = r'https?://(?:www\.)?onlygayvideo\.com/videos/(?P<id>\d+)/(?P<title>[^\/\$]+)'
    _SITE_URL = 'https://onlygayvideo.com'
