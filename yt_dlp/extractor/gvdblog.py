from __future__ import unicode_literals

import json
import re
import sys
import traceback
from datetime import datetime
from urllib.parse import unquote

from backoff import constant, on_exception

from ..utils import ExtractorError, try_get
from .commonwebdriver import SeleniumInfoExtractor, limiter_1


class GVDBlogBaseIE(SeleniumInfoExtractor):
    
    
    def get_videourl(self, x):

        temp = ""
        for el in x:
            if any(re.search(_re, el) for _re in [r'imdb\.com', r'blogger\.com', r'https?://.+\.gs/.+']):
                continue
            elif not 'dood.' in el and self._is_valid(el, ""):
                return el
            elif 'dood.' in el:
                temp = el
        return temp

            
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @limiter_1.ratelimit("gvdblog", delay=True)
    def _send_request(self, url, _type="GET", data=None, headers=None):        
        
        res = None
        try:
            self.logger_info(f"[_send_request] {url}") 
            res = self.send_request(url, _type=_type, data=data, headers=headers)
            res.raise_for_status()
            return res
        except Exception as e:
            if res: 
                msg_error = f'{res} - {res.request} \n{res.request.headers}'
            else: msg_error = ""
            self.logger_info(f"[_send_request][{url}] error {repr(e)} - {msg_error}")
            raise
        

    def _real_initialize(self):
        super()._real_initialize()

class GVDBlogPostIE(GVDBlogBaseIE):
    IE_NAME = "gvdblogpost"
    _VALID_URL = r'https?://(www\.)?gvdblog\.com/\d{4}/\d+/.+\.html'
    
    @classmethod
    def get_post_time(cls, webpage):
        post_time = try_get(re.findall(r"<span class='post-timestamp'[^>]+><a[^>]+>([^<]+)<", webpage.replace('\n','')), lambda x: x[0])            
            
        if post_time:
            _info_date = datetime.strptime(post_time, '%B %d, %Y')

            return {
                'release_date': _info_date.strftime('%Y%m%d'),
                'release_timestamp': int(_info_date.timestamp())}

    def _real_initialize(self):
        super()._real_initialize()
               
    def _real_extract(self, url):
        
        self.report_extraction(url)

        try:

            webpage = try_get(self._send_request(url), lambda x: x.text)
            if not webpage: raise ExtractorError("couldnt download webpage")
            #self.to_screen(webpage)
            videourl = try_get(re.findall(r'href="([^" ]+)" target=', webpage), self.get_videourl) or try_get(re.findall(r'iframe[^>]*src=[\"\']([^\"\']+)[\"\']', webpage), self.get_videourl)             
                            
            postdate = try_get(re.findall(r"<span class='post-timestamp'[^>]+><a[^>]+>([^<]+)<", webpage), lambda x: datetime.strptime(x[0], '%B %d, %Y'))            
            if not videourl: raise ExtractorError("no video url")
            self.to_screen(videourl)
            _entry = {
                '_type': 'url_transparent',
                'url': unquote(videourl)}
            if postdate:                
                _entry.update({
                    'release_date': postdate.strftime('%Y%m%d'),
                    'release_timestamp': int(postdate.timestamp())})
            
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
        
        params = { el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
        
        urlquery = f"https://www.gvdblog.com/feeds/posts/full?alt=json-in-script&max-results=9999"
        
        if _category:=params.get('label'):
            urlquery += f"&category={_category}"
            
        res = self._send_request(urlquery)
        if not res: raise ExtractorError("no search results")
        video_entries = try_get(re.search(r"gdata.io.handleScriptLoaded\((?P<data>.*)\);", res.text), getter)
        if not video_entries: raise ExtractorError("no video entries")
        _entries = []
        for _entry in video_entries:
            postdate = datetime.strptime(_entry['published']['$t'].split('T')[0], '%Y-%m-%d')
            videourlpost = _entry['link'][-1]['href']
            videourl = try_get(re.findall(r'href="([^" ]+)" target=', _entry['content']['$t']), self.get_videourl) or try_get(re.findall(r'iframe[^>]*src=[\"\']([^\"\']+)[\"\']', _entry['content']['$t']), self.get_videourl)
            if videourl:
                _entries.append({
                    '_type': 'url_transparent',
                    'original_url': videourlpost,
                    'webpage_url': url,
                    'release_date': postdate.strftime('%Y%m%d'),
                    'release_timestamp': int(postdate.timestamp()),
                    'url': unquote(videourl)
                })
            else:
                self.report_warning(f'[{url}][{videourlpost}] couldnt get video from this entry')

        if not _entries: raise ExtractorError("no video list")
        return self.playlist_result(_entries, f"gvdblog_playlist", f"gvdblog_playlist")
             
        
        