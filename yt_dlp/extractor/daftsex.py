# coding: utf-8
from __future__ import unicode_literals

import re

from .common import InfoExtractor
from ..utils import (
    ExtractorError, int_or_none, 
    std_headers,
    sanitize_filename
)


import httpx
import time
from urllib.parse import unquote
import logging
import base64
import hashlib
import json
import demjson

logger = logging.getLogger("daftsex")


class DaftSexIE(InfoExtractor):
    IE_NAME = 'daftsex'
    _VALID_URL = r'https?://(www.)?daftsex\.com/watch/(?P<id>[a-zA-Z0-9_-]+)(?:$|/)'
    

    def _get_info(self, url, client):
        
        count = 0
        try:
            
            _res = None
            while (count<3):
                
                try:
                    
                    res = client.head(url)
                    if res.status_code > 400:
                        time.sleep(1)
                        count += 1
                    else: 
                        _size = int_or_none(res.headers.get('content-length'))
                        _url = unquote(str(res.url))
                        if _size and _url:
                            _res = {'url': _url, 'filesize': _size}                         
                            break
                        else: count += 1
            
                except Exception as e:
                    count += 1
        except Exception as e:
            pass
                
        return _res


    
    def _real_extract(self, url):

        
        
        try:
        
            
            client = httpx.Client(headers=std_headers, timeout=httpx.Timeout(10, connect=30), limits=httpx.Limits(max_keepalive_connections=None, max_connections=None)) 
            
            
            self.report_extraction(url)
            
            webpage = client.get(url).text
            mobj = re.findall(r'(hash|color):\"([^\"]+)\"',webpage.replace(" ",""))
            if not mobj: raise ExtractorError("no info about embed url")
            
            _data = dict(mobj)
            
            #self.to_screen(_data)
            
            mobj = re.findall(r'og:title\" +content=\"([^\"]+)\"', webpage)
            if mobj:
                _title = sanitize_filename(mobj[0],restricted=True)
            else:
                _title = "video"
            
            _url = f"https://daxab.com/player/{_data['hash']}?color={_data['color']}"
            
            webpage2 = client.get(_url,headers={'referer': 'https://daftsex.com/'}).text       
            #mobj = re.findall(r'(id|server|c_key|access_token|credentials):\"([^\"]+)"',webpage2.replace(" ",""))
            mobj = re.findall(r'window.globParams = ({[^\;]+);',webpage2)
            if not mobj: raise ExtractorError("no video info")
            #_data2 = dict(mobj)
            _data2 = demjson.decode(mobj[0])
            #self.to_screen(_data2)
            
            # mobj = re.findall(r'(cdn_files):(\{[^\}]+\})',webpage2.replace(" ",""))
            # if mobj:
            #     _data4 = {mobj[0][0]: json.loads(mobj[0][1])}
            
            _host = base64.b64decode(_data2['server'][::-1]).decode('utf-8')
            _videoid = str(int(hashlib.sha256(_data2['video']['id'].encode('utf-8')).hexdigest(),16) % 10**8)
            _formats = []
            if _data2['video'].get('credentials'):
                _url2 = f"https://{_host}/method/video.get/{_data2['video']['id']}?token={_data2['video']['access_token']}&videos={_data2['video']['id']}&ckey={_data2['c_key']}&credentials={_data2['video']['credentials']}"
                _data3 = client.get(_url2, headers={'referer':'https://dabax.com/', 'origin':'https://dabax.com'}).json()
                
                if not _data3: raise ExtractorError("no info video json")
                
                #self.to_screen(_data3)
                
                
                try:
                    _info_formats = _data3.get('response').get('items')[0].get('files')
                
                except Exception as e:
                    raise ExtractorError(e)
                
                if not _info_formats: raise ExtractorError("no info video")
                
                #self.to_screen(_info_formats)
            
               
                
                for _fid, _furl in _info_formats.items():
                    _info = self._get_info(_furl.replace("https://",f"https://{_host}/"), client)
                    _formats.append({
                        'format_id': _fid,
                        'ext' : 'mp4',
                        'url': _info.get('url'),
                        'filesize': _info.get('filesize')
                        
                    })
            else:
                _info_formats = _data2['video'].get('cdn_files')
                if not _info_formats: raise ExtractorError("no info video")
                
                
                for _fid, _furl in _info_formats.items():
                    _info = self._get_info(f"https://{_host}/videos/{_data2['video']['id'].split('_')[0]}/{_data2['video']['id'].split('_')[1]}/{_furl.replace('.','?extra=')}", client)
                    _formats.append({
                        'format_id': _fid,
                        'ext' : 'mp4',
                        'url': _info.get('url'),
                        'filesize': _info.get('filesize')
                        
                    })
                
            
            if not _formats: raise ExtractorError("no formats")
            self._sort_formats(_formats)
        except Exception as e:
            self.to_screen(e)
            raise
            
        finally:
            client.close()

        return {
            'id': _videoid,
            'title': _title,
            'formats': _formats,
            'ext': 'mp4'
        }



