import sys
import traceback



from ..utils import ExtractorError, sanitize_filename
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_1, By, ec


class get_videourl():
    def __call__(self, driver):
        elcont = driver.find_element(By.CSS_SELECTOR, "html")
        elcont.click()
        elcont2 = driver.find_element(By.CSS_SELECTOR, "div.loading-container.faplbu")
        elcont2.click()
        elvid = driver.find_element(By.TAG_NAME, "video")
        videourl = elvid.get_attribute('src')
        if not videourl: return False
        else: return videourl
        

class GayMovieSupportIE(SeleniumInfoExtractor):
    IE_NAME = 'gaymoviesupport'
    _VALID_URL = r'https?://gaymoviesupport\.[^/]+/v/(?P<id>.*)'

    def _get_video_info(self, url):        
        self.logger_debug(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
        

    def _send_request(self, driver, url):
        self.logger_debug(f"[send_request] {url}")   
        driver.get(url)
    
    
    @dec_on_exception
    @limiter_1.ratelimit("gaymoviesupport", delay=True)
    def request_to_host(self, _type, *args, **kwargs):
    
        if _type == "video_info":
            return self._get_video_info(*args)
        elif _type == "url_request":
            self._send_request(*args)
        elif _type == "post":
            res = self._CLIENT.post(*args, **kwargs)
            res.raise_for_status()
            return(res.json())    
    
    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        
        self.report_extraction(url)
        
        #driver = self.get_driver()
 
        try:
            
            videoid = self._match_id(url)
            _headers = {
                'X-Requested-With': 'XMLHttpRequest', 
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 
                'Referer': url,
                'Origin': 'https://gaymoviesupport.cf'
            }
            _data =  {"r": "", "d": "gaymoviesupport.cf"}
                
            videojson = self.request_to_host("post", f"https://gaymoviesupport.cf/api/source/{videoid}", data=_data, headers=_headers)

            #video_url = self.wait_until(driver, 30, get_videourl())

            if videojson.get('data'):
                self.to_screen(videojson['data'])
                #_info = self.request_to_host("video_info", video_url)
                _formats = []
                for _format in videojson['data']:
                    _videourl = _format.get('file')
                    if not _videourl: continue
                    _info = self.request_to_host("video_info", _videourl)
                    if not _info: continue
                    _desc = _format.get('label', 'mp4')
                    _format_video = {
                            'format_id' : f"http-{_desc}",
                            'url' : _info.get('url'),
                            'filesize' : _info.get('filesize'),                            
                            'ext': 'mp4'
                    }
                    
                    if _desc != 'mp4':
                        _format_video.update(
                            {
                                'resolution': _desc,
                                'height' : int(_desc[:-1])                            
                            }
                        )
                    
                    _formats.append(_format_video)
                                    
                _entry_video = {
                    'id' : videoid,                    
                    'formats' : _formats,
                    'ext': "mp4"
                }
                
                return _entry_video
            else: raise ExtractorError("couldnt get video info")
            
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        # finally:
        #     try:
        #         self.rm_driver(driver)
        #     except Exception:
        #         pass
