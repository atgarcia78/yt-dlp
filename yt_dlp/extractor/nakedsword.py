from __future__ import unicode_literals

import re
import threading

from .commonwebdriver import SeleniumInfoExtractor
from ..utils import (
    ExtractorError,
    sanitize_filename,
    std_headers,
    try_get
)

from threading import Lock
import traceback
import sys

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import httpx

import json
from urllib.parse import quote, unquote

from collections import OrderedDict

from concurrent.futures import ThreadPoolExecutor

from queue import Queue
class NakedSwordBaseIE(SeleniumInfoExtractor):
    IE_NAME = 'nakedsword'
    IE_DESC = 'nakedsword'
    
    _SITE_URL = "https://nakedsword.com/"
    _LOGIN_URL = "https://nakedsword.com/signin"
    _LOGOUT_URL = "https://nakedsword.com/signout"
    _NETRC_MACHINE = 'nakedsword'

    def _headers_ordered(self, extra=None):
        _headers = OrderedDict()
        
        if not extra: extra = dict()
        
        for key in ["User-Agent", "Accept", "Accept-Language", "Accept-Encoding", "Content-Type", "X-Requested-With", "Origin", "Connection", "Referer", "Upgrade-Insecure-Requests"]:
        
            value = extra.get(key) if extra.get(key) else std_headers.get(key)
            if value:
                _headers[key.lower()] = value
      
        
        return _headers
    

    
    def _login(self):
        
        self.report_login()
        username, password = self._get_login_info()
        if not username or not password:
            self.raise_login_required(
                'A valid %s account is needed to access this media.'
                % self._NETRC_MACHINE)            

        driver = self.get_driver()
        try:
            driver.get(self._SITE_URL)
            if driver.current_url == "https://nakedsword.com/members":
                self.to_screen("Login OK")
                return driver.get_cookies()
                
            driver.get(self._LOGIN_URL)
            
            el_username = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#SignIn_login.SignInFormInput.SignInFormUsername")))
            el_psswd = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#SignIn_password.SignInFormInput.SignInFormPassword")))
            el_submit = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input.button.expanded.SignInBtnSubmit")))
            self.wait_until(driver, 2, ec.title_is("DUMMYFORWAIT"))
            el_username.send_keys(username)
            self.wait_until(driver, 2, ec.title_is("DUMMYFORWAIT"))
            el_psswd.send_keys(password)
            self.wait_until(driver, 2, ec.title_is("DUMMYFORWAIT"))
            el_submit.submit()
            self.wait_until(driver, 60, ec.url_changes(self._LOGIN_URL))
            if driver.current_url == "https://nakedsword.com/members":
                self.to_screen("Login OK")
                return driver.get_cookies()
            else: raise ExtractorError("login nok")
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(f"login nok: {repr(e)}")
        finally:
            self.rm_driver(driver)
                    


        
    def get_entries_scenes(self, url):
        
        entries = []
        webpage = self._download_webpage(url, None, "Downloading web page playlist", fatal=False)
        if webpage:  
                        
            videos_paths = re.findall(
                r"<div class='SRMainTitleDurationLink'><a href='/([^\']+)'>",
                webpage)     
            
            if videos_paths:
                
                for video in videos_paths:
                    _urlscene = self._SITE_URL + video
                    res = NakedSwordSceneIE._get_info(_urlscene)
                    if res:
                        _id = res.get('id')
                        _title = res.get('title')
                    entry = self.url_result(_urlscene, ie=NakedSwordSceneIE.ie_key(), video_id=_id, video_title=_title)
                    entries.append(entry)
 
        return entries
    
    def get_entries_movies(self, url):
        
        entries = []
        webpage = self._download_webpage(url, None, "Downloading web page playlist", fatal=False)
        if webpage:  
                        
            videos_paths = re.findall(
                r"<div class='BoxResultsLink'><a href='/([^\']+)'>",
                webpage)     
            
            if videos_paths:
                
                for video in videos_paths:
                    _urlmovie = self._SITE_URL + video                    
                    entry = self.url_result(_urlmovie, ie=NakedSwordMovieIE.ie_key())
                    entries.append(entry)
 
        return entries
        
class NakedSwordSceneIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:scene'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<movieid>[\d]+)/(?P<title>[^\/]+)/scene/(?P<id>[\d]+)/?$"

    _LOCK = Lock()
    _COOKIES = {}
    
    @staticmethod
    def _get_info(url, _res=None):       
        
        if not _res:
            count = 0
            while count < 3:
                try:
                    _res = httpx.get(url)
                    if _res.status_code < 400:         
                        res = re.findall(r"class=\'M(?:i|y)MovieTitle\'[^\>]*\>([^\<]*)<[^\>]*>[^\w]+(Scene[^\<]*)\<", _res.text)
                        res2 = re.findall(r"\'SCENEID\'content\=\'([^\']+)\'", _res.text.replace(" ",""))
                        if res and res2: break
                        else: count += 1
                        
                    else: count += 1
                except Exception as e:
                    count += 1 
        else:
            
            res = re.findall(r"class=\'M(?:i|y)MovieTitle\'[^\>]*\>([^\<]*)<[^\>]*>[^\w]+(Scene[^\<]*)\<", _res.text)
            res2 = re.findall(r"\'SCENEID\'content\=\'([^\']+)\'", _res.text.replace(" ",""))
            if res and res2: count = 0
            else: count = 3
                           
        
        return({'id': res2[0], 'title': sanitize_filename(f'{res[0][0]}_{res[0][1].lower().replace(" ","_")}', restricted=True)} if count < 3 else None)
    
    def _get_url(self, client, url, headers):
        count = 0
        while count < 3:
            try:
                _res = client.get(url, headers=headers)
                if _res.status_code < 400: break
                else: count += 1
            except Exception as e:
                count += 1
        return(_res if count < 3 else None)
    
    def _get_formats(self, client, url, stream_url, _type):
        
        _headers_json = self._headers_ordered({"Referer": url, "X-Requested-With": "XMLHttpRequest",  "Content-Type" : "application/json",
                                                "Accept": "application/json, text/javascript, */*; q=0.01"})
        _headers_mpd = self._headers_ordered({"Accept": "*/*", "Origin": "https://nakedsword.com", "Referer": self._SITE_URL})
        
        try:
                    
            res = self._get_url(client, stream_url, _headers_json)
            if not res or not res.content: raise ExtractorError("Cant get stream url info")
            #self.to_screen(f"{res.request} - {res} - {res.request.headers} - {res.headers} - {res.content}")
            info_json = res.json()
            if not info_json: raise ExtractorError("Can't get json")                                                     
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{type(e)}: {str(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f"Cant get json info - {str(e)}")
            
        
                
        #self.to_screen(info_json)
        mpd_url = info_json.get("StreamUrl") 
        if not mpd_url: raise ExtractorError("Can't find url mpd")    
        #self.to_screen(mpd_url) 
        #NakedSwordSceneIE._COOKIES = client.cookies      
        
        try:
            res = self._get_url(client, mpd_url, _headers_mpd)
            #self.to_screen(f"{res.request} - {res} - {res.headers} - {res.request.headers} - {res.content}")
            if not res or not res.content: raise ExtractorError("Cant get mpd info")
            
            mpd_doc = (res.content).decode('utf-8', 'replace')
            if _type == "dash":
                mpd_doc = self._parse_xml(mpd_doc, None)
            #self.to_screen(mpd_doc)
            if not mpd_doc: raise ExtractorError("Cant get mpd doc") 
                
            if _type == "m3u8":
                formats, subtitles = self._parse_m3u8_formats_and_subtitles(mpd_doc, mpd_url, ext="mp4", entry_protocol="m3u8_native", m3u8_id="hls")
            elif _type == "dash":
                formats = self._parse_mpd_formats(mpd_doc, mpd_id="dash", mpd_url=mpd_url, mpd_base_url=(mpd_url.rsplit('/', 1))[0])
                
            if not formats: raise ExtractorError("Cant get formats") 
            
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{type(e)}: {str(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f"Cant get formats {_type} - {str(e)}") 
            
               
        
        return formats               
                
    def _real_extract(self, url):

        try:
            
            _headers = self._headers_ordered({"Upgrade-Insecure-Requests": "1"})
            _timeout = httpx.Timeout(60, connect=60)        
            _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
            _verify = not self._downloader.params.get('nocheckcertificate')
            client = httpx.Client(timeout=_timeout, limits=_limits, headers=_headers, verify=_verify)
            client.cookies.set("ns_pfm", "True", "nakedsword.com")
        
            with NakedSwordSceneIE._LOCK:
                if not NakedSwordSceneIE._COOKIES:
                    try:
                        
                        NakedSwordSceneIE._COOKIES = self._login()
                        
                    except Exception as e:
                        self.to_screen(f"{repr(e)}")
                        raise
                
                for cookie in NakedSwordSceneIE._COOKIES:
                    if cookie['name'] in ("ns_auth", "ns_pk"):
                        client.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
                
        
        
            res = self._get_url(client, url, _headers)
            info_video = self._get_info(url, res)
            if not info_video: raise ExtractorError("Can't find sceneid")
                          
            scene_id = info_video.get('id')
            if not scene_id: raise ExtractorError("Can't find sceneid")
            
            stream_url = "/".join(["https://nakedsword.com/scriptservices/getstream/scene", str(scene_id)])                                   
            
            with ThreadPoolExecutor(thread_name_prefix="nakedsword", max_workers=2) as ex:
                # futs = [ex.submit(self._get_formats, client, url, "/".join([stream_url, "HLS"]), "m3u8"), 
                #        ex.submit(self._get_formats, client, url, "/".join([stream_url, "DASH"]), "dash")]
                futs = [ex.submit(self._get_formats, client, url, "/".join([stream_url, "HLS"]), "m3u8")]
                
            formats = []
            for _fut in futs:
                try:
                    formats += _fut.result()
                except Exception as e:
                    self.to_screen(f"{repr(e)}")
                   
            
            self._sort_formats(formats) 
            
            return {
                "id": scene_id,
                "title": info_video.get('title'),
                "formats": formats,
                "ext": "mp4"
            }
 
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            client.close()

        

class NakedSwordMovieIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:movie:playlist'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<id>[\d]+)/(?P<title>[a-zA-Z\d_-]+)/?$"
    _MOVIES_URL = "https://nakedsword.com/movies/"


    def _real_extract(self, url):

        playlist_id, title = self._match_valid_url(url).group('id', 'title')
        
        webpage = self._download_webpage(url, playlist_id, "Downloading web page playlist")

        pl_title = self._html_search_regex(r'(?s)<title>(?P<title>.*?)<', webpage, 'title', group='title').split(" | ")[1]

        scenes_paths = re.findall(rf'{title}/scene/([\d]+)', webpage)

        entries = []
        for scene in scenes_paths:
            _urlscene = self._MOVIES_URL + playlist_id + "/" + title + "/" + "scene" + "/" + scene
            res = NakedSwordSceneIE._get_info(_urlscene)
            if res:
                _id = res.get('id')
                _title = res.get('title')
            entry = self.url_result(_urlscene, ie=NakedSwordSceneIE.ie_key(), video_id=_id, video_title=_title)
            entries.append(entry)

        return {
            '_type': 'playlist',
            'id': playlist_id,
            'title': sanitize_filename(pl_title, True),
            'entries': entries,
        }

class NakedSwordMostWatchedIE(NakedSwordBaseIE):
    IE_NAME = "nakedsword:mostwatched:playlist"
    _VALID_URL = r'https?://(?:www\.)?nakedsword.com/most-watched/?'
    _MOST_WATCHED = 'https://nakedsword.com/most-watched?content=Scenes&page='
    
    def _real_extract(self, url):      
       

        entries = []

        with ThreadPoolExecutor(thread_name_prefix="nakedsword", max_workers=5) as ex:
            
            futures = [ex.submit(self.get_entries_scenes, f"{self._MOST_WATCHED}{i}") for i in range(1, 3)]
        
        for fut in futures:
            try:
                entries += fut.result()
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')  
                raise ExtractorError(repr(e)) from e
        
        if entries:
            return {
                '_type': 'playlist',
                'id': "NakedSWord mostwatched",
                'title': "NakedSword mostwatched",
                'entries': entries,
            }


class NakedSwordStarsIE(NakedSwordBaseIE):
    IE_NAME = "nakedsword:stars:playlist"
    _VALID_URL = r'https?://(?:www\.)?nakedsword.com/(?P<typepl>(?:stars|studios))/(?P<id>[\d]+)/(?P<name>[a-zA-Z\d_-]+)/?$'
    _MOST_WATCHED = "?content=Scenes&sort=MostWatched&page="
    _NPAGES = {"stars" : 2, "studios" : 3}
    
    def _real_extract(self, url):     
       
        
        data_list = re.search(self._VALID_URL, url).group("typepl", "id", "name")
        
        entries = []

        with ThreadPoolExecutor(max_workers=5) as ex:
            
            futures = [ex.submit(self.get_entries_scenes, f"{url}{self._MOST_WATCHED}{i}") for i in range(1, self._NPAGES[data_list[0]] + 1)]

        for fut in futures:
            try:
                entries += fut.result()
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f'{repr(e)} \n{"!!".join(lines)}')  
                raise ExtractorError(repr(e)) from e
        

        return {
            '_type': 'playlist',
            'id': data_list[1],
            'title':  f"NSw{data_list[0].capitalize()}_{''.join(w.capitalize() for w in data_list[2].split('-'))}",
            'entries': entries,
        }
        
class NakedSwordPlaylistIE(NakedSwordBaseIE):
    IE_NAME = "nakedsword:playlist"
    _VALID_URL = r'https?://(?:www\.)?nakedsword.com/(?P<id>[^?&]+)$'
    
    
    def _real_extract(self, url):      
       

        entries = []

        webpage = self._download_webpage(url, None, "Downloading web page playlist")
        if webpage: 

            if 'SCENE LIST GRID WRAPPER' in webpage:
                
                entries = self.get_entries_scenes(url)
                
            else:
                
                entries = self.get_entries_movies(url)
                       
        if entries:
            return {
                '_type': 'playlist',
                'id': "NakedSword_Playlist",
                'title': sanitize_filename(self._match_id(url), restricted=True).upper(),
                'entries': entries,
            }
        
        else: raise ExtractorError("No entries")
        
class NakedSwordSearchIE(NakedSwordBaseIE):
    IE_NAME = "nakedsword:searchresult:playlist"
    _VALID_URL = r'https?://(?:www\.)?nakedsword.com/search\?(?P<query>.+)'
    _SEARCH_SITE_URL = 'https://vod.nakedsword.com'
    
    _CATEGORIES = {
        'alt': '687',
        'amateur': '501',
        'anal': '582',
        'asian': '502',
        'auto-fellatio': '621',
        'bareback': '567',
        'bdsm': '511',
        'bear': '561',
        'big-dick': '515',
        'bisexual': '516',
        'black': '503',
        'blowjob': '510',
        'blue-collar': '683',
        'body-builders': '574',
        'boyfriends': '648',
        'brazilian': '651',
        'british': '693',
        'bubble-butt': '653',
        'chubs': '571',
        'classic': '556',
        'compilation': '594',
        'cops': '581',
        'cowboy': '563',
        'cream-pies': '672',
        'creator-content': '710',
        'cumshot': '512',
        'czech': '647',
        'daddy': '681',
        'dildo': '584',
        'double-penetration': '673',
        'euro': '521',
        'exclusive': '709',
        'extreme-penetration': '611',
        'feature': '523',
        'fetish': '505',
        'foot': '524',
        'fratboys': '579',
        'french-speaking': '695',
        'gangbang': '506',
        'gender-queer': '674',
        'gloryhole': '624',
        'hardcore': '596',
        'hidden-camera': '592',
        'high-definition': '685',
        'instructional': '554',
        'international': '559',
        'interracial': '528',
        'japanese-unmosaic': '664',
        'jocks': '562',
        'latin': '514',
        'leather': '555',
        'massage': '686',
        'masturbation': '532',
        'mature': '536',
        'military': '593',
        'model': '646',
        'muscles': '557',
        'new-release': '513',
        'orgies': '537',
        'outdoors': '580',
        'parody': '684',
        'pigs': '649',
        'pissing': '540',
        'pre-condom': '661',
        'prison-sex': '688',
        'punishment': '620',
        'russian': '583',
        'safe-sex': '657',
        'sale-downloads': '698',
        'sale-rentals': '700',
        'sale-streaming': '703',
        'shaving': '542',
        'softcore': '585',
        'spanish-speaking': '544',
        'spanking': '545',
        'str8-bait': '606',
        'straight-for-gay': '659',
        'taboo': '702',
        'threeway': '644',
        'twink': '566',
        'ultra-high-definition': '707',
        'uncut': '604',
        'uniform': '558',
        'vintage': '569',
        'voyeur': '551',
        'vr-3d-360': '706',
        'white-collar': '682',
        'wrestling': '608'}
    
        
    _SETTINGS = {
        'abandonedbuilding': '48146',
        'airplane': '48001',
        'alley': '48002',
        'altar': '48003',
        'arcade': '48098',
        'arena': '48004',
        'artgallery': '48121',
        'athleticcourt': '48125',
        'attic': '48148',
        'balcony': '48005',
        'balletstudio': '48006',
        'bar': '48007',
        'barbershop-salon': '48135',
        'barn': '48008',
        'barracks': '48122',
        'basement': '48009',
        'bathroom': '48010',
        'bathtub': '48011',
        'beach': '48012',
        'bedroom': '48013',
        'boat': '48014',
        'bowlingalley': '48015',
        'boxingring': '48016',
        'bus': '48017',
        'business': '48144',
        'cabin': '48018',
        'cafeteria': '48147',
        'cage': '48019',
        'casino': '48021',
        'cave': '48139',
        'church': '48022',
        'circus': '48100',
        'classroom': '48023',
        'closet': '48024',
        'compilation': '48132',
        'conferenceroom': '48094',
        'constructionsite': '48112',
        'conventioncenter': '48123',
        'couch': '48110',
        'courtroom': '48025',
        'courtyard': '48145',
        'crypt': '48026',
        'diningroom': '48027',
        'doctoroffice': '48028',
        'dojo': '48029',
        'dormroom': '48105',
        'dressingroom': '48030',
        'dungeon': '48031',
        'elevator': '48032',
        'fantasy': '48113',
        'farm': '48114',
        'firestation': '48033',
        'forest': '48108',
        'funeralhome': '48142',
        'gameroom': '48128',
        'garage': '48034',
        'gazebo': '48107',
        'genericroom': '48035',
        'gloryhole': '48136',
        'graveyard': '48117',
        'gym': '48036',
        'hairsalon': '48037',
        'hallway': '48038',
        'hangar': '48131',
        'hardwarestore': '48099',
        'helicopter': '48039',
        'hospitalroom': '48040',
        'hotelroom': '48041',
        'icecreamparlor': '48109',
        'invehicle': '48020',
        'interrogationroom': '48134',
        'jacuzzi': '48042',
        'jailcell': '48043',
        'junkyard': '48111',
        'kitchen': '48044',
        'laboratory': '48045',
        'lake': '48140',
        'laundryroom': '48046',
        'library': '48106',
        'limousine': '48047',
        'liquorstore': '48091',
        'livingroom': '48048',
        'lobby': '48049',
        'lockerroom': '48050',
        'lounge': '48051',
        'massageparlor': '48052',
        'militarybase': '48129',
        'motorhome': '48053',
        'movieset': '48054',
        'nightclub': '48141',
        'office': '48055',
        'onvehicle': '48126',
        'outdoors': '48056',
        'paddedcell': '48057',
        'parkinglot': '48095',
        'patio': '48127',
        'photostudio': '48058',
        'playground': '48104',
        'pool': '48130',
        'poolhall': '48059',
        'pooltable': '48138',
        'poolside': '48060',
        'porch': '48103',
        'pornshop': '48101',
        'publicplace': '48061',
        'radiostudio': '48062',
        'restaurant': '48063',
        'rooftop': '48064',
        'sauna-steamroom': '48065',
        'school': '48066',
        'securityoffice': '48124',
        'sewer': '48096',
        'sexclub': '48067',
        'sexswing': '48115',
        'shed': '48068',
        'shed-shack': '48133',
        'shipcabin': '48069',
        'shootingrange': '48137',
        'shower': '48070',
        'spaceship': '48071',
        'stable': '48072',
        'stage': '48073',
        'staircase': '48102',
        'stairs': '48074',
        'store': '48075',
        'stripclub': '48076',
        'swimmingpool': '48077',
        'tattooparlor': '48078',
        'televisionstudio': '48119',
        'tenniscourt': '48079',
        'tent': '48080',
        'theater': '48081',
        'trailer': '48082',
        'train': '48083',
        'trainstation': '48084',
        'underwater': '48085',
        'van': '48116',
        'waitingroom': '48120',
        'warehouse': '48086',
        'waterfall': '48087',
        'whorehouse': '48088',
        'winecellar': '48089',
        'woods-jungle': '48090',
        'workshop': '48118'}
    _SEX_ACTS = {
        '3-way': '32001',
        'analdaisychain': '32002',
        'analsex': '32005',
        'asstomouth': '32006',
        'asstoothermouth': '32007',
        'blowjob': '32010',
        'bondage': '32012',
        'bootlicking': '32025',
        'breastplay': '32125',
        'bukkake': '32015',
        'casting': '32153',
        'choking': '32017',
        'circlejerk': '32140',
        'clubbing': '32018',
        'cock&ballstorture': '32064',
        'collar&lead-leash': '32026',
        'creampie': '32019',
        'cumswallowing': '32021',
        'cumswap': '32023',
        'deepthroating': '32024',
        'docking': '32102',
        'domination': '32112',
        'doublepenetration': '32028',
        'enema': '32107',
        'exhibitionism': '32108',
        'extremepenetration': '32158',
        'faceslapping': '32034',
        'facesitting': '32035',
        'felching': '32037',
        'fetish': '32138',
        'fingercuffing-anal': '32038',
        'fingercuffing-dp': '32039',
        'fingercuffing-vaginal': '32040',
        'fishhooking': '32101',
        'fisting': '32110',
        'fondling': '32145',
        'foodplay': '32120',
        'footjob': '32044',
        'footplay': '32041',
        'gagging': '32045',
        'gangbang': '32047',
        'gapes': '32048',
        'girlongirlaction': '32049',
        'grinding': '32050',
        'grooming': '32131',
        'hairpulling': '32051',
        'handjob': '32052',
        'humiliation': '32123',
        'jousting': '32054',
        'lactation': '32111',
        'maleonmaleaction': '32149',
        'massage': '32104',
        'masturbation': '32055',
        'modeling': '32105',
        'multiplepops': '32056',
        'nippleplay': '32156',
        'oralsex': '32011',
        'orgy': '32063',
        'pissing': '32066',
        'ponyplay': '32124',
        'punishment': '32067',
        'reversegangbang': '32069',
        'rimjob': '32070',
        'rustytrombone': '32071',
        'self-bondage': '32113',
        'self-fucking': '32143',
        'self-torture': '32154',
        'shaving': '32072',
        'showering-bathing': '32116',
        'sloppyseconds,anal': '32073',
        'smoking': '32118',
        'snowballing': '32075',
        'spanking-paddling': '32076',
        'spitting': '32078',
        'squirting': '32079',
        'straight-to-anal': '32080',
        'strap-on': '32081',
        'stripping': '32126',
        'teabagging': '32083',
        'throatfucking': '32139',
        'tickling': '32084',
        'tittiefucking': '32086',
        'toesucking': '32087',
        'torture': '32115',
        'toyplay-anal': '32089',
        'toyplay-cockandball': '32144',
        'toyplay-doubleanal': '32090',
        'toyplay-doublepenetration': '32091',
        'toyplay-doublevaginal': '32092',
        'toyplay-oral': '32088',
        'toyplay-vaginal': '32093',
        'trampling': '32122',
        'urethraplay': '32142',
        'vaginalsex': '32097',
        'vomiting': '32098',
        'voyeurism': '32109',
        'wet-messy': '32132',
        'whipping': '32099',
        'worship': '32114',
        'wrestling': '32100'}


    _SORTBY = {'scenes': ['Popularity', 'Trending', 'Newest'], 'movies': ['MostWatched', 'Trending', 'Newest', 'Released']}
    
    _CONTENTS = ['movies', 'scenes']    
    
    _PARAMS = {'movies': ['content', 'pages', 'tag', 'star', 'studio', 'videoquality', 'director', 'releasedate'],
               'scenes': ['content', 'pages', 'tag', 'star', 'studio', 'videoquality', 'setting', 'sexact', 'position']}
    
    _STUDIOS = {}
    
    _STARS = {}
    
    @staticmethod
    def get_info_conf():
        with open("/Users/antoniotorres/Projects/common/logs/nakedsword_conf.json", 'r') as file:
            conf = json.load(file)
        return conf
    
    @staticmethod
    def upt_info_conf():
        conf_str = '{"studios": ' + json.dumps(NakedSwordSearchIE._STUDIOS) + ', ' + '"stars": ' + json.dumps(NakedSwordSearchIE._STARS) + '}' 
        with open("/Users/antoniotorres/Projects/common/logs/nakedsword_conf.json", 'w') as file:
            file.write(conf_str)
            
        
    
    
    def get_starid(self, driver, starname):
         
        query = starname.replace(' ', '+')
        url = f"https://vod-classic.nakedsword.com/dispatcher/fts?targetSearchMode=basic&isAdvancedSearch=false&isFlushAdvancedSearchCriteria=false&userQuery={query}d&sortType=Relevance&theaterId=22299&genreId=102&locale=en"
        
        driver.get(url)
        
        elstar = self.wait_until(driver, 60, ec.presence_of_element_located((By.CLASS_NAME, "exactMatchStar")))
        if elstar:
            ela = try_get(elstar.find_elements(By.TAG_NAME, "a"), lambda x: x[0])
            if ela:
                starid = try_get(re.findall(r'starId=(\d+)', ela.get_attribute('href')), lambda x: x[0])
                if starid: 
                    NakedSwordSearchIE._STARS[starname.lower().replace(' ', '').replace("/", "-")] = starid
                    NakedSwordSearchIE._STARS = {_key: NakedSwordSearchIE._STARS[_key] for _key in sorted(NakedSwordSearchIE._STARS)}
                    self.to_screen(NakedSwordSearchIE._STARS)
                    NakedSwordSearchIE.upt_info_conf()
                    return starid
                
    
    def get_studioid(self, driver, studioname):
         
        query = studioname.replace(' ', '+')
        url = f"https://vod-classic.nakedsword.com/dispatcher/fts?targetSearchMode=basic&isAdvancedSearch=false&isFlushAdvancedSearchCriteria=false&userQuery={query}&sortType=Relevance&theaterId=22299&genreId=102&locale=en"
        
        driver.get(url)
        
        elstudio = self.wait_until(driver, 60, ec.presence_of_element_located((By.CLASS_NAME, "exactMatchStudio")))
        if elstudio:
            ela = try_get(elstudio.find_elements(By.TAG_NAME, "a"), lambda x: x[0])
            if ela:
                studioid = try_get(re.findall(r'studioId=(\d+)', ela.get_attribute('href')), lambda x: x[0])
                if studioid: 
                    NakedSwordSearchIE._STUDIOS[studioname.lower().replace(' ', '').replace("/", "-")] = studioid
                    NakedSwordSearchIE._STUDIOS = {_key: NakedSwordSearchIE._STUDIOS[_key] for _key in sorted(NakedSwordSearchIE._STUDIOS)}
                    self.to_screen(NakedSwordSearchIE._STUDIOS)
                    NakedSwordSearchIE.upt_info_conf()
                    return studioid


    def get_scenes_ns(self, urls):
        
                    
        _headers = self._headers_ordered({"Upgrade-Insecure-Requests": "1"})
        _timeout = httpx.Timeout(60, connect=60)        
        _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
        _verify = not self._downloader.params.get('nocheckcertificate')
        client = httpx.Client(timeout=_timeout, follow_redirects=True, limits=_limits, headers=_headers, verify=_verify)
        client.cookies.set("ns_pfm", "True", "nakedsword.com")
        

        def _get_scenes_url(j):
            _driver = self.get_driver()
                        
            try:                
                while True:
                    _pos, _uq = self._urlqueriesqueue.get()
                    if _uq == "KILL": break
                    self.to_screen(f'[get_scenes][{j}][{_pos}/{self._num}] {_uq}')
                    try:
                        _driver.execute_script("window.stop();")
                        _driver.get(_uq[0])
                        el_title = self.wait_until(_driver, 2, ec.presence_of_element_located((By.TAG_NAME, "title")))
                        if not el_title: continue
                        elscenes = self.wait_until(_driver, 60, ec.presence_of_all_elements_located((By.CLASS_NAME, "dts-panel ")))
                        if not elscenes: continue
                        _list_scenes_urls = []
                        for el in elscenes:

                            elinfo = try_get(el.find_elements(By.TAG_NAME, "a"), lambda x: x[0])
                            if not elinfo: continue
                            num_scene = elinfo.text.split(" ")[-1]
                            movie = try_get(re.findall(r'gay/movies/(.+)#', elinfo.get_attribute('href')), lambda x: x[0])
                            if movie and num_scene:
                                _urlscene = f"https://nakedsword.com/movies/{movie}/scene/{num_scene}" 
                                _list_scenes_urls.append((_urlscene, _uq[1], _uq[2]))
                        
                        if not _list_scenes_urls: continue
                        _nw = min((_size:=len(_list_scenes_urls)), 5)
                        
                        def _check_url(_urlsc, _n):
                            try:
                                self.to_screen(f'[get_scenes][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] {_urlsc}')
                                res = client.get(_urlsc[0])
                                res.raise_for_status()
                                if res.text:  self._urlscenesqueue.put_nowait((_urlsc[0], _urlsc[1], _urlsc[2], _n))
                               
                        
                            except Exception as e:
                                self.to_screen(f'[get_scenes][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] error {repr(e)}')
                        
                        with ThreadPoolExecutor(max_workers=_nw) as _ex:               
                            for _k, _elurl in enumerate(_list_scenes_urls):
                                _ex.submit(_check_url, _elurl, _k+1)
                    
                    except Exception as e:
                        lines = traceback.format_exception(*sys.exc_info())
                        self.to_screen(f"[get_scenes][{j}][{_pos}/{self._num}]  {repr(e)}\n{'!!'.join(lines)}")
                
            
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f"[get_scenes][{j}] {repr(e)}\n{'!!'.join(lines)}")
            finally:
                self.rm_driver(_driver)
                self.to_screen(f'[get_scenes][{j}] bye') 

        try:
            
            self._num = len(urls)
            self._urlqueriesqueue = Queue()
            self._urlscenesqueue = Queue()
            for _i, _urlquery in enumerate(urls):
                self._urlqueriesqueue.put_nowait((_i+1, _urlquery))
            n_workers = min(self._num, 5)
            for _ in range(n_workers):
                self._urlqueriesqueue.put_nowait((-1, "KILL"))
            with ThreadPoolExecutor(max_workers=n_workers) as exe:
                for _j in range(n_workers):
                    exe.submit(_get_scenes_url, _j)
                
            return list(self._urlscenesqueue.queue)
        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(f"{repr(e)}")
        finally:
            client.close()
    
    
    def get_movies_ns(self, urls):
        
                    
        _headers = self._headers_ordered({"Upgrade-Insecure-Requests": "1"})
        _timeout = httpx.Timeout(60, connect=60)        
        _limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
        _verify = not self._downloader.params.get('nocheckcertificate')
        client = httpx.Client(timeout=_timeout, follow_redirects=True, limits=_limits, headers=_headers, verify=_verify)
        client.cookies.set("ns_pfm", "True", "nakedsword.com")

        def _get_movies_url(j):
            _driver = self.get_driver()
                        
            try:                
                while True:
                    _pos, _uq = self._urlqueriesqueue.get()
                    if _uq == "KILL": break
                    self.to_screen(f'[get_movies][{j}][{_pos}/{self._num}] {_uq}')
                    try:
                        _driver.execute_script("window.stop();")
                        _driver.get(_uq[0])
                        el_title = self.wait_until(_driver, 2, ec.presence_of_element_located((By.TAG_NAME, "title")))
                        if not el_title: continue
                        elmovies = self.wait_until(_driver, 60, ec.presence_of_all_elements_located((By.CLASS_NAME, "dts-image-overlay-container")))
                        if not elmovies: continue
                        _list_movies_urls = []
                        for el in elmovies:

                            elinfo = try_get(el.find_elements(By.TAG_NAME, "a"), lambda x: x[0])
                            if not elinfo: continue
                            movie = try_get(re.findall(r'gay/movies/(.+)', elinfo.get_attribute('href')), lambda x: x[0])
                            if movie:
                                _urlmovie = f"https://nakedsword.com/movies/{movie}"
                                 
                                _list_movies_urls.append((_urlmovie, _uq[1], _uq[2]))
                        
                        if not _list_movies_urls: continue
                        _nw = min((_size:=len(_list_movies_urls)), 5)
                        
                        def _check_url(_urlmv, _n):
                            try:
                                self.to_screen(f'[get_movies][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] {_urlmv}')
                                res = client.get(_urlmv[0])
                                res.raise_for_status()
                                if 'NakedSword.com | Untitled Page' in res.text: self._urlmoviesqueue.put_nowait((_urlmv[0], _urlmv[1], _urlmv[2], _n))
                        
                            except Exception as e:
                                self.to_screen(f'[get_movies][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] error {repr(e)}')
                        
                        with ThreadPoolExecutor(max_workers=_nw) as _ex:               
                            futures = [_ex.submit(_check_url, _elurl, _k+1) for _k, _elurl in enumerate(_list_movies_urls)]
                    
                    except Exception as e:
                        lines = traceback.format_exception(*sys.exc_info())
                        self.to_screen(f"[get_movies][{j}][{_pos}/{self._num}]  {repr(e)}\n{'!!'.join(lines)}")
                
            
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.to_screen(f"[get_movies][{j}] {repr(e)}\n{'!!'.join(lines)}")
            finally:
                self.rm_driver(_driver)
                self.to_screen(f'[get_movies][{j}] bye') 

        try:
            
            self._num = len(urls)
            self._urlqueriesqueue = Queue()
            self._urlmoviesqueue = Queue()
            for _i, _urlquery in enumerate(urls):
                self._urlqueriesqueue.put_nowait((_i+1, _urlquery))
            n_workers = min(self._num, 5)
            for _ in range(n_workers):
                self._urlqueriesqueue.put_nowait((-1, "KILL"))
            with ThreadPoolExecutor(max_workers=n_workers) as exe:
                for _j in range(n_workers):
                    exe.submit(_get_movies_url, _j)
                
            return list(self._urlmoviesqueue.queue)
        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(f"{repr(e)}")
        finally:
            client.close()
    
       
    def _real_initialize(self):
        conf = NakedSwordSearchIE.get_info_conf()
        NakedSwordSearchIE._STUDIOS = conf['studios']
        NakedSwordSearchIE._STARS = conf['stars']
    
    def _real_extract(self, url):
        
        driver = self.get_driver()
        
        query = re.search(self._VALID_URL, url).group('query')
        
        params = { el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
        
        content = params.get('content', 'scenes')
        
        if params.get('sort'):
            criteria_list = [{'sort': params['sort']}]
        else:
            criteria_list = [{'sort': _sort} for _sort in self._SORTBY[content]]
            
        if (_studio:=params.get('studio')):
            if not (_studioid:=NakedSwordSearchIE._STUDIOS.get(_studio.lower().replace(' ', '').replace('/', '-'))):
                _studioid = self.get_studioid(driver, _studio)
        if (_star:=params.get('star')):
            if not (_starid:=NakedSwordSearchIE._STAR.get(_star.lower().replace(' ', '').replace('/', '-'))):
                _starid = self.get_starid(driver, _star)
        if (_tag:=params.get('tag')):
            _tagid = [int(_id) for el in _tag.split(',') if (_id:=NakedSwordSearchIE._CATEGORIES.get(el))]
        if (_setting:=params.get('setting')):
            _settingid = [int(_id) for el in _setting.split(',') if (_id:=NakedSwordSearchIE._SETTINGS.get(el))]
        if (_sexact:=params.get('sexact')):
            _sexactid = [int(_id) for el in _sexact.split(',') if (_id:=NakedSwordSearchIE._SEX_ACTS.get(el))]
        for criteria in criteria_list:
            if _tag and _tagid: criteria.update({'tagFilters': _tagid})
            if _setting and _settingid and content == 'scenes': criteria.update({'settingFilters': _settingid})
            if _sexact and _sexactid and content == 'scenes': criteria.update({'sexActFilters': _sexactid})
            if _studio and _studioid: criteria.update({'studioFilters': [int(_studioid)]})
            if _star and _starid: criteria.update({'starFilters': [int(_starid)]})
            
        
        criteria_list_str = [json.dumps(criteria).replace(" ", "") for criteria in criteria_list]        
        
        
        maxpages = int(params.get('pages', 5))
        url_query = [(f'https://vod.nakedsword.com/gay/search/{content}/page/{page+1}?criteria={quote(criteria_str)}&viewMode=List', criteria['sort'], page+1) for criteria_str, criteria in zip(criteria_list_str, criteria_list) for page in range(maxpages)]
        self.to_screen(f"url query list[{len(url_query)}]: \n{url_query}")
        url_query_str = '\n'.join([f'{unquote(_el[0])}, {_el[0].split("?")[-1]}' for _el in url_query])
        self.to_screen(f"url query list[{len(url_query)}]: \n{url_query_str}")
        
        #self.to_screen(f"url query: {unquote(url_query[0])} {url_query[0]}")
        
        
        
        try:
            entries = []
            if content == 'scenes':
                list_res = self.get_scenes_ns(url_query)
                self.to_screen(list_res)
                if list_res:
                    list_res_sorted = sorted(list_res, key=lambda x: (NakedSwordSearchIE._SORTBY['scenes'].index(x[1]),x[2], x[3]))
                    self.to_screen(list_res_sorted)
                    list_res_final = []
                    for el in list_res_sorted:
                        if el[0] not in list_res_final: list_res_final.append(el[0])
                    entries = [self.url_result(_urlscene, ie=NakedSwordSceneIE.ie_key()) for _urlscene in list_res_final]
                
            elif content == 'movies':
                #list_res = list(set(self.get_movies_ns(url_query)))
                list_res = self.get_movies_ns(url_query)
                self.to_screen(list_res)
                if list_res:
                    list_res_sorted = sorted(list_res, key=lambda x: (NakedSwordSearchIE._SORTBY['movies'].index(x[1]),x[2], x[3]))
                    self.to_screen(list_res_sorted)
                    list_res_final = []
                    for el in list_res_sorted:
                        if el[0] not in list_res_final: list_res_final.append(el[0])
                    entries = [self.url_result(_urlmovie, ie=NakedSwordMovieIE.ie_key()) for _urlmovie in list_res_final]
                
            if entries:
                return {
                    '_type': 'playlist',
                    'id': "NakedSword_Search_Playlist",
                    'title': "NakedSword_Search_Playlist",
                    'entries': entries,
                }
            
            else: raise ExtractorError("No entries")
        except ExtractorError:
            raise
        except Exception as e:
            self.to_screen(repr(e))
            raise ExtractorError(f"{repr(e)}")
        finally:
            self.rm_driver(driver)
    
            
            
            
