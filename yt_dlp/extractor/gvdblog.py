import json
import re
from datetime import datetime
import html
import itertools
from ..utils import ExtractorError, try_get, sanitize_filename, traverse_obj, get_domain
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_0_5, limiter_0_1

from concurrent.futures import ThreadPoolExecutor

class GVDBlogBaseIE(SeleniumInfoExtractor):

    def getbestvid(self, x, check=True, msg=None):

        _x = x if isinstance(x, list) else [x]
        iedood = self._get_extractor('DoodStream')
        _x.sort(key=lambda y: iedood.suitable(y)) #tube prior to dood

        pre = ' '
        if msg: pre = f'{msg}{pre}'       
        
        for el in _x:
            ie = self._get_extractor(el)
            
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
    def get_urls(post):
        
        if isinstance(post, str):
            webpage = post
            
        else:
            webpage = traverse_obj(post, ('content', '$t'))

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
                    if i == (len(list_urls) - 1):
                        list1.append(el[0])
                    elif traverse_obj(list_urls, (i+1, 1)) or traverse_obj(list_urls, (i+1, 2)):
                        _subvideo2.append(el[0])

        if _subvideo:
            list1.append(_subvideo)
        if _subvideo2:
            list1.append(_subvideo2)
        return list1

    @staticmethod               
    def get_info(post):

        if isinstance(post, str):
            
            postid = try_get(re.findall(r"class='related-tag' data-id='(\d+)'", post), lambda x: x[0])
            title = try_get(re.findall(r"title>([^<]+)<", post), lambda x: x[0])
            postdate = try_get(re.findall(r"class='entry-time mi'><time class='published' datetime='[^']+'>([^<]+)<", post), lambda x: datetime.strptime(x[0], '%B %d, %Y') if x else None)
            return(postdate, title, postid)
            
        else:
            postid = traverse_obj(post, ('id', '$t'), default="").split('post-')[-1]
            title = traverse_obj(post, ('title', '$t'))
            postdate = datetime.fromisoformat(traverse_obj(post, ('published', '$t')).split('T')[0])
            return(postdate, title, postid)
    
    def get_entries_from_blog_post(self, post, check=True):
        
        if isinstance(post, str):
            url = post
            self.report_extraction(url)
            post = try_get(self._send_request(url), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)) if x else None)
            if not post: raise ExtractorError("no webpage")
            
        else:
            url = traverse_obj(post, ('link', -1, 'href'))
            self.report_extraction(url)

        try:
            
            postdate, title, postid = self.get_info(post)
            list_candidate_videos = self.get_urls(post)
                
            if not postdate or not title or not postid or not list_candidate_videos: raise ExtractorError(f"[{url} no video info")   
                
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
        
        entries, title, postid = self.get_entries_from_blog_post(url)
        if not entries: raise ExtractorError("no videos")
            
        return self.playlist_result(entries, playlist_id=postid, playlist_title=sanitize_filename(title, restricted=True))
                


class GVDBlogPlaylistIE(GVDBlogBaseIE):
    IE_NAME = "gvdblog:playlist"
    _VALID_URL = r'https?://(?:www\.)?gvdblog.com/search\?(?P<query>.+)'
    

    def send_api_search(self, query):
        
        def getter(x):
            if not x:
                return []
            if _jsonstr:=x.group("data"):
                return json.loads(_jsonstr).get('feed', {}).get('entry', [])
            
        
        _urlquery = f"https://www.gvdblog.com/feeds/posts/full?alt=json-in-script&max-results=99999{query}"
        
        self.to_screen(_urlquery)
                
        res_search = try_get(self._send_request(_urlquery), lambda x: x.text)        
        if not res_search: 
            raise ExtractorError("no search results")
        video_entries = try_get(re.search(r"gdata.io.handleScriptLoaded\((?P<data>.*)\);", res_search), getter)
        if not video_entries: 
            raise ExtractorError("no video entries")
        self.logger_debug(f'[entries result] {len(video_entries)}')
        
        return video_entries

    def get_blog_posts_search(self, url):        
        
        query = re.search(self._VALID_URL, url).group('query')
        
        params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&') if el.count('=') == 1}        
        
        urlquery = ""
        
        if _upt_max:=params.get('updated-max'):
            urlquery += f"&updated-max={_upt_max}T23:59:59"
        if _upt_min:=params.get('updated-min'):
            urlquery += f"&updated-min={_upt_min}T00:00:00"
        if _category:=(params.get('label') or params.get('category')):
            urlquery += f"&category={_category}"
        if _q:=params.get('q'):
            urlquery += f"&q={_q}"
            
        if params.get('check','').lower() == 'no':
            self._check = False
        else: self._check = True
        
        post_blog_entries_search = self.send_api_search(urlquery) 
        
        if (_upto:=params.get('upto')):
            _upto = datetime.fromisoformat(_upto)
            post_blog_entries_search = list(filter(lambda x: datetime.fromisoformat(traverse_obj(x, ('updated', '$t')).split('T')[0]) >= _upto, post_blog_entries_search))
        
        _nentries = int(params.get('entries', -1))
        _from = int(params.get('from', 1))
        
        if _nentries > 0:
            final_entries = post_blog_entries_search[_from-1:_from-1+_nentries]
        else:
            final_entries = post_blog_entries_search[_from-1:]
            
        return final_entries  

    
    def get_entries_search(self, url):         
    
        
        blog_posts_list = self.get_blog_posts_search(url)
        
        self.logger_debug(f'[blog_post_list] {blog_posts_list}')
            
        posts_vid_url = [traverse_obj(post_entry, ('link', -1, 'href')) for post_entry in blog_posts_list]
        
        self.logger_debug(f'[posts_vid_url] {posts_vid_url}')
        
        _entries = []
        
        with ThreadPoolExecutor(thread_name_prefix="gvdpl") as ex:
                
            futures = {ex.submit(self.get_entries_from_blog_post, _post_blog, check=self._check): _post_url for (_post_blog, _post_url) in zip(blog_posts_list, posts_vid_url)}       

              
        for fut in futures:
            try:
                
                if (_res:=try_get(fut.result(), lambda x: x[0])):
                    _entries += _res
                else:                    
                    
                    self.report_warning(f'[get_entries] fails fut {futures[fut]}')
            except Exception as e:                
                self.report_warning(f'[get_entries] fails fut {futures[fut]}')
        
        def get_list_interl(res):
            _dict = {}
            for ent in res:
                _key = get_domain(ent['formats'][0]['url'])
                if not _dict.get(_key): _dict[_key] = [ent]
                else: _dict[_key].append(ent)
            
            self.to_screen(f'[get_entries] {len(list(_dict.keys()))} different hosts, longest with {len(max(list(_dict.values()), key=len))} entries')
            _interl = []
            for el in list(itertools.zip_longest(*list(_dict.values()))):
                _interl.extend([_el for _el in el if _el])
            return _interl   
        
        
        return get_list_interl(_entries)
    
    
    def _real_initialize(self):
        super()._real_initialize()
               
    
    def _real_extract(self, url):
        
        
        self.report_extraction(url)
        
        query = re.search(self._VALID_URL, url).group('query')
        
        entries =  self.get_entries_search(url)
        
        self.logger_debug(entries)

        
        return self.playlist_result(entries, f'{sanitize_filename(query, restricted=True)}', f"Search")