from __future__ import unicode_literals

import json
import re
import sys
import traceback
import html
from datetime import datetime
from urllib.parse import unquote

from backoff import constant, on_exception

from ..utils import ExtractorError, try_get
from .commonwebdriver import SeleniumInfoExtractor, limiter_1

from concurrent.futures import ThreadPoolExecutor


class GVDBlogBaseIE(SeleniumInfoExtractor):
    
    
    def get_videourl(self, x, check=True):

        temp = ""
        for el in x:
            if any(re.search(_re, el) for _re in [r'imdb\.com', r'blogger\.com', r'https?://.+\.gs/.+']):
                continue
            elif not 'dood.' in el: 
                
                ie = self._downloader.get_info_extractor(self._get_ie_key(el))
                ie._real_initialize()
                if (func:=getattr(ie, '_video_active', None)):
                    if (_entry:=func(el)): return _entry
                    else: continue                    
                else:
                    if (not check or self._is_valid(el, "")): return el
                    
            elif 'dood.' in el:
                temp = el
        
        ie = self._downloader.get_info_extractor('DoodStream')
        ie._real_initialize()
        _entry = ie._real_extract(temp)
        _entry.update({'webpage_url': temp, 'extractor': 'doodstream', 'extractor_key': 'DoodStream'})
        return _entry

            
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @limiter_1.ratelimit("gvdblog", delay=True)
    def _send_request(self, url, _type="GET", data=None, headers=None):        
        
        
        self.logger_debug(f"[_send_request] {self._get_url_print(url)}") 
        return(self.send_http_request(url, _type=_type, data=data, headers=headers))
        
        
        

    def _real_initialize(self):
        super()._real_initialize()

class GVDBlogPostIE(GVDBlogBaseIE):
    IE_NAME = "gvdblogpost"
    _VALID_URL = r'https?://(www\.)?gvdblog\.com/\d{4}/\d+/.+\.html'
    
    @classmethod
    def get_post_time(cls, webpage):
        _info_date = try_get(re.findall(r"<time>([^<]+)</time>", webpage), lambda x: datetime.strptime(x[0], '%B %d, %Y'))            
            
        if _info_date:           

            return {
                'release_date': _info_date.strftime('%Y%m%d'),
                'release_timestamp': int(_info_date.timestamp())}

    def _real_initialize(self):
        super()._real_initialize()
               
    def _real_extract(self, url):
        
        self.report_extraction(url)

        try:

            webpage = try_get(self._send_request(url), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)))
            if not webpage: raise ExtractorError("couldnt download webpage")
            
            entry = try_get(re.findall(r'href="([^" ]+)" target=', webpage), self.get_videourl) or try_get(re.findall(r'iframe[^>]*src=[\"\']([^\"\']+)[\"\']', webpage), self.get_videourl)            
            if not entry: raise ExtractorError("no video url")
            
            postdate = try_get(re.findall(r"<time>([^<]+)</time>", webpage), lambda x: datetime.strptime(x[0], '%B %d, %Y'))
            _entrydate = {}
            if postdate: 
                _entrydate = {
                    'release_date': postdate.strftime('%Y%m%d'),
                    'release_timestamp': int(postdate.timestamp())}

            if type(entry) == dict:
                entry.update(_entrydate)                    
                return entry                    
            
            _entry = {
                '_type': 'url',
                'url': entry,
            }
            _entry.update(_entrydate)
            
            return _entry
                
        
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f'{type(e)} \n{"!!".join(lines)}')  
            raise ExtractorError(str(e))
        
class GVDBlogPlaylistIE(GVDBlogBaseIE):
    IE_NAME = "gvdblog:playlist"
    _VALID_URL = r'https?://(?:www\.)?gvdblog.com/search\?(?P<query>.+)'
    
    
    def _real_initialize(self):
        super()._real_initialize()
               
    def _real_extract(self, url):
        
        def getter(x):

            if not x:
                return []
            if _jsonstr:=x.group("data"):
                return json.loads(_jsonstr).get('feed', {}).get('entry', [])
        
        self.report_extraction(url)
        
        query = re.search(self._VALID_URL, url).group('query')
        
        params = { el.split('=')[0]: el.split('=')[1] for el in query.split('&') if el.count('=') == 1}
        
        urlquery = f"https://www.gvdblog.com/feeds/posts/full?alt=json-in-script&max-results=99999"
        
        if _category:=params.get('label'):
            urlquery += f"&category={_category}"
        _check = True 
        if params.get('check','').lower() == 'no':
            _check = False
        
        res = self._send_request(urlquery)
        if not res: raise ExtractorError("no search results")
        video_entries = try_get(re.search(r"gdata.io.handleScriptLoaded\((?P<data>.*)\);", res.text), getter)
        if not video_entries: raise ExtractorError("no video entries")
        
        self._entries = []
                
        def get_entry(_entry):
            
            postdate = datetime.strptime(_entry['published']['$t'].split('T')[0], '%Y-%m-%d')
            videourlpost = _entry['link'][-1]['href']
            entry = try_get(re.findall(r'href="([^" ]+)" target=', _entry['content']['$t']), lambda x: self.get_videourl(x, _check)) or try_get(re.findall(r'iframe[^>]*src=[\"\']([^\"\']+)[\"\']', _entry['content']['$t']), lambda x: self.get_videourl(x, _check))
            if entry:
                
                _res = {
                    'original_url': videourlpost,
                    'release_date': postdate.strftime('%Y%m%d'),
                    'release_timestamp': int(postdate.timestamp())}
                
                if type(entry) == dict:
                    _res.update(entry)
                    
                else:
                    _res.update({
                        '_type': 'url',
                        'url': entry,
                        
                    })
                    
                self._entries.append(_res)
 
            else:
                self.report_warning(f'[{url}][{videourlpost}] couldnt get video from this entry')
        
                
        with ThreadPoolExecutor(thread_name_prefix="gvdpl") as ex:
                
            futures = [ex.submit(get_entry, _entry) for _entry in video_entries]       


        if not self._entries: raise ExtractorError("no video list")
        return self.playlist_result(self._entries, f"gvdblog_playlist", f"gvdblog_playlist")
             
        
        