from __future__ import unicode_literals


from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_1
)

from ..utils import (
    ExtractorError,
    sanitize_filename,


)


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

from browsermobproxy import Server

import traceback
import sys

import threading

import re

from backoff import constant, on_exception

class get_videourl():
    
    def __init__(self, _type):
        self.id = "player-1" if _type == 'embed' else "videoplayer"
    def __call__(self, driver):
        el_player = driver.find_elements(by=By.ID, value=self.id)
        if not el_player: return False
        else:
            el_video = el_player[0].find_elements(by=By.TAG_NAME, value="video")
            if not el_video: return False
            video_url = el_video[0].get_attribute('src', '').replace('blob:','')
            if video_url: 
                return video_url
            else: return False

class TheGayIE(SeleniumInfoExtractor):

    IE_NAME = 'thegayx'
    _VALID_URL = r'https?://(?:www\.)?thegay\.com/(?P<type>(?:embed|videos))/(?P<id>[^\./]+)[\./]'
    _LOCK = threading.Lock()

    def _get_video_info(self, url):        
        self.logger_info(f"[get_video_info] {url}")
        return self.get_info_for_format(url)       
            

    def _send_request(self,url, driver):
        self.logger_info(f"[send_request] {url}")   
        driver.get(url)
    
    
    @on_exception(constant, Exception, max_tries=5, interval=1)    
    @limiter_1.ratelimit("thegay", delay=True)
    def request_to_host(self, _type, url, driver=None):
    
        if _type == "video_info":
            return self._get_video_info(url)
        elif _type == "url_request":
            self._send_request(url, driver)
        elif _type == "client_request":
            res = self._CLIENT.get(url, headers = {'Referer': 'https://thegay.com/', 'Origin':'https://thegay.com' })
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
        self.report_extraction(url)
               
        _type, videoid = re.search(self._VALID_URL, url).groups()

        try:
            
            with TheGayIE._LOCK:
        
               
                n = 0
                while True:
                    _server_port = 18080 + n*100                 
                    _server = Server(path="/Users/antoniotorres/Projects/async_downloader/browsermob-proxy-2.1.4/bin/browsermob-proxy", options={'port': _server_port})
                    try:
                        if _server._is_listening():
                            n += 1
                            if n == 25: raise Exception("mobproxy max tries")
                        else:
                            _server.start({"log_path": "/dev", "log_file": "null"})
                            self.to_screen(f"[{url}] browsermob-proxy start OK on port {_server_port}")
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
                    
                    self.request_to_host("url_request", url, driver)
                    self.wait_until(driver, 30, get_videourl(_type))
                    _title = driver.title.replace(" - TheGay.com", "").strip()
                    har = _harproxy.har            
                    m3u8_url = self.scan_for_request(har, f"har_{videoid}", f"video.m3u8")
                    if m3u8_url:
                        self.write_debug(f"[{url}] m3u8 url - {m3u8_url}")
                        headers =  {'Referer': 'https://thegay.com/', 'Origin':'https://thegay.com' }
                        formats_m3u8 = self._extract_m3u8_formats(
                            m3u8_url, None, m3u8_id="hls", ext="mp4", entry_protocol="m3u8", headers=headers, fatal=False)
                        
                        # res = self.request_to_host("client_request", m3u8_url)
                        # if not res: raise ExtractorError(f"[{url}] no m3u8 doc")
                        # m3u8_doc = (res.content).decode('utf-8', 'replace')
                        # self.write_debug(f"[{url}] \n{m3u8_doc}")        
                        # formats_m3u8, _ = self._parse_m3u8_formats_and_subtitles(
                        #     m3u8_doc, m3u8_url, ext="mp4", entry_protocol='m3u8_native', m3u8_id="hls")

                        if not formats_m3u8:
                            raise ExtractorError(f"[{url}] Can't find any M3U8 format")

                        self._sort_formats(formats_m3u8)
                        for _format in formats_m3u8:
                            if (_head:=_format.get('http_headers')):
                                _head.update(headers)
                            else:
                                _format.update({'http_headers': headers})
                        
                        return ({ 
                                "id": videoid,
                                "title": sanitize_filename(_title, restricted=True),                    
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
                    
        
        
        
        # driver = self.get_driver(usequeue=True) 
        
        # try:

        #     self.request_to_host("url_request",url, driver)

        #     video_url = self.wait_until(driver, 30, get_videourl(_type)) 

        #     if not video_url: raise ExtractorError("no video url")            
        #     _title = driver.title.replace(" - TheGay.com", "").strip()
        #     _videoinfo = self.request_to_host("video_info", video_url)
        #     if not _videoinfo: raise Exception(f"error video info")

        #     _format = {
        #             'format_id': 'http-mp4',
        #             'url': _videoinfo['url'],
        #             'filesize': _videoinfo['filesize'],
        #             'ext': 'mp4'
        #     }
            
        #     _entry_video = {
        #         'id' : _videoid,
        #         'title' : sanitize_filename(_title, restricted=True),
        #         'formats' : [_format],
        #         'ext': 'mp4'
        #     } 
            
        #     if not _entry_video: raise ExtractorError("no video info")
        #     else:
        #         return _entry_video      
            
        
        # except ExtractorError as e:
        #     raise
        # except Exception as e:
        #     lines = traceback.format_exception(*sys.exc_info())
        #     self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
        #     raise ExtractorError(repr(e))
        # finally:
        #     try:
        #         self.put_in_queue(driver)
        #     except Exception:
        #         pass