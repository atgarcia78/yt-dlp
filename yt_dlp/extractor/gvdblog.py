import json
import re
from datetime import datetime
import html

from ..utils import ExtractorError, try_get, sanitize_filename, traverse_obj
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_0_5, limiter_0_1

from concurrent.futures import ThreadPoolExecutor

class GVDBlogBaseIE(SeleniumInfoExtractor):

    def getbestvid(self, x, check=True, msg=None):

        _x = x if isinstance(x, list) else [x]
        iedood = self._downloader.get_info_extractor('DoodStream')
        _x.sort(key=lambda y: iedood.suitable(y)) #tube prior to dood
        
        if msg: pre = f'{msg} '
        else: pre = ' '
       
        for el in _x:
            #ie = self._downloader.get_info_extractor(ie_key:=self._get_ie_key(el))
            ie = self._get_extractor(el)
            #ie._real_initialize()
            
            try:
                _entry = ie._get_entry(el, check_active=check, msg=pre)
                if _entry:
                    self.logger_debug(f"{pre}[{self._get_url_print(el)}] OK got entry video")
                    return _entry
                else:
                    self.report_warning(f'{pre}[{self._get_url_print(el)}] WARNING not entry video')
            except Exception as e:
                self.report_warning(f'{pre}[{self._get_url_print(el)}] WARNING error entry video {repr(e)}')
                
    @staticmethod
    def get_urls(webpage):    

        #_reg_expr = r'<iframe allowfullscreen="true"(?:([^>]+mozallowfullscreen="(?P<ppal>true)"[^>]+)|[^>]+)src=[\"\'](?P<url>[^\'\"]+)[\"\']'
        _reg_expr = r'<iframe (?:(allowfullscreen="true")|(allow="(?P<ppal2>autoplay)" allowfullscreen=""))(?:([^>]+mozallowfullscreen="(?P<ppal>true)"[^>]+)|[^>]+)src=[\"\'](?P<url>[^\'\"]+)[\"\']'
        list_urls = [[mobj.group('url'),mobj.group('ppal'), mobj.group('ppal2')] for mobj in re.finditer(_reg_expr, webpage) if mobj]
        n_ppal = len([el for el in list_urls if (el[1] or el[2])])
        n_downloads = len(re.findall(r'<button class="mybutton2">Download\s*</button>', webpage))
        if n_ppal > n_downloads:
            for i in range(1, len(list_urls), 2):
                list_urls[i][1] = None
                list_urls[i][2] = None
        list1 = []
        _subvideo = []
        _subvideo2 = []
        
        for i,el in enumerate(list_urls):
            if not el[0]:
                continue
            if el[1] or el[2]:
                if _subvideo:
                    list1.append(_subvideo)
                    _subvideo = []
                if _subvideo2:
                    _subvideo2.append(el[0])
                    list1.append(_subvideo2)
                    _subvideo2 = []
                else:
                    _subvideo.append(el[0])
            else:
                if _subvideo:
                    _subvideo.append(el[0])
                    list1.append(_subvideo)
                    _subvideo = []
                else:
                    #if not try_get(list_urls, lambda y: y[i+1]):
                    if i == (len(list_urls) - 1):
                        list1.append(el[0])
                    elif traverse_obj(list_urls, (i+1, 1)) or traverse_obj(list_urls, (i+1, 2)):#try_get(list_urls, lambda y: (y[i+1][1] or y[i+1][2])):
                        _subvideo2.append(el[0])

        if _subvideo:
            list1.append(_subvideo)
        if _subvideo2:
            list1.append(_subvideo2)
        return list1

    @staticmethod               
    def get_info(webpage):

        postid = try_get(re.findall(r"class='related-tag' data-id='(\d+)'", webpage), lambda x: x[0])
        title = try_get(re.findall(r"title>([^<]+)<", webpage), lambda x: x[0])
        postdate = try_get(re.findall(r"class='entry-time mi'><time class='published' datetime='[^']+'>([^<]+)<", webpage), lambda x: datetime.strptime(x[0], '%B %d, %Y') if x else None)
        return(postdate, title, postid)
            
    
    def get_entries(self, url, check=True):
        
        self.report_extraction(url)

        try:

            webpage = try_get(self._send_request(url), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)) if x else None)
            if not webpage: raise ExtractorError("no webpage")
            
            postdate, title, postid = self.get_info(webpage)
            list_candidate_videos = self.get_urls(webpage)
                
            if not postdate or not title or not postid or not list_candidate_videos: raise ExtractorError("no video info")   
                
            pre = f'[get_entries]:{self._get_url_print(url)}'
            
            entries = []
            if (_len:=len(list_candidate_videos)) > 1:
                with ThreadPoolExecutor(thread_name_prefix="gvdblog_pl", max_workers=min(len(list_candidate_videos), 5)) as exe:
                    futures = {exe.submit(self.getbestvid, _el, check=check, msg=pre): _el for _el in list_candidate_videos}
                
                
                for fut in futures:
                    try:
                        if (_res:=fut.result()):
                            entries.append(_res)
                        else: raise ExtractorError("no entry")
                    except Exception as e:
                        self.report_warning(f'{pre} entry [{futures[fut]}] {repr(e)}')
                
            elif _len == 1:
                try:
                    _entry = self.getbestvid(list_candidate_videos[0], check=check, msg=pre)
                    if _entry:
                        entries.append(_entry)
                except Exception as e:
                    pass
            
            if not entries: raise ExtractorError(f"{pre} no video entries")

            _entryupdate = {'original_url': url}
            
            if postdate: 
                _entryupdate.update({
                    'release_date': postdate.strftime('%Y%m%d'),
                    'release_timestamp': int(postdate.timestamp())})

            for _el in entries:
                _el.update(_entryupdate)
            
            return (entries, title, postid)
        
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            self.report_warning(f'{pre} {repr(e)}')  
            raise ExtractorError(f'{pre} {repr(e)}')


    
    @dec_on_exception
    @limiter_0_1.ratelimit("gvdblog", delay=True)
    def _send_request(self, url, driver=None, msg=None):
        
        if msg: pre = f'{msg}[send_req]'
        else: pre = '[send_req]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}") 
        if driver:
            driver.get(url)
        else:
            return(self.send_http_request(url))
        
    def _real_initialize(self):
        super()._real_initialize()

class GVDBlogPostIE(GVDBlogBaseIE):
    IE_NAME = "gvdblogpost:playlist"
    _VALID_URL = r'https?://(www\.)?gvdblog\.com/\d{4}/\d+/.+\.html'
    _TESTS = [{
        'url': 'https://www.gvdblog.com/2022/06/aingeru-solo.html',
        'info_dict': {
            'id': '4577767402561614008', 
            'title': 'Aingeru_Solo_Part_1',
        },
        'playlist_mincount': 5,
        'params': {
            'skip_download': True,
        }
    }]
    

    def _real_initialize(self):
        super()._real_initialize()
               
    def _real_extract(self, url):
        
        entries, title, postid = self.get_entries(url)
        if not entries: raise ExtractorError("no videos")
            
        return self.playlist_result(entries, playlist_id=postid, playlist_title=sanitize_filename(title, restricted=True))
                

        
class GVDBlogPlaylistIE(GVDBlogBaseIE):
    IE_NAME = "gvdblog:playlist"
    _VALID_URL = r'https?://(?:www\.)?gvdblog.com/search\?(?P<query>.+)'
    
    
    def _real_initialize(self):
        super()._real_initialize()
               
    def _real_extract(self, url):
        
        def getter(x):

            if not x:
                return []
            if _jsonstr:=x.group("data"):
                return json.loads(_jsonstr).get('feed', {}).get('entry', [])
        
        self.report_extraction(url)
        
        query = re.search(self._VALID_URL, url).group('query')
        
        params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&') if el.count('=') == 1}
        
        urlquery = f"https://www.gvdblog.com/feeds/posts/full?alt=json-in-script&max-results=99999"
        
        if _category:=params.get('label'):
            urlquery += f"&category={_category}"
        _check = True 
        if params.get('check','').lower() == 'no':
            _check = False
        
        _nentries = int(params.get('entries', -1))
        _from = int(params.get('from', 1))
        
        
        res_search = try_get(self._send_request(urlquery), lambda x: x.text)        
        if not res_search: raise ExtractorError("no search results")
        video_entries = try_get(re.search(r"gdata.io.handleScriptLoaded\((?P<data>.*)\);", res_search), getter)
        if not video_entries: raise ExtractorError("no video entries")


        if _nentries > 0:
            video_entries = video_entries[_from-1:_from-1+_nentries]
        else:
            video_entries = video_entries[_from-1:]
                
        
        self._entries = []
                
        def get_list_entries(_entry, check):
            
            
            try:
                
                videourlpost = _entry['link'][-1]['href']
                entries, title, postid = self.get_entries(videourlpost, check=check)
                    
                if entries:
                    #self._entries += entries
                    return entries
                else:
                    self.report_warning(f'[{url}][{videourlpost}] couldnt get video from this entry')
            except Exception as e:
                self.report_warning(f'[{url}][{videourlpost}] couldnt get video from this entry')
                
        
                
        with ThreadPoolExecutor(thread_name_prefix="gvdpl") as ex:
                
            futures = [ex.submit(get_list_entries, _entry, _check) for _entry in video_entries]       

        for fut in futures:
            try:
                if entries:=fut.result():
                    self._entries += entries                
            except Exception as e:
                pass
            
        if not self._entries: raise ExtractorError("no video list")
        return self.playlist_result(self._entries, f"gvdblog_playlist", f"gvdblog_playlist")