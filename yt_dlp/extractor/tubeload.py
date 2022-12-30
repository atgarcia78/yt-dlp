import html
import re
from urllib.parse import unquote
import subprocess
import logging
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
    limiter_non,
    my_dec_on_exception,
)
from ..utils import (
    ExtractorError,
    get_domain,
    sanitize_filename,
    traverse_obj,
    try_get,
)


on_exception_vinfo = my_dec_on_exception((TimeoutError, ExtractorError), raise_on_giveup=False, max_tries=2, interval=0.1)

class BaseloadIE(SeleniumInfoExtractor):

    _LOCK = Lock()
    _IP_ORIG = None

    @on_exception_vinfo
    @dec_on_exception2
    def _get_video_info(self, url, **kwargs):        
        
        pre = f'[get_video_info][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'

        with limiter_0_1.ratelimit(self.IE_NAME, delay=True):
            try:
                return self.get_info_for_format(url, headers={'Range': 'bytes=0-', 'Referer': self._SITE_URL + "/", 'Origin': self._SITE_URL, 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'})
            except (HTTPStatusError, ConnectError) as e:
                self.logger.debug(f"{pre}: inner error sin raise - {repr(e)}")



    @dec_on_exception3
    @dec_on_exception2
    def _send_request(self, url, **kwargs):       

        headers = kwargs.get('headers', None)
        max_limit = kwargs.get('max_limit', None)
        pre = f'[send_req][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'
        
        with limiter_non.ratelimit(f'{self.IE_NAME}2', delay=True):
            
            self.logger.debug(f"{pre}: start") 
            
            try:
                if not max_limit:               
                    return self.send_http_request(url, headers=headers)
                else:
                    return self.stream_http_request(url, truncate='</script><style>', headers=headers)
            except (HTTPStatusError, ConnectError) as e:
                self.logger.warning(f"{pre}: error - {repr(e)}")


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
    
    def _getres0(self, _url):
        if (mainjs := self.get_mainjs(_url)) and (argsjs := self._get_args(mainjs)):            
            cmd0 = "node /Users/antoniotorres/Projects/common/logs/tubeload_deofus.js " + " ".join([str(el) for el in argsjs])
            res0 = subprocess.run(cmd0.split(' '), capture_output=True, encoding="utf-8").stdout.strip('\n')
            if res0: self.cache.store(self.IE_NAME, f'{self._key}res0', res0)
            return res0

    def _getinfofromwebpage(self, _url, webpage, max_limit, pre):
        _args = None
        title = None
        if not webpage:
            webpage = try_get(self._send_request(_url, max_limit=max_limit), lambda x: html.unescape(x) if isinstance(x, str) else html.unescape(x.text))
            if not webpage: 
                raise ExtractorError("error 404 no webpage")
            self.logger.debug(f'{pre} size webpage dl: {len(webpage)}')
            if '<title>404' in webpage:
                raise ExtractorError("error 404 no webpage")
        title = re.sub(r'(?i)((at )?%s$)' % get_domain(self._SITE_URL), '', self._html_extract_title(webpage).replace('.mp4','')).strip('[_,-, ]')
        _args = self._get_args(webpage)
        if not _args: 
            raise ExtractorError("error extracting video args")
        cmd1 = "node /Users/antoniotorres/Projects/common/logs/tubeload_deofus.js " + " ".join([str(el) for el in _args])
        return (subprocess.run(cmd1.split(' '), capture_output=True, encoding="utf-8").stdout.strip('\n'), title)
    
    def _get_entry(self, url, **kwargs):     

        
        check = kwargs.get('check')
        webpage = kwargs.get('webpage', None)
        max_limit = kwargs.get('max_limit', True)
        pre = f'[get_entry][{self._get_url_print(url)}]'
        if (msg:=kwargs.get('msg', None)):
            pre = f'{msg}{pre}'
        videoid = self._match_id(url)
        _url =  f"{self._SITE_URL}/e/{videoid}"

        try:

            res0 = self.cache.load(self.IE_NAME, f'{self._key}res0')
            if not res0:
                with ThreadPoolExecutor(thread_name_prefix="tload") as exe:
                    futures = {exe.submit(self._getinfofromwebpage, _url, webpage, max_limit, pre): 'infowebpage', exe.submit(self._getres0, _url): 'res0'}
        
                for fut in futures:
                    if 'infowebpage' in futures[fut]:
                        res1, title = fut.result()
                    else:
                        res0 = fut.result()
            
            else:
            
                res1, title = self._getinfofromwebpage(_url, webpage, max_limit, pre)

            if not res0 or not res1:
                raise ExtractorError(f"error in res0[{not res0}] or res1[{not res1}]")

            video_url = subprocess.run(['node', '/Users/antoniotorres/Projects/common/logs/tubeload_getvurl.js', res0, res1], capture_output=True, encoding="utf-8").stdout.strip('\n')

            _format = {
                'format_id': 'http-mp4',
                'url': unquote(video_url),               
                'http_headers': {'Referer': f'{self._SITE_URL}/', 'Origin': self._SITE_URL},
                'ext': 'mp4'
            }

            if check:
                _host = get_domain(video_url)
                with self.get_param('lock'):
                    if not (_sem:=traverse_obj(self.get_param('sem'), _host)): 
                        _sem = Lock()
                        self.get_param('sem').update({_host: _sem})                    
                with _sem:
                    _videoinfo = self._get_video_info(video_url, msg=pre)
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
            
        except Exception as e:
            self.logger.debug(f"{pre} error {repr(e)} - {str(e)}")
            raise


    def _real_initialize(self):        

        super()._real_initialize()
        if not self.get_param('proxy'):
            self._ip_orig = try_get(self._get_ip_origin(), lambda x: x if x else "")
            self._key = self._ip_orig
        else:
            self._key = try_get(self.get_param('proxy'), lambda x: traverse_obj(self.get_param('routing_table'), int(x.split(":")[-1])) if x else self._get_ip_origin())

        self.logger = logging.getLogger(self.IE_NAME)


    def _real_extract(self, url):
        
        self.report_extraction(url)

        try:                            

            # if not self.get_param('embed'): _check = True
            # else: _check = False
            _check=True

            return self._get_entry(url, check=_check)  
            
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