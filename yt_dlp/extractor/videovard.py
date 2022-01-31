from __future__ import unicode_literals

from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_0_1
)

from ..utils import (
    ExtractorError)


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


from browsermobproxy import Server


import sys
import traceback
import threading


from backoff import on_exception, constant


class VideovardIE(SeleniumInfoExtractor):

    IE_NAME = "videovard"
    _SITE_URL = "https://videovard.sx"
    _VALID_URL = r'https?://videovard\.sx/e/(?P<id>[^&]+)'
    
    _LOCK = threading.Lock()     

 
    @on_exception(constant, Exception, max_tries=5, interval=0.1)
    @limiter_0_1.ratelimit("onlyfans2", delay=True)
    def send_request(self, driver, url):
        
        if driver:
            driver.execute_script("window.stop();")
            driver.get(url)
        else:
            res = self._CLIENT.get(url)
            res.raise_for_status()
            return res

    def scan_for_request(self, _har, _ref, _link):
                          
        #self.write_debug(_har)
        
        for entry in _har['log']['entries']:
                            
            if entry['pageref'] == _ref:
                
                if _link in (_url:=entry['request']['url']):
                    
                    self.write_debug(_url)
                    self.write_debug(entry['request']['headers'])                   
                    
                    return _url            

  

    def _real_initialize(self):

        super()._real_initialize()        

                
    def _real_extract(self, url):

        try:            
            
            with VideovardIE._LOCK:
                _server_port = 18080                 
                _server = Server(path="/Users/antoniotorres/Projects/async_downloader/browsermob-proxy-2.1.4/bin/browsermob-proxy", options={'port': _server_port})
                _server.start({'log_path': '/dev', 'log_file': 'null'})
                _host = 'localhost'
                _port = _server_port + 1                
                _harproxy = _server.create_proxy({'port' : _port})

            driver  = self.get_driver(host=_host, port=_port)
                        
            self.report_extraction(url)                  
            
            videoid = self._match_id(url)
            
            _harproxy.new_har(options={'captureHeaders': True, 'captureContent': True}, ref=f"har_{videoid}", title=f"har_{videoid}")
            self.send_request(driver, url) 
            vpl = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID, "videoplayer")))
            vpl.click()
            self.wait_until(driver, 1)
            vpl.click()
            har = _harproxy.har            
            m3u8_url = self.scan_for_request(har, f"har_{videoid}", f"master.m3u8")
            if m3u8_url:
                res = self.send_request(None, m3u8_url)
                if not res: raise ExtractorError(f"[{url}] no m3u8 doc")
                m3u8_doc = (res.content).decode('utf-8', 'replace')
                self.write_debug(f"[{url}] \n{m3u8_doc}")        
                formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                    m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")

                if not formats_m3u8:
                    raise ExtractorError(f"[{url}] Can't find any M3U8 format")

                self._sort_formats(formats_m3u8)
                
                return ({ 
                        "id": videoid,                    
                        "formats": formats_m3u8,
                        "ext": "mp4"})
        
        except ExtractorError as e:
            raise
        except Exception as e:                
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(repr(e))
        finally:
            _harproxy.close()
            _server.stop()
            self.rm_driver(driver)