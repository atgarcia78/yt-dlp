import re
import sys
import traceback
import html
import time
from .commonwebdriver import (
    SeleniumInfoExtractor,
    dec_on_exception,
    dec_on_exception2,
    dec_on_exception3,
    HTTPStatusError,
    ConnectError,
    limiter_1,
    ec,
    By
)
from ..utils import ExtractorError, sanitize_filename, try_get, get_element_text_and_html_by_tag

import logging

logger = logging.getLogger('streamsb')

class getvideourl:
    def __call__(self, driver):
        _res_click = try_get(driver.find_elements(By.CLASS_NAME, 'g-recaptcha'), lambda x: {'ok': x[0].click()})
        time.sleep(2)
        _el_a = try_get(driver.find_elements(By.CLASS_NAME, 'contentbox'), lambda x: x[0].find_element(By.TAG_NAME, 'a'))
        if (_vurl:=_el_a.get_attribute('href')):
            return _vurl
        else: return False

class StreamSBIE(SeleniumInfoExtractor):
    
    _DOMAINS = r'(?:gaymovies\.top|sbanh\.com)'
    _VALID_URL = r'''(?x)https?://(?:.+?\.)?(?P<domain>%s)/((?:d|e)/)?(?P<id>[\dA-Za-z]+)(\.html)?''' % _DOMAINS
    IE_NAME = 'streamsb'
    
    @dec_on_exception3
    @dec_on_exception2    
    def _get_video_info(self, url, **kwargs):        
        
        pre = f'[get_video_info][{self._get_url_print(url)}]'
        if (msg:=kwargs.get('msg')): pre = f'{msg}{pre}'
        _headers = kwargs.get('headers', {})
                
        _headers = {'Range': 'bytes=0-', 'Referer': _headers.get('Referer'),
                    'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 
                    'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 
                    'Cache-Control': 'no-cache'}
        
        with limiter_1.ratelimit(self.IE_NAME, delay=True):
            try:
                self.logger_debug(pre)
                return self.get_info_for_format(url, headers=_headers)
            except (HTTPStatusError, ConnectError) as e:
                _msg_error = f"{repr(e)}"
                self.logger_debug(f"{pre}: {_msg_error}")
                return {"error_res": _msg_error}

    @dec_on_exception3
    @dec_on_exception2    
    def _send_request(self, url, **kwargs):        
        
        pre = f'[send_request][{self._get_url_print(url)}]'
        if (msg:=kwargs.get('msg')): pre = f'{msg}{pre}'
        
        driver = kwargs.get('driver', None)

        with limiter_1.ratelimit(f"{self.IE_NAME}2", delay=True):
            self.logger_debug(pre)
            if driver:
                driver.get(url)
            else:
                try:
                    return self.send_http_request(url)
                except (HTTPStatusError, ConnectError) as e:
                    _msg_error = f"{repr(e)}"
                    self.logger_debug(f"{pre}: {_msg_error}")
                    return {"error_res": _msg_error}


    def _get_entry(self, url, **kwargs):
        
        check_active = kwargs.get('check_active', False)
        msg = kwargs.get('msg', None)
        videoid, dom = re.search(self._VALID_URL, url).group('id', 'domain')

        driver = self.get_driver()
        
        try:
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}{pre}'

            url_dl = f"https://{dom}/d/{videoid}"
            webpage = try_get(self._send_request(url_dl, msg=pre), lambda x: html.unescape(x.text) if not isinstance(x, dict) else x)
            self.raise_from_res(webpage, "no webpage")
            _title = try_get(get_element_text_and_html_by_tag('h3', webpage), lambda x: x[0])
            sources = try_get(re.findall(r'\((.+)\)"\>(\d+)p', webpage), lambda x: {_el[1].replace("'", ""): {key: val for val,key in zip(_el[0].replace("'", "").split(','), ['id', 'mode', 'hash'])} for _el in x})
            _formats = []

            for res,data in sources.items():
                _url = f"https://{dom}/dl?op=download_orig&id={videoid}&mode={data['mode']}&hash={data['hash']}"
                
                self._send_request(_url, driver=driver)
                _videourl = self.wait_until(driver, 30, getvideourl())
                
                _format = {
                    'format_id': f'http-mp4-{res}',
                    'url': _videourl,               
                    'http_headers': {'Referer': f"https://{dom}/"},
                    'ext': 'mp4',
                    'height': int(res)
                }

                if check_active:
                    _video_info = self._get_video_info(_videourl, headers={'Referer': f"https://{dom}/"})
                    self.raise_from_res(_video_info, "no video info")
                    _format.update(_video_info)

                _formats.append(_format)

            
            _entry = {
                'id': videoid,
                'title': sanitize_filename(_title.replace('Download ', ''), restricted=True),
                'formats': _formats,
                'ext': 'mp4',
                'extractor_key': 'StreamSB',
                'extractor': 'streamsb',
                'webpage_url': url}
                        
            return _entry
            
        except Exception as e:
            logger.exception(str(e))
            raise
        finally:
            self.rm_driver(driver)

    def _real_initialize(self):
        super()._real_initialize()
               
    def _real_extract(self, url):
        
        self.report_extraction(url)
        try: 
            if not self.get_param('embed'): _check_active = True
            else: _check_active = False

            return self._get_entry(url, check_active=_check_active)  
        except ExtractorError:
            raise
        except Exception as e:            
            self.to_screen(f"{repr(e)}")
            raise ExtractorError(repr(e))
        