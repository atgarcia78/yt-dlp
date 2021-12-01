from __future__ import unicode_literals


import re
from .common import InfoExtractor
from ..utils import (
    ExtractorError,   
    std_headers,
    sanitize_filename,
    int_or_none,

)

import httpx
import demjson

class EbembedIE(InfoExtractor):
    
    IE_NAME = 'ebembed'
    _VALID_URL = r'https?://(www\.)?ebembed\.com/(?:videos|embed)/(?P<id>\d+)/?(?P<title>[^\$]*)$'
    
    def get_info_for_format(self, url, client=None, headers=None):
        
        count = 0
        if not client:
            _timeout = httpx.Timeout(15, connect=15)        
            _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
            client = httpx.Client(timeout=_timeout, limits=_limits, headers=std_headers, verify=(not self._downloader.params.get('nocheckcertificate')))
            close_client=True
        else: close_client=False
            
        try:
            
            
            while (count<3):
                
                try:
                    
                    #res = self._send_request(client, url, 'HEAD')
                    res = client.head(url, follow_redirects=True, headers=headers)
                    res.raise_for_status()
                    _filesize = int_or_none(res.headers.get('content-length'))
                    _url = str(res.url)
                    break
                        
            
                except Exception as e:
                    _error = e
                    count += 1
        except Exception as e:
            pass
        finally:
            if close_client:
                try:
                    client.close()
                except Exception:
                    pass

        if count < 3: return ({'url': _url, 'filesize': _filesize}) 
        else: return ({'error': f'max retries - {repr(_error)}'})  
    

    def _real_extract(self, url):
        
                       
        self.report_extraction(url)
        
        
        _timeout = httpx.Timeout(15, connect=15)        
        _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
        client = httpx.Client(timeout=_timeout, limits=_limits, headers=std_headers, follow_redirects=True, verify=(not self._downloader.params.get('nocheckcertificate')))
        
        try:    
            
            res = client.get(url)
            if res.status_code > 400: raise ExtractorError(f'{url}:{res}')
            else: webpage = res.text
            flashvars = re.findall(r'(?ms)<script.*?>.*?var\s+flashvars\s*=\s*(\{.*?\});.*?</script>', webpage)
            entry = None
            if flashvars:
                data = demjson.decode(flashvars[0])
                if data:             
                    formats = []

                    if (_target:=data.get("video_url")):
                        
                        _url = re.findall(r'(https.*)', _target)[0]
                        if (_rnd:=data.get('rnd')): _url = _url +"?rnd=" + _rnd
                        _desc = data.get("video_url_text", "")
                        info_video = self.get_info_for_format(_url, client)
                        if not info_video: raise Exception(f"error video info")
                        formats.append({'format_id': 'http' + _desc, 'url': info_video.get('url'), 'filesize': info_video.get('filesize'), 'ext': 'mp4', 'resolution': _desc, 'height' : int_or_none(_desc[:-1] if _desc else None)})
                        
                    if (_urlalt:=data.get("video_alt_url")):
                        
                        _desc = data.get("video_alt_url_text", "")
                        info_video = self.get_info_for_format(_urlalt, client)
                        if (error_msg:=info_video.get('error')): raise Exception(f"error video info - {error_msg}")
                        formats.append({'format_id': 'http' + _desc, 'url': info_video.get('url'), 'filesize': info_video.get('filesize'), 'ext': 'mp4', 'resolution': _desc, 'height' : int_or_none(_desc[:-1] if _desc else None)})
                        
                    if not formats: raise ExtractorError("No formats found")
                    else:
                        self._sort_formats(formats)
                        video_id = self._match_id(url)
                        mobj = re.findall(r"<title>([^<]+)<", res.text) or [re.search(self._VALID_URL, url).group('title')]
                        title = mobj[0] if mobj else "video_from_ebembed"
                        entry = {
                            'id' : video_id,
                            'title' : sanitize_filename(title, restricted=True),
                            'formats' : formats,
                            'ext': 'mp4'
                        }            
            if not entry: raise ExtractorError("no video info")
            else: return entry
        
        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(repr(e)) from e    
        finally:
            try:
                client.close()
            except Exception:
                pass
