from hashlib import sha256
import traceback
import sys

from ..utils import sanitize_filename, try_get, traverse_obj, get_domain
from .commonwebdriver import dec_on_exception2, dec_on_exception, dec_on_exception3, ExtractorError, SeleniumInfoExtractor, limiter_1, limiter_2, limiter_5, By, HTTPStatusError, ConnectError, Lock

from urllib.parse import unquote

class getvideourl:
    def __call__(self, driver):
        el_vid = driver.find_element(By.ID, "video_player_html5_api")
        if (_videourl:=el_vid.get_attribute('src')):
            return unquote(_videourl)
        else: return False

class DoodStreamIE(SeleniumInfoExtractor):
    
    IE_NAME = 'doodstream'
    _VALID_URL = r'https?://(?:www\.)?dood(?:stream)?\.[^/]+/[ed]/(?P<id>[a-z0-9]+)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(?:www\.)?dood(?:stream)?\.[^/]+/[ed]/[a-z0-9]+)\1']
    _SITE_URL = 'https://dood.to/'
    
    
    _TESTS = [{
        'url': 'http://dood.to/e/5s1wmbdacezb',
        'md5': '4568b83b31e13242b3f1ff96c55f0595',
        'info_dict': {
            'id': '5s1wmbdacezb',
            'ext': 'mp4',
            'title': 'Kat Wonders - Monthly May 2020',
            'description': 'Kat Wonders - Monthly May 2020 | DoodStream.com',
            'thumbnail': 'https://img.doodcdn.com/snaps/flyus84qgl2fsk4g.jpg',
        }
    }, {
        'url': 'http://dood.watch/d/5s1wmbdacezb',
        'md5': '4568b83b31e13242b3f1ff96c55f0595',
        'info_dict': {
            'id': '5s1wmbdacezb',
            'ext': 'mp4',
            'title': 'Kat Wonders - Monthly May 2020',
            'description': 'Kat Wonders - Monthly May 2020 | DoodStream.com',
            'thumbnail': 'https://img.doodcdn.com/snaps/flyus84qgl2fsk4g.jpg',
        }
    }, {
        'url': 'https://dood.to/d/jzrxn12t2s7n',
        'md5': '3207e199426eca7c2aa23c2872e6728a',
        'info_dict': {
            'id': 'jzrxn12t2s7n',
            'ext': 'mp4',
            'title': 'Stacy Cruz Cute ALLWAYSWELL',
            'description': 'Stacy Cruz Cute ALLWAYSWELL | DoodStream.com',
            'thumbnail': 'https://img.doodcdn.com/snaps/8edqd5nppkac3x8u.jpg',
        }
    }]
    
    @dec_on_exception3  
    @dec_on_exception2
    def _get_video_info(self, url, msg=None):        
        
        _host = get_domain(url)
        if msg: pre = f'{msg}[get_video_info]'
        else: pre = '[get_video_info]'

        with self.get_param('lock'):
            if not (_sem:=traverse_obj(self.get_param('sem'), _host)): 
                _sem = Lock()
                self.get_param('sem').update({_host: _sem})

        with limiter_1.ratelimit(f"dstr{_host}", delay=True):
            try:
                with _sem:
                    self.logger_debug(f"{pre} {self._get_url_print(url)}")                
                    return self.get_info_for_format(url, headers={'Range': 'bytes=0-', 'Referer': self._SITE_URL, 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'})
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"{pre} {self._get_url_print(url)}: error - {repr(e)}")
        
    
    
    @dec_on_exception
    @limiter_1.ratelimit("doodstream", delay=True)
    def _send_request(self, url, driver=None, msg=None):        
    
        if msg: pre = f'{msg}[send_req]'
        else: pre = '[send_req]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}")
        driver.get(url)

           
    
    def _get_entry(self, url, check=False, msg=None):
        
        try:

            if msg: pre = f'{msg}[get_entry][{self._get_url_print(url)}]'
            else: pre = f'[get_entry][{self._get_url_print(url)}]'
                      
            video_id = self._match_id(url)
            driver = self.get_driver()
            driver.delete_all_cookies()
            _url = f'https://dood.to/e/{video_id}'
            self._send_request(_url, driver=driver, msg=pre)

            video_url = self.wait_until(driver, 30, getvideourl())
            if not video_url: raise ExtractorError("couldnt get videourl")
            
            title = try_get(driver.title, lambda x: x.replace(' - DoodStream', '')) 
    
            
            _format =  {
                'format_id': 'http-mp4',
                'url': video_url,           
                'http_headers': {'Referer': self._SITE_URL},
                'ext': 'mp4'
            }
            
            if check:
                _videoinfo = self._get_video_info(video_url, msg=pre)
                if not _videoinfo: raise ExtractorError("error 404: no video info")
                if _videoinfo and _videoinfo['filesize'] > 20:
                    
                    _format.update({'url': _videoinfo['url'],'filesize': _videoinfo['filesize'], 'accept_ranges': _videoinfo['accept_ranges']})
                else:
                    raise ExtractorError(f"error filesize[{_videoinfo['filesize']}] < 20 bytes")
            
            
            _entry = {
                'id': str(int(sha256(video_id.encode('utf-8')).hexdigest(),16) % 10**12) if len(video_id) > 12 else video_id,
                'title': sanitize_filename(title, restricted=True),
                'formats': [_format],
                'ext': 'mp4',
                'extractor_key': 'DoodStream',
                'extractor': 'doodstream',
                'webpage_url': url
            }        

            return _entry
        
        except Exception:
            raise
        finally:
            self.rm_driver(driver)
        
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):
        
        self.report_extraction(url)

        try:                            

            if not self.get_param('embed'): _check = True
            else: _check = False

            return self._get_entry(url, check=_check)  
            
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.report_warning(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        

