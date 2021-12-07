from __future__ import unicode_literals

import re

from .webdriver import SeleniumInfoExtractor
from ..utils import (
    ExtractorError,
    sanitize_filename,
    std_headers,
    get_value_list_or_none
)

from threading import Lock
import traceback
import sys

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import httpx


from collections import OrderedDict

from concurrent.futures import ThreadPoolExecutor
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
                    _url = self._SITE_URL + video
                    res = NakedSwordSceneIE._get_info(_url)
                    if res:
                        _id = res.get('id')
                        _title = res.get('title')
                    entry = self.url_result(_url, ie=NakedSwordSceneIE.ie_key(), video_id=_id, video_title=_title)
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
                    _url = self._SITE_URL + video                    
                    entry = self.url_result(_url, ie=NakedSwordMovieIE.ie_key())
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
            client = httpx.Client(timeout=60,verify=(not self._downloader.params.get('nocheckcertificate')))
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

        mobj = re.match(self._VALID_URL, url)
        
        playlist_id = mobj.group('id')
        title = mobj.group('title')

        webpage = self._download_webpage(url, playlist_id, "Downloading web page playlist")

        pl_title = self._html_search_regex(r'(?s)<title>(?P<title>.*?)<', webpage, 'title', group='title').split(" | ")[1]

        scenes_paths = re.findall(rf'{title}/scene/([\d]+)', webpage)

        entries = []
        for scene in scenes_paths:
            _url = self._MOVIES_URL + playlist_id + "/" + title + "/" + "scene" + "/" + scene
            res = NakedSwordSceneIE._get_info(_url)
            if res:
                _id = res.get('id')
                _title = res.get('title')
            entry = self.url_result(_url, ie=NakedSwordSceneIE.ie_key(), video_id=_id, video_title=_title)
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
    _VALID_URL = r'https?://(?:www\.)?nakedsword.com/(?P<id>.+)$'
    
    
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
    
    _STUDIOS = {
        'Older4Me': '21563',
        'Bel Ami': '19982',
        'EricVideos': '22988',
        'Boys Halfway House': '22652',
        'Cockyboys': '21970',
        'Dragon Media': '22004',
        'Falcon Studios': '19904',
        'Bareback Network': '23125',
        'Sean Cody': '22816',
        'Active Duty': '9199',
        'Lucas Entertainment': '18773',
        'Dark Alley Media': '20168',
        'Raw Fuck Club': '21699',
        'Corbin Fisher': '21911',
        'William Higgins': '20137',
        'Staxus': '21449',
        'Raunchy Bastards': '22842',
        'Raging Stallion Studios': '15369',
        'Men': '22838',
        'Iconmale': '22478',
        'Missionary Boyz': '22809',
        'Raw Strokes': '21638',
        'CJXXX': '22721',
        'Reality Dudes': '22919'}
    
    _SETTINGS = {
        'Abandoned Building': '48146',
        'Elevator': '48032',
        'Photo Studio': '48058',
        'Airplane': '48001',
        'Fantasy': '48113',
        'Playground': '48104',
        'Alley': '48002',
        'Farm': '48114',
        'Pool': '48130',
        'Altar': '48003',
        'Fire Station': '48033',
        'Pool Hall': '48059',
        'Arcade': '48098',
        'Forest': '48108',
        'Pool Table': '48138',
        'Arena': '48004',
        'Funeral Home': '48142',
        'Poolside': '48060',
        'Art Gallery': '48121',
        'Game Room': '48128',
        'Porch': '48103',
        'Athletic court': '48125',
        'Garage': '48034',
        'Porn Shop': '48101',
        'Attic': '48148',
        'Gazebo': '48107',
        'Public Place': '48061',
        'Balcony': '48005',
        'Generic Room': '48035',
        'Radio Studio': '48062',
        'Ballet Studio': '48006',
        'Gloryhole': '48136',
        'Restaurant': '48063',
        'Bar': '48007',
        'Graveyard': '48117',
        'Rooftop': '48064',
        'Barbershop / Salon': '48135',
        'Gym': '48036',
        'Sauna/Steam Room': '48065',
        'Barn': '48008',
        'Hair Salon': '48037',
        'School': '48066',
        'Barracks': '48122',
        'Hallway': '48038',
        'Security Office': '48124',
        'Basement': '48009',
        'Hangar': '48131',
        'Sewer': '48096',
        'Bathroom': '48010',
        'Hardware Store': '48099',
        'Sex Club': '48067',
        'Bathtub': '48011',
        'Helicopter': '48039',
        'Sex Swing': '48115',
        'Beach': '48012',
        'Hospital Room': '48040',
        'Shed': '48068',
        'Bedroom': '48013',
        'Hotel Room': '48041',
        'Shed/Shack': '48133',
        'Boat': '48014',
        'Ice Cream Parlor': '48109',
        'Ship Cabin': '48069',
        'Bowling Alley': '48015',
        'In Vehicle': '48020',
        'Shooting Range': '48137',
        'Boxing Ring': '48016',
        'Interrogation Room': '48134',
        'Shower': '48070',
        'Bus': '48017',
        'Jacuzzi': '48042',
        'Spaceship': '48071',
        'Business': '48144',
        'Jail Cell': '48043',
        'Stable': '48072',
        'Cabin': '48018',
        'Junkyard': '48111',
        'Stage': '48073',
        'Cafeteria': '48147',
        'Kitchen': '48044',
        'Staircase': '48102',
        'Cage': '48019',
        'Laboratory': '48045',
        'Stairs': '48074',
        'Casino': '48021',
        'Lake': '48140',
        'Store': '48075',
        'Cave': '48139',
        'Laundry Room': '48046',
        'Strip Club': '48076',
        'Church': '48022',
        'Library': '48106',
        'Swimming Pool': '48077',
        'Circus': '48100',
        'Limousine': '48047',
        'Tattoo Parlor': '48078',
        'Classroom': '48023',
        'Liquor Store': '48091',
        'Television Studio': '48119',
        'Closet': '48024',
        'Living Room': '48048',
        'Tennis Court': '48079',
        'Compilation': '48132',
        'Lobby': '48049',
        'Tent': '48080',
        'Conference Room': '48094',
        'Locker Room': '48050',
        'Theater': '48081',
        'Construction Site': '48112',
        'Lounge': '48051',
        'Trailer': '48082',
        'Convention Center': '48123',
        'Massage Parlor': '48052',
        'Train': '48083',
        'Couch': '48110',
        'Military Base': '48129',
        'Train Station': '48084',
        'Courtroom': '48025',
        'Motor Home': '48053',
        'Underwater': '48085',
        'Courtyard': '48145',
        'Movie Set': '48054',
        'Van': '48116',
        'Crypt': '48026',
        'Night Club': '48141',
        'Waiting Room': '48120',
        'Dining Room': '48027',
        'Office': '48055',
        'Warehouse': '48086',
        'Doctor Office': '48028',
        'On Vehicle': '48126',
        'Waterfall': '48087',
        'Dojo': '48029',
        'Outdoors': '48056',
        'Whorehouse': '48088',
        'Dorm Room': '48105',
        'Padded Cell': '48057',
        'Wine Cellar': '48089',
        'Dressing Room': '48030',
        'Parking Lot': '48095',
        'Woods/Jungle': '48090',
        'Dungeon': '48031',
        'Patio': '48127',
        'Workshop': '48118'}
    
    _SEX_ACTS = {
        '3-Way': '32001',
        'Fisting': '32110',
        'Shaving': '32072',
        'Anal Daisy Chain': '32002',
        'Fondling': '32145',
        'Showering/Bathing': '32116',
        'Anal Sex': '32005',
        'Food Play': '32120',
        'Sloppy Seconds, Anal': '32073',
        'Ass To Mouth': '32006',
        'Footjob': '32044',
        'Smoking': '32118',
        'Ass To Other Mouth': '32007',
        'Footplay': '32041',
        'Snow Balling': '32075',
        'Blowjob': '32010',
        'Gagging': '32045',
        'Spanking/Paddling': '32076',
        'Bondage': '32012',
        'GangBang': '32047',
        'Spitting': '32078',
        'Boot Licking': '32025',
        'Gapes': '32048',
        'Squirting': '32079',
        'Breast Play': '32125',
        'Girl on Girl action': '32049',
        'Straight-To-Anal': '32080',
        'Bukkake': '32015',
        'Grinding': '32050',
        'Strap-On': '32081',
        'Casting': '32153',
        'Grooming': '32131',
        'Stripping': '32126',
        'Choking': '32017',
        'Hair Pulling': '32051',
        'Teabagging': '32083',
        'Circle Jerk': '32140',
        'Handjob': '32052',
        'Throat Fucking': '32139',
        'Clubbing': '32018',
        'Humiliation': '32123',
        'Tickling': '32084',
        'Cock & Balls Torture': '32064',
        'Jousting': '32054',
        'Tittie Fucking': '32086',
        'Collar & Lead/Leash': '32026',
        'Lactation': '32111',
        'Toe Sucking': '32087',
        'Creampie': '32019',
        'Male On Male Action': '32149',
        'Torture': '32115',
        'Cum Swallowing': '32021',
        'Massage': '32104',
        'Toy Play - Anal': '32089',
        'Cum Swap': '32023',
        'Masturbation': '32055',
        'Toy Play - Cock and Ball': '32144',
        'Deep Throating': '32024',
        'Modeling': '32105',
        'Toy Play - Double Anal': '32090',
        'Docking': '32102',
        'Multiple Pops': '32056',
        'Toy Play - Double Penetration': '32091',
        'Domination': '32112',
        'Nipple Play': '32156',
        'Toy Play - Double Vaginal': '32092',
        'Double Penetration': '32028',
        'Oral Sex': '32011',
        'Toy Play - Oral': '32088',
        'Enema': '32107',
        'Orgy': '32063',
        'Toy Play - Vaginal': '32093',
        'Exhibitionism': '32108',
        'Pissing': '32066',
        'Trampling': '32122',
        'Extreme Penetration': '32158',
        'PonyPlay': '32124',
        'Urethra Play': '32142',
        'Face Slapping': '32034',
        'Punishment': '32067',
        'Vaginal Sex': '32097',
        'Facesitting': '32035',
        'Reverse Gangbang': '32069',
        'Vomiting': '32098',
        'Felching': '32037',
        'Rim Job': '32070',
        'Voyeurism': '32109',
        'Fetish': '32138',
        'Rusty Trombone': '32071',
        'Wet / Messy': '32132',
        'Fingercuffing - Anal': '32038',
        'Self-Bondage': '32113',
        'Whipping': '32099',
        'Fingercuffing - DP': '32039',
        'Self-Fucking': '32143',
        'Worship': '32114',
        'Fingercuffing - Vaginal': '32040',
        'Self-Torture': '32154',
        'Wrestling': '32100',
        'Fishhooking': '32101'}
        
        
    

    

    def get_starid(self, driver, starname):
         
        query = starname.replace(' ', '+')
        url = f"https://vod-classic.nakedsword.com/dispatcher/fts?targetSearchMode=basic&isAdvancedSearch=false&isFlushAdvancedSearchCriteria=false&userQuery={query}d&sortType=Relevance&theaterId=22299&genreId=102&locale=en"
        
        driver.get(url)
        
        elstar = self.wait_until(driver, 30, ec.presence_of_element_located((By.CLASS_NAME, "exactMatchStar")))
        if elstar:
            ela = get_value_list_or_none(elstar.find_elements(By.TAG_NAME, "a"))
            if ela:
                starid = get_value_list_or_none(re.findall(r'starId=(\d+)', ela.get_attribute('href')))
        
        
    

    def get_scenes_ns(self, driver, urls):
        list_scenes_urls = []

        for url in urls:

            driver.get(url)
            elscenes = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CLASS_NAME, "dts-panel ")))
            if not elscenes: continue
            for el in elscenes:

                elinfo = get_value_list_or_none(el.find_elements(By.TAG_NAME, "a"))
                if not elinfo: continue
                num_scene = elinfo.text.split(" ")[-1]
                movie = get_value_list_or_none(re.findall(r'gay/movies/(.+)#', elinfo.get_attribute('href')))
                if movie and num_scene:
                    _url = f"https://nakedsword.com/movies/{movie}/scene/{num_scene}"                
                    try:
                        res = httpx.get(_url, timeout=30)
                        res.raise_for_status()
                        if res.text:  list_scenes_urls.append(_url)
                        
                    except Exception as e:
                        self.to_screen(repr(e))
        
        return (list_scenes_urls)
    
    def get_movies_ns(self, driver, urls):
        list_movies_urls = []

        for url in urls:

            driver.get(url)
            elmovies = self.wait_until(driver, 30, ec.presence_of_all_elements_located((By.CLASS_NAME, "dts-image-overlay-container")))
            if not elmovies: continue
            for el in elmovies:

                elinfo = get_value_list_or_none(el.find_elements(By.TAG_NAME, "a"))
                if not elinfo: continue
                movie = get_value_list_or_none(re.findall(r'gay/movies/(.+)', elinfo.get_attribute('href')))
                if movie:
                    _url = f"https://nakedsword.com/movies/{movie}"
                    try:
                        res = httpx.get(_url, timeout=30)
                        res.raise_for_status()
                        if res.text:  list_movies_urls.append(_url)
                        
                    except Exception as e:
                        self.to_screen(repr(e))

        return (list_movies_urls)

