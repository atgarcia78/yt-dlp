# coding: utf-8
from __future__ import unicode_literals

import random
import urllib.parse
import re

from .common import InfoExtractor
from ..utils import (
    multipart_encode,
    ExtractorError,
    clean_html,
    get_element_by_class)


class SlamRushBaseIE(InfoExtractor):
    _LOGIN_URL = "https://slamrush.com/sign-in"
    _LOG_OUT_URL = "https://slamrush.com/sign-out"
    _SITE_URL = "https://slamrush.com"
    _ENTER_URL = "https://slamrush.com/enter"
    _WARNING_URL = "https://slamrush.com/warning"
    _AUTH_URL = "https://slamrush.com/authorize2"
    _ABORT_URL = "https://slamrush.com/multiple-sessions/abort"
    _MULT_URL = "https://slamrush.com/multiple-sessions"
    _NETRC_MACHINE = 'slamrush'

    def __init__(self):
        self.headers = dict()

    
    def islogged(self):

        webpage, _ = self._download_webpage_handle(
            self._SITE_URL,
            None,
            None
        )

        return ("Logout" in webpage)
    
    def _login(self):

        self.username, self.password = self._get_login_info()
    
        self.report_login()
        
        if not self.username or not self.password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)
        
        self._set_cookie('slamrush.com', 'pp-accepted', 'true')

        self._download_webpage(
            self._SITE_URL,
            None,
            'Downloading site page',
                
        )

        self.cookies = self._get_cookies(self._LOGIN_URL)

        data = {
            "username": self.username,
            "password": self.password,
            "_csrf-token": urllib.parse.unquote(self.cookies['X-EMA-CSRFToken'].coded_value)
        }

        
        boundary = "-----------------------------" + str(random.randrange(11111111111111111111111111111, 99999999999999999999999999999))
        
        out, content = multipart_encode(data, boundary)
        login_page, url_handle = self._download_webpage_handle(
            self._LOGIN_URL,
            None,
            'Log in request',
            data=out,
            headers={
                "Referer": self._LOGIN_URL,
                "Origin": self._SITE_URL,
                "Content-Type": content,

            }
        )

        if self._AUTH_URL in url_handle.geturl():
            data = {
                "email": "a.tgarc@gmail.com",
                "last-name": "Torres",
                "_csrf-token": urllib.parse.unquote(self.cookies['X-EMA-CSRFToken'].coded_value)
            }
            out, content = multipart_encode(data, boundary)
            auth_page, url_handle = self._download_webpage_handle(
                self._AUTH_URL,
                None,
                "Log in ok after auth2",
                data=out,
                headers={
                    "Referer": self._AUTH_URL,
                    "Origin": self._SITE_URL,
                    "Content-Type": content,
 
                }
            )
        
        if self._LOGIN_URL in url_handle.geturl():
            error = clean_html(get_element_by_class('login-error', login_page))
            if error:
                raise ExtractorError(
                    'Unable to login: %s' % error, expected=True)
            raise ExtractorError('Unable to log in')

        elif self._MULT_URL in url_handle.geturl():
            abort_page, url_handle = self._download_webpage_handle(
                self._ABORT_URL,
                None,
                "Log in ok after abort sessions",
                headers={
                    "Referer": self._MULT_URL,
 
                }
            )

        
    def _log_out(self):
        logout_page, url_handle = self._download_webpage_handle(
                    self._LOG_OUT_URL,
                    None,
                    'Log out'
                )
      
        if (url_handle.geturl() == self._MULT_URL):
                abort_page, url_handle = self._download_webpage_handle(
                    self._ABORT_URL,
                    None,
                    headers={
                        "Referer": self._MULT_URL,
                    }
                )
 
class SlamRushIE(SlamRushBaseIE):
    IE_NAME = 'slamrush'
    _API_TOKEN = "https://videostreamingsolutions.net/api:ov-embed/parseToken?token="
    _API_MANIFEST = "https://videostreamingsolutions.net/api:ov-embed/manifest/"
    _VALID_URL = r"https://videostreamingsolutions.net/embed/"

    
   
    def _real_extract(self, url):

        vembed_page, _ = self._download_webpage_handle(url, None, "Downloaging video embed page", headers={'Referer' : self._SITE_URL})
        regex_token = r"token: \'(?P<tokenid>.*?)\'"
        mobj = re.search(regex_token, vembed_page)
        tokenid = mobj.group("tokenid")
        #print(tokenid)
        info = self._download_json(self._API_TOKEN + tokenid, None)
        #print(info)
        videoid = info['xdo']['video']['id']            
        
        manifestid = info['xdo']['video']['manifest_id']
        manifesturl = self._API_MANIFEST + manifestid + "/manifest.m3u8"

        #print(manifesturl)

        formats_m3u8 = self._extract_m3u8_formats(
                 manifesturl, None, m3u8_id="hls", ext="mp4", entry_protocol="m3u8", fatal=False
            )
        self._sort_formats(formats_m3u8)

        #print(formats_m3u8)

        return({
            "_type" : "video",
            "id" : str(videoid),
            "formats" : formats_m3u8,
        })
     



class SlamRushPlaylistIE(SlamRushBaseIE):
    IE_NAME = 'slamrush:playlist'
    _VALID_URL = r"https?://(?:www\.)?slamrush.com"

    def _real_initialize(self):
        
        self._set_cookie('slamrush.com', 'pp-accepted', 'true')
        
        self.islogged()
        
        # if not self.islogged():
        #      self._login()
        # else:
        #      self.username, self.password = self._get_login_info() 
        

    def _real_extract(self, url):
       

        webpage, _ = self._download_webpage_handle(url, None, "Downloading playlist webpage")

        if not webpage:
            raise ExtractorError("webpage don't work")

        video_embed_list =  re.findall(r"episodePlayer: ?\'([^\']+)\'", webpage)
        video_title_list = re.findall(r"class=\"name\">([^<]+)<", webpage)
    
        if len(video_embed_list) != len(video_title_list):
            raise ExtractorError("doesnt match number of embed videos with number of titles")        
        
        entries = []

        for url_embed, title in zip(video_embed_list,video_title_list):

            
            entries.append({
                "_type" : "url_transparent",
                "url": url_embed,
                "title": title.replace("\n","").replace("\t","").replace(" ","_"),
                "ie_key" : SlamRushIE.ie_key()
            })
    

        return self.playlist_result(entries, "SlamRush" )
