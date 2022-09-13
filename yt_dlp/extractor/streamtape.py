import re
import sys
import time
import traceback
import pyduktape3 as pyduk
import html

from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, HTTPStatusError, ConnectError, SeleniumInfoExtractor, limiter_0_1, limiter_1, By

class video_or_error_streamtape():
    
    def __call__(self, driver):
  
        elh1 = driver.find_elements(By.CSS_SELECTOR, "h1")
        if elh1: #error
            errormsg = elh1[0].get_attribute('innerText').strip("!")                    
            return ("error", errormsg)
        
        elover = driver.find_elements(By.CLASS_NAME, "play-overlay")
        if elover:
            for _ in range(5):
                try:
                    elover[0].click()
                    time.sleep(1)
                except Exception as e:
                    break
            
        if (el_vid:=driver.find_elements(By.CSS_SELECTOR, "video")):
            if (_src:=el_vid[0].get_attribute('src')):
                _title = try_get(driver.find_elements(By.CSS_SELECTOR, 'h2'), lambda x: x[0].text)
                return (_src, _title)
        return False

class StreamtapeIE(SeleniumInfoExtractor):

    IE_NAME = 'streamtape'
    _VALID_URL = r'https?://(www.)?(?:streamtape|streamta)\.(?:com|net|pe)/(?:d|e|v)/(?P<id>[a-zA-Z0-9_-]+)/?'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?streamtape\.(?:com|net)/(?:e|v|d)/.+?)\1']

    @dec_on_exception3
    @dec_on_exception2
    @limiter_1.ratelimit("streamtape", delay=True)
    def _get_video_info(self, url, headers=None, msg=None):        
        
        if msg: pre = f'{msg}[get_video_info]'
        else: pre = '[get_video_info]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}")
        _headers = {'Range': 'bytes=0-', 'Referer': headers['Referer'],
                        'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
                        'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
        try:
            return self.get_info_for_format(url, headers=_headers)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
    
    @dec_on_exception
    @dec_on_exception3
    @dec_on_exception2    
    def _send_request(self, url, **kwargs):        
        
        driver = kwargs.get('driver', None)
        msg = kwargs.get('msg', None)
        lim = kwargs.get('lim', None)
        if lim:
            dec = lim.ratelimit("streamtape2", delay=True)
        else:            
            dec = limiter_1.ratelimit("streamtape2", delay=True)
        
        @dec
        def _aux():            
            
            if msg: pre = f'{msg}[send_req]'
            else: pre = '[send_req]'
            self.logger_debug(f"{pre} {self._get_url_print(url)}")
            if driver:
                driver.get(url)
            else:
                try:
                    return self.send_http_request(url)
                except (HTTPStatusError, ConnectError) as e:
                    self.report_warning(f"[send_request] {self._get_url_print(url)}: error - {repr(e)}")
        
        return _aux()


    def _get_entry(self, url, **kwargs):
        
        check_active = kwargs.get('check_active', False)
        msg = kwargs.get('msg', None)
        webpage = kwargs.get('webpage', None)
        
        try:
            
            url = url.replace('/e/', '/v/')
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}[get_entry][{self._get_url_print(url)}]'
            if not webpage:
                webpage = try_get(self._send_request(url, msg=pre, lim=limiter_0_1), lambda x: html.unescape(x.text))
            
            if not webpage: raise ExtractorError("no webpage")
            el_node = try_get(re.findall(r'var srclink\s+=\s+\$\([\'\"]#([^\'\"]+)[\'\"]', webpage), lambda x: x[0])
            if not el_node: raise ExtractorError("error when retrieving video url")
            _code = try_get(re.findall(r'ById\([\'\"]%s[\'\"]\)\.innerHTML\s+=\s+([^<]+)<' % (el_node), webpage), lambda x: x[0])
            
           
            
            try:
                _duk_ctx = pyduk.DuktapeContext()
                _res = _duk_ctx.eval_js(_code)                
            except Exception as e:
                raise ExtractorError("error video url")
            
            if not _res: raise ExtractorError("error video url")
            video_url = 'https:' + _res + '&stream=1'
            _title = self._html_search_regex((r'>([^<]+)</h2>', r'(?s)<title\b[^>]*>([^<]+)</title>'), webpage, 'title',fatal=False)
            
            if not _title:
                _title = self._html_search_meta(('og:title', 'twitter:title'), webpage, None)
                                        
             
            _format = {
                'format_id': 'http-mp4',
                'url': video_url,
                'ext': 'mp4',
                'http_headers': {'Referer': url}
            }
            
            
            if check_active:
                _videoinfo = self._get_video_info(video_url, headers= {'Referer': url}, msg=pre)
                if not _videoinfo: 
                    raise ExtractorError("error 404: no video info")
                _format.update({'url': _videoinfo['url'],'filesize': _videoinfo['filesize'] })
                
            _entry_video = {
                'id' : self._match_id(url),
                'title' : sanitize_filename(_title.replace('.mp4',''), restricted=True),
                'formats' : [_format],
                'ext': 'mp4',
                'extractor_key': 'Streamtape',
                'extractor': 'streamtape',
                'webpage_url': url
            }            
            
            return _entry_video
            
        except Exception as e:
            raise

    
    def _real_initialize(self):
        
        # with StreamtapeIE._LOCK:
        #     if all([StreamtapeIE._DUK_CTX, SeleniumInfoExtractor._YTDL, SeleniumInfoExtractor._YTDL != self._downloader]):
        #         StreamtapeIE._DUK_CTX = None
        #     super()._real_initialize()            
        #     if not StreamtapeIE._DUK_CTX:
        #         StreamtapeIE._DUK_CTX = pyduk.DuktapeContext()
        super()._real_initialize()
    
    def _real_extract(self, url):
        
        self.report_extraction(url)

        try:                            

            if self.get_param('external_downloader'): _check_active = True
            else: _check_active = False

            return self._get_entry(url, check_active=_check_active)  
            
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.report_warning(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))