import json
import re
from datetime import datetime
import html
from ..utils import ExtractorError, try_get, sanitize_filename, traverse_obj, get_element_html_by_id, int_or_none
from .commonwebdriver import (
    unquote, dec_on_exception, dec_on_exception2, dec_on_exception3, 
    SeleniumInfoExtractor, limiter_1, limiter_0_1, limiter_0_5, limiter_non, HTTPStatusError, ConnectError)

from concurrent.futures import ThreadPoolExecutor

import logging

logger = logging.getLogger('GVDBlog')

class GVDBlogBaseIE(SeleniumInfoExtractor):
    _SLOW_DOWN = False

    def get_entry_video(self, x, **kwargs):
        
        check = kwargs.get('check', True)
        msg = kwargs.get('msg', None)

        _x = x if isinstance(x, list) else [x]
        _x.sort(reverse=True)

        pre = ' '
        if msg: pre = f'{msg}{pre}'       
        
        for el in _x:
            ie = self._get_extractor(el)
            
            try:
                _entry = ie._get_entry(el, check=check, msg=pre)
                if _entry:
                    self.logger_debug(f"{pre}[{self._get_url_print(el)}] OK got entry video")
                    return _entry
                else:
                    self.report_warning(f'{pre}[{self._get_url_print(el)}] WARNING not entry video')
            except Exception as e:
                self.report_warning(f'{pre}[{self._get_url_print(el)}] WARNING error entry video {repr(e)}')
                
    
    def get_urls(self, post, msg=None):
        
        if isinstance(post, str):
            webpage =  get_element_html_by_id('post-body', post)
           
        else:
            webpage = traverse_obj(post, ('content', '$t'))

        p1 = re.findall(r'<iframe ([^>]+)>|mybutton2["\']>([^<]+)<|target=["\']_blank["\']>([^>]+)<', webpage, re.IGNORECASE)
        p2 = [(l1[0].replace("src=''", "src=\"DUMMY\""), l1[1], l1[2]) for l1 in p1 if any([(l1[0] and 'src=' in l1[0]), (l1[1] and not any([_ in l1[1].lower() for _ in ['subtitle', 'imdb']])), (l1[2] and not any([_ in l1[2].lower() for _ in ['subtitle', 'imdb']]))])]
        p3 = [{_el.split('="')[0]:_el.split('="')[1].strip('"') for _el in l1[0].split(' ') if len(_el.split('="')) == 2} for l1 in p2]
        list_urls = [item.get('src') for item in p3 if all([_ not in item.get('src', '_FORKEEP') for _ in ("youtube.com", "blogger.com", "DUMMY")])]

        iedood = self._downloader.get_info_extractor('DoodStream')
        iehigh = self._downloader.get_info_extractor('Highload')
        n_videos = list_urls.count(None)
        n_videos_dood = len([el for el in list_urls if el and iedood.suitable(el)])
        if not n_videos_dood: 
            n_videos_dood = len([el for el in list_urls if el and iehigh.suitable(el)])
            if not n_videos_dood:
                n_videos_dood = len(list_urls) - n_videos
        
        
        _final_urls = []
        if n_videos and n_videos_dood and n_videos >= n_videos_dood:
            _final_urls.extend(list_urls)
        elif ((n_videos_dood + n_videos) == len(list_urls)):
            for el in list_urls:
                if el: _final_urls.extend([el, None])
                
        else:
            _pre = "[get_urls]"
            if msg: _pre += f"[{msg}]"
            self.report_warning(f"{_pre} please check urls extracted: {list_urls}")

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
                    j = 0
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
                        '''
                        if list_urls[i+j] and iedood.suitable(list_urls[i+j]):
                            _final_urls.append(list_urls[i+j])
                            _final_urls.append(None)
                            _pass += 1
                        '''
                    if list_urls[i+j] and iedood.suitable(list_urls[i+j]):
                        _final_urls.append(list_urls[i+j])
                        _final_urls.append(None)
                        _pass += 1 
        
        
        
        _subvideo = []
        list1 = []
        for el in _final_urls:
            if el:
                _subvideo.append(unquote(el))
            else:
                if _subvideo:
                    _subvideo.sort(reverse=True)
                    list1.append(_subvideo)
                    _subvideo = []
        
        if _subvideo: list1.append(_subvideo)
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
    
    def get_entries_from_blog_post(self, post, **kwargs):

        check = kwargs.get('check', True)
       

        if isinstance(post, str):
            url = unquote(post)
            self.report_extraction(url)
            post = try_get(self._send_request(url), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)) if x else None)
            if not post: raise ExtractorError("no webpage")
            
        else:
            url = try_get(traverse_obj(post, ('link', -1, 'href')), lambda x: unquote(x) if x != None else None)
            self.report_extraction(url)

        if GVDBlogBaseIE._SLOW_DOWN:
            check = False
        
        pre = f'[get_entries]:{self._get_url_print(url)}'

        try:
            
            postdate, title, postid = self.get_info(post)
            list_candidate_videos = self.get_urls(post, msg=url)
                
            if not postdate or not title or not postid or not list_candidate_videos: raise ExtractorError(f"[{url} no video info")   
                
            
            
            entries = []
            if (_len:=len(list_candidate_videos)) > 1:
                with ThreadPoolExecutor(thread_name_prefix="gvdblog_pl") as exe:
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

            for i, _el in enumerate(entries):
                _el.update(_entryupdate)
                _el.update({'__gvd_playlist_index': i+1, '__gvd_playlist_count': len(entries)})
                if len(entries) > 1: _comment = f'{url}#{i+1}'
                else: _comment = f'{url}'
                _el.update({'meta_comment': _comment})

            return (entries, title, postid)
        
        except ExtractorError as e:                 
            raise 
        except Exception as e:
            logger.debug(f'{pre} {repr(e)}')  
            raise ExtractorError(f'{pre} {repr(e)}')


    #@dec_on_exception
    @dec_on_exception3
    @dec_on_exception2    
    def _send_request(self, url, **kwargs):
        
        driver = kwargs.get('driver', None)
        pre = f'[send_req][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'        
        _limiter = limiter_1 if GVDBlogBaseIE._SLOW_DOWN else limiter_0_1
        with _limiter.ratelimit("gvdblog", delay=True):
            self.logger_debug(f"{pre}: start") 
            if driver:
                driver.get(url)
            else:
                try:                
                    return self.send_http_request(url)                
                except (HTTPStatusError, ConnectError) as e:
                    self.report_warning(f"{pre}: error - {repr(e)}")
                except Exception as e:
                    self.report_warning(f"{pre}: error - {repr(e)}")
                    raise
        
    def _real_initialize(self):
        super()._real_initialize()


class GVDBlogPostIE(GVDBlogBaseIE):
    IE_NAME = "gvdblogpost:playlist"
    _VALID_URL = r'https?://(www\.)?gvdblog\.com/\d{4}/\d+/.+\.html(\?(?P<query>[^#]+))?'

    def _real_initialize(self):
        super()._real_initialize()
               
    def _real_extract(self, url):
        
        query = re.search(self._VALID_URL, url).group('query')
        
        _check = True
        if query:
            params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&') if el.count('=') == 1}

            if params.get('check','yes').lower() == 'no':
                _check = False

        entries, title, postid = self.get_entries_from_blog_post(url, check=_check)
        if not entries: raise ExtractorError("no videos")
            
        return self.playlist_result(entries, playlist_id=postid, playlist_title=sanitize_filename(title, restricted=True))
                

class GVDBlogPlaylistIE(GVDBlogBaseIE):
    IE_NAME = "gvdblog:playlist"
    _VALID_URL = r'https?://(?:www\.)?gvdblog.com/search\?(?P<query>[^#]+)'
    

    def send_api_search(self, query):
        
        try:
            _urlquery = f"https://www.gvdblog.com/feeds/posts/full?alt=json-in-script&max-results=99999{query}"
            self.logger_debug(_urlquery)
            res_search = try_get(self._send_request(_urlquery), lambda x: x.text.replace(',,',','))        
            if not res_search: 
                raise ExtractorError("no search results")
            data = try_get(re.search(r"gdata.io.handleScriptLoaded\((?P<data>.*)\);", res_search), lambda x: x.group('data'))
            if not data:
                raise ExtractorError("no video entries")
            info_json = json.loads(data)
            self.logger_debug(f'[entries result] {info_json}')

            video_entries = traverse_obj(info_json, ('feed', 'entry'))
            if not video_entries: 
                raise ExtractorError("no video entries")
            self.logger_debug(f'[entries result] videos entries [{len(video_entries)}]')

            return video_entries
        except Exception as e:
            logger.debug(repr(e))
            raise

    def get_blog_posts_search(self, url):        
        
        try:

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
                
            post_blog_entries_search = self.cache.load(self.IE_NAME.replace(':',''), urlquery.replace('&', '_').replace(':','').replace('=','_'))
            if not post_blog_entries_search:
                post_blog_entries_search = self.send_api_search(urlquery) 
                self.cache.store(self.IE_NAME.replace(':',''), urlquery.replace('&', '_').replace(':','').replace('=','_'), post_blog_entries_search)
            
            _nentries = int_or_none(params.get('entries'))
            _from = int(params.get('from', 1))
            
            if _nentries != None and _nentries >= 0:
                final_entries = post_blog_entries_search[_from-1:_from-1+_nentries]
            else:
                final_entries = post_blog_entries_search[_from-1:]

            return final_entries
        except Exception as e:
            logger.exception(f"{repr(e)} - {str(e)}")
            raise


    def iter_get_entries_search(self, url, check=True):
        blog_posts_list = self.get_blog_posts_search(url)
        
        if len(blog_posts_list) > 50: 
            GVDBlogBaseIE._SLOW_DOWN = True
            check = False
        
        self.logger_debug(f'[blog_post_list] {blog_posts_list}')
            
        posts_vid_url = [try_get(traverse_obj(post_entry, ('link', -1, 'href')), lambda x: unquote(x) if x != None else None) for post_entry in blog_posts_list]
        
        self.logger_debug(f'[posts_vid_url] {posts_vid_url}')
        
        if self.get_param('embed') or (self.get_param('extract_flat','') != 'in_playlist'):
            for _post_blog in blog_posts_list:            
                yield try_get(self.get_entries_from_blog_post(_post_blog, check=check), lambda x: x[0][0])
        else:
            for _url in posts_vid_url:
                yield self.url_result(_url if check else f"{_url}?check=no", ie=GVDBlogPostIE.ie_key())


    def get_entries_search(self, url, check=True):         
    
        try:        
            blog_posts_list = self.get_blog_posts_search(url)

            logger.info(f'[blog_post_list] len[{len(blog_posts_list)}]')

            if len(blog_posts_list) >= 50: 
                GVDBlogBaseIE._SLOW_DOWN = True
                check = False
            
            self.logger_debug(f'[blog_post_list] {blog_posts_list}')
                
            posts_vid_url = [try_get(traverse_obj(post_entry, ('link', -1, 'href')), lambda x: unquote(x) if x != None else None) for post_entry in blog_posts_list]
            
            self.logger_debug(f'[posts_vid_url] {posts_vid_url}')
            
            _entries = []

            if self.get_param('embed') or (self.get_param('extract_flat','') != 'in_playlist'):
            
                
                with ThreadPoolExecutor(thread_name_prefix="gvdpl") as ex:
                        
                    futures = {ex.submit(self.get_entries_from_blog_post, _post_blog, check=check): _post_url for (_post_blog, _post_url) in zip(blog_posts_list, posts_vid_url)}       

                    
                for fut in futures:
                    try:
                        
                        if (_res:=try_get(fut.result(), lambda x: x[0])):
                            _entries += _res
                        else:                    
                            logger.warning(f'[get_entries] no entry, fails fut {futures[fut]}')
                    except Exception as e:                
                        logger.exception(f'[get_entries] fails fut {futures[fut]} {repr(e)}')
            
            else:
                _entries = [self.url_result(_post_url if check else f"{_post_url}?check=no", ie=GVDBlogPostIE.ie_key()) for _post_url in posts_vid_url]

            self.logger_debug(f'[entries] {_entries}')
            
            return _entries
        except Exception as e:
            logger.exception(f"{repr(e)} - {str(e)}")
            raise

 
    def _real_initialize(self):
        super()._real_initialize()
        
    def _real_extract(self, url):
        
        self.report_extraction(url)

        _check = True
        _iter = False

        query = re.search(self._VALID_URL, url).group('query')

        if query:
            params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&') if el.count('=') == 1}
        
            if params.get('check','yes').lower() == 'no':
                _check = False
        
        
            if params.get('iter', 'no').lower() == 'yes':
                _iter = True
        
        if _iter:
            entries = self.iter_get_entries_search(url, check=_check)
        else:
            entries =  self.get_entries_search(url, check=_check)
        
        self.logger_debug(entries)

        return self.playlist_result(entries, playlist_id=f'{sanitize_filename(query, restricted=True)}'.replace('%23', ''), playlist_title="Search")