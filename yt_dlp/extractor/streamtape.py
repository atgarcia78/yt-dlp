from __future__ import unicode_literals

import html
import re
import sys
import time
import traceback
from urllib.parse import urlparse



from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_5, By, ec, Keys


class video_or_error_streamtape():
    def __init__(self, logger):
        self.logger = logger
    def __call__(self, driver):
        try:

            elover = driver.find_elements(By.CLASS_NAME, "plyr-overlay")
            if elover:
                for _ in range(5):
                    try:
                        elover[0].click()
                        time.sleep(1)
                    except Exception as e:
                        break
            el_vid = driver.find_elements(By.ID, "mainvideo")
            if el_vid:
                if _src:=el_vid[0].get_attribute('src'):
                    return _src
                else:
                    return False
            else: 
                elbutton = driver.find_elements(By.CSS_SELECTOR, "button.plyr__controls__item")
                if elbutton:
                    for _ in range(5):
                        try:
                            elbutton[0].click()
                            time.sleep(1)
                        except Exception as e:
                            break
                elh1 = driver.find_elements(By.TAG_NAME, "h1")
                if elh1:
                    errormsg = elh1[0].get_attribute('innerText').strip("!")
                    self.logger(f'[streamtape_url][{driver.current_url[26:]}] error - {errormsg}')
                    return "error"
                    
                return False
        except Exception as e:
            return False


class StreamtapeIE(SeleniumInfoExtractor):

    IE_NAME = 'streamtape'
    _VALID_URL = r'https?://(www.)?streamtape\.(?:com|net)/(?:d|e|v)/(?P<id>[a-zA-Z0-9_-]+)/?((?P<title>.+)\.mp4)?'
    
    
    @staticmethod
    def _extract_urls(webpage):
        #return try_get(re.search(r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?streamtape\.(?:com|net)/(?:e|v|d)/.+?)\1',webpage), lambda x: x.group('url'))
        return [mobj.group('url') for mobj in re.finditer(r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?streamtape\.(?:com|net)/(?:e|v|d)/.+?)\1',webpage)]

    @dec_on_exception
    @limiter_5.ratelimit("streamtape", delay=True)
    def _get_video_info(self, url):        
        
        self.logger_info(f"[get_video_info] {url}")
        return self.get_info_for_format(url)     
    
    @dec_on_exception
    @limiter_5.ratelimit("streamtape", delay=True)
    def _send_request(self, url, driver):        
        
        self.logger_info(f"[send_request] {url}") 
        driver.get(url)
        
    def _real_initialize(self):
        super()._real_initialize()
        
    
    def _real_extract(self, url):

        
        self.report_extraction(url)
        
        driver = self.get_driver(usequeue=True)
        
        
        try:        
            #we need to disable the adblock addon to bypass cloudflare bot detection
            driver.get("about:addons")
            elbutton = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CSS_SELECTOR, "input.toggle-button.extension-enable-button")))
            elbutton[1].click()
            
            #open a new tab to load the url webpage
            eltab =  driver.find_element(By.CSS_SELECTOR, "a")
            eltab.send_keys(Keys.COMMAND + Keys.RETURN)
            driver.switch_to.window(driver.window_handles[1])
            self.wait_until(driver, timeout=5)
            self._send_request(url.replace(".com", "adblock.art"), driver)           
            self.wait_until(driver, 30, ec.title_contains("Streamtape"))
            #enable again the addon adblock
            driver.switch_to.window(driver.window_handles[0])
            elbutton = driver.find_elements(By.CSS_SELECTOR, "input.toggle-button.extension-enable-button")            
            elbutton[1].click()
            driver.close()            
            driver.switch_to.window(driver.window_handles[0]) 
                       
            webpage = html.unescape(driver.page_source)
            video_url = try_get(re.findall(r"(//streamtapeadblock\.art/get_video\?.+)<\/div>", webpage), lambda x: f'https:{x[0]}&stream=1')
            self.to_screen(f'[{url}] {video_url}')
            #video_url = self.wait_until(driver, 30, video_or_error_streamtape(self.to_screen))
            if not video_url or video_url == 'error': raise ExtractorError('404 video not found')
            # _info_video = self._get_video_info(video_url)
            # if not _info_video: raise ExtractorError("error info video")
             
            title = try_get(re.findall(r'og:title" content="([^"]+)"', webpage), 
                            lambda x: re.sub(r'\.mp4| at Streamtape\.com|amp;', '', x[0], re.IGNORECASE))
                                        
             
            _format = {
                'format_id': 'http-mp4',
                #'url': _info_video.get('url'),
                'url': video_url,
                #'filesize': _info_video.get('filesize'),
                'ext': 'mp4',
                'http_headers': {'Referer': (urlp:=urlparse(url)).scheme + "//" + urlp.netloc + "/"}
            }
            
            if self._downloader.params.get('external_downloader'):
                _videoinfo = self._get_video_info(video_url)
                if _videoinfo:
                    _format.update({'url': _videoinfo['url'],'filesize': _videoinfo['filesize'] })
                
            return({
                'id' : self._match_id(url),
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [_format],
                'ext': 'mp4'
            })

            
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")            
            raise ExtractorError(repr(e)) 
        finally:
            self.put_in_queue(driver)
