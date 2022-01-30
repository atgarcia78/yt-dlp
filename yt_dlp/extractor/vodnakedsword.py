from __future__ import unicode_literals


from .commonwebdriver import (
    SeleniumInfoExtractor,
    limiter_0_1
)

from ..utils import (

    sanitize_filename,
    try_get
)

from threading import Lock

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


import json

from collections import OrderedDict



from backoff import on_exception, constant

class VODNakedSwordBaseIE(SeleniumInfoExtractor):
    IE_NAME = 'vodnakedsword'
    IE_DESC = 'vodnakedsword'
    
    _SITE_URL = "https://vod.nakedsword.com/gay"
    _LOGIN_URL = "https://vod.nakedsword.com/gay/login?f=%2Fgay"
    _POST_URL = "https://vod.nakedsword.com/gay/deliver"
    _NETRC_MACHINE = 'vodnakedsword'
    
    _LOCK = Lock()
    _COOKIES = None
    _NSINIT = False
    

    def _headers_ordered(self, extra=None):
        _headers = OrderedDict()
        
        if not extra: extra = dict()
        
        for key in ["User-Agent", "Accept", "Accept-Language", "Accept-Encoding", "Content-Type", "X-Requested-With", "Origin", "Connection", "Referer", "Upgrade-Insecure-Requests"]:
        
            value = extra.get(key) if extra.get(key) else VODNakedSwordBaseIE._CLIENT_CONFIG['headers'].get(key.lower())
            if value:
                _headers[key.lower()] = value
      
        
        return _headers
    
    @on_exception(constant, Exception, max_tries=5, interval=1)
    @limiter_0_1.ratelimit("vodnakedsword", delay=True)
    def _send_request(self, url, _type="GET", data=None, headers=None):
        
        res = VODNakedSwordBaseIE._CLIENT.request(_type, url, data=data, headers=headers)
        res.raise_for_status()
        return res
    
    def get_driver_NS(self):
        driver = self.get_driver(usequeue=True)
        driver.get(self._SITE_URL)
        for cookie in VODNakedSwordBaseIE._COOKIES:
            driver.add_cookie(cookie)
        return driver
        
    
    def _login(self):
        pass
        
                    
    def _init(self):
        
        super()._init()
        
        with VODNakedSwordBaseIE._LOCK:           
            if not VODNakedSwordBaseIE._NSINIT:
                
                
                if not VODNakedSwordBaseIE._COOKIES:
                    try:                        
                        with open("/Users/antoniotorres/Projects/common/logs/VODNSWORD_COOKIES.json", "r") as f:
                            VODNakedSwordBaseIE._COOKIES = json.load(f)
                        
                    except Exception as e:
                        self.to_screen(f"{repr(e)}")
                        raise
                
                for cookie in VODNakedSwordBaseIE._COOKIES:
                    VODNakedSwordBaseIE._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
                    
                VODNakedSwordBaseIE._NSINIT = True
            
    def _real_initialize(self):
    
        self._init()
        return
  
    
        

class VODNakedSwordMovieIE(VODNakedSwordBaseIE):
    IE_NAME = 'vodnakedsword:movie'
    _VALID_URL = r"https?://(?:www\.)?vod.nakedsword.com/gay/movies/(?P<id>[\d]+)/(?P<title>[a-zA-Z\d_-]+)/?$"
    


    def _real_extract(self, url):

        movie_id, _title = self._match_valid_url(url).group('id', 'title')
        _title = _title.replace("-", " ").title()
        
        data = {
            'movieId': movie_id, 
            'embedHLS': 'true',
            'consumptionRate': '1',
            'popoutTitle': f"Watching Movie {_title}",
            'format': 'HLS',
            'maxBitrate': '100000',
            'trickPlayImgPrefix': 'https://pic.aebn.net/dis/t/',
            'isEmbedded': 'false',
            'popoutHtmlUrl': '/resources/unified-player/player/fullframe.html'}
        
        headers_post = {
            'Accept': '*/*',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://vod.nakedsword.com',
            'Referer': url}
        
        res = VODNakedSwordBaseIE._CLIENT.post(self._POST_URL, data=data, headers=headers_post)
        res.raise_for_status()
        info = res.json()
        m3u8_url = info.get('url')
        _headers = {'referer': 'https://vod.nakedsword.com/', 'origin': 'https://vod.nakedsword.com' , 'accept': '*/*'}
        formats = self._extract_m3u8_formats(m3u8_url, movie_id, 'mp4', entry_protocol='m3u8_native', m3u8_id='hls', headers=_headers, fatal=False)
        if formats:
            self._sort_formats(formats)
            _entry = {
                'id': movie_id,
                'title': sanitize_filename(_title,restricted=True),
                'ext': 'mp4',
                'formats': formats                
            }
            return _entry


       

