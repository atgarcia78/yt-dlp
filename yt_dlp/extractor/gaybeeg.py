import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import unquote


from ..utils import ExtractorError, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_1, By, ec, HTTPStatusError


class get_links_netdna():
    def __init__(self, logger):
        self.old_len = -1
        self.logger = logger
        
        
    def __call__(self, driver):
        try:
            
            el_footer = driver.find_element(By.ID, "footer")        
            driver.execute_script("window.scrollTo(arguments[0]['x'], arguments[0]['y']);", el_footer.location)

            el_a_list = driver.find_elements(By.XPATH, '//a[contains(@href, "//netdna-storage.com")]')

            self.logger(f"[gets_links_netdna] {el_a_list}")
            
            if (new_len:=len(el_a_list)) > self.old_len:
                self.old_len = new_len
                return False
            else:
                if not el_a_list: return "no entries"
                else: return el_a_list
        
        except Exception as e:
            self.logger(f"[gets_links_netdna] {repr(e)}")
            raise
            

class GayBeegBaseIE(SeleniumInfoExtractor):

    def _get_entries_netdna(self, el_list):
        
        _list_urls_netdna = {}
        for _el in el_list:
            _url = _el.get_attribute('href')
            _tree = _el.find_elements(by=By.XPATH, value="./ancestor-or-self::*")
            _tree.reverse()
            if any((_el_date:=el.find_elements(By.CLASS_NAME, 'date')) for el in _tree):
                _date = _el_date[0].text
                if not _list_urls_netdna.get(_url):
                    _list_urls_netdna[_url] = {'dates': [_date]}
                else:
                    _list_urls_netdna[_url]['dates'].append(_date)
            if any((_el_h2:=el.find_elements(By.CSS_SELECTOR, 'h2')) for el in _tree):
                if (_orig_url:=try_get(_el_h2[0].find_elements(By.CSS_SELECTOR, 'a'), lambda x: x[0].get_attribute('href') if x else None)):
                    _list_urls_netdna[_url]['original_url'] = _orig_url
                 

        ie_netdna = self._downloader.get_info_extractor('NetDNA')
        ie_netdna._real_initialize()
        _num_workers = min(6, len(_list_urls_netdna))
        with ThreadPoolExecutor(thread_name_prefix="ent_netdna", max_workers=_num_workers) as ex:
            futures = {ex.submit(ie_netdna.get_video_info_url, _url): _url for _url in list(_list_urls_netdna.keys())}
        
        for fut in futures:
            try:
                res = fut.result()
                if not res:
                    self.to_screen(f'[get_entries_netdna][{futures[fut]}] no entries')
                    _list_urls_netdna[futures[fut]].update({'info_video': {}})
                elif (_errormsg:=res.get('error')):
                    self.to_screen(f'[get_entries_netdna][{futures[fut]}] ERROR {_errormsg}')
                    _list_urls_netdna[futures[fut]].update({'info_video': {}})
                    
                else:
                    _list_urls_netdna[futures[fut]].update({'info_video': res})
                                
            except Exception as e:
                self.to_screen(f'[get_entries_netdna][{futures[fut]}] ERROR ] {repr(e)}') 
                _list_urls_netdna[futures[fut]].update({'info_video': {}})
                
        entries = []
        for _url, _item in _list_urls_netdna.items():            
            
            try: 
                _info_video = _item.get('info_video')
                if not _info_video: continue
                _ent = {'_type' : 'url_transparent', 'url' : _url, 'ie_key' : 'NetDNA', 'title': _info_video.get('title'), 'id' : _info_video.get('id'), 'ext': _info_video.get('ext'), 'filesize': _info_video.get('filesize')}                
                _list_dates_str =  _item.get('dates')
                _info_date = try_get(sorted([datetime.strptime(date_str, '%B %d, %Y') for date_str in _list_dates_str]), lambda x: x[0])
                if _info_date:
                    _ent.update({'release_date': _info_date.strftime('%Y%m%d'), 'release_timestamp': int(_info_date.timestamp())})
                if (_orig_url:=_item.get('original_url')):
                    _ent.update({'original_url': _orig_url})
                    
                entries.append(_ent)
            except Exception as e:
                self.to_screen(f'{_url}: {repr(e)}')                

        return entries
    

    def _get_entries(self, url):
        
        try:
        
            _driver = self.get_driver()

            self.logger_debug(f'[get_entries] {url}')

            self.send_driver_request(_driver, url)

            el_netdna_list = self.wait_until(_driver, 60, get_links_netdna(self.to_screen), poll_freq=2)

            if not el_netdna_list or el_netdna_list == "no entries":
                raise ExtractorError("No entries")
            else:
                self.logger_debug(f"[{url}] list links: {len(el_netdna_list)}")
                return self._get_entries_netdna(el_netdna_list)
            
        except Exception as e:
            self.report_warning(f'[get_entries][{url}] {repr(e)}')
            
        finally:
            self.rm_driver(_driver)
           

    @limiter_1.ratelimit("gaybeeg2", delay=True)  
    def send_driver_request(self, driver, url):
        
        try:        
            driver.execute_script("window.stop();")
        except Exception:
            pass
        driver.get(url)
        
        
    @dec_on_exception
    @limiter_1.ratelimit("gaybeeg3", delay=True)
    def get_info_pages(self, url):
        
        try:
            webpage = try_get(self.send_http_request(url), lambda x: x.text if x else None)
            if not webpage: raise ExtractorError("not webpage")
            num_pages = try_get(re.findall(r'class="pages">Page 1 of ([\d\,]+)', webpage), lambda x: int(x[0].replace(',',''))) or 1
            if num_pages == 1: _href = url
            else: _href = try_get(re.findall(r'class="page" title="\d">\d</a><a href="([^"]+)"', webpage), lambda x: unquote(x[0]))
            return (num_pages, _href)
        except HTTPStatusError as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
            
    def _real_initialize(self):
        super()._real_initialize()
        
class GayBeegPlaylistPageIE(GayBeegBaseIE):
    IE_NAME = "gaybeeg:onepage:playlist"
    _VALID_URL = r'https?://(www\.)?gaybeeg\.info.*/page/.*'
    
    def _real_initialize(self):
        super()._real_initialize()
        
    def _real_extract(self, url):        
        
        try:
                   
            self.report_extraction(url)
            
            entries = self._get_entries(url)
            
            if not entries: raise ExtractorError("No entries")  
                      
            return self.playlist_result(entries, "gaybeeg", "gaybeeg")
            
   
            
        except ExtractorError as e:
            raise
        except Exception as e:
            self.to_screen(repr(e))            
            raise ExtractorError(repr(e))

class GayBeegPlaylistIE(GayBeegBaseIE):
    IE_NAME = "gaybeeg:allpages:playlist"    
    _VALID_URL = r'https?://(www\.)?gaybeeg\.info/(?:((?P<type>(?:site|pornstar|tag))(?:$|(/(?P<name>[^\/$\?]+)))(?:$|/$|/(?P<search1>\?(?:tag|s)=[^$]+)$))|((?P<search2>\?(?:tag|s)=[^$]+)$))'
    
    def _real_initialize(self):
        super()._real_initialize()
        
        
    def _real_extract(self, url):        
        
        try:
                                   
            self.report_extraction(url)

            num_pages, _href = try_get(self.get_info_pages(url), lambda x: x if x else (1,url))

            self.to_screen(f"Pages to check: {num_pages}")                    
                
            list_urls_pages = [re.sub(r'page/\d+', f'page/{i}', _href) for i in range(1, num_pages+1)]
            
            self.to_screen(list_urls_pages)
            
            _num_workers = min(6, len(list_urls_pages))
            
            with ThreadPoolExecutor(thread_name_prefix="gybgpages", max_workers=_num_workers) as ex:
                futures = {ex.submit(self._get_entries, _url): _url for _url in list_urls_pages}
                
            entries = []
            for fut in futures:
                try:
                    res = fut.result()
                    if res:
                        entries += res
                except Exception as e:
                    self.report_warning(f"[get_entries] {self._get_url_print(url)}: error - {repr(e)}")


            if entries:
                return self.playlist_result(entries, "gaybeegplaylist", "gaybeegplaylist")
            else: raise ExtractorError("No entries")
            
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            self.to_screen(repr(e))            
            raise ExtractorError(repr(e))



class GayBeegIE(GayBeegBaseIE):
    IE_NAME = "gaybeeg:post:playlist"
    _VALID_URL = r'https?://(www\.)?gaybeeg\.info/\d\d\d\d/\d\d/\d\d/.*'
    
    def _real_initialize(self):
        super()._real_initialize()           
    
    def _real_extract(self, url):        
        
        try:
                 
            self.report_extraction(url)
            
            entries = self._get_entries(url)            
                        
            if not entries:
                raise ExtractorError("No video entries")
            else:
                return self.playlist_result(entries, "gaybeegpost", "gaybeegpost")  
            
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            self.to_screen(repr(e))            
            raise ExtractorError(repr(e))
