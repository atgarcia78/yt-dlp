# coding: utf-8
from __future__ import unicode_literals

import re

import httpx
import time

from .common import InfoExtractor
from ..utils import (
    ExtractorError, 
    int_or_none,
    sanitize_filename,
    
)
import hashlib



class Mat6TubeIE(InfoExtractor):
    IE_NAME = 'mat6tube'
    IE_DESC = 'mat6tube'
    _VALID_URL = r"https?://(?:www\.)?adult.mat6tube.com/watch/\-(?P<id>\d+\_\d+)"   
    _SITE_URL = "https://adult.mat6tube.com"


    def _get_filesize(self, url):
        
        count = 0
        try:
            cl = httpx.Client(timeout=60,verify=(not self._downloader.params.get('nocheckcertificate')))
            _res = None
            while (count<3):
                
                try:
                    
                    res = cl.head(url)
                    if res.status_code > 400:
                        time.sleep(1)
                        count += 1
                    else: 
                        _res = int_or_none(res.headers.get('content-length')) 
                        break
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass
        finally:
            cl.close()
        
        return _res
    
        
    

    def _real_extract(self, url):
        
        self.report_extraction(url)
        cl = httpx.Client(timeout=60,verify=(not self._downloader.params.get('nocheckcertificate')))
        res = cl.get(url)
        if res.status_code > 400: raise ExtractorError()
        mobj = re.findall(r'iplayer\"src=\"/([^\"]+)\"',res.text.replace(" ",""))
        if not mobj: raise ExtractorError()
        _url2 = ("/").join([self._SITE_URL, mobj[0]])
        res2 = cl.get(_url2, headers={'Referer': str(res.url)})
        if res2.status_code > 400: raise ExtractorError()
        mobj2 = re.findall(r"playlistUrl=\'/([^\']+)\'",res2.text.replace(" ",""))
        if not mobj2: raise ExtractorError()
        _url3 = ("/").join([self._SITE_URL, mobj2[0]])
        res3 = cl.get(_url3, headers={'Referer': str(res2.url)})
        if res3.status_code > 400: raise ExtractorError()
        data = res3.json()
        
        if not data or not data.get('sources'): raise ExtractorError()
        
        strid = self._match_id(url)
        _videoid = str(int(hashlib.sha256(strid.encode('utf-8')).hexdigest(),16) % 10**8)
        
        _title = self._search_regex((r'\"name_\": "(?P<title>[^\"]+)\"', r'<h1>(?P<title>[^\<]+)\<', r'\"og:title\" content=\"(?P<title>[^\"]+)\"'), res.text, "title", fatal=False, default="no_title", group="title")
        _title = _title.replace("&amp;", "&")
        _title = sanitize_filename(_title, restricted=True)
        
        _formats = [{
            'url': _el['file'],
            'height': int(_el['label']),
            'ext': _el['type'],
            'filesize': self._get_filesize(_el['file']),
            'format_id': f"http{_el['label']}"
            
        } for _el in data['sources']]
        
        
        self._sort_formats(_formats)

        return {
            "id": _videoid,
            "title": _title,
            "formats": _formats
        }

        
