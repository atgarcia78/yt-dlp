from __future__ import unicode_literals

import json
import re
import sys
import traceback
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Lock
from urllib.parse import quote, unquote
import html


from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_0_1, By, ec, HTTPStatusError


class NakedSwordBaseIE(SeleniumInfoExtractor):

    
    _SITE_URL = "https://nakedsword.com/"
    _LOGIN_URL = "https://nakedsword.com/signin"
    _LOGOUT_URL = "https://nakedsword.com/signout"
    _NETRC_MACHINE = 'nakedsword'
    
    _LOCK = Lock()
    _COOKIES = {}
    _NSINIT = False
    

    def _headers_ordered(self, extra=None):
        _headers = OrderedDict()
        
        if not extra: extra = dict()
        
        for key in ["User-Agent", "Accept", "Accept-Language", "Accept-Encoding", "Content-Type", "X-Requested-With", "Origin", "Connection", "Referer", "Upgrade-Insecure-Requests"]:
        
            value = extra.get(key) if extra.get(key) else NakedSwordBaseIE._CLIENT_CONFIG['headers'].get(key.lower())
            if value:
                _headers[key.lower()] = value
      
        
        return _headers
    
    @dec_on_exception
    @dec_on_exception2
    @dec_on_exception3
    @limiter_0_1.ratelimit("nakedsword", delay=True)
    def _send_request(self, url, driver=None, _type="GET", data=None, headers=None):
        
        if not driver:
            
            try:
                return(self.send_http_request(url, _type=_type, data=data, headers=headers))

            except HTTPStatusError as e:
                self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")
        else:
            driver.execute_script("window.stop();")
            driver.get(url)
            

    def _get_info(self, anystr):       
        
        if anystr.startswith('http'):

            webpage = try_get(self._send_request(anystr), lambda x: x.text if x else '')
            
        else:
            webpage = anystr
        
        if webpage:   
            res = re.findall(r"class=\'M(?:i|y)MovieTitle\'[^\>]*\>([^\<]*)<[^\>]*>[^\w]+(Scene[^\<]*)\<", webpage)
            res2 = re.findall(r"\'SCENEID\'content\=\'([^\']+)\'", webpage.replace(" ",""))

            if res and res2:
                return({'id': res2[0], 'title': sanitize_filename(f'{res[0][0]}_{res[0][1].lower().replace(" ","_")}', restricted=True)} if res and res2 else None)

    def get_entries_scenes(self, url, page=None, func=None):
        
        entries = []
        
        try:
            premsg = f"[get_entries_scenes]"
            if page: premsg = f"{premsg}[page {page}]"
            self.report_extraction(f"{premsg} {url}")
            #webpage = self._download_webpage(url, None, None, fatal=False)
            webpage = try_get(self._send_request(url), lambda x: re.sub('[\t\n]','', html.unescape(x.text)) if x else None)
            
            if webpage:  
                            
                videos_paths = re.findall(
                    r"<div class='SRMainTitleDurationLink'><a href='/([^\']+)'>",
                    webpage)     
                
                if videos_paths:
                    
                    list_urlscenes = [f"{self._SITE_URL}{video}" for video in videos_paths]
                    if func:
                        list_urlscenes = list(filter(func, list_urlscenes))
                    
                    self.logger_debug(f"{premsg} scenes found [{len(list_urlscenes)}]: \n{list_urlscenes}")
                    
                    if list_urlscenes:               
                        with ThreadPoolExecutor(thread_name_prefix="nsgetscenes", max_workers=min(len(list_urlscenes), 10)) as exe:                                     
                            
                            futures = {exe.submit(self._get_entry, _urlscene, _type="m3u8", msg=premsg): _urlscene for _urlscene in list_urlscenes}

                        for fut in futures:
                            try:
                                _entry = fut.result()
                                if not _entry: raise ExtractorError("no entry")
                                _entry.update({'original_url': url})
                                entries.append(_entry)
                            except Exception as e:
                                self.report_warning(f"[get_entries_scenes] {url} - {futures[fut]} error - {repr(e)}")                                             
    
            return entries
        except Exception as e:
            self.report_warning(f"[get_entries_scenes] {url} error - {repr(e)}")
    
    def get_entries_movies(self, url):
        
        entries = []
        webpage = try_get(self._send_request(url), lambda x: re.sub('[\t\n]','', html.unescape(x.text)) if x else None)
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
    
    def _get_entry(self, url, **kwargs):        
        
        _headers_json = self._headers_ordered({"Referer": url, "X-Requested-With": "XMLHttpRequest",  "Content-Type" : "application/json", "Accept": "application/json, text/javascript, */*; q=0.01"})
        _headers_mpd = self._headers_ordered({"Accept": "*/*", "Origin": "https://nakedsword.com", "Referer": self._SITE_URL})        
        _type_dict = {'m3u8': 'HLS', 'dash': 'DASH'}
        
        
        _type = kwargs.get('_type', 'm3u8')
        msg = kwargs.get('msg')
        
        try:
            premsg = f"[get_entry]"
            if msg: premsg = f"{msg}{premsg}"
            self.logger_debug(f"{premsg} start to get entry")
            
            info_video = self._get_info(url)
            if not info_video: raise ExtractorError(f"{premsg}: error - Can't get video info")
                          
            scene_id = info_video.get('id')
            _title = info_video.get('title')
            
            premsg = f"{premsg}[{scene_id}][{_title}]"
            
            getstream_url = "/".join(["https://nakedsword.com/scriptservices/getstream/scene", str(scene_id), _type_dict[_type]]) 
                    
            self.logger_debug(f"{premsg} [getstream_url] {getstream_url}")
            info_json = try_get(self._send_request(getstream_url, headers=_headers_json), lambda x: x.json() if x else None)
            if not info_json: raise ExtractorError(f"{premsg}: error - Cant get json")
            mpd_url = info_json.get("StreamUrl") 
            if not mpd_url: raise ExtractorError(f"{premsg}: error - Can't find stream url")
            mpd_doc = try_get(self._send_request(mpd_url, headers=_headers_mpd), lambda x: (x.content).decode('utf-8', 'replace') if x else None)
            if not mpd_doc: raise ExtractorError(f"{premsg}: error - Cant get mpd doc") 
            # if _type == "dash":
            #     mpd_doc = self._parse_xml(mpd_doc, None)

            # @dec_on_exception
            # def _extract_formats():               
            #     if _type == "m3u8":
            #         return(self._extract_m3u8_formats(mpd_url, scene_id, ext="mp4", m3u8_id="hls", headers=_headers_mpd))
            #     elif _type == "dash":
            #         return(self._extract_mpd_formats(mpd_url, scene_id, mpd_id="dash", headers=_headers_mpd))
                
            # formats = _extract_formats()
            
            if _type == "m3u8":
                formats, _ = self._parse_m3u8_formats_and_subtitles(mpd_doc, mpd_url, ext="mp4", m3u8_id="hls", headers=_headers_mpd)
            # elif _type == "dash":
            #     formats = self._parse_mpd_formats(mpd_doc, mpd_url, scene_id, mpd_id="dash", headers=_headers_mpd)
            
            
            if formats:
                self._sort_formats(formats)
            
                _entry = {
                    "id": scene_id,
                    "title": _title,
                    "formats": formats,
                    "ext": "mp4",
                    "webpage_url": url,
                    "extractor_key": 'NakedSwordScene',
                    "extractor": 'nakedswordscene'
                }
            
                self.to_screen(f"{premsg}: OK got entry")
                return _entry
            
        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(f'{premsg}: error - {repr(e)}')
       
       
    def _is_logged(self, driver):
        
        self._send_request(self._SITE_URL, driver)
        logged_ok = driver.current_url == "https://nakedsword.com/members"
        self.logger_debug(f"[is_logged] {logged_ok}")
        return(logged_ok)
        
    
    def _login(self):
        

        driver = self.get_driver()
        try:
            
            if not self._is_logged(driver):

                self.report_login()
                username, password = self._get_login_info()
                if not username or not password:
                    self.raise_login_required(
                        'A valid %s account is needed to access this media.'
                        % self._NETRC_MACHINE)        
                
                self._send_request(self._LOGIN_URL, driver)
                
                el_username = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#SignIn_login.SignInFormInput.SignInFormUsername")))
                el_psswd = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input#SignIn_password.SignInFormInput.SignInFormPassword")))
                el_submit = self.wait_until(driver, 60, ec.presence_of_element_located((By.CSS_SELECTOR, "input.button.expanded.SignInBtnSubmit")))
                self.wait_until(driver, 2)
                el_username.send_keys(username)
                self.wait_until(driver, 2)
                el_psswd.send_keys(password)
                self.wait_until(driver, 2)
                el_submit.submit()
                self.wait_until(driver, 60, ec.url_changes(self._LOGIN_URL))
                if driver.current_url == "https://nakedsword.com/members":
                    self.to_screen("[login] Login OK")
                    return driver.get_cookies()
                else: raise ExtractorError("login nok")
            
            else:
                self.to_screen(f"[login] Already logged")
                return driver.get_cookies()

        finally:
            self.rm_driver(driver)
                    
   
    def _real_initialize(self):
    
        super()._real_initialize()
        
        with NakedSwordBaseIE._LOCK:           
            if not NakedSwordBaseIE._NSINIT:
                NakedSwordBaseIE._CLIENT.cookies.set("ns_pfm", "True", "nakedsword.com")
                
                if not NakedSwordBaseIE._COOKIES:
                    try:                        
                        NakedSwordBaseIE._COOKIES = self._login()
                        
                    except Exception as e:
                        self.report_warning(f"[login] login nok: {repr(e)}")
                        raise ExtractorError(f"[login] login nok: {repr(e)}")
                
                for cookie in NakedSwordBaseIE._COOKIES:
                    if cookie['name'] in ("ns_auth", "ns_pk"):
                        NakedSwordBaseIE._CLIENT.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'])
                    
                NakedSwordBaseIE._NSINIT = True
        
  
    
class NakedSwordSceneIE(NakedSwordBaseIE):
    IE_NAME = 'nakedswordscene'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<movieid>[\d]+)/(?P<title>[^\/]+)/scene/(?P<id>[\d]+)/?$"


    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):

        try:            
            self.report_extraction(url)            
            return self._get_entry(url)
 
        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f'{repr(e)}')
            


class NakedSwordMovieIE(NakedSwordBaseIE):
    IE_NAME = 'nakedsword:movie:playlist'
    _VALID_URL = r"https?://(?:www\.)?nakedsword.com/movies/(?P<id>[\d]+)/(?P<title>[a-zA-Z\d_-]+)/?$"
    _MOVIES_URL = "https://nakedsword.com/movies/"


    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
        
        playlist_id, title = self._match_valid_url(url).group('id', 'title')
        
        webpage = try_get(self._send_request(url), lambda x: re.sub('[\t\n]','', html.unescape(x.text)) if x else None)
        
        if not webpage: raise ExtractorError("Couldnt get webpage")

        pl_title = self._html_search_regex(r'(?s)<title>(?P<title>.*?)<', webpage, 'title', group='title').split(" | ")[1]

        scenes_paths = re.findall(rf'{title}/scene/([\d]+)', webpage)

        entries = []
        for scene in scenes_paths:
            _urlscene = self._MOVIES_URL + playlist_id + "/" + title + "/" + "scene" + "/" + scene
            res = self._get_info(_urlscene)
            if res:
                _id = res.get('id')
                _title = res.get('title')
                entry = self.url_result(_urlscene, ie=NakedSwordSceneIE.ie_key(), video_id=_id, video_title=_title)
                entries.append(entry)

        if entries:
            self.to_screen(f"[get_entries_list][{url}] got entries list OK")
            return {
                '_type': 'playlist',
                'id': playlist_id,
                'title': sanitize_filename(pl_title, True),
                'entries': entries,
            }
        else: raise ExtractorError("no entries")

class NakedSwordMostWatchedIE(NakedSwordBaseIE):
    IE_NAME = "nakedsword:mostwatched:playlist"
    _VALID_URL = r'https?://(?:www\.)?nakedsword.com/most-watched(\?pages=(?P<pages>\d+))?'
    _MOST_WATCHED = 'https://nakedsword.com/most-watched?content=Scenes&page='
    
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):      
       
        pages = try_get(re.search(self._VALID_URL, url), lambda x: x.group('pages')) or "1"
        entries = []
        list_pages = [(i, f"{self._MOST_WATCHED}{i}") for i in range(1, int(pages) + 1)]
        with ThreadPoolExecutor(thread_name_prefix="nakedsword", max_workers=10) as ex:
            
            futures = {ex.submit(self.get_entries_scenes, el[1], el[0]): f"page={el[0]}"  for el in list_pages}
        
        for fut in futures:
            try:
                _res = fut.result()
                if _res:
                    entries += _res
                else: raise ExtractorError("no entries")
            except Exception as e:
                self.report_warning(f'[{url}][{futures[fut]}] {repr(e)}')  
                #raise ExtractorError(repr(e))
        
        if entries:
            return {
                '_type': 'playlist',
                'id': f"nakedsword:mostwatched:pages:{pages}",
                'title': f"nakedsword:mostwatched:pages:{pages}",
                'entries': entries,
            }
        
        else: raise ExtractorError("no entries")


class NakedSwordStarsStudiosIE(NakedSwordBaseIE):
    IE_NAME = "nakedsword:starsstudios:playlist"
    _VALID_URL = r'https?://(?:www\.)?nakedsword.com/(?P<typepl>(?:stars|studios))/(?P<id>[\d]+)/(?P<name>[a-zA-Z\d_-]+)/?\?(?P<query>.+)'
    _MOST_WATCHED = "?content=Scenes&sort=MostWatched&page="
    
    def _get_last_page(self, _urlqbase):
        i = 1
        while(True):
            webpage = try_get(self._send_request(f"{_urlqbase}{i}"), lambda x: html.unescape(x.text))
            if "Next Page" in webpage:
                i += 1
            else:
                break
        return i
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):     
       
        data = try_get(re.search(self._VALID_URL, url), lambda x: x.groupdict())
        query = data.get('query')        
        if query:
            params = { el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
        else:
            params = {}
        npages = params.get('pages', '1')
        if npages != '1':        
            base_url = url.split("?")[0]
            base_url_search = f'{base_url}{self._MOST_WATCHED}'
            last_page = self._get_last_page(base_url_search)

            if npages == 'all': npages = last_page
            elif (_npages:=int(npages)) > last_page:
                npages = last_page
            else:
                npages = _npages or 1
        else: npages = 1
        
        filter_by = params.get('filter_by')
        if filter_by:
            tokens_filter = filter_by.split(',')
            if tokens_filter[0] == 'not':
                func = lambda x: not(re.search(r'%s' % tokens_filter[1].replace(' ','-'), x, re.IGNORECASE) != None)
            else:
                func = lambda x: re.search(r'%s' % tokens_filter[0].replace(' ','-'), x, re.IGNORECASE)
        else: func = None    
                
        entries = []

        with ThreadPoolExecutor(max_workers=10) as ex:
            
            futures = {ex.submit(self.get_entries_scenes, f"{base_url}{self._MOST_WATCHED}{i}", i, func) : f"page={i}" for i in range(1, npages + 1)}

        for fut in futures:
            try:
                _res = fut.result()
                if _res:
                    entries += _res
                else: raise ExtractorError("no entries")
            except Exception as e:
                self.report_warning(f'[{url}][{futures[fut]}] {repr(e)}')  
                #raise ExtractorError(repr(e))
        
        if entries:
            return {
                '_type': 'playlist',
                'id': data['id'],
                'title':  f"NSw{data['typepl'].capitalize()}_{''.join(w.capitalize() for w in data['name'].split('-'))}",
                'entries': entries,
            }
        else: raise ExtractorError("no entries")
        
class NakedSwordPlaylistIE(NakedSwordBaseIE):
    IE_NAME = "nakedsword:playlist"
    _VALID_URL = r'https?://(?:www\.)?nakedsword.com/(?P<id>[^?&]+)$'
    
    def _real_initialize(self):
        super()._real_initialize()
    
    def _real_extract(self, url):      
       

        entries = []

        webpage = try_get(self._send_request(url), lambda x: re.sub('[\t\n]','', html.unescape(x.text)) if x else None)
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
    _SORTBY = {'scenes': ['Popularity', 'Trending', 'Newest', 'Relevance'], 'movies': ['MostWatched', 'Trending', 'Newest', 'Released', 'Relevance']}
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
 
    def get_starid(self, starname):
         
        query = starname.replace(' ', '+')
        url = f"https://vod-classic.nakedsword.com/dispatcher/fts?targetSearchMode=basic&isAdvancedSearch=false&isFlushAdvancedSearchCriteria=false&userQuery={query}d&sortType=Relevance&theaterId=22299&genreId=102&locale=en"
        
        driver = self.get_driver()
        
        try:
            
            self._send_request(url, driver)
            
            elstar = self.wait_until(driver, 60, ec.presence_of_element_located((By.CLASS_NAME, "exactMatchStar")))
            if elstar:
                ela = try_get(elstar.find_elements(By.TAG_NAME, "a"), lambda x: x[0])
                if ela:
                    starid = try_get(re.findall(r'starId=(\d+)', ela.get_attribute('href')), lambda x: x[0])
                    if starid: 
                        NakedSwordSearchIE._STARS[starname.lower().replace(' ', '').replace("/", "-")] = starid
                        NakedSwordSearchIE._STARS = {_key: NakedSwordSearchIE._STARS[_key] for _key in sorted(NakedSwordSearchIE._STARS)}
                        self.logger_debug(NakedSwordSearchIE._STARS)
                        NakedSwordSearchIE.upt_info_conf()
                        return starid
        except Exception as e:
            self.report_warning(f'[get_starid] {repr(e)}')
        finally:
            self.rm_driver(driver)        
    
    def get_studioid(self, studioname):
         
        query = studioname.replace(' ', '+')
        url = f"https://vod-classic.nakedsword.com/dispatcher/fts?targetSearchMode=basic&isAdvancedSearch=false&isFlushAdvancedSearchCriteria=false&userQuery={query}&sortType=Relevance&theaterId=22299&genreId=102&locale=en"
        
        driver = self.get_driver()
        
        try:
            
            self._send_request(url, driver)
            
            class getstudioid():
                def __call__(self,driver):
                    elstudio = driver.find_elements(By.CLASS_NAME, "exactMatchStudio")
                    if not elstudio:
                        elres = driver.find_element(By.CLASS_NAME, "searchDetails")
                        return "NotFound"
                    else:
                        if (ela:=try_get(elstudio[0].find_elements(By.TAG_NAME, "a"), lambda x: x[0])):
                            if (studioid:=try_get(re.findall(r'studioId=(\d+)', ela.get_attribute('href')), lambda x: x[0])):
                                return studioid
                        return "NotFound"
                        
                            
            
            
            # elstudio = self.wait_until(driver, 60, ec.presence_of_element_located((By.CLASS_NAME, "exactMatchStudio")))
            # if elstudio:
            #     ela = try_get(elstudio.find_elements(By.TAG_NAME, "a"), lambda x: x[0])
            #     if ela:
            #         studioid = try_get(re.findall(r'studioId=(\d+)', ela.get_attribute('href')), lambda x: x[0])
            #         if studioid: 
            #             NakedSwordSearchIE._STUDIOS[studioname.lower().replace(' ', '').replace('-', '')] = studioid
            #             NakedSwordSearchIE._STUDIOS = {_key: NakedSwordSearchIE._STUDIOS[_key] for _key in sorted(NakedSwordSearchIE._STUDIOS)}
            #             self.to_screen(NakedSwordSearchIE._STUDIOS)
            #             NakedSwordSearchIE.upt_info_conf()
            #             return studioid
            
            studioid = self.wait_until(driver, 60, getstudioid())
            if studioid and studioid != 'NotFound':
                NakedSwordSearchIE._STUDIOS[studioname.lower().replace(' ', '').replace('-', '')] = studioid
                NakedSwordSearchIE._STUDIOS = {_key: NakedSwordSearchIE._STUDIOS[_key] for _key in sorted(NakedSwordSearchIE._STUDIOS)}
                self.logger_debug(NakedSwordSearchIE._STUDIOS)
                NakedSwordSearchIE.upt_info_conf()                
                return studioid
                
        except Exception as e:
            self.report_warning(f'[get_studioid] {repr(e)}')
        finally:
            self.rm_driver(driver)

    def get_scenes_ns(self, urls):
        

        def _get_scenes_url(j):
            _driver = self.get_driver()
                        
            try:                
                while True:
                    _pos, _uq = self._urlqueriesqueue.get()
                    if _uq == "KILL": break
                    self.logger_debug(f'[get_scenes][{j}][{_pos}/{self._num}] {_uq}')
                    try:
                        self._send_request(_uq[0], _driver)
                        el_title = self.wait_until(_driver, 2, ec.presence_of_element_located((By.TAG_NAME, "title")))
                        if not el_title: continue
                        elscenes = self.wait_until(_driver, 2, ec.presence_of_all_elements_located((By.CLASS_NAME, "dts-panel ")))
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
                        _nw = min((_size:=len(_list_scenes_urls)), 12)
                        
                        def _check_url(_urlsc, _n):
                            try:
                                
                                #res = NakedSwordSearchIE._CLIENT.get(_urlsc[0])
                                #res.raise_for_status()
                                res = try_get(self._send_request(_urlsc[0]), lambda x: x.text)
                                if res:  
                                    self.logger_debug(f'[get_scenes][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] {_urlsc[0]} OK is available')
                                    self._urlscenesqueue.put_nowait((_urlsc[0], _urlsc[1], _urlsc[2], _n))
                                else:
                                    self.logger_debug(f'[get_scenes][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] {_urlsc[0]} ERROR not available')
                               
                        
                            except Exception as e:
                                self.logger_debug(f'[get_scenes][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] {_urlsc[0]} ERROR {repr(e)}')
                        
                        with ThreadPoolExecutor(max_workers=_nw) as _ex:               
                            for _k, _elurl in enumerate(_list_scenes_urls):
                                _ex.submit(_check_url, _elurl, _k+1)
                    
                    except Exception as e:
                        lines = traceback.format_exception(*sys.exc_info())
                        self.logger_debug(f"[get_scenes][{j}][{_pos}/{self._num}]  {repr(e)}\n{'!!'.join(lines)}")
                
            
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.logger_debug(f"[get_scenes][{j}] {repr(e)}\n{'!!'.join(lines)}")
            finally:
                self.rm_driver(_driver)
                self.logger_debug(f'[get_scenes][{j}] bye') 

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
            self.logger_debug(f'[get_scenes] {repr(e)}')
            raise ExtractorError(f"{repr(e)}")

    def get_movies_ns(self, urls):

        def _get_movies_url(j):
            _driver = self.get_driver()
                        
            try:                
                while True:
                    _pos, _uq = self._urlqueriesqueue.get()
                    if _uq == "KILL": break
                    self.logger_debug(f'[get_movies][{j}][{_pos}/{self._num}] {_uq}')
                    try:
                        self._send_request(_uq[0], _driver)
                        el_title = self.wait_until(_driver, 2, ec.presence_of_element_located((By.TAG_NAME, "title")))
                        if not el_title: continue
                        elmovies = self.wait_until(_driver, 2, ec.presence_of_all_elements_located((By.CLASS_NAME, "dts-image-overlay-container")))
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
                                
                                res = try_get(self._send_request(_urlmv[0]), lambda x: x.text)                                
                                if res and not 'NakedSword.com | Untitled Page' in res: 
                                    self.logger_debug(f'[get_movies][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] {_urlmv[0]} OK is available')
                                    self._urlmoviesqueue.put_nowait((_urlmv[0], _urlmv[1], _urlmv[2], _n))
                                else:
                                    self.logger_debug(f'[get_movies][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] {_urlmv[0]} ERROR not available')
                                    
                        
                            except Exception as e:
                                self.logger_debug(f'[get_movies][{j}][{_pos}/{self._num}][check_url][{_n}/{_size}] {_urlmv[0]} ERROR {repr(e)}')
                        
                        with ThreadPoolExecutor(max_workers=_nw) as _ex:               
                            futures = [_ex.submit(_check_url, _elurl, _k+1) for _k, _elurl in enumerate(_list_movies_urls)]
                    
                    except Exception as e:
                        lines = traceback.format_exception(*sys.exc_info())
                        self.logger_debug(f"[get_movies][{j}][{_pos}/{self._num}]  {repr(e)}\n{'!!'.join(lines)}")
                
            
            except Exception as e:
                lines = traceback.format_exception(*sys.exc_info())
                self.logger_debug(f"[get_movies][{j}] {repr(e)}\n{'!!'.join(lines)}")
            finally:
                self.rm_driver(_driver)
                self.logger_debug(f'[get_movies][{j}] bye') 

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
            self.logger_debug(f'[get_movies] {repr(e)}')
            raise ExtractorError(f"{repr(e)}")
    
       
    def _real_initialize(self):
        super()._real_initialize()
        conf = NakedSwordSearchIE.get_info_conf()
        NakedSwordSearchIE._STUDIOS = conf['studios']
        NakedSwordSearchIE._STARS = conf['stars']
    
    def _real_extract(self, url):

        query = re.search(self._VALID_URL, url).group('query')
        
        params = { el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
        
        if (_s:=params.get('s', None)):
            stext = f"sysQuery={_s}&"
        else:
            stext = "sysQuery=&"
            

        content = params.get('content', 'scenes')
        
        
        if (_sortby:=params.get('sort')):
            _sortby = _sortby.replace(' ','').lower()
            if _sortby == 'mostwatched':
                if content == 'scenes': _sby = 'Popularity'
                else: _sby = 'MostWatched'
            elif _sortby == 'released':
                if content == 'scenes': _sby = 'Newest'
                else: _sby = 'Released'                
            elif _sortby in ['trending', 'newest', 'relevance']: 
                _sby = _sortby.capitalize()
            else:
                _sby = 'Relevance'
            criteria = {'sort': _sby}
        else:
            #criteria_list = [{'sort': _sort} for _sort in self._SORTBY[content]]
            criteria = {'sort': 'Relevance'}
            
        if (_studio:=params.get('studio')):
            if not (_studioid:=NakedSwordSearchIE._STUDIOS.get(_studio.lower().replace(' ', '').replace('-', ''))):
                _studioid = self.get_studioid(_studio)
        if (_star:=params.get('star')):
            if not (_starid:=NakedSwordSearchIE._STAR.get(_star.lower().replace(' ', '').replace('/', '-'))):
                _starid = self.get_starid(_star)
        if (_tag:=params.get('tag')):
            _tagid = [int(_id) for el in _tag.split(',') if (_id:=NakedSwordSearchIE._CATEGORIES.get(el))]
        if (_setting:=params.get('setting')):
            _settingid = [int(_id) for el in _setting.split(',') if (_id:=NakedSwordSearchIE._SETTINGS.get(el))]
        if (_sexact:=params.get('sexact')):
            _sexactid = [int(_id) for el in _sexact.split(',') if (_id:=NakedSwordSearchIE._SEX_ACTS.get(el))]
        
        if _tag and _tagid: criteria.update({'tagFilters': _tagid})
        if _setting and _settingid and content == 'scenes': criteria.update({'settingFilters': _settingid})
        if _sexact and _sexactid and content == 'scenes': criteria.update({'sexActFilters': _sexactid})
        if _studio and _studioid: criteria.update({'studioFilters': [int(_studioid)]})
        if _star and _starid: criteria.update({'starFilters': [int(_starid)]})
            
        
        criteria_str = json.dumps(criteria).replace(" ", "")       
        
        url_query_base = f'https://vod.nakedsword.com/gay/search/{content}/page/1?{stext}criteria={quote(criteria_str)}&viewMode=List'
        pages = int(params.get('pages', '5'))        
        maxpages = min(try_get(self._send_request(url_query_base), lambda x: try_get(re.findall(r'<a class="dts-paginator-tagging" href="/gay/search/(?:scenes|movies)/page/(\d+)\?', x.text), lambda y: int(y[-1]) if y else 1)), pages)
        

        url_query = [(f'https://vod.nakedsword.com/gay/search/{content}/page/{page+1}?{stext}criteria={quote(criteria_str)}&viewMode=List', criteria['sort'], page+1) for page in range(maxpages)]
        self.logger_debug(f"url query list[{len(url_query)}]: \n{url_query}")
        url_query_str = '\n'.join([f'{unquote(_el[0])}, {_el[0].split("?")[-1]}' for _el in url_query])
        self.logger_debug(f"url query list[{len(url_query)}]: \n{url_query_str}")
        

        try:
            entries = []
            if content == 'scenes':
                list_res = self.get_scenes_ns(url_query)
                self.logger_debug(list_res)
                if list_res:
                    list_res_sorted = sorted(list_res, key=lambda x: (NakedSwordSearchIE._SORTBY['scenes'].index(x[1]),x[2], x[3]))
                    self.logger_debug(list_res_sorted)
                    list_res_final = []
                    for el in list_res_sorted:
                        if el[0] not in list_res_final: list_res_final.append(el[0])
                    entries = [self.url_result(_urlscene, ie=NakedSwordSceneIE.ie_key()) for _urlscene in list_res_final]
                
            elif content == 'movies':
                #list_res = list(set(self.get_movies_ns(url_query)))
                list_res = self.get_movies_ns(url_query)
                self.logger_debug(list_res)
                if list_res:
                    list_res_sorted = sorted(list_res, key=lambda x: (NakedSwordSearchIE._SORTBY['movies'].index(x[1]),x[2], x[3]))
                    self.logger_debug(list_res_sorted)
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
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"error {repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(f"{repr(e)}")

