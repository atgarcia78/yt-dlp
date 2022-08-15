from __future__ import unicode_literals

import sys
import traceback
import re
import time


from ..utils import try_get, ExtractorError, sanitize_filename
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_0_1, By, ec, HTTPStatusError
from urllib.parse import unquote, urlparse

class FembedIE(SeleniumInfoExtractor):

    IE_NAME = 'fembed'
    _VALID_URL = r'https?://(?:www\.)?fembed\.com/v/(?P<id>[^\#]+)'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?fembed\.com/v/.+?)\1']

    @dec_on_exception3 
    @dec_on_exception2
    @limiter_0_1.ratelimit("fembed", delay=True)
    def _get_video_info(self, url, headers):        
        
        self.logger_debug(f"[get_video_info] {url}")
        _headers = {'Range': 'bytes=0-', 'Referer': headers['Referer'],
                            'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
                            'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
        try:
            return self.get_info_for_format(url, headers=_headers)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
        
        
    @dec_on_exception
    @limiter_0_1.ratelimit("fembed", delay=True)
    def _send_request(self, url, driver):        
        self.logger_debug(f"[send_request] {url}") 
        driver.get(url)
    
    # @staticmethod
    # def _extract_urls(webpage):

    #     return [mobj.group('url') for mobj in re.finditer(r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?fembed\.com/v/.+?)\1',webpage)]
    
    
    def _get_entry(self, url, **kwargs):
        
        check_active = kwargs.get('check_active', False)
        msg = kwargs.get('msg', None)
         

        try:
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg: pre = f'{msg}{pre}'
            driver = self.get_driver()
            videoid = self._match_id(url)
            title = try_get(unquote(url).split('#'), lambda x: x[1].replace(".mp4", ""))
            self._send_request(_wurl:=(url.split('#')[0].replace('fembed', 'vanfem')), driver)            

            _headers = {'Referer': _wurl.split('v/')[0]}

            el_div = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CSS_SELECTOR, 'div'))) 
            
            #self.to_screen(el_div)
            
            for el in el_div:
                            
                while True:
                    try:
                        el.click()
                        time.sleep(1)
                    except Exception:
                        break
            # cont = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "loading-container.faplbu")))
            # if cont:
            #     try:
            #         cont.click()
            #     except Exception:
            #         pass
            # else:
            #     elobs = self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, 'svg')))
            #     if elobs:
            #         try:
            #             elobs.click()
            #         except Exception:
            #             pass
            
            if not title:
                title = driver.title.replace("Video ", "").replace(".mp4", "").strip().lower()

            _formats = []
            
            if (but_resume:=try_get(driver.find_elements(By.CSS_SELECTOR, 'button#resume_no.button'), lambda x: x[0])):
                but_resume.click()
            vstr = self.wait_until(driver, 30, ec.presence_of_element_located((By.ID, "vstr")))
            if vstr:
                vstr.click()            

            try:
                if (setb:=self.wait_until(driver, 30, ec.presence_of_element_located((
                        By.CSS_SELECTOR,
                        "div.jw-icon.jw-icon-inline.jw-button-color.jw-reset.jw-icon-settings.jw-settings-submenu-button",
                    )))):
                        setb.click()
                        if (qbmenu:=self.wait_until(driver, 30, ec.presence_of_element_located((
                            By.CSS_SELECTOR, "div.jw-reset.jw-settings-submenu.jw-settings-submenu-active"
                        )))):
                            qbmenubut = qbmenu.find_elements(By.TAG_NAME, "button")
                            nquality = len(qbmenubut)
                            setb.click()
                            if (nquality == 0) or nquality > 4:
                                raise ExtractorError('no extra qualities')
                
            except Exception as e:
                _videourl = try_get(self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "video"))), lambda x: x.get_attribute('src'))
                _f = {
                    'format_id': f'http-mp4',
                    'url': _videourl,
                    'http_headers': _headers,
                    'ext': 'mp4'
                }
                if check_active: 
                    _info_video = self._get_video_info(_videourl, _headers)
                    if _info_video:
                        _f.update({'url': _info_video['url'],'filesize': _info_video['filesize']})
                        _formats.append(_f)
                    else:
                        self.report_warning(f"{pre} not video info")
                else:
                     _formats.append(_f)
                    
            
            else:
               
                vid = self.wait_until(driver, 30, ec.presence_of_element_located((By.TAG_NAME, "video"))) 
            
                for i in range(nquality):
                    vstr = self.wait_until(driver, 30, ec.presence_of_element_located((By.ID, "vstr")))
                    vstr.click()
                    setb.click()
                    qbmenu = self.wait_until(driver, 30, ec.presence_of_element_located((
                        By.CSS_SELECTOR, "div.jw-reset.jw-settings-submenu.jw-settings-submenu-active"
                    )))
                    qbmenubut = qbmenu.find_elements(By.TAG_NAME, "button")
                    _formatid = qbmenubut[i].text
                    qbmenubut[i].click()                
                    _videourl = vid.get_attribute("src")
                    _f = {
                        'format_id': f'http-mp4-{_formatid}',
                        'height': int(_formatid[:-1]),
                        'url': _videourl,
                        'http_headers': _headers,                        
                        'ext': 'mp4'
                    }
                    if check_active: 
                        _info_video = self._get_video_info(_videourl, _headers)
                        if _info_video:
                            _f.update({'url': _info_video['url'],'filesize': _info_video['filesize']})
                            _formats.append(_f)
                        else:
                            self.report_warning(f"{pre} not video info")
                            
                    
                    else:
                        _formats.append(_f)
                    
                vstr.click()

            if _formats: 
                self._sort_formats(_formats)
                
            return({
                'id' : videoid,
                'title': sanitize_filename(title, restricted=True),             
                'formats' : _formats,                
                'ext': 'mp4',
                'extractor_key': 'Fembed',
                'extractor': 'fembed',
                'webpage_url': url
            })
        
        except Exception:
            #lines = traceback.format_exception(*sys.exc_info())
            #self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise
        finally:
            self.rm_driver(driver)
    
    def _real_initialize(self):
        super()._real_initialize()
    

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
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
       

    

