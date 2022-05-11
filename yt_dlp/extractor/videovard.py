from __future__ import unicode_literals

import sys
import threading
import traceback

from backoff import constant, on_exception
from browsermobproxy import Server
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import SeleniumInfoExtractor, limiter_0_1


class VideovardIE(SeleniumInfoExtractor):

    IE_NAME = "videovard"
    _SITE_URL = "https://videovard.sx"
    _VALID_URL = r'https?://videovard\.\w\w/[e,v]/(?P<id>[^&]+)'
    
    _LOCK = threading.Lock()
    _NUM = 0     

 
    @on_exception(constant, Exception, max_tries=5, interval=0.1)
    @limiter_0_1.ratelimit("videovard", delay=True)
    def send_multi_request(self, driver, url):
        
        if driver:
            driver.execute_script("window.stop();")
            driver.get(url)
        else:
            res = self._CLIENT.get(url)
            res.raise_for_status()
            return res

    def scan_for_request(self, _har, _ref, _link):
                          
        for entry in _har['log']['entries']:
                            
            if entry['pageref'] == _ref:
                
                if _link in (_url:=entry['request']['url']):
                    
                    #self.write_debug(_url)
                    #self.write_debug(entry['request']['headers'])                   
                    
                    return _url            

  

    def _real_initialize(self):

        super()._real_initialize()        

                
    def _real_extract(self, url):

        try:
            
            with VideovardIE._LOCK:
        
                self.report_extraction(url) 
                videoid = self._match_id(url)

                
                while True:
                    _server_port = 18080 + VideovardIE._NUM*100                 
                    _server = Server(path="/Users/antoniotorres/Projects/async_downloader/browsermob-proxy-2.1.4/bin/browsermob-proxy", options={'port': _server_port})
                    try:
                        if _server._is_listening():
                            VideovardIE._NUM += 1
                            if VideovardIE._NUM == 25: raise Exception("mobproxy max tries")
                        else:
                            _server.start({"log_path": "/dev", "log_file": "null"})
                            self.to_screen(f"[{url}] browsermob-proxy start OK on port {_server_port}")
                            VideovardIE._NUM += 1
                            break
                    except Exception as e:
                        lines = traceback.format_exception(*sys.exc_info())
                        self.to_screen(f'[{url}] {repr(e)} \n{"!!".join(lines)}')
                        if _server.process: _server.stop()                   
                        raise ExtractorError(f"[{url}] browsermob-proxy start error - {repr(e)}")

                _host = 'localhost'
                _port = _server_port + 1                
                _harproxy = _server.create_proxy({'port' : _port})
                driver  = self.get_driver(host=_host, port=_port)
                            
                try:
                    _harproxy.new_har(options={'captureHeaders': True, 'captureContent': True}, ref=f"har_{videoid}", title=f"har_{videoid}")
                    self.send_multi_request(driver, url.replace('/e/', '/v/'))
                    title = try_get(self.wait_until(driver, 60, ec.presence_of_element_located((By.TAG_NAME, "h1"))), lambda x: x.text)
                    
                    vpl = self.wait_until(driver, 60, ec.presence_of_element_located((By.ID, "vplayer")))
                    for i in range(2):
                        try:
                            vpl.click()
                            self.wait_until(driver, 1)
                            vpl.click()
                            break
                        except Exception as e:
                            el_kal = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "div.kalamana")))
                            if el_kal: el_kal.click()
                            self.wait_until(driver, 1)
                            el_rul = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "div.rulezco")))
                            if el_rul: el_rul.click()
                            self.wait_until(driver, 1)
                            continue
                        
                    har = _harproxy.har            
                    m3u8_url = self.scan_for_request(har, f"har_{videoid}", f"master.m3u8")
                    if m3u8_url:
                        self.write_debug(f"[{url}] m3u8 url - {m3u8_url}")
                        res = self.send_multi_request(None, m3u8_url)
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
                                "title": sanitize_filename(title, restricted=True),                    
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
                
        except Exception as e:                
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
            raise ExtractorError(repr(e))
               
                    