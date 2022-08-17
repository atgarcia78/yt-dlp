import sys
import traceback
import re
import html


from ..utils import ExtractorError, sanitize_filename, try_get, int_or_none
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_1, By, HTTPStatusError, ConnectError

class GayStreamBase(SeleniumInfoExtractor):

    @dec_on_exception
    @dec_on_exception2
    @dec_on_exception3
    @limiter_1.ratelimit("gaystream", delay=True)
    def _send_multi_request(self, url, **kwargs):
        
        _driver = kwargs.get('driver', None)
        _hdrs = kwargs.get('headers', None)
        _type = kwargs.get('_type', "GET")
        _data = kwargs.get('data', None)
        
        if _driver:
            _driver.execute_script("window.stop();")
            _driver.get(url)
        else:
            try:
                                
                return self.send_http_request(url, _type=_type, headers=_hdrs, data=_data)
        
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
        
    @dec_on_exception3 
    @dec_on_exception2
    @limiter_1.ratelimit("gaystream", delay=True)
    def _get_video_info(self, url, **kwargs):        
    
        self.logger_debug(f"[get_video_info] {url}")
        _headers = {'Range': 'bytes=0-', 'Referer': self._SITE_URL,
                        'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
                        'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
        try:
            return self.get_info_for_format(url, headers=_headers)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
        
        
    def _real_initialize(self):
        super()._real_initialize()



class GayStreamPWIE(GayStreamBase):
       
    _SITE_URL = 'https://gaystream.pw/'
    _VALID_URL = r'https?://(?:www\.)?gaystream.pw/video/(?P<id>\d+)/?([^$]+)?$'
    
    def _get_entry(self, url, **kwargs):

        try:            
            
            webpage = try_get(self._send_multi_request(url), lambda x: html.unescape(x.text) if x else None)
            if not webpage: raise ExtractorError("no video webpage")
            _url_embed = try_get(re.search(r'onclick=[\'\"]document\.getElementById\([\"\']ifr[\"\']\)\.src=[\"\'](?P<eurl>[^\"\']+)[\"\']', webpage), lambda x: x.group('eurl'))
            if not _url_embed: raise ExtractorError("no embed url")
            ie_embed = self._downloader.get_info_extractor('GayStreamEmbed')
            ie_embed._real_initialize()                
            _entry_video = ie_embed._get_entry(_url_embed)
            if not _entry_video:
                raise ExtractorError("no entry video")
            return _entry_video
        except ExtractorError as e:
            raise
        except Exception as e:               
                
            raise ExtractorError(repr(e))
    
    def _real_initialize(self):

        super()._real_initialize()        

                
    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        
        try: 
            _url = url.replace('//www.', '//')
            return self._get_entry(_url)  
            
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        


class GayStreamEmbedIE(GayStreamBase):
    
    _INSTANCES_RE = r'(?:watchgayporn.online|streamxxx.online|feurl.com)'
    
    _VALID_URL = r'https?://(www\.)?(?P<host>%s)/v/(?P<id>.+)' % _INSTANCES_RE
    
    def _get_entry(self, url, **kwargs):
    
        try:

            _host = try_get(re.search(self._VALID_URL, url), lambda x: x.group('host'))
            self._SITE_URL = f"https://{_host}/"

            _headers_post = {
                'Referer': url,
                'Origin': self._SITE_URL.strip('/'),
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest'
            }
            
            _data = {
                'r': '',
                'd': _host
            }
            
            _videoid = self._match_id(url)
            
            _post_url = f"{self._SITE_URL}api/source/{_videoid}"
            
            info = try_get(self._send_multi_request(_post_url, _type="POST", headers=_headers_post, data=_data), lambda x: x.json() if x else None)
            _formats = []
            if info:
                for vid in info.get('data'):
                    _url = vid.get('file')
                    _info_video = self._get_video_info(_url)
                    if not _info_video: 
                        self.report_warning(f"[{_url}] no video info")
                    else:
                        _formats.append({
                                'format_id': vid.get('label'),
                                'url': _info_video.get('url'),
                                'resolution' : vid.get('label'),
                                'height': int_or_none(vid.get('label')[:-1]),                                
                                'filesize': _info_video.get('filesize'),
                                'ext': 'mp4',
                                'http_headers': {'Referer': self._SITE_URL}
                            })
                        
            if _formats:
                self._sort_formats(_formats)
                
                webpage = try_get(self._send_multi_request(url), lambda x: x.text if x else None)
                _title = try_get(self._html_extract_title(webpage), lambda x: x.replace('Video ', '').replace('.mp4', '').replace('.', '_').replace(' ', '_'))
                
                _entry_video = {
                    'id' : _videoid,
                    'title' : sanitize_filename(_title, restricted=True).replace('___','_').replace('__', '_'),
                    'formats' : _formats,
                    'extractor': self.IE_NAME,
                    'extractor_key': self.ie_key(),
                    'ext': 'mp4',
                    'webpage_url': url
                }
                
                return _entry_video
            else: raise ExtractorError("couldn find video formats")

        except ExtractorError as e:
            raise
        except Exception as e:               
            
            raise ExtractorError(repr(e))
        
    def _real_initialize(self):

        super()._real_initialize()        

                
    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        
        try: 
            _url = url.replace('//www.', '//')
            return self._get_entry(_url)  
            
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
                   

    
    

                    
