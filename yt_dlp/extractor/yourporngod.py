import html
import re

from ..utils import ExtractorError, sanitize_filename, try_get, js_to_json, parse_resolution
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_1, HTTPStatusError

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
        except HTTPStatusError as e:
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
            except HTTPStatusError as e:
                self.report_warning(f"[send_requests] {self._get_url_print(url)}: error - {repr(e)}")


    def _get_entry(self, url, **kwargs):
        
        if self.IE_NAME == "pornhat":
            _url = url
            videoid = None

        elif self.IE_NAME == 'homoxxx':
            
            videoid = self._match_id(url)
            _url = url 
            
        else:
            
            videoid = self._match_id(url)
            _url = f"{self._SITE_URL}/embed/{videoid}"
            
        
        webpage = try_get(self._send_request(_url), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)) if x else None)
        flashvars =  self._parse_json(
                        self._search_regex(
                            r'var\s+flashvars\s*=\s*({.+?});', webpage, 'flashvars', default='{}'), videoid, transform_source=js_to_json)
        
        title = re.sub(r'(?i)(^(hd_video_|sd_video_|video_))|(%s$)|(%s\.mp4)|(.mp4$)' % (self.IE_NAME, self.IE_NAME), '', sanitize_filename(self._html_extract_title(webpage), restricted=True)).strip('[_,-, ]')
        
        if not videoid:
            videoid = flashvars.get('video_id')
        self.logger_debug(flashvars)
        
        url_keys = list(filter(re.compile(r'video_url|video_alt_url\d*').fullmatch, flashvars.keys()))
        
        iegen = self._get_extractor('Generic')
        
        _headers = {'Referer': _url}
        
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
            
            formats.append(_format)
            if not formats[-1].get('height'):
                formats[-1]['quality'] = 1
                
        self._sort_formats(formats)

                        
        entry = {
            'id' : videoid,
            'title' : sanitize_filename(title, restricted=True),
            'formats' : formats,
            'ext': 'mp4',
            'extractor': self.IE_NAME,
            'extractor_key': self.ie_key(),
            'webpage_url': _url
            }            
        return entry
        
    
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
    
    
    
# class YourPornGodPlayListIE(SeleniumInfoExtractor):
    
#     IE_NAME = 'yourporngod:playlist'
#     _VALID_URL = r'https?://(?:www\.)?yourporngod\.com/(?:((?P<type1>playlists)/(?P<id>\d+)/(?P<title>[^\/\$]+))|((?P<type3>models)/(?P<model>[^\/\$]+))|((?P<type2>categories)/(?P<categorie>[^\/\$]+)))'
#     _SEARCH_URL = {"playlists" : "?mode=async&function=get_block&block_id=playlist_view_playlist_view&sort_by=added2fav_date&from=",
#                    "models" : "?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed&from=",
#                    "categories": "?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed&from="}
#     _REGEX_ENTRIES = {"playlists": r'data-playlist-item\=[\"\']([^\'\"]+)[\'\"]',
#                       "models": r'item  [\"\']><a href=["\']([^\'\"]+)[\'\"]',
#                       "categories": r'item  [\"\']><a href=["\']([^\'\"]+)[\'\"]'}
    
    
#     @dec_on_exception
#     @limiter_1.ratelimit("yourporngod", delay=True)
#     def _send_request(self, url):
#         self.logger_debug(f"[send_request] {url}")   
#         res = YourPornGodPlayListIE._CLIENT.get(url)
#         res.raise_for_status()
#         return res

#     def _get_entries(self, url, _type):
#         res = self._send_request(url)
#         if res:
#             webpage = re.sub('[\t\n]', '', html.unescape(res.text))
#             entries = re.findall(self._REGEX_ENTRIES[_type],webpage)
#             return entries
    
#     def _real_initialize(self):
#         super()._real_initialize()
    
#     def _real_extract(self, url):
        
#         self.report_extraction(url)
#         #playlist_id = self._match_id(url)
#         _type1, _type2, _type3, _id, _title, _model, _categorie = re.search(self._VALID_URL, url).group('type1','type2','type3','id','title','model','categorie')
        
#         _type = _type1 or _type2 or _type3
                      
#         self.report_extraction(url)
        
#         res = self._send_request(url)        
#         if not res: raise ExtractorError("couldnt download webpage")
#         webpage = re.sub('[\t\n]', '', html.unescape(res.text))
        
#         mobj = re.findall(r"<title>([^<]+)<", webpage)
#         title = mobj[0] if mobj else _title or _model or _categorie
        
#         playlist_id = _id or _model or _categorie

#         mobj = re.findall(r'\:(\d+)[\"\']>Last', webpage)        
#         last_page = int(mobj[0]) if mobj else 1
        
#         base_url = url + self._SEARCH_URL[_type]        
        
#         with ThreadPoolExecutor(max_workers=16) as ex:        
            
#             futures = [ex.submit(self._get_entries, base_url + str(i), _type) for i in range(1,last_page+1)]
                
#         res = []
        
#         for fut in futures:
#             try:
#                 res += fut.result()
#             except Exception as e:
#                 pass
            
#         entries = [self.url_result(_url, ie="YourPornGod") for _url in res]
        
#         return {
#             '_type': 'playlist',
#             'id': playlist_id,
#             'title': sanitize_filename(title,restricted=True),
#             'entries': entries,
            
#         }
 
    

    
