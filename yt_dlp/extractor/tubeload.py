import html
import re
from urllib.parse import unquote
import subprocess
from concurrent.futures import ThreadPoolExecutor


from .commonwebdriver import (
    ConnectError,
    HTTPStatusError,
    Lock,
    SeleniumInfoExtractor,
    StatusStop,
    dec_on_exception,
    dec_on_exception2,
    dec_on_exception3,
    limiter_0_1,
    limiter_0_01,
    limiter_0_5,
    limiter_non,
    limiter_1
)
from ..utils import (
    ExtractorError,
    get_domain,
    sanitize_filename,
    traverse_obj,
    try_get,
)


class BaseloadIE(SeleniumInfoExtractor):

    _LOCK = Lock()
    _IP_ORIG = None

    
    @dec_on_exception3  
    @dec_on_exception2
    def _get_video_info(self, url, msg=None):        
        
        with limiter_0_1.ratelimit(self.IE_NAME, delay=True):
            try:
                if msg: pre = f'{msg}[get_video_info]'
                else: pre = '[get_video_info]'
                self.logger_debug(f"{pre} {self._get_url_print(url)}")
                _host = get_domain(url)
                
                with self.get_param('lock'):
                    if not (_sem:=traverse_obj(self.get_param('sem'), _host)): 
                        _sem = Lock()
                        self.get_param('sem').update({_host: _sem})                    
                            
                with _sem:

                    self.check_stop()

                    return self.get_info_for_format(url, headers={'Range': 'bytes=0-', 'Referer': self._SITE_URL + "/", 'Origin': self._SITE_URL, 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'})
                
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"{pre} {self._get_url_print(url)}: error - {repr(e)}")


    @dec_on_exception3
    @dec_on_exception2
    def _send_request(self, url, **kwargs):       

        msg = kwargs.get('msg', None)
        headers = kwargs.get('headers', None)
        max_limit = kwargs.get('max_limit', None)
        
        with limiter_1.ratelimit(f'{self.IE_NAME}2', delay=True):
            if msg: pre = f'{msg}[send_req]'
            else: pre = '[send_req]'
            self.logger_debug(f"{pre} {self._get_url_print(url)}") 
            
            self.check_stop()

            try:
                if not max_limit:               
                    return self.send_http_request(url, headers=headers)
                else:
                    return self.stream_http_request(url, truncate='</script><style>', headers=headers)
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"{pre} {self._get_url_print(url)}: error - {repr(e)}")


    def _get_args(self, webpage, _all=False):
        
        def getter(x):
            if not x: return            
            _res = []                        
            for el in x:            
                _args = el.split(',')
                if len(_args) != 6: return
                for i in range(len(_args)):
                    if _args[i].isdecimal(): _args[i] = int(_args[i])
                    else: _args[i] = _args[i].strip('"')
                if not _all:
                    return _args
                else:
                    _res.append(_args)
            return _res
            
        args = try_get(re.findall(r'var .+eval\(.+decodeURIComponent\(escape\(r\)\)\}\(([^\)]+)\)', webpage), lambda x: getter(x))       
        return args
        
    
    def get_mainjs(self, url):
        _headers_mainjs = {    
            'Referer': url,
            'Sec-Fetch-Dest': 'script',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'same-origin',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
        }
        
        return(try_get(self._send_request(self._MAINJS, headers=_headers_mainjs), lambda x: x.text))
    
    def _get_entry(self, url, **kwargs):     

        
        check_active = kwargs.get('check_active', False)
        self.webpage = kwargs.get('webpage', None)
        self.max_limit = kwargs.get('max_limit', True)
        self.pre = f'[get_entry][{self._get_url_print(url)}]'
        if (msg:=kwargs.get('msg', None)):
            self.pre = f'{msg}{self.pre}'
        videoid = self._match_id(url)
        self._url =  f"{self._SITE_URL}/e/{videoid}"
        
        def _getres0():
            if (mainjs := self.get_mainjs(self._url)) and (argsjs := self._get_args(mainjs)):            
                cmd0 = "node /Users/antoniotorres/Projects/common/logs/tubeload_deofus.js " + " ".join([str(el) for el in argsjs])
                res0 = subprocess.run(cmd0.split(' '), capture_output=True, encoding="utf-8").stdout.strip('\n')
                if res0: self.cache.store(self.IE_NAME, f'{self._key}res0', res0)
                return res0

        def _getinfofromwebpage():
            _args = None
            title = None
            if not self.webpage:
                self.webpage = try_get(self._send_request(self._url, max_limit=self.max_limit), lambda x: html.unescape(x) if isinstance(x, str) else html.unescape(x.text))
                if not self.webpage: 
                    #self.report_warning(f"{self.pre} no webpage")
                    raise ExtractorError("error 404 no webpage")
                self.logger_debug(f'{self.pre} size webpage dl: {len(self.webpage)}')
                if '<title>404' in self.webpage:
                    raise ExtractorError("error 404 no webpage")
            title = re.sub(r'(?i)((at )?%s$)' % get_domain(self._SITE_URL), '', self._html_extract_title(self.webpage).replace('.mp4','')).strip('[_,-, ]')
            _args = self._get_args(self.webpage)
            if not _args: 
                #self.report_warning("no args in webpage")
                raise ExtractorError("error extracting video args")
            cmd1 = "node /Users/antoniotorres/Projects/common/logs/tubeload_deofus.js " + " ".join([str(el) for el in _args])
            return (subprocess.run(cmd1.split(' '), capture_output=True, encoding="utf-8").stdout.strip('\n'), title)

        try:
            

            res0 = self.cache.load(self.IE_NAME, f'{self._key}res0')
            if not res0:
                with ThreadPoolExecutor(thread_name_prefix="tload") as exe:
                    futures = {'infowebpage':exe.submit(_getinfofromwebpage), 'res0': exe.submit(_getres0)}
        
                res1, title = futures['infowebpage'].result()
                res0 = futures['res0'].result()
            
            else:
            
                res1, title = _getinfofromwebpage()

            if not res0 or not res1:
                raise ExtractorError(f"error in res0[{not res0}] or res1[{not res1}]")

            video_url = subprocess.run(['node', '/Users/antoniotorres/Projects/common/logs/tubeload_getvurl.js', res0, res1], capture_output=True, encoding="utf-8").stdout.strip('\n')

            _format = {
                'format_id': 'http-mp4',
                'url': unquote(video_url),               
                'http_headers': {'Referer': f'{self._SITE_URL}/', 'Origin': self._SITE_URL},
                'ext': 'mp4'
            }

            if check_active:
                _videoinfo = self._get_video_info(video_url, msg=self.pre)
                if not _videoinfo: raise ExtractorError(f"error 404: no video info")
                else:
                    _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize'], 'accept_ranges': _videoinfo['accept_ranges']})

            _entry_video = {
                'id' : videoid,
                'title' : sanitize_filename(title, restricted=True),
                'formats' : [_format],
                'extractor_key' : self.ie_key(),
                'extractor': self.IE_NAME,
                'ext': 'mp4',
                'webpage_url': url
            } 
            
            return _entry_video
            
        except Exception:
            self.report_warning(f"{self.pre} error {repr(e)} - {str(e)}")
            raise


    def _real_initialize(self):        

        super()._real_initialize()
        if not self.get_param('proxy'):
            self._ip_orig = try_get(self._get_ip_origin(), lambda x: x if x else "")
            self._key = self._ip_orig
        else:
            self._key = try_get(self.get_param('proxy'), lambda x: traverse_obj(self.get_param('routing_table'), int(x.split(":")[-1])) if x else self._get_ip_origin())


    def _real_extract(self, url):
        
        self.report_extraction(url)

        try:                            

            if not self.get_param('embed'): _check_active = True
            else: _check_active = False

            return self._get_entry(url, check_active=_check_active)  
            
        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))
        

class TubeloadIE(BaseloadIE):
    
    IE_NAME = 'tubeload'    
    _SITE_URL = "https://tubeload.co"
    _VALID_URL = r'https?://(?:www\.)?tubeload.co/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?tubeload\.co/e/.+?)\1']
    _MAINJS = f'https://tubeload.co/assets/js/main.min.js'
    _DOMAIN = 'tubeload.co'


class RedloadIE(BaseloadIE):
    
    _SITE_URL = "https://redload.co"    
    IE_NAME = 'redload'
    _VALID_URL = r'https?://(?:www\.)?redload.co/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'    
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?redload\.co/e/.+?)\1']
    _MAINJS = f'https://redload.co/assets/js/main.min.js' 
    _DOMAIN = 'redload.co'

class HighloadIE(BaseloadIE):

    _SITE_URL = "https://highload.to"    
    IE_NAME = 'highload'
    _VALID_URL = r'https?://(?:www\.)?highload.to/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?highload\.to/e/.+?)\1']
    _MAINJS = 'https://highload.to/assets/js/master.js'
    _DOMAIN = 'highload.co'

class EmbedoIE(BaseloadIE):
    
    _SITE_URL = "https://embedo.co"
    IE_NAME = 'embedo'
    _VALID_URL = r'https?://(?:www\.)?embedo.co/e/(?P<id>[^\/$]+)(?:\/|$)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?embedo\.co/e/.+?)\1']
    _MAINJS = 'https://embedo.co/assets/js/master.js'
    _DOMAIN = 'embedo.co'