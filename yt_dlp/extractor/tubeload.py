import html
import re
import sys
import traceback
from urllib.parse import unquote

import pyduktape2 as pyduk

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
                    if ((_stop:=self.get_param('stop')) and _stop.is_set()):
                        self.logger_debug(f"{pre} {self._get_url_print(url)}: stop")
                        raise StatusStop(f"{pre} {self._get_url_print(url)}")                    
                    return self.get_info_for_format(url, headers={'Range': 'bytes=0-', 'Referer': self._SITE_URL + "/", 'Origin': self._SITE_URL, 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'})
                
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"{pre} {self._get_url_print(url)}: error - {repr(e)}")


    @dec_on_exception3
    @dec_on_exception2
    def _send_request(self, url, **kwargs):       

        msg = kwargs.get('msg', None)
        headers = kwargs.get('headers', None)
        max_limit = kwargs.get('max_limit', None)
        
        with limiter_non.ratelimit(f'{self.IE_NAME}2', delay=True):
            if msg: pre = f'{msg}[send_req]'
            else: pre = '[send_req]'
            self.logger_debug(f"{pre} {self._get_url_print(url)}") 
            if ((_stop:=self.get_param('stop')) and _stop.is_set()):
                self.logger_debug(f"{pre} {self._get_url_print(url)}: stop")
                raise StatusStop(f"{pre} {self._get_url_print(url)}")


            try:
                if not max_limit:               
                    return self.send_http_request(url, headers=headers)
                else:
                    return self.stream_http_request(url, stopper='</script><style>', headers=headers)
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
        
    
    def _get_entry(self, url, **kwargs):     

        check_active = kwargs.get('check_active', False)
        msg = kwargs.get('msg', None)
        webpage = kwargs.get('webpage', None)
        max_limit = kwargs.get('max_limit', True)
        #max_limit = kwargs.get('max_limit', None)

        
        try:
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}{pre}'
            #self.to_screen(f"{pre} check[{check_active}]")
            _videoinfo = None            
            videoid = self._match_id(url)
            if not webpage:
                webpage = try_get(self._send_request(f"{self._SITE_URL}/e/{videoid}", max_limit=max_limit), lambda x: html.unescape(x) if isinstance(x, str) else html.unescape(x.text))
            if not webpage: 
                self.report_warning(f"{pre} no webpage")
                raise ExtractorError("error 404 no webpage")
            self.logger_debug(f'{pre} size webpage dl: {len(webpage)}')
            if '<title>404' in webpage:
                raise ExtractorError("error 404 no webpage")

            _args = self._get_args(webpage)
            if not _args: 
                self.report_warning(f"{pre} no args in webpagwe")
                raise ExtractorError("error extracting video args")
                      
            try:                
                video_url = self.init_ctx(f"{self._SITE_URL}/e/{videoid}", data=_args)                
            except BaseException as e:
                #error when something changes in network, dontknowwhy
                lines = traceback.format_exception(*sys.exc_info())
                self.report_warning(f"{pre} error videourl [1] {repr(e)}\n%no%{'!!'.join(lines)}")
                #video_url = None
                self._real_initialize()
                try:
                    video_url = self.init_ctx(f"{self._SITE_URL}/e/{videoid}", data=_args, force=True)
                except BaseException as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.report_warning(f"{pre} error videourl [2] {repr(e)}\n%no%{'!!'.join(lines)}")
                    raise ExtractorError("error 404 no video url")
                
                #if not video_url: raise ExtractorError("error no video url")

            title = re.sub(r'(?i)((at )?%s$)' % get_domain(self._SITE_URL), '', self._html_extract_title(webpage).replace('.mp4','')).strip('[_,-, ]')
                        
            _format = {
                'format_id': 'http-mp4',
                'url': unquote(video_url),               
                'http_headers': {'Referer': f'{self._SITE_URL}/', 'Origin': self._SITE_URL},
                'ext': 'mp4'
            }

            if check_active:
                _videoinfo = self._get_video_info(video_url, msg=pre)
                if not _videoinfo: raise ExtractorError("error 404: no video info")
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
            raise


    def _real_initialize(self):        

        super()._real_initialize()
        
    
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
            
    
    def init_ctx(self, url, **kwargs):        

         
        try:
        
            force = kwargs.get('force', False)
            _args = kwargs.get('data', [])

            jscode_deofus = 'function deofus(h,u,n,t,e,r){var _data=["","split","0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ+/","slice","indexOf","","",".","pow","reduce","reverse","0"];function _aux(d,e,f){var g=_data[2][_data[1]](_data[0]);var h=g[_data[3]](0,e);var i=g[_data[3]](0,f);var j=d[_data[1]](_data[0])[_data[10]]()[_data[9]](function(a,b,c){if(h[_data[4]](b)!==-1)return a+=h[_data[4]](b)*(Math[_data[8]](e,c))},0);var k=_data[0];while(j>0){k=i[j%f]+k;j=(j-(j%f))/f}return k||_data[11]};function _aux2(h,u,n,t,e,r){r="";for(var i=0,len=h.length;i<len;i++){var s="";while(h[i]!==n[e]){s+=h[i];i++}for(var j=0;j<n.length;j++)s=s.replace(new RegExp(n[j],"g"),j);r+=String.fromCharCode(_aux(s,e,10)-t)};return decodeURIComponent(escape(r))};return _aux2(h,u,n,t,e,r)};'                
            jscode_atob = 'function atob(str){return (new TextDecoder().decode(Duktape.dec("base64", str)))}'

            with BaseloadIE._LOCK:
                if not self.get_param('proxy'):
                    if not BaseloadIE._IP_ORIG:
                        BaseloadIE._IP_ORIG = try_get(self._get_ip_origin(), lambda x: x if x else "")
                    _key = BaseloadIE._IP_ORIG
                else:
                    _key = try_get(self.get_param('proxy'), lambda x: traverse_obj(self.get_param('routing_table'), int(x.split(":")[-1])) if x else self._get_ip_origin())
                
                if not force:
                    jscode_final = self.cache.load(self.IE_NAME, f'{_key}jscode')
                else: jscode_final = None            
                
                _duk_ctx = pyduk.DuktapeContext()
                
                if not jscode_final:
                    if not force:
                        mainjs = self.cache.load(self.IE_NAME, f'{_key}mainjs')
                    else: mainjs = None
                    if not mainjs:
                        mainjs = self.get_mainjs(url)                
                        if mainjs: 
                            self.cache.store(self.IE_NAME, f'{_key}mainjs', mainjs)
                        else: raise ExtractorError("couldnt get mainjs")        
                    
                    _duk_ctx.eval_js(jscode_deofus)
                    _duk_ctx.eval_js(jscode_atob)
                    _code = _duk_ctx.get_global('deofus')(*self._get_args(mainjs))
                    _jscode_1, _var = try_get(re.findall(r'(var res = ([^\.]+)\.replace.*); var decode', _code), lambda x: x[0])
                    
                    jscode_final = f'function getvurl(h,u,n,t,e,r){{var res1 = deofus(h,u,n,t,e,r); var {_var} = RegExp("{_var}=([^;]+);").exec(res1)[1].slice(1,-1); {_jscode_1};return atob(res2)}};'
                    
                    #version full for cache
                    _jscode_cache = f'function getvurl(h,u,n,t,e,r){{{jscode_deofus}var res1 = deofus(h,u,n,t,e,r); var {_var} = RegExp("{_var}=([^;]+);").exec(res1)[1].slice(1,-1); {_jscode_1};{jscode_atob};return atob(res2)}};'
                    self.cache.store(self.IE_NAME, f'{_key}jscode', _jscode_cache)

            _duk_ctx.eval_js(jscode_final)
            get_videourl = _duk_ctx.get_global('getvurl')
            return get_videourl(*_args)
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            pre = f'[init_ctx][{self._get_url_print(url)}]'
            self.report_warning(f"{pre}%no% {repr(e)}\n{'!!'.join(lines)}")
            raise

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