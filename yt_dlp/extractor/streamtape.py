from __future__ import unicode_literals


import re

from ..utils import (
    ExtractorError,
    int_or_none,
    std_headers,
    sanitize_filename,
    
    
)

import httpx
import sys
import traceback

from .common import InfoExtractor
from ratelimit import limits, sleep_and_retry

from backoff import on_exception, constant

from urllib.parse import quote, unquote


class StreamtapeIE(InfoExtractor):

    IE_NAME = 'streamtape'
    _VALID_URL = r'https?://(www.)?streamtape\.(?:com|net)/(?:d|e|v)/(?P<id>[a-zA-Z0-9_-]+)/?((?P<title>.+)\.mp4)?'
    
    
    @staticmethod
    def _extract_url(webpage):
        mobj = re.search(r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?streamtape\.(?:com|net)/(?:e|v|d)/.+?)\1',webpage)
        if mobj is not None:
            return mobj.group('url')

    
   
    
    @on_exception(constant, Exception, max_tries=5, interval=1)
    def _get_infovideo(self, client, url, headers):
        
       
        res = client.head(url, headers=headers)        
        res.raise_for_status()
        _filesize = int_or_none(res.headers.get('content-length'))
        _url = unquote(str(res.url))
        if _url and _filesize: return ({'url': _url, 'filesize': _filesize})
    

    
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @sleep_and_retry
    @limits(calls=1, period=5)
    def _send_request(self, client, url, _type):
        
        res = client.request(_type, url)
        res.raise_for_status()
        return res
        
    
    def _real_extract(self, url):

        try:
        
            _timeout = httpx.Timeout(30, connect=30)        
            _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
            client = httpx.Client(timeout=_timeout, limits=_limits, headers=std_headers, follow_redirects=True, verify=(not self._downloader.params.get('nocheckcertificate')))


            res = self._send_request(client, url, 'GET')            
                                        
            webpage = re.sub('[\n\t]', '', res.text)            
            mobj = re.findall(r'id=\"(?:norobotlink|robotlink)\" style\=\"display\:none;\"\>/streamtape\.(?:com|net)/get_video\?([^\<]+)\<', webpage)
            mobj2 = re.findall(r"getElementById\(\'(?:norobotlink|robotlink)\'\).+(token=[^\"\']+)[\'\"]", webpage)
            if mobj and mobj2:
                _params = mobj[0].split('token')[0] + mobj2[0]
                
                video_url = f"https://streamtape.com/get_video?{_params}"
                _headers = {'referer': quote(url)}
                _info_video = self._get_infovideo(client, video_url, _headers)
                if not _info_video.get: raise ExtractorError("error info video max retries")
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
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")            
            raise ExtractorError(repr(e)) 
        finally:
            client.close()
