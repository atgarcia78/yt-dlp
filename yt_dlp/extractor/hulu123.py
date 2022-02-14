from __future__ import unicode_literals

from backoff import on_exception

from ..utils import (
    ExtractorError,
    sanitize_filename,
    try_get)


from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_5
)

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import re
import traceback
import sys

from backoff import (
    constant, 
    on_exception
)

from .streamtape import video_or_error_streamtape
from .userload import video_or_error_userload
from .evoload import video_or_error_evoload
from .eplayvid import video_or_error_eplayvid

from concurrent.futures import ThreadPoolExecutor

class Hulu123IE(SeleniumInfoExtractor):
    IE_NAME = "hulu123"
    _VALID_URL = r'https?://(www\.)?123hulu\.com/watch/(?P<id>[^-]+)-[^\./]+(?:\.html|/(?P<format>(?:vip|streamtape|userload|evoload)))'
 
    @on_exception(constant, Exception, max_tries=5, interval=5)
    @limiter_5.ratelimit("hulu123", delay=True)
    def _send_request(self, url, driver):        
        
        self.logger_info(f"[send_request] {url}") 
        driver.get(url)    
    

    def _worker(self, key, func, server_list):
        
        if not server_list: return ""
        driver = self.get_driver(usequeue=True)
        
        try:
            
            @limiter_5.ratelimit("hulu123" + key, delay=True)
            def _getter(server):
                self.to_screen(f'[{key}][{server[26:]}] getting video url')
                driver.get(server)
                el_ifr = self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "iframe")))
                if el_ifr:
                    _url = el_ifr.get_attribute('src')                    
                    driver.switch_to.frame(el_ifr)                
                    if (_val:=self.wait_until(driver, 30, func(self.to_screen))) and _val != "error": 
                        _res_url = _val
                        self.to_screen(f'[{key}][{server[26:]}] OK:[{_url}][{_val}]')
                    else:
                        _res_url = "error"
                        self.to_screen(f'[{key}][{server[26:]}] NOK:[{_url}]')
                    
                    return _res_url            
            
            for server in server_list:
                vid_url = _getter(server)
                if vid_url and vid_url != "error":
                    break
            
            return vid_url
        
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')  
        finally:
            self.put_in_queue(driver)
            
                      
        
    
    def _real_initialize(self):
        super()._real_initialize()
        
               
    def _real_extract(self, url):        
        
        self.report_extraction(url)        
        driver = self.get_driver(usequeue=True) 

        try:

            self._send_request(url, driver)
            el_title = try_get(self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "h3"))), lambda x: x.get_attribute('innerText')) or ""
            video_id = try_get(re.findall(r'og:url" content="([^"]+)"', driver.page_source), lambda x: self._match_id(x[0]))
            
            _format = try_get(re.search(self._VALID_URL, url), lambda x: x.group('format'))
            if not _format:
                el_servers = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CLASS_NAME, "server_play")))
                servers_list = [_serv for _el in el_servers if (_serv:=try_get(_el.find_elements(By.TAG_NAME, "a"), lambda x: x[0].get_attribute("href")))]
            else:
                servers_list = [url]
            
            self.write_debug(f'servers list: {servers_list}')
            
            _res_urls = {'vip_url': "", 'userload_url': "", 'evoload_url': "", 'streamtape_url' :""}
            
            _server_vip_list = [server for server in servers_list if "vip.html" in server]
            _server_userload_list = [server for server in servers_list if "userload.html" in server]
            _server_evoload_list = [server for server in servers_list if "evoload.html" in server]
            _server_streamtape_list = [server for server in servers_list if "streamtape.html" in server]

            self.to_screen(f'servers list:[{len(servers_list)}]:vip[{len(_server_vip_list)}]:userload[{len(_server_userload_list)}]:evoload[{len(_server_evoload_list)}]:streamtape[{len(_server_streamtape_list)}]')
            
            if _server_vip_list and _server_userload_list:  _server_streamtape_list = []

            _server_all_list = [(video_or_error_eplayvid, _server_vip_list, 'vip_url'), (video_or_error_userload, _server_userload_list, 'userload_url'), (video_or_error_evoload, _server_evoload_list, 'evoload_url'), (video_or_error_streamtape, _server_streamtape_list, 'streamtape_url')]
            
            with ThreadPoolExecutor(thread_name_prefix="hulu123_ex", max_workers=4) as ex:
                futures = {ex.submit(self._worker, _keyurl, _func, _list): _keyurl for (_func, _list, _keyurl) in _server_all_list}
                
            for _fut, _keyurl in futures.items():
                try:
                    _res_urls[_keyurl] = _fut.result() 
                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')
   
            vip_url = _res_urls['vip_url']
            userload_url = _res_urls['userload_url']
            evoload_url = _res_urls['evoload_url']
            streamtape_url = _res_urls['streamtape_url']
                      
            #self.to_screen(f'vip:[{vip_url}]:userload:[{userload_url}]:evoload:[{evoload_url}]:streamtape:[{streamtape_url}]')
            self.to_screen(f'RESULT: {_res_urls}')
            if vip_url == 'error' and userload_url == "error" and evoload_url == "error" and streamtape_url == "error": raise ExtractorError("404 UserLoad & EverLoad $ StreamTape servers available but no video found in any")
            if vip_url == "" and userload_url == "" and evoload_url == "" and streamtape_url == "": raise ExtractorError("no UserLoad & EverLoad & Streamtape servers available")
            
            video_urls = [(_url, _id) for (_url, _id) in [(vip_url, "vip"), (userload_url, "userload"), (evoload_url, "evoload"), (streamtape_url, "streamtape")] if _url and _url != "error"]
            
            if not video_urls: raise ExtractorError("404 UserLoad & EverLoad $ StreamTape servers available but no video found in any")

            _formats = []
            for (_url, _id) in video_urls:
                try:
                    if _id == 'vip': 
                        headers = {'Referer': 'https://eplayvid.net/'}
                        _f = {'http_headers': headers}
                    else: 
                        headers = None
                        _f = {}
                    _info_video = self.get_info_for_format(_url, headers=headers)
                    if not _info_video: raise ExtractorError(f"no info video")
                    _f.update({
                        'format_id': f'http-mp4-{_id}',
                        'url': _info_video.get('url'),
                        'filesize': _info_video.get('filesize'),
                        'ext': 'mp4'
                    })
                    _formats.append(_f)
                except Exception as e:
                    self.to_screen(f"[get_formats][{_url[26:]}] {repr(e)}")
            if _formats:
                self._sort_formats(_formats)
                return({'id': video_id, 'title': sanitize_filename(el_title, restricted=True), 'formats': _formats, 'ext': 'mp4'})

        except ExtractorError as e:                 
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{str(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e))
        finally:
            self.put_in_queue(driver)
 
        