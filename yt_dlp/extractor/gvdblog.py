import json
import re
from datetime import datetime
import html
from ..utils import ExtractorError, try_get, sanitize_filename, traverse_obj
from .commonwebdriver import (
    dec_on_exception, dec_on_exception2, dec_on_exception3, 
    SeleniumInfoExtractor, limiter_0_1, HTTPStatusError, ConnectError)

from concurrent.futures import ThreadPoolExecutor

import logging

logger = logging.getLogger('GVDBlog')

class GVDBlogBaseIE(SeleniumInfoExtractor):

    def get_entry_video(self, x, check=True, msg=None):

        _x = x if isinstance(x, list) else [x]
        _x.sort(reverse=True)

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
                
    
    def get_urls(self, post):
        
        if isinstance(post, str):
            webpage = post            
        else:
            webpage = traverse_obj(post, ('content', '$t'))
            
        list_urls = [item.get('src') for item in [{_el.split('=')[0]:_el.split('=')[1].strip('"') for _el in l1[0].split(' ') if len(_el.split('=')) == 2} for l1 in re.findall(r'<iframe ([^>]+)>|>(Download\s*)<', webpage, re.IGNORECASE) if any(_ in l1[0] for _ in ['allowfullscreen="true"', 'allow="autoplay" allowfullscreen=""']) or 'download' in l1[1].lower()]]
        
        iedood = self._downloader.get_info_extractor('DoodStream')
        n_videos = list_urls.count(None)
        n_videos_dood = len([el for el in list_urls if el and iedood.suitable(el)])
        if not n_videos_dood: n_videos_dood = len(list_urls) - n_videos
        if n_videos and n_videos_dood and n_videos == n_videos_dood:
            _final_urls = list_urls
        
        
        else:
            _final_urls = []
            _pass = 0
            for i in range(len(list_urls)):
                if _pass:
                    _pass -= 1
                    continue
                if list_urls[i] and iedood.suitable(list_urls[i]):
                    if i == (len(list_urls) - 1):
                        _final_urls.append(list_urls[i])
                        _final_urls.append(None)
                    else:
                        j = 1
                        _temp = []
                        while True:
                            if list_urls[i+j] and not iedood.suitable(list_urls[i+j]):
                                _temp.append(list_urls[i+j])
                                j += 1
                                if j + i == len(list_urls): break
                            else: break
                        if _temp:
                            _final_urls.extend(_temp)
                            _pass = len(_temp)
                        if not list_urls[i+j]:
                            _pass += 1
                        _final_urls.append(list_urls[i])
                        _final_urls.append(None)
                        
                elif list_urls[i] and not iedood.suitable(list_urls[i]):

                    _temp = []
                    if i < (len(list_urls) - 1):
                        j = 1
                        while True:
                            if list_urls[i+j] and not iedood.suitable(list_urls[i+j]):
                                _temp.append(list_urls[i+j])
                                j += 1
                                if j + i == len(list_urls):
                                    j -= 1
                                    break
                            else: break
                    
                    _final_urls.append(list_urls[i])
                    if _temp:
                        _final_urls.extend(_temp)
                        _pass = len(_temp)
                        if list_urls[i+j] and iedood.suitable(list_urls[i+j]):
                            _final_urls.append(list_urls[i+j])
                            _final_urls.append(None)
                            _pass += 1 
        
        
        # _final_urls = []
        # for i,el in enumerate(list_urls):
        #     _final_urls.append(el)
        #     if el and iedood.suitable(el):
        #         if i == (len(list_urls) - 1):
        #             _final_urls.append(None)
        #         else:
        #             if list_urls[i+1] and iedood.suitable(list_urls[i+1]):
        #                 _final_urls.append(None)

        
        _subvideo = []
        list1 = []
        for el in _final_urls:
            if el:
                _subvideo.append(el)
            else:
                if _subvideo:
                    _subvideo.sort(reverse=True)
                    list1.append(_subvideo)
                    _subvideo = []
        
        return list1

                   
    def get_info(self, post):

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
                    futures = {exe.submit(self.get_entry_video, _el, check=check, msg=pre): _el for _el in list_candidate_videos}
                
                
                for fut in futures:
                    try:
                        if (_res:=fut.result()):
                            entries.append(_res)
                        else: raise ExtractorError("no entry")
                    except Exception as e:
                        self.report_warning(f'{pre} entry [{futures[fut]}] {repr(e)}')
                
            elif _len == 1:
                try:
                    _entry = self.get_entry_video(list_candidate_videos[0], check=check, msg=pre)
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
            logger.exception(f'{pre} {repr(e)}')  
            raise ExtractorError(f'{pre} {repr(e)}')


    @dec_on_exception
    @dec_on_exception3
    @dec_on_exception2
    @limiter_0_1.ratelimit("gvdblog", delay=True)
    def _send_request(self, url, driver=None, msg=None):
        
        if msg: pre = f'{msg}[send_req]'
        else: pre = '[send_req]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}") 
        if driver:
            driver.get(url)
        else:
            try:                
                return self.send_http_request(url)                
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"{pre} {self._get_url_print(url)}: error - {repr(e)}")
        
    def _real_initialize(self):
        super()._real_initialize()


class GVDBlogPostIE(GVDBlogBaseIE):
    IE_NAME = "gvdblogpost:playlist"
    _VALID_URL = r'https?://(www\.)?gvdblog\.com/\d{4}/\d+/.+\.html'

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
        
        try:
            
        
            _urlquery = f"https://www.gvdblog.com/feeds/posts/full?alt=json-in-script&max-results=99999{query}"
            
            self.to_screen(_urlquery)
                    
            res_search = try_get(self._send_request(_urlquery), lambda x: x.text.replace(',,',','))        
            if not res_search: 
                raise ExtractorError("no search results")
            
            data = try_get(re.search(r"gdata.io.handleScriptLoaded\((?P<data>.*)\);", res_search), lambda x: x.group('data'))
            
            self.logger_debug(f'[entries result] {data}')
            
            info_json = json.loads(data)

            video_entries = traverse_obj(info_json, ('feed', 'entry'))
            if not video_entries: 
                raise ExtractorError("no video entries")
            self.logger_debug(f'[entries result] {len(video_entries)}')
            
            return video_entries
        except Exception as e:
            logger.exception(repr(e))

    def get_blog_posts_search(self, url):        
        
        query = re.search(self._VALID_URL, url).group('query')
        
        params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&') if el.count('=') == 1}        
        
        urlquery = ""
        
        if _upt:=params.get('updated'):
            urlquery += f"&updated-max={_upt}T23:59:59&updated-min={_upt}T00:00:00&orderby=updated"
        if _publ:=params.get('published'):
            urlquery += f"&published-max={_publ}T23:59:59&published-min={_publ}T00:00:00&orderby=published"
        if _category:=(params.get('label') or params.get('category')):
            urlquery += f"&category={_category}"
        if _q:=params.get('q'):
            urlquery += f"&q={_q}"
            
        if params.get('check','').lower() == 'no':
            self._check = False
        else: self._check = True
        
        post_blog_entries_search = self.send_api_search(urlquery) 
        
        
        _nentries = int(params.get('entries', -1))
        _from = int(params.get('from', 1))
        
        if _nentries > 0:
            final_entries = post_blog_entries_search[_from-1:_from-1+_nentries]
        else:
            final_entries = post_blog_entries_search[_from-1:]
            
        return final_entries  

    def iter_get_entries_search(self, url):
        blog_posts_list = self.get_blog_posts_search(url)
        
        self.logger_debug(f'[blog_post_list] {blog_posts_list}')
            
        posts_vid_url = [traverse_obj(post_entry, ('link', -1, 'href')) for post_entry in blog_posts_list]
        
        self.logger_debug(f'[posts_vid_url] {posts_vid_url}')
        
        for _post_blog in blog_posts_list:
            yield try_get(self.get_entries_from_blog_post(_post_blog), lambda x: x[0][0])

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
                    logger.error(f'[get_entries] no entry, fails fut {futures[fut]}')
            except Exception as e:                
                logger.exception(f'[get_entries] fails fut {futures[fut]} {repr(e)}')
        

        
        return _entries
 
    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):
        
        
        self.report_extraction(url)
        
        query = re.search(self._VALID_URL, url).group('query')
        
        if "iter=yes" in query:
            entries = self.iter_get_entries_search(url)
        
        else:
            entries =  self.get_entries_search(url)
        
        self.logger_debug(entries)

        
        return self.playlist_result(entries, f'{sanitize_filename(query, restricted=True)}', f"Search")