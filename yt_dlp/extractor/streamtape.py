from __future__ import unicode_literals


import re


from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    int_or_none,
    std_headers,
    sanitize_filename,
    
    
)

import httpx
import sys
import traceback


from ratelimit import limits, sleep_and_retry


class StreamtapeIE(InfoExtractor):

    IE_NAME = 'streamtape'
    _VALID_URL = r'https?://(www.)?streamtape\.(?:com|net)/(?:d|e|v)/(?P<id>[a-zA-Z0-9_-]+)/?((?P<title>.+)\.mp4)?'
    
    
    @staticmethod
    def _extract_url(webpage):
        mobj = re.search(r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?streamtape\.(?:com|net)/(?:e|v|d)/.+?)\1',webpage)
        if mobj is not None:
            return mobj.group('url')

    
    def _get_infovideo(self, url, url_ref, client):
        
        count = 0
        try:
            
          
            while (count<3):
                
                try:
                    
                    #res = self._send_request(client, url, 'HEAD')
                    res = client.head(url, follow_redirects=True, headers={'referer': url_ref})
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
        
            _timeout = httpx.Timeout(15, connect=15)        
            _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
            client = httpx.Client(timeout=_timeout, limits=_limits, headers=std_headers, follow_redirects=True, verify=(not self._downloader.params.get('nocheckcertificate')))

            count = 0
            while(count < 3):
                
                try:
                

                    
                    try:                            
                        
                        res = self._send_request(client, url, 'GET')            
                        if res.status_code >= 400:
                            raise ExtractorError(f"Error {res.status_code} - Page not found")                                                       
                    except Exception as e:
                        raise  
                            
                    
                    webpage = re.sub('[\n\t]', '', res.text)
                    mobj = re.findall(r'id=\"(?:norobotlink|robotlink)\" style\=\"display\:none;\"\>/streamtape\.(?:com|net)/get_video\?([^\<]+)\<', webpage)
                    mobj2 = re.findall(r"getElementById\(\'(?:norobotlink|robotlink)\'\).+(token=[^\"\']+)[\'\"]", webpage)
                    if mobj and mobj2:
                        _params = mobj[0].split('token')[0] + mobj2[0]
                        
                        video_url = f"https://streamtape.com/get_video?{_params}"
                        _info_video = self._get_infovideo(video_url, url, client)
                        if _info_video.get('error'): raise ExtractorError("error info video max retries")
                        mobj = re.search(r'og:title\" content=\"(?P<title>[^\"]+)\"', webpage) or re.search(self._VALID_URL, url)
                        if mobj:
                            title = mobj.group('title')
                            if title: title = re.sub('\.mp4| at Streamtape\.com|amp;', '', title, re.IGNORECASE)
                            else: title = "streamtape_video"
                        
                        
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
                        self.to_screen(f"count[{count}] {url}")
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
        
                



       


