from __future__ import unicode_literals


import re

import threading

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    int_or_none,
    std_headers,
    sanitize_filename,
    
    
)

from httpx import (
    Client,
    Timeout,
    Limits,
)
import html
import time
import sys
import traceback
import threading

from ratelimit import limits, sleep_and_retry


class StreamtapeIE(InfoExtractor):

    IE_NAME = 'streamtape'
    _VALID_URL = r'https?://(www.)?streamtape\.(?:com|net)/(?:d|e|v)/(?P<id>[a-zA-Z0-9_-]+)(?:$|/)'
    
    
    _LOCK = threading.Lock()
    
    
    @staticmethod
    def _extract_url(webpage):
        mobj = re.search(r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?streamtape\.(?:com|net)/(?:e|v|d)/.+?)\1',webpage)
        if mobj is not None:
            return mobj.group('url')

    
    def _get_infovideo(self, url, client):
        
        count = 0
        try:
            
            _res = None
            while (count<3):
                
                try:
                    
                    #res = self._send_request(client, url, 'HEAD')
                    res = client.head(url)
                    if res.status_code >= 400:
                        
                        count += 1
                    else: 
                        _filesize = int_or_none(res.headers.get('content-length'))
                        _url = str(res.url)
                        if _filesize and _url:
                            break
                        else:
                            count += 1
                        
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass

        if count < 3: return ({'url': _url, 'filesize': _filesize}) 
        else: return ({'error': 'max retries'})  

    
    @sleep_and_retry
    @limits(calls=1, period=3)
    def _send_request(self, client, url, _type):
        
        self.to_screen(f'[send_request] {_type}:{url}')
        if _type == 'GET': 
            return client.get(url)
        elif _type == 'HEAD':
            return client.head(url)
        
    
    def _real_extract(self, url):
        
   
        
        
        try:
        
            _timeout = Timeout(30, connect=30)        
            _limits = Limits(max_keepalive_connections=None, max_connections=None)
            client = Client(timeout=_timeout, limits=_limits, headers=std_headers, verify=(not self._downloader.params.get('nocheckcertificate')))
            
            _url = re.search(r'(?P<url>https?://(www.)?streamtape\.(?:com|net)/(?:d|e|v)/(?P<id>[a-zA-Z0-9_-]+))', url.replace('/e/', '/v/')).group('url')
            if url == _url:
                self.report_extraction(url)
                
            else:
                self.report_extraction(f'{_url} from {url}')
            
            count = 0
            while(count < 3):
                
                try:
                
                    # with StreamtapeIE._LOCK:
                        
                    #     try:                            
                            
                    #         res = self._send_request(client, _url, 'GET')            
                    #         if res.status_code >= 400:
                    #             raise ExtractorError(f"Error {res.status_code} - Page not found")                                                       
                    #     except Exception as e:
                    #         raise  
                    
                    try:                            
                        
                        res = self._send_request(client, _url, 'GET')            
                        if res.status_code >= 400:
                            raise ExtractorError(f"Error {res.status_code} - Page not found")                                                       
                    except Exception as e:
                        raise  
                            
                    
                    webpage = re.sub('[\n\t]', '', res.text)
                    mobj = re.findall(r'id=\"norobotlink\" style\=\"display\:none;\"\>/streamtape\.com/get_video\?([^\<]+)\<', webpage)
                    mobj2 = re.findall(r"getElementById\(\'norobotlink\'\).+(token=[^\"\']+)[\'\"]", webpage)
                    if mobj and mobj2:
                        _params = mobj[0].split('token')[0] + mobj2[0]
                        
                        video_url = f"https://streamtape.com/get_video?{_params}"
                        _info_video = self._get_infovideo(video_url, client)
                        title = re.sub('\.mp4| at Streamtape\.com|amp;', '', re.search(r'og:title\" content=\"(?P<title>[^\"]+)\"', webpage).group('title'))
                        
                        videoid = self._match_id(url)
                    
                        _format = {
                                'format_id': 'http-mp4',
                                'url': _info_video.get('url'),
                                'filesize': _info_video.get('filesize'),
                                'ext': 'mp4'
                        }
                        
                        _entry_video = {
                            'id' : videoid,
                            'title' : sanitize_filename(title, restricted=True),
                            'formats' : [_format],
                            'ext': 'mp4'
                        }   
                        
                        if _entry_video:
                            return _entry_video
                        else: raise ExtractorError("No video info")
                    else: 
                        self.write_debug(webpage)
                        raise ExtractorError("Couldnt find tokens")
                    
                except ExtractorError as e:
                    count += 1
                    if count == 3: 
                        raise
                    else: 
                        self.to_screen(f"count[{count}] {_url}")
                        continue
                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
                    count += 1
                    if count == 3:
                        raise ExtractorError(str(e)) from e
                    else: 
                        self.to_screen(f"count: {count}")
                        continue
                
        
        finally:
            client.close()
        
                



       


