import sys
import traceback
from urllib.parse import unquote
import re
import html
import pyduktape3 as pyduk


from ..utils import ExtractorError, sanitize_filename, traverse_obj, try_get, get_domain
from .commonwebdriver import (
    dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, 
    limiter_0_5, limiter_0_1, HTTPStatusError, ConnectError, ConnectError, Lock)


class BaseloadIE(SeleniumInfoExtractor):

    @dec_on_exception
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
                    return self.get_info_for_format(url, headers={'Range': 'bytes=0-', 'Referer': self._SITE_URL + "/", 'Origin': self._SITE_URL, 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'})
                
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"{pre} {self._get_url_print(url)}: error - {repr(e)}")

            
    @dec_on_exception
    @dec_on_exception3
    @dec_on_exception2
    def _send_request(self, url, **kwargs):       
        
        driver = kwargs.get('driver', None)
        msg = kwargs.get('msg', None)
        headers = kwargs.get('headers', None)
        
        with limiter_0_1.ratelimit(f'{self.IE_NAME}2', delay=True):
            if msg: pre = f'{msg}[send_req]'
            else: pre = '[send_req]'
            self.logger_debug(f"{pre} {self._get_url_print(url)}") 
            if driver:
                driver.get(url)
            else:
                try:                
                    return self.send_http_request(url, headers=headers)                
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
        if not args: raise ExtractorError("error extracting video args")
        return args
        
    
    def _get_entry(self, url, **kwargs):     

        check_active = kwargs.get('check_active', False)
        msg = kwargs.get('msg', None)
        webpage = kwargs.get('webpage', None)

        try:
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}{pre}'
            _videoinfo = None            
            videoid = self._match_id(url)
            if not webpage:
                webpage = try_get(self._send_request(f"{self._SITE_URL}/e/{videoid}"), lambda x: html.unescape(x.text))
            if not webpage: raise ExtractorError("error 404 no webpage")
            args = self._get_args(webpage)
                      
            try:                
                self.init_ctx(f"{self._SITE_URL}/e/{videoid}")                
                video_url = self.get_videourl(*args)
            except pyduk.JSError as e:
                #error when something changes in network, dontknowwhy
                lines = traceback.format_exception(*sys.exc_info())
                self.report_warning(f"{repr(e)}\n{'!!'.join(lines)}")
                video_url = None
            
            if not video_url:
            
                self._real_initialize()
                #webpage = try_get(self._send_request(f"{self._SITE_URL}/e/{videoid}"), lambda x: html.unescape(x.text))
                #if not webpage: raise ExtractorError("error 404 no webpage")
                try:
                    #args = self._get_args(webpage)                
                    self.init_ctx(f"{self._SITE_URL}/e/{videoid}", force=True)
                    video_url = self.get_videourl(*args)                    
                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.report_warning(f"{repr(e)}\n{'!!'.join(lines)}")
                    raise ExtractorError("error 404 no video url")
                
                if not video_url: raise ExtractorError("error no video url")
            
            title = re.sub(r'(?i)((at )?%s.co$)' % self.IE_NAME, '', self._html_extract_title(webpage).replace('.mp4','')).strip('[_,-, ]')
                        
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
            
    
    def get_mainjs(self, url, **kwargs):
        _headers_mainjs = {    
            'Referer': url,
            'Sec-Fetch-Dest': 'script',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'same-origin',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
        }

        return(try_get(self._send_request(f'https://{self.IE_NAME}.co/assets/js/main.min.js', headers=_headers_mainjs), lambda x: x.text))
    
    def init_ctx(self, url, force=False):
        
        self._DUK_CTX = pyduk.DuktapeContext()
        
        #helper functions: deofus, atob
        jscode_deofus = 'function deofus(h,u,n,t,e,r){var _data=["","split","0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ+/","slice","indexOf","","",".","pow","reduce","reverse","0"];function _aux(d,e,f){var g=_data[2][_data[1]](_data[0]);var h=g[_data[3]](0,e);var i=g[_data[3]](0,f);var j=d[_data[1]](_data[0])[_data[10]]()[_data[9]](function(a,b,c){if(h[_data[4]](b)!==-1)return a+=h[_data[4]](b)*(Math[_data[8]](e,c))},0);var k=_data[0];while(j>0){k=i[j%f]+k;j=(j-(j%f))/f}return k||_data[11]};function _aux2(h,u,n,t,e,r){r="";for(var i=0,len=h.length;i<len;i++){var s="";while(h[i]!==n[e]){s+=h[i];i++}for(var j=0;j<n.length;j++)s=s.replace(new RegExp(n[j],"g"),j);r+=String.fromCharCode(_aux(s,e,10)-t)};return decodeURIComponent(escape(r))};return _aux2(h,u,n,t,e,r)};'                
        jscode_atob = 'function atob(str){return (new TextDecoder().decode(Duktape.dec("base64", str)))}'
        
        '''
        def atob(str):
            return(base64.b64decode(str).decode('iso-8859-1'))
        '''
        
        self._DUK_CTX.eval_js(jscode_deofus)
        self._DUK_CTX.eval_js(jscode_atob)
        
        #initial conf data
            
        # _headers_mainjs = {    
        #     'Referer': url,
        #     'Sec-Fetch-Dest': 'script',
        #     'Sec-Fetch-Mode': 'no-cors',
        #     'Sec-Fetch-Site': 'same-origin',
        #     'Pragma': 'no-cache',
        #     'Cache-Control': 'no-cache',
        # }

        #mainjs = try_get(self._send_request(f'https://{self.IE_NAME}.co/assets/js/main.min.js', headers=_headers_mainjs), lambda x: x.text)
        mainjs = self.get_mainjs(url, force=force)
        if not mainjs:
            raise ExtractorError("couldnt get mainjs")
        _code = self._DUK_CTX.get_global('deofus')(*self._get_args(mainjs))
        _jscode_1, _var = try_get(re.findall(r'(var res = ([^\.]+)\.replace.*); var decode', _code), lambda x: x[0])
        
        jscode = f'function getvurl(h,u,n,t,e,r){{var res1 = deofus(h,u,n,t,e,r); var {_var} = RegExp("{_var}=([^;]+);").exec(res1)[1].slice(1,-1); {_jscode_1};return atob(res2)}};'
        
        self._DUK_CTX.eval_js(jscode)
        
        self.get_videourl = self._DUK_CTX.get_global('getvurl')
        
        self.jscode_final = f'function getvurl(h,u,n,t,e,r){{{jscode_deofus}var res1 = deofus(h,u,n,t,e,r); var {_var} = RegExp("{_var}=([^;]+);").exec(res1)[1].slice(1,-1); {_jscode_1};{jscode_atob};return atob(res2)}};'
   

    def _real_extract(self, url):
        
        self.report_extraction(url)

        try:                            

            if self.get_param('external_downloader'): _check_active = True
            else: _check_active = False

            return self._get_entry(url, check_active=_check_active)  
            
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.report_warning(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        

class TubeloadIE(BaseloadIE):
    
    IE_NAME = 'tubeload'    
    _SITE_URL = "https://tubeload.co"
    _VALID_URL = r'https?://(?:www\.)?tubeload.co/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?tubeload\.co/e/.+?)\1']

class RedloadIE(BaseloadIE):
    
    _SITE_URL = "https://redload.co"    
    IE_NAME = 'redload'
    _VALID_URL = r'https?://(?:www\.)?redload.co/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'    
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?redload\.co/e/.+?)\1']