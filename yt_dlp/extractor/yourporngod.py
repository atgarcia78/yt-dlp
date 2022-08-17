import html
import re

from ..utils import ExtractorError, sanitize_filename, try_get, js_to_json, parse_resolution
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_1, HTTPStatusError, ConnectError

class BaseKVSIE(SeleniumInfoExtractor):
    

    @dec_on_exception2
    @dec_on_exception3
    @limiter_1.ratelimit("basekvs", delay=True)
    def _get_video_info(self, url, **kwargs):
        
        headers = kwargs.get('headers', None)        

        self.logger_debug(f"[get_video_info] {url}")
        _headers = {'Range': 'bytes=0-', 'Referer': headers['Referer'],
                    'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
                    'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
        try:
            return self.get_info_for_format(url, headers=_headers)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
                
       
        
    @dec_on_exception
    @dec_on_exception2
    @dec_on_exception3
    @limiter_1.ratelimit("basekvs", delay=True)
    def _send_request(self, url, **kwargs):
        
        driver = kwargs.get('driver', None)

        if driver:
            self.logger_debug(f"[send_request] {url}")   
            driver.get(url)
        else:
            try:
                return self.send_http_request(url)
            except (HTTPStatusError, ConnectError) as e:
                self.logger_debug(f"[send_requests] {self._get_url_print(url)}: error - {repr(e)}")


    def _get_entry(self, url, **kwargs):
        
        if self.IE_NAME == "pornhat":            
            videoid = None
            
        else:            
            videoid = self._match_id(url)
            
        if self.IE_NAME == "homoxxx":
            url = url.replace('/embed/', '/videos/')
            
        webpage = try_get(self._send_request(url), lambda x: html.unescape(x.text) if x else None)
        
        display_id = self._search_regex(
                    r'(?:<link href="https?://.+/(.+?)/?" rel="canonical"\s*/?>'
                    r'|<link rel="canonical" href="https?://.+/(.+?)/?"\s*>)',
                    webpage, 'display_id', fatal=False
                )
        
        webpage = re.sub(r'[\t\n]', '', webpage)
        
        flashvars =  self._parse_json(
                        self._search_regex(
                            r'var\s+flashvars\s*=\s*({.+?});', webpage, 'flashvars', default='{}'), videoid, transform_source=js_to_json)
        
        self.logger_debug(flashvars)
        
        _title = self._html_search_regex(r'<h1>([^<]+)</h1>', webpage, 'title',fatal=False) or self._html_extract_title(webpage)
        title = re.sub(r'(?i)(^(hd video|sd video|video))\s*:?\s*|((?:\s*-\s*|\s*at\s*)%s(\..+)?$)|(.mp4$)|(\s*[/|]\s*embed player)' % (self.IE_NAME), '', _title).strip('[,-_ ').lower()

        if not videoid:
            videoid = flashvars.get('video_id')        
        
        
        thumbnail = flashvars['preview_url']
        if thumbnail.startswith('//'):
            protocol, _, _ = url.partition('/')
            thumbnail = protocol + thumbnail
        
        url_keys = list(filter(re.compile(r'video_url|video_alt_url\d*').fullmatch, flashvars.keys()))
        
        iegen = self._get_extractor('Generic')
        
        _headers = {'Referer': url}
        
        formats = []
        for key in url_keys:
            if '/get_file/' not in flashvars[key]:
                continue
            format_id = flashvars.get(f'{key}_text', key)
            _format = {
                'url': (_videourl:=iegen._kvs_getrealurl(flashvars[key], flashvars['license_code'])),
                'format_id': format_id,
                'http_headers': _headers,
                'ext': 'mp4',
                 
                **(parse_resolution(format_id) or parse_resolution(flashvars[key]))
            }
            
            _videoinfo = self._get_video_info(_videourl, headers=_headers)
            if _videoinfo:
                _format.update({'url': _videoinfo['url'],'filesize': _videoinfo['filesize'] })
                if not _format.get('height'): _format['quality'] = 1
                                
                formats.append(_format)
          
        if not formats: raise ExtractorError('no formats')
        
        self._sort_formats(formats)
                        
        entry = {
            'id' : videoid,
            'display_id' : display_id,
            'title' : sanitize_filename(title, restricted=True),
            'formats' : formats,
            'ext': 'mp4',
            'thumbnail': thumbnail,
            'extractor': self.IE_NAME,
            'extractor_key': self.ie_key(),
            'webpage_url': url}            
        
        return entry
        
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
        
        self.report_extraction(url)
        
        try: 
            return self._get_entry(url)  
        except ExtractorError as e:
            raise
        except Exception as e:            
            self.report_warning(f"{repr(e)}")
            raise ExtractorError(repr(e))
            

class YourPornGodIE(BaseKVSIE):
    
    IE_NAME = 'yourporngod'
    _VALID_URL = r'https?://(?:www\.)?yourporngod\.com/(?:embed|videos)/(?P<id>\d+)'
    _SITE_URL = 'https://yourporngod.com'

class OnlyGayVideoIE(BaseKVSIE):
    IE_NAME = 'onlygayvideo'
    _VALID_URL = r'https?://(?:www\.)?onlygayvideo\.com/(?:embed|videos)/(?P<id>\d+)'
    _SITE_URL = 'https://onlygayvideo.com'
    
class EbembedIE(BaseKVSIE):
    IE_NAME = 'ebembed'
    _VALID_URL = r'https?://(www\.)?ebembed\.com/(?:videos|embed)/(?P<id>\d+)'
    _SITE_URL = 'https://ebembed.com'
    
class Gay0DayIE(BaseKVSIE):
    
    IE_NAME = 'gay0day'
    _VALID_URL = r'https?://(www\.)?gay0day\.com/(.+/)?(?:videos|embed)/(?P<id>\d+)'
    _SITE_URL = 'https://gay0day.com'
    
class PornHatIE(BaseKVSIE):
    
    IE_NAME = 'pornhat'
    _VALID_URL = r'https?://(www\.)?pornhat\.com/(?:video|embed)/.+'
    _SITE_URL = 'https://pornhat.com'
    
class HomoXXXIE(BaseKVSIE):
    
    IE_NAME = 'homoxxx'
    _VALID_URL = r'https?://(www\.)?homo\.xxx/(?:videos|embed)/(?P<id>\d+)'
    _SITE_URL = 'https://homo.xxx'
    
class ThisVidIE(BaseKVSIE):
    
    IE_NAME = 'thisvid'
    _VALID_URL = r'https?://(?:[^\.]+\.)?thisvid\.com/(?:(embed/(?P<id>\d+))|(videos/.*))'
    _SITE_URL = 'https://thisvid.com/'
    _EMBED_REGEX = [r'<iframe[^>]+?src=(["\'])(?P<url>(?:https?:)?//(?:[^\.]+\.)?thisvid\.com/embed/(?P<id>\d+))\1']
    
    
