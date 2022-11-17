import html
import re


from ..utils import ExtractorError, sanitize_filename, try_get, get_domain, traverse_obj, url_basename, base_url
from .commonwebdriver import (
    dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_1, limiter_5, HTTPStatusError, ConnectError, Lock)

class JustTheGaysIE(SeleniumInfoExtractor):
    
    IE_NAME = 'justthegays'
    _VALID_URL = r'https?://(?:www\.)?justthegays\.com/video/[^/]+/?$'
    _SITE_URL = 'https://justthegays.com/'
    

    @dec_on_exception2
    @dec_on_exception3
    @limiter_1.ratelimit("justthegays", delay=True)
    def _get_video_info(self, url, **kwargs):
        
        headers = kwargs.get('headers', None)        

        self.logger_debug(f"[get_video_info] {url}")
        _headers = {'Range': 'bytes=0-', 'Referer': headers['Referer'],
                    'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
                    'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
        try:
            _host = get_domain(url)
            
            with self.get_param('lock'):
                if not (_sem:=traverse_obj(self.get_param('sem'), _host)): 
                    _sem = Lock()
                    self.get_param('sem').update({_host: _sem})
                
            with _sem:                 
                return self.get_info_for_format(url, headers=_headers)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
                 
       
        
    @dec_on_exception
    @dec_on_exception2
    @dec_on_exception3
    @limiter_1.ratelimit("justthegays2", delay=True)
    def _send_request(self, url, **kwargs):
        
        driver = kwargs.get('driver', None)

        if driver:
            self.logger_debug(f"[send_request] {url}")   
            driver.get(url)
        else:
            try:
                return self.send_http_request(url)
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"[send_requests] {self._get_url_print(url)}: error - {repr(e)}")


    def _get_entry(self, url, **kwargs):        
        
        webpage = try_get(self._send_request(url), lambda x: html.unescape(x.text) if x else None)
            
        if not webpage: raise ExtractorError("no webpage")
            
        _title = self._html_search_regex((r'>([^<]+)</h1>', r'(?s)<title\b[^>]*>([^<]+)</title>'), webpage, 'title',fatal=False) 
            
        iehtml5 = self._downloader._ies['HTML5MediaEmbed']        
        gen = iehtml5.extract_from_webpage(self._downloader, url, webpage)
        
        _entry = next(gen)        
        
        if not _entry: ExtractorError("no video formats")
        
        _entry = self._downloader.sanitize_info(_entry)
        
        self.logger_debug(_entry)

        _videoid = None
        
        if (_url:=traverse_obj(_entry, ('formats', 0, 'url'))):
            _videoid = try_get(re.findall(r'([a-zA-Z0-9]+)\.mp4', url_basename(_url)), lambda x: x[0])
        
        if not _videoid:
            _videoid = self._generic_id(url)
            
        
        _entry.update({'id': _videoid, 'webpage_url': url, 'extractor': self.IE_NAME, 
                       'extractor_key': self.ie_key()})
        
        if _title:        
            _entry.update({'title': sanitize_filename(_title, restricted=True)})
        else:
            _entry['title'] = None
              
        for f in _entry['formats']:
            
            _videoinfo = self._get_video_info(f['url'], headers=f['http_headers'])
            if _videoinfo:
                f.update({'url': _videoinfo['url'],'filesize': _videoinfo['filesize']})
                
   
        return _entry
        
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        try: 
            return self._get_entry(url)  
        except ExtractorError:
            raise
        except Exception as e:            
            self.to_screen(f"{repr(e)}")
            raise ExtractorError(repr(e))
            


    

    