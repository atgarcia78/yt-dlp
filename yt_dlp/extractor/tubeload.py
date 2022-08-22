import time
import sys
import traceback
from urllib.parse import unquote, urlparse
import re
#from .openload import PhantomJSwrapper
import threading
import html
#import js2py
import pyduktape3 as pyduk

from ..utils import ExtractorError, sanitize_filename, traverse_obj, try_get
from .commonwebdriver import (
    dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, 
    limiter_0_5, By, HTTPStatusError, ConnectError, ConnectError, PriorityLock)


class TubeloadIE(SeleniumInfoExtractor):

    IE_NAME = 'tubeload'    
    _SITE_URL = "https://tubeload.co"
    _VALID_URL = r'https?://(?:www\.)?tubeload.co/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?tubeload\.co/e/.+?)\1']
    _DUK_CTX = None
    _LOCK = threading.Lock()
    
    @dec_on_exception3  
    @dec_on_exception2
    @limiter_0_5.ratelimit("tubeload", delay=True)
    def _get_video_info(self, url, msg=None):        
        
        try:
            if msg: pre = f'{msg}[get_video_info]'
            else: pre = '[get_video_info]'
            self.logger_debug(f"{pre} {self._get_url_print(url)}")
            _host = urlparse(url).netloc
            
            with self.get_param('lock'):
                if not (_sem:=traverse_obj(self.get_param('sem'), _host)): 
                    _sem = PriorityLock()
                    self.get_param('sem').update({_host: _sem})
                
            _sem.acquire(priority=10)                
            return self.get_info_for_format(url, headers={'Range': 'bytes=0-', 'Referer': self._SITE_URL + "/", 'Origin': self._SITE_URL, 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'})
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"{pre} {self._get_url_print(url)}: error - {repr(e)}")
        finally:
            if _sem: _sem.release()
            
    @dec_on_exception
    @dec_on_exception3
    @dec_on_exception2
    @limiter_0_5.ratelimit("tubeload2", delay=True)
    def _send_request(self, url, driver=None, msg=None):        
        
        if msg: pre = f'{msg}[send_req]'
        else: pre = '[send_req]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}") 
        if driver:
            driver.get(url)
        else:
            try:                
                return self.send_http_request(url)                
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"{pre} {self._get_url_print(url)}: error - {repr(e)}")
                
    
    def getter(self, x):
        if not x: return
        args = x[0].split(',')
        if len(args) != 6: return
        for i in range(len(args)):
            if args[i].isdecimal(): args[i] = int(args[i])
            else: args[i] = args[i].strip('"')
        return args
    
    def _get_entry(self, url, check_active=False, msg=None, webpage=None):        

        try:
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}{pre}'
            _videoinfo = None            
            videoid = self._match_id(url)
            if not webpage:
                webpage = try_get(self._send_request(f"{self._SITE_URL}/e/{videoid}"), lambda x: html.unescape(x.text))
            if not webpage: raise ExtractorError("error 404 no webpage")
            args = try_get(re.findall(r'var .+eval\(.+decodeURIComponent\(escape\(r\)\)\}\(([^\)]+)\)', webpage), lambda x: self.getter(x))
            if not args: raise ExtractorError("error extracting video data")
            self.logger_debug(f'{pre} args:\n {args}')
            try:
                video_url = TubeloadIE._DUK_CTX.get_global('vurl')(*args)
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
                    _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})

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
        with TubeloadIE._LOCK:
            if not TubeloadIE._DUK_CTX:
                TubeloadIE._DUK_CTX = pyduk.DuktapeContext()
                jscode1 = 'function deofus(h,u,n,t,e,r){var _0xc61e=["","split","0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ+/","slice","indexOf","","",".","pow","reduce","reverse","0"];function _aux(d,e,f){var g=_0xc61e[2][_0xc61e[1]](_0xc61e[0]);var h=g[_0xc61e[3]](0,e);var i=g[_0xc61e[3]](0,f);var j=d[_0xc61e[1]](_0xc61e[0])[_0xc61e[10]]()[_0xc61e[9]](function(a,b,c){if(h[_0xc61e[4]](b)!==-1)return a+=h[_0xc61e[4]](b)*(Math[_0xc61e[8]](e,c))},0);var k=_0xc61e[0];while(j>0){k=i[j%f]+k;j=(j-(j%f))/f}return k||_0xc61e[11]};function _aux2(h,u,n,t,e,r){r="";for(var i=0,len=h.length;i<len;i++){var s="";while(h[i]!==n[e]){s+=h[i];i++}for(var j=0;j<n.length;j++)s=s.replace(new RegExp(n[j],"g"),j);r+=String.fromCharCode(_aux(s,e,10)-t)}return decodeURIComponent(escape(r))};var res1 = _aux2(h,u,n,t,e,r); return(res1)};'
                TubeloadIE._DUK_CTX.eval_js(jscode1)
                mainjs = try_get(self._send_request('https://tubeload.co/assets/js/main.min.js'), lambda x: x.text)
                args = try_get(re.findall(r'var .+eval\(.+decodeURIComponent\(escape\(r\)\)\}\(([^\)]+)\)', mainjs), lambda x: self.getter(x))
                _code = TubeloadIE._DUK_CTX.get_global('deofus')(*args)
                _jscode_1, _var = try_get(re.findall(r'(var res = (\w{12}).replace.*); var decode', _code), lambda x: x[0])
                TubeloadIE._DUK_CTX.eval_js('function atob(str){return Buffer.prototype.toString.call(Duktape.dec("base64", str));}')
                jscode2 = f'function vurl(h,u,n,t,e,r){{var res1 = deofus(h,u,n,t,e,r); var {_var} = RegExp("{_var}=([^;]+);").exec(res1)[1].slice(1,-1); {_jscode_1};return atob(res2)}};'
                #self.logger_debug(jscode2)
                TubeloadIE._DUK_CTX.eval_js(jscode2)    

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
        
class RedloadIE(TubeloadIE):
    
    _SITE_URL = "https://redload.co"
    
    IE_NAME = 'redload'
    _VALID_URL = r'https?://(?:www\.)?redload.co/(?:e|f)/(?P<id>[^\/$]+)(?:\/|$)'
    
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?redload\.co/e/.+?)\1']