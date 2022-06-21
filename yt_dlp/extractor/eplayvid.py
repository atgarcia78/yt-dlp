from __future__ import unicode_literals

import sys
import traceback



from ..utils import ExtractorError, sanitize_filename
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_5, By, ec


class video_or_error_eplayvid:
    def __init__(self, logger):
        self.logger = logger

    def __call__(self, driver):
        try:
                        
            el_vid = driver.find_elements(By.ID, "player_html5_api")
            if el_vid:
                el_src = el_vid[0].find_elements(By.TAG_NAME, "source")
                if el_src:
                    if _src := el_src[0].get_attribute("src"):
                        return _src
            return False
        except Exception as e:
            return False


class EPlayVidIE(SeleniumInfoExtractor):

    IE_NAME = 'eplayvid'
    _VALID_URL = r'https?://(?:www\.)?eplayvid\.net/watch/[^\/$]+'

    @dec_on_exception
    @limiter_5.ratelimit("userload2", delay=True)
    def _get_video_info(self, url):        
        self.write_debug(f"[get_video_info] {url}")
        return self.get_info_for_format(url, headers={'Referer': 'https://eplayvid.net/'})       
        
        
    @dec_on_exception
    @limiter_5.ratelimit("userload", delay=True)
    def _send_request(self, url, driver):        
        
        self.logger_debug(f"[send_request] {url}") 
        driver.get(url)
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):

        self.report_extraction(url)
        driver = self.get_driver(usequeue=True)
        
        try:

            self._send_request(url, driver)
            video_url = self.wait_until(driver, 30, video_or_error_eplayvid(self.to_screen))
            if not video_url or video_url == 'error': raise ExtractorError('404 video not found')
            _info_video = self._get_video_info(video_url)
            if not _info_video: raise ExtractorError("error info video")
            video_id = video_url.split("___")[-1].replace(".mp4", "")
            title = video_url.split('/')[-1].replace(".mp4", "").replace(video_id, "").strip()
            
            _format = {
                'format_id': 'http-mp4',
                'url': _info_video['url'],
                'filesize': _info_video['filesize'],
                'ext': 'mp4'
            }

            return({
                'id' : video_id,
                'title': sanitize_filename(title, restricted=True),             
                'formats' : [_format],
                'http_headers': {'Referer': 'https://eplayvid.net/'},
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
        