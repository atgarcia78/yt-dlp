from __future__ import unicode_literals

import sys
import threading
import traceback
import re




from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_0_1, By, ec


class VideovardIE(SeleniumInfoExtractor):

    IE_NAME = "videovard"
    _SITE_URL = "https://videovard.sx/"
    _VALID_URL = r'https?://videovard\.\w\w/[e,v]/(?P<id>[^&]+)'
    
    _LOCK = threading.Lock()
    
    
    @staticmethod
    def _extract_urls(webpage):
       
        return [mobj.group('url') for mobj in re.finditer(r'<iframe[^>]+?src=([\"\'])(?P<url>https://videovard\.sx/e/.+?)\1',webpage)]

    @dec_on_exception
    @limiter_0_1.ratelimit("videovard", delay=True)
    def send_multi_request(self, url, driver=None, _type=None):
        
        if driver:
            driver.execute_script("window.stop();")
            driver.get(url)
        else:
            if not _type:
                res = self._CLIENT.get(url)
                res.raise_for_status()
                return res
            else:
                return self.get_info_for_format(url, headers={'Referer': self._SITE_URL})

    def scan_for_request(self, _har, _ref, _link):

        for entry in _har['log']['entries']:
            if entry['pageref'] == _ref:
                if _link in (_url:=entry['request']['url']):
                    return _url            


    def _real_initialize(self):

        super()._real_initialize()        

                
    def _real_extract(self, url):

        try:
            
            with VideovardIE._LOCK:
        
                self.report_extraction(url) 
                videoid = self._match_id(url)

                _server, _server_port = self.start_browsermob(url)

                _host = 'localhost'
                _port = _server_port + 1                
                _harproxy = _server.create_proxy({'port' : _port})
                driver  = self.get_driver(host=_host, port=_port)
                            
                try:
                    _harproxy.new_har(options={'captureHeaders': True, 'captureContent': True}, ref=f"har_{videoid}", title=f"har_{videoid}")
                    self.send_multi_request(url.replace('/e/', '/v/'), driver)
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
                    
                    _headers = {'Referer': self._SITE_URL}
                    video_url = try_get(driver.find_elements(By.TAG_NAME, 'video'), lambda x: x[0].get_attribute('src'))
                    if video_url and not video_url.startswith('blob'):
                        _info_video = self.send_multi_request(video_url, _type="info_video")
                        if not _info_video: raise ExtractorError("no info video")
                        _format = {'format_id': 'http-mp4', 'url': _info_video['url'], 'filesize': _info_video['filesize'], 'ext': 'mp4'}
                        return ({ 
                                "id": videoid,
                                "title": sanitize_filename(title, restricted=True),                    
                                "formats": [_format],
                                "http_headers": _headers,
                                "ext": "mp4"})
                    else:
                        m3u8_url = self.scan_for_request(har, f"har_{videoid}", f"master.m3u8")
                        if m3u8_url:
                            self.write_debug(f"[{url}] m3u8 url - {m3u8_url}")
                            res = self.send_multi_request(m3u8_url)
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
               
                    