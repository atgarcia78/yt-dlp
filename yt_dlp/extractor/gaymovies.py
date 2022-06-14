from __future__ import unicode_literals

import re
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor


from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_1


class get_episodes():
    def __call__(self, driver):
        el_ep = driver.find_elements(By.CLASS_NAME, "episodios")
        if el_ep:
            return({'type': 'multi', 'el': el_ep[0]})
        else:
            el_ep = driver.find_elements(By.CLASS_NAME, "season")
            if el_ep:
                return({'type': 'single', 'el': el_ep[0]})
            else: return False

class GayMoviesIE(SeleniumInfoExtractor):
    IE_NAME = "gaymovies:playlist"
    _VALID_URL =r'https?://(www\.)?gaymovies\.lgbt/watch/(?P<title>[^\.]+)\.html(\?key=(?P<key>.*))?'
 
    @dec_on_exception
    @limiter_1.ratelimit("gaymovies", delay=True)
    def _send_request(self, url, driver=None):        
        
        self.logger_info(f"[send_request] {url}") 
        if driver:
            driver.get(url)
        else:
            res = self._CLIENT.get(url)
            res.raise_for_status()
            return res
        
        
    def _get_playlist(self, url, check_active=False):
        
        
        
        try:
            driver = self.get_driver()
            self._send_request(url, driver)
            _type, el_episodes = try_get(self.wait_until(driver, 30, get_episodes()), lambda x: (x['type'], x['el'])) or (None, None)
            if not el_episodes: raise ExtractorError("error 404 videos not found")
            el_title = try_get(driver.find_elements(By.CSS_SELECTOR, "span.pull-left.title"), lambda x: x[0].get_attribute("innerText"))
            el_a = el_episodes.find_elements(By.TAG_NAME, "a")
            info_videos = {}
            
            def _getter(_type, el):
                _wurl = el.get_attribute('href')
                if not _wurl: return
                if _type == 'multi':
                    extr, title = try_get(el.find_elements(By.CLASS_NAME, "numerando"), lambda x: x[0].get_attribute('innerText').split(' ')) or ("","")
                elif _type == 'single':
                    extr = el.get_attribute("innerText") or ""
                    title = "main"
                
                extr = extr.lower()
                if extr in ['streamtape', 'fembed']:
                    webpage = try_get(self._send_request(_wurl), lambda x: x.text)
                    if webpage:                                    
                        _vurl = try_get(re.findall(r'responsive-embed-item" src="([^"]+)"', webpage), lambda x: x[0])
                        if _vurl:
                            return({'original_url': _wurl, 'url': _vurl, 'title': title, 'extr': extr})
            

                    
            for el in el_a:
                _info = _getter(_type, el)
                if not _info: 
                    continue
                if not _info['title'] in info_videos: 
                    info_videos[_info['title']] = {}
                info_videos[_info['title']].update({_info['extr']: {'original_url': _info['original_url'], 'url': _info['url']}})
            
            self.to_screen(info_videos)
            if not info_videos: raise ExtractorError("error 404 videos not found")
            iestr = self._downloader.get_info_extractor('Streamtape') 
            iestr._real_initialize()
            iefem = self._downloader.get_info_extractor('Fembed')
            iefem._real_initialize()
            _entries = []
            for _title, _value in info_videos.items():
                    
                _entry = {}                         
                try:
                    _entry = iefem._get_entry(_value['fembed']['url'], check_active=check_active)
                    _original_url = _value['fembed']['original_url']
                except Exception as e:
                    self.to_screen(repr(e))
                    try:
                        _entry = iestr._get_entry(_value['streamtape']['url'], check_active=check_active)
                        _original_url = _value['streamtape']['original_url']
                    except Exception as e:
                        self.to_screen(repr(e))
                
                if not _entry: 
                    continue
                
                if _title == "main": _post = ""
                else: _post = f" {_title}"
                _entry.update({'title': sanitize_filename(f"{el_title}{_post}", restricted=True),
                               "original_url": _original_url})
                _entries.append(_entry)
                
            return self.playlist_result(_entries, playlist_id=el_title, playlist_title=el_title)
        
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            self.rm_driver(driver)
                

    
    def _real_initialize(self):
        super()._real_initialize()
        
               
    def _real_extract(self, url):
        
        self.report_extraction(url)

        try:                            

            if self._downloader.params.get('external_downloader'): _check_active = True
            else: _check_active = False

            return self._get_playlist(url, check_active=_check_active)  
            
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        