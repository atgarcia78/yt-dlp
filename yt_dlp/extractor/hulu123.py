from __future__ import unicode_literals

from backoff import on_exception

from ..utils import (
    ExtractorError,
    sanitize_filename,
    try_get)


from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_0_1,
    limiter_15,
    limiter_5
)



from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By



import re
import traceback
import sys

from backoff import constant, on_exception

from .streamtape import video_or_error_streamtape
from .userload import video_or_error_userload
from .evoload import video_or_error_evoload    

class Hulu123IE(SeleniumInfoExtractor):
    IE_NAME = "hulu123"
    _VALID_URL = r'https?://(www\.)?123hulu\.com/watch/(?P<id>[^-]+)-[^\./]+(?:\.html|/(?P<format>(?:streamtape|userload|evoload)))'
 
    @on_exception(constant, Exception, max_tries=5, interval=5)
    @limiter_5.ratelimit("hulu123", delay=True)
    def _send_request(self, url, driver):        
        
        self.logger_info(f"[send_request] {url}") 
        driver.get(url)
       
    
    def _real_initialize(self):
        super()._real_initialize()
        
               
    def _real_extract(self, url):        
        
                
        self.report_extraction(url)        
         
        driver = self.get_driver(usequeue=True) 
        #driver = self.get_driver(noheadless=True)  
        
        try:

            self._send_request(url, driver)
            el_title = try_get(self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "h3"))), lambda x: x.text) or ""
            video_id = try_get(re.findall(r'og:url" content="([^"]+)"', driver.page_source), lambda x: self._match_id(x[0]))
            
            _format = try_get(re.search(self._VALID_URL, url), lambda x: x.group('format'))
            if not _format:
                el_servers = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CLASS_NAME, "server_play")))
                servers_list = [_serv for _el in el_servers if (_serv:=try_get(_el.find_elements(By.TAG_NAME, "a"), lambda x: x[0].get_attribute("href")))]
            else:
                servers_list = [url]
            
            self.to_screen(f'servers list: {servers_list}')
            userload_url = evoload_url = streamtape_url = ""
            for server in servers_list:                
                if ('userload' in server and (not userload_url or userload_url == "error")) or ('evoload' in server and (not evoload_url or evoload_url == "error")) or ('streamtape' in server and (not streamtape_url or streamtape_url == "error")):
                    self.to_screen(server)
                    self._send_request(server, driver)
                    el_ifr = self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "iframe")))
                    if el_ifr:
                        _url = el_ifr.get_attribute('src') or ""                    
                        driver.switch_to.frame(el_ifr)
                        if 'userload' in server: 
                            if (_valul:=self.wait_until(driver, 30, video_or_error_userload(self.to_screen))) and _valul != "error": 
                                userload_url = _valul
                                self.to_screen(f'userload OK:[{_url}][{_valul}')
                            else:
                                userload_url = "error"
                                self.to_screen(f'userload NOK:{_url}')
                        elif 'evoload' in server:
                            #if (_valel:=self._valid_evoload(_url, driver)) and _valel == True: 
                            if (_valel:=self.wait_until(driver, 30, video_or_error_evoload(self.to_screen), poll_freq=5)) and _valel != "error":
                                evoload_url = _valel
                                self.to_screen(f'evoload OK:[{_url}][{_valel}]')
                            else:
                                evoload_url = "error"
                                self.to_screen(f'evoload NOK:{_url}')
                        elif 'streamtape' in server:
                            if (_valst:=self.wait_until(driver, 30, video_or_error_streamtape(self.to_screen))) and _valst != "error":
                                streamtape_url = _valst
                                self.to_screen(f'streamtape OK:[{_url}][{_valst}]')
                            else:
                                streamtape_url = "error"
                                self.to_screen(f'streamtape NOK:{_url}')
                            
                    else:
                        self.to_screen(f'[{server}] No iframe')
                        
                        
            self.to_screen(f'userload:{userload_url}\nevoload:{evoload_url}\nstreamtape:{streamtape_url}')
            if userload_url == "error" and evoload_url == "error" and streamtape_url == "error": raise ExtractorError("404 UserLoad & EverLoad $ StreamTape servers available but no video found in any")
            if userload_url == "" and evoload_url == "" and streamtape_url == "": raise ExtractorError("no UserLoad & EverLoad & Streamtape servers available")
            
            video_urls = [(_url, _id) for (_url, _id) in [(userload_url, "userload"), (evoload_url, "evoload"), (streamtape_url, "streamtape")] if _url and _url != "error"]
            
            if not video_urls: raise ExtractorError("404 UserLoad & EverLoad $ StreamTape servers available but no video found in any")
                
            _formats = []
            for (_url, _id) in video_urls:
                try:
                    _info_video = self.get_info_for_format(_url)
                    if not _info_video: raise ExtractorError(f"no info video")
                    _formats.append({
                        'format_id': f'http-mp4-{_id}',
                        'url': _info_video.get('url'),
                        'filesize': _info_video.get('filesize'),
                        'ext': 'mp4'
                    })
                except Exception as e:
                    self.to_screen(f"[get_formats][{_url}] {repr(e)}")
            if _formats:
                self._sort_formats(_formats)
                return({'id': video_id, 'title': sanitize_filename(el_title, restricted=True), 'formats': _formats, 'ext': 'mp4'})

        except ExtractorError as e:                 
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e))
        finally:
            self.put_in_queue(driver)
 
        