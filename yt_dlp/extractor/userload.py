from __future__ import unicode_literals


import re
from .common import InfoExtractor, ExtractorError
from ..utils import (
    urlencode_postdata,
    sanitize_filename,
    std_headers,
    int_or_none

)
import httpx
import brotli

class UserLoadIE(InfoExtractor):

    IE_NAME = 'userload'
    _VALID_URL = r'https?://(?:www\.)?userload\.co'

    
    def _real_extract(self, url):
        
   
        client = httpx.Client()
        headers = std_headers
        headers.update({"Alt-Used": "userload.co", "Referer": "https://www.myvidster.com"})
        
        res  = client.get(url, headers = headers)
        
        if res.headers.get("content-encoding") == "br":
            webpage = (brotli.decompress(res.content)).decode("UTF-8", "replace")
        else: webpage = res.text
        
        #self.to_screen(webpage)      
        
        data = re.findall(r"var\|+([^\']*)\'", webpage.replace(" ",""))
        _data = None
        if data:
            _data = data[0].split('|')
        
        if not _data:
            raise ExtractorError("No video data")
        
        #self.to_screen(data)
        
        data = {
            "morocco": _data[13],
            "mycountry": _data[17],
        }
        
        self.to_screen(_data[13])
        self.to_screen(_data[17])
        
        headers_post = std_headers
        headers_post.update({
                "Referer": url,
                "Origin": "https://userload.co",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "*/*",
                "Alt-Used": "userload.co"
            })

        res = client.post(
            "https://userload.co/api/request/",
            data=data,
            headers=headers_post
        )
        self.to_screen(f"{res}:{res.request.headers}:{res.headers}")
        if res.headers.get("content-encoding") == "br":
            video_info = (brotli.decompress(res.content)).decode("UTF-8", "replace")
        else: video_info = res.text
        
        
        #self.to_screen(video_info)
        
        if not video_info or not video_info.startswith("http"):
            raise ExtractorError("No video data after api request")
            
        format_video = {
            'format_id' : 'http-mp4',
            'url' : video_info,
            'filesize' : int_or_none(client.head(video_info).headers.get('content-length')),
            'ext' : 'mp4'
        }

        entry_video = {
            
            'id' : _data[0],
            'title' : _data[3],
            'formats': [format_video],
            'ext': "mp4"
        }

        return entry_video


