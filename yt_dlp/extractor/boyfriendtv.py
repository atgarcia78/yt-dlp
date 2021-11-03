# coding: utf-8
from __future__ import unicode_literals

import re

from .seleniuminfoextractor import SeleniumInfoExtractor

from ..utils import (
    ExtractorError,  
    urljoin,
    int_or_none,
    sanitize_filename,
    std_headers

)

import html
import time
import threading


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import traceback
import sys

import httpx
import demjson
from urllib.parse import unquote


class BoyFriendTVBaseIE(SeleniumInfoExtractor):
    _LOGIN_URL = 'https://www.boyfriendtv.com/login/'
    _SITE_URL = 'https://www.boyfriendtv.com/'
    _NETRC_MACHINE = 'boyfriendtv'
    _LOGOUT_URL = 'https://www.boyfriendtv.com/logout'

    _LOCK = threading.Lock()
    
    _COOKIES = {}
    
    def _get_info_video(self, url, client):
       
        count = 0
        while (count<5):
                
            try:
                
                res = client.head(url)
                if res.status_code > 400:
                    
                    count += 1
                else: 
                    
                    _filesize = int_or_none(res.headers.get('content-length')) 
                    _url = str(res.url)
                    #self.to_screen(f"{url}:{_url}:{_res}")
                    if _filesize and _url: 
                        break
                    else:
                        count += 1
        
            except Exception as e:
                count += 1
                
            time.sleep(1)
                
        if count < 5: return ({'url': _url, 'filesize': _filesize}) 
        else: return ({'error': 'max retries'})  

    def _login(self, driver):
        
        
        username, password = self._get_login_info()
        
        #self.to_screen(f'{username}:{password}')
        
        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)
        
        self.report_login()
        driver.get(self._SITE_URL)
        el_login = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "a#login-url")))
        if el_login: el_login.click()
        el_username = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "input#login.form-control")))
        el_password = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "input#password.form-control")))
        el_login = self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, "input.btn.btn-submit")))
        if el_username and el_password and el_login:
            el_username.send_keys(username)
            self.wait_until(driver, 2, ec.presence_of_element_located((By.CSS_SELECTOR, "DUMMYFORWAIT")))
            el_password.send_keys(password)
            self.wait_until(driver, 2, ec.presence_of_element_located((By.CSS_SELECTOR, "DUMMYFORWAIT")))            
            el_login.submit()
            el_menu = self.wait_until(driver, 15, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))
        #self.to_screen(driver.current_url)
        #self.to_screen(driver.current_url == self._SITE_URL)
            if not el_menu: 
                self.raise_login_required("Invalid username/password")
            else:
                self.to_screen("Login OK")


 
class BoyFriendTVIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtv'
    _VALID_URL = r'https?://(?:(?P<prefix>m|www|es|ru|de)\.)?(?P<url>boyfriendtv\.com/videos/(?P<id>[0-9]+)/?(?:([0-9a-zA-z_-]+/?)|$))'


    def _real_extract(self, url):
        
                
        with BoyFriendTVIE._LOCK:
            
            try:

                driver, tempdir = self.get_driver(prof='/Users/antoniotorres/Library/Application Support/Firefox/Profiles/22jv66x2.selenium0')
                    
                driver.get(self._SITE_URL)
                el_menu = self.wait_until(driver, 10, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))
                if not el_menu:
                    if BoyFriendTVIE._COOKIES:
                        for _cookie in BoyFriendTVIE._COOKIE: driver.add_cookie(_cookie)
                        driver.get(self._SITE_URL)
                        el_menu = self.wait_until(driver, 10, ec.presence_of_element_located((By.CSS_SELECTOR, "a.show-user-menu")))
                        if el_menu:
                            self.to_screen(f"Login already")
                            
                        else:
                            self._login(driver)
                    else:
                        driver.add_cookie({'name': 'rta_terms_accepted', 'value': 'true', 'sameSite': 'Lax', 'secure': True, 'domain': '.boyfriendtv.com'})                
                        self._login(driver)
                else:
                    self.to_screen("Login already")
                    
                BoyFriendTVIE._COOKIES = driver.get_cookies()
                
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
                raise ExtractorError(f"Login error: {repr(e)}") from e
            finally:
                try:
                    self.rm_driver(driver, tempdir)
                except Exception:
                    pass
                           
                
            
        self.report_extraction(url) 
        
        
        try:
        
            driver.get(url)
            
            el_vplayer = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "video-player")))
            el_title = self.wait_until(driver, 10, ec.presence_of_element_located((By.TAG_NAME, "title")))
            if el_title: _title = el_title.get_attribute("innerHTML")
            if "deleted" in _title or "removed" in _title or "page not found" in _title or not el_vplayer:
                raise ExtractorError("Page not found")   
            _title_video = _title.replace(" - BoyFriendTV.com", "").strip()            
            el_html = self.wait_until(driver, 60, ec.presence_of_element_located((By.TAG_NAME, "html")))
            webpage = el_html.get_attribute("outerHTML")                    
            mobj = re.findall(r'sources:\s+(\{.*\})\,\s+poster',re.sub('[\t\n]','', html.unescape(webpage)))
            
            if mobj:
                
                try:
                        
                    client = httpx.Client(timeout=10, headers={'User-Agent': std_headers['User-Agent']}, verify=(not self._downloader.params.get('nocheckcertificate')))
                    info_sources = demjson.decode(mobj[0])
                    _formats = []
                    for _src in info_sources.get('mp4'):
                        _url = unquote(_src.get('src'))
                        _info_video = self._get_info_video(_url, client)
                            
                        if (_error:=_info_video.get('error')): 
                            self.to_screen(_error)
                            raise ExtractorError('Error 404')
                        
                        _formats.append({
                            'url': _info_video.get('url'),
                            'ext': 'mp4',
                            'format_id': f"http-{_src.get('desc')}",
                            'resolution': _src.get('desc'),
                            'height': int_or_none(_src.get('desc').lower().replace('p','')),
                            'filesize': _info_video.get('filesize')
                        })
                        
                    self._sort_formats(_formats)
                    
                    return({
                        'id': self._match_id(url),
                        'title': sanitize_filename(_title_video, restricted=True),
                        'formats': _formats,
                        'ext': 'mp4'
                
                    })
                  
                   
                except Exception as e:
                    lines = traceback.format_exception(*sys.exc_info())
                    self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
                    raise ExtractorError(repr(e)) from e
                finally:
                    try:
                        client.close()
                    except Exception:
                        pass
        
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e)) from e
        finally:
            try:
                self.rm_driver(driver, tempdir)
            except Exception:
                pass
           
       
 

class BoyFriendTVEmbedIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtv:embed'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/embed/(?:((?P<id>[0-9]+)/)|embed.php\?)'
    
   
    def _real_extract(self, url):
        
        self.report_extraction(url)
        try:
            if not self._match_id(url):
                _url_embed = httpx.URL(url)
                _params_dict = dict(_url_embed.params.items())
                _url = f"https://{_url_embed.host}/embed/{_params_dict.get('m')}/{_params_dict.get('h')}"
            else: _url = url
            
            
            client = httpx.Client(timeout=10, headers={'User-Agent': std_headers['User-Agent']}, verify=(not self._downloader.params.get('nocheckcertificate')))
            
            res = client.get(_url)            
                
            webpage = re.sub('[\t\n]','', html.unescape(res.text))
            
            #self.to_screen(webpage)
            mobj = re.findall(r'sources:\s+(\{.*\})\,\s+poster', webpage)
            mobj2 = re.findall(r'title:\s+\"([^-\"]*)[-\"]', webpage)        
            
            _title_video = mobj2[0].strip() if mobj2 else "boyfriendtv_video"
 
            if mobj:
                info_sources = demjson.decode(mobj[0])
                _formats = []
                for _src in info_sources.get('mp4'):
                    _url = unquote(_src.get('src'))
                    _info_video = self._get_info_video(_url, client) 
                    _formats.append({
                        'url': _info_video.get('url'),
                        'ext': 'mp4',
                        'format_id': f"http-{_src.get('desc')}",
                        'resolution': _src.get('desc'),
                        'height': int_or_none(_src.get('desc').lower().replace('p','')),
                        'filesize': _info_video.get('filesize')
                    })
                    
                self._sort_formats(_formats)
                
                return({
                    'id': self._match_id(str(res.url)),
                    'title': sanitize_filename(_title_video, restricted=True),
                    'formats': _formats,
                    'ext': 'mp4'
            
                })
                
            else: raise ExtractorError("Video not found")
                
        except ExtractorError as e:
            raise     
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            raise ExtractorError(str(e)) from e
        finally:
            try:
                client.close()
            except Exception:
                pass
        


class BoyFriendTVPlayListIE(BoyFriendTVBaseIE):
    IE_NAME = 'boyfriendtv:playlist'
    IE_DESC = 'boyfriendtv:playlist'
    _VALID_URL = r'https?://(?:(m|www|es|ru|de)\.)boyfriendtv\.com/playlists/(?P<playlist_id>.*?)(?:(/|$))'

 
    
    def _real_extract(self, url):
        mobj = re.match(self._VALID_URL, url)
        playlist_id = mobj.group('playlist_id')

        try:
            
            driver, tempdir = self.get_driver(prof='/Users/antoniotorres/Library/Application Support/Firefox/Profiles/22jv66x2.selenium0')
                
            driver.get(self._SITE_URL)
            
            el = self.wait_until(driver, 15, ec.presence_of_element_located((By.CLASS_NAME, "swal2-container")))
            if el:
                driver.add_cookie({'name': 'rta_terms_accepted', 'value': 'true', 'sameSite': 'Lax', 'secure': True, 'domain': '.boyfriendtv.com'})      
                
        
            entries = []
            driver.get(url)
            el_title = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "h1")))
            _title = el_title.text.splitlines()[0]
            
            while True:

                el_sources = self.wait_until(driver, 60, ec.presence_of_all_elements_located((By.CSS_SELECTOR, "div.thumb.vidItem")))
                
                if el_sources:                        
                    entries += [self.url_result((el_a:=el.find_element(by=By.TAG_NAME, value='a')).get_attribute('href').rsplit("/", 1)[0], ie=BoyFriendTVIE.ie_key(), video_id=el.get_attribute('data-video-id'), video_title=sanitize_filename(el_a.get_attribute('title'), restricted=True)) for el in el_sources]

                el_next = self.wait_until(driver, 60, ec.presence_of_element_located((By.PARTIAL_LINK_TEXT, "Next")))
                if el_next: 
                    driver.get(urljoin(self._SITE_URL, el_next.get_attribute('href')))                    
                else: break
                
            if not entries: raise ExtractorError("cant find any video")
            
            return {
                '_type': 'playlist',
                'id': playlist_id,
                'title': sanitize_filename(_title, restricted=True),
                'entries': entries,
            }
            
            
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)} {str(e)} \n{'!!'.join(lines)}")
            if "ExtractorError" in str(e.__class__): raise
            else: raise ExtractorError(str(e))            
        finally:
            try:
                self.rm_dir(driver, tempdir)
            except Exception:
                pass

                

        