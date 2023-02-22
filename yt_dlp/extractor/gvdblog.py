import json
import re
from datetime import datetime
import html
from ..utils import (
    ExtractorError,
    try_get,
    sanitize_filename,
    traverse_obj,
    get_element_html_by_id,
    int_or_none,
    get_domain)
from .commonwebdriver import (
    unquote, dec_on_exception2, dec_on_exception3,
    SeleniumInfoExtractor, limiter_1, limiter_0_1, HTTPStatusError, ConnectError, cast, Tuple)

from concurrent.futures import ThreadPoolExecutor

import logging

logger = logging.getLogger("gvdblog")


class GVDBlogBaseIE(SeleniumInfoExtractor):
    _SLOW_DOWN: bool = False

    def get_entry_video(self, x, **kwargs):

        check = kwargs.get('check', True)
        premsg = '[get_entry_video]'
        if (msg := kwargs.get('msg', None)):
            premsg = f'{msg}{premsg}'

        _x = x if isinstance(x, list) else [x]

        urldict = {
            _ie.IE_NAME: {'url': _url, 'ie': _ie}
            for _url in _x
            if (_ie := self._get_extractor(_url)) and hasattr(_ie, '_get_entry') and _ie.IE_NAME in (
                'tubeload', 'doodstream')
        }

        if not urldict:
            logger.warning(f'{premsg} couldnt get any tubeload, doodstrem video from:\n{_x}')
            return

        _videos = []
        for key in ('tubeload', 'doodstream'):
            if key in urldict:
                ie = urldict[key]['ie']
                el = urldict[key]['url']
                try:
                    _entry = ie._get_entry(el, check=check, msg=premsg)
                    if _entry:
                        logger.debug(f"{premsg}[{self._get_url_print(el)}] OK got entry video")
                        return _entry
                    else:
                        logger.debug(f'{premsg}[{self._get_url_print(el)}] WARNING not entry video')
                except Exception as e:
                    logger.debug(f'{premsg}[{self._get_url_print(el)}] WARNING error entry video {repr(e)}')
                _videos.append(el)
        _msg = f'{premsg} couldnt get any working video from original list:\n{_x}\n'
        _msg += f'that was filter to final list videos:\n{_videos}'
        logger.warning(_msg)

    def get_urls(self, webpage, msg=None):

        p1 = re.findall(
            r'<iframe ([^>]+)>|button2["\']>([^<]+)<|target=["\']_blank["\']>([^>]+)<', webpage,
            flags=re.IGNORECASE)   # type: ignore
        p2 = [(l1[0].replace("src=''", "src=\"DUMMY\""), l1[1], l1[2])
              for l1 in p1 if any(
            [(l1[0] and 'src=' in l1[0]), (l1[1] and not any([_ in l1[1].lower() for _ in ['subtitle', 'imdb']])),
             (l1[2] and not any([_ in l1[2].lower() for _ in ['subtitle', 'imdb']]))])]
        p3 = [{_el.split('="')[0]:_el.split('="')[1].strip('"')
               for _el in l1[0].split(' ') if len(_el.split('="')) == 2} for l1 in p2]

        list_urls = []

        for i, el in enumerate(p3):
            _url = el.get('data-litespeed-src', el.get('data-lazy-src', el.get('src', 'DUMMY')))
            if any([_ in _url for _ in ("//tubeload.co", "//dood.")]):
                if i != 0 and "//tubeload.co" in _url and list_urls[-1]:
                    list_urls.append(None)
                list_urls.append(_url)
                if "//dood." in _url:
                    list_urls.append(None)

        _final_urls = []

        if self.keyapi == 'gvdblog.net':
            _final_urls = list_urls

        else:
            iedood = self._downloader.get_info_extractor('DoodStream')  # type: ignore
            n_videos = list_urls.count(None)
            n_videos_dood = len([el for el in list_urls if el and iedood.suitable(el)])
            if not n_videos_dood:
                n_videos_dood = len(list_urls) - n_videos

            if n_videos and n_videos_dood and n_videos >= n_videos_dood:
                _final_urls.extend(list_urls)
            elif ((n_videos_dood + n_videos) == len(list_urls)):
                for el in list_urls:
                    if el:
                        _final_urls.extend([el, None])
            else:
                _pre = "[get_urls]"
                if msg:
                    _pre += f"[{msg}]"
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
                                if list_urls[i + j] and not iedood.suitable(list_urls[i + j]):
                                    _temp.append(list_urls[i + j])
                                    j += 1
                                    if j + i == len(list_urls):
                                        break
                                else:
                                    break
                            if _temp:
                                _final_urls.extend(_temp)
                                _pass = len(_temp)
                            if not list_urls[i + j]:
                                _pass += 1
                            _final_urls.append(list_urls[i])
                            _final_urls.append(None)

                    elif list_urls[i] and not iedood.suitable(list_urls[i]):
                        j = 0
                        _temp = []
                        if i < (len(list_urls) - 1):
                            j = 1
                            while True:
                                if list_urls[i + j] and not iedood.suitable(list_urls[i + j]):
                                    _temp.append(list_urls[i + j])
                                    j += 1
                                    if j + i == len(list_urls):
                                        j -= 1
                                        break
                                else:
                                    break

                        _final_urls.append(list_urls[i])
                        if _temp:
                            _final_urls.extend(_temp)
                            _pass = len(_temp)
                            '''
                            if list_urls[i + j] and iedood.suitable(list_urls[i + j]):
                                _final_urls.append(list_urls[i + j])
                                _final_urls.append(None)
                                _pass += 1
                            '''
                        if list_urls[i + j] and iedood.suitable(list_urls[i + j]):
                            _final_urls.append(list_urls[i + j])
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

        if _subvideo:
            list1.append(_subvideo)
        return list1

    def get_info(self, post) -> Tuple:

        if isinstance(post, str):

            postid = try_get(
                re.search(r"(?:(class='related-tag' data-id='(?P<id1>\d+)')|(wp-json/wp/v2/posts/(?P<id2>\d+)))", post),
                lambda x: traverse_obj(x.groupdict(), ('id1'), ('id2')))
            title = try_get(re.findall(r"title>([^<]+)<", post), lambda x: x[0])
            _pattern = r"(?:(class='entry-time mi'><time class='published' datetime='[^']+'>(?P<date1>[^<]+)<)|(calendar[\"']></i> Date: (?P<date2>[^<]+)<))"
            postdate = try_get(
                re.search(_pattern, post),
                lambda x: try_get(
                    traverse_obj(x.groupdict(), ('date1'), ('date2')),
                    lambda y: datetime.strptime(y, '%B %d, %Y') if y else None) if x else None)

            return (postdate, title, postid)

        else:
            if self.keyapi == 'gvdblog.com':
                postid = try_get(traverse_obj(post, ('id', '$t')), lambda x: x.split('post-')[-1])
                title = traverse_obj(post, ('title', '$t'))
                postdate = try_get(
                    traverse_obj(post, ('published', '$t')),
                    lambda x: datetime.fromisoformat(x.split('T')[0]))
                return (postdate, title, postid)
            else:
                postid = post.get('id')
                title = traverse_obj(post, ('title', 'rendered'))
                postdate = try_get(post.get('date'), lambda x: datetime.fromisoformat(x.split('T')[0]))
                return (postdate, title, postid)

    def get_entries_from_blog_post(self, post, **kwargs):

        check = kwargs.get('check', True)
        if GVDBlogBaseIE._SLOW_DOWN:
            check = False

        url = None
        post_content = None
        postdate = None
        title = None
        postid = None
        list_candidate_videos = None

        try:

            if isinstance(post, str) and post.startswith('http'):
                url = unquote(post)
                self.report_extraction(url)
                post_content = try_get(
                    self._send_request(url),
                    lambda x: re.sub('[\t\n]', '', html.unescape(x.text)) if x else None)
                if post_content:
                    postdate, title, postid = self.get_info(post_content)
                    if self.keyapi == 'gvdblog.com':
                        post_content = get_element_html_by_id('post-body', post_content)
                    list_candidate_videos = self.get_urls(post_content, msg=url)

            elif isinstance(post, dict):
                if self.keyapi == 'gvdblog.com':
                    url = try_get(
                        traverse_obj(post, ('link', -1, 'href')),
                        lambda x: unquote(x) if x is not None else None)
                    post_content = traverse_obj(post, ('content', '$t'))
                else:
                    url = try_get(post.get('link'), lambda x: unquote(x) if x is not None else None)
                    post_content = traverse_obj(post, ('content', 'rendered'))

                self.report_extraction(url)
                postdate, title, postid = self.get_info(post)
                if post_content:
                    list_candidate_videos = self.get_urls(post_content, msg=url)

            else:
                ExtractorError("incorrect type of data as post")

        except Exception as e:
            logger.exception(f"[get_entries_from_post] {repr(e)}")
        finally:
            premsg = f'[get_entries]:{self._get_url_print(url)}'
            if not postdate or not title or not postid or not list_candidate_videos:
                raise ExtractorError(f"[{url} no video info")
            self.logger_debug(f"{postid} - {title} - {postdate} - {list_candidate_videos}")

        entries = []

        try:

            if len(list_candidate_videos) > 1:
                with ThreadPoolExecutor(thread_name_prefix="gvdblog_pl") as exe:
                    futures = {
                        exe.submit(self.get_entry_video, _el, check=check, msg=premsg): _el
                        for _el in list_candidate_videos}

                for fut in futures:
                    try:
                        if (_res := fut.result()):
                            entries.append(_res)
                        else:
                            raise ExtractorError("no entry")
                    except Exception as e:
                        logger.debug(f'{premsg} entry [{futures[fut]}] {repr(e)}')

            else:
                try:
                    _entry = self.get_entry_video(list_candidate_videos[0], check=check, msg=premsg)
                    if _entry:
                        entries.append(_entry)
                except Exception:
                    pass

            if not entries:
                raise ExtractorError(f"{premsg} no video entries")

            _entryupdate = {'original_url': url}

            if postdate:
                _entryupdate.update({
                    'release_date': postdate.strftime('%Y%m%d'),
                    'release_timestamp': int(postdate.timestamp())})

            for i, _el in enumerate(entries):
                _el.update(_entryupdate)
                _el.update({'__gvd_playlist_index': i + 1, '__gvd_playlist_count': len(entries)})
                if len(entries) > 1:
                    _comment = f'{url} [{i + 1}]'
                else:
                    _comment = f'{url}'
                _el.update({'meta_comment': _comment})

            return (entries, title, postid)

        except ExtractorError:
            raise
        except Exception as e:
            logger.debug(f'{premsg} {repr(e)}')
            raise ExtractorError(f'{premsg} {repr(e)}')

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
                    return self.send_http_request(url, **kwargs)
                except (HTTPStatusError, ConnectError) as e:
                    logger.warning(f"{pre}: error - {repr(e)}")
                except Exception as e:
                    logger.warning(f"{pre}: error - {repr(e)}")
                    raise

    def _real_initialize(self):
        super()._real_initialize()
        self.keyapi: str


class GVDBlogPostIE(GVDBlogBaseIE):
    IE_NAME = "gvdblogpost:playlist"  # type: ignore
    _VALID_URL = r'''(?x)
        https?://(www\.)?gvdblog\.(?:(com/\d{4}/\d+/.+\.html)|(net/(?!search\?)[^\/\?]+))
        (\?(?P<nocheck>check=no))?'''

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.keyapi = cast(str, get_domain(url))
        _check = True
        if try_get(re.search(self._VALID_URL, url), lambda x: x.group('nocheck')):
            _check = False

        entries, title, postid = self.get_entries_from_blog_post(url, check=_check)
        if not entries:
            raise ExtractorError("no videos")

        return self.playlist_result(
            entries, playlist_id=postid, playlist_title=sanitize_filename(title, restricted=True))


class GVDBlogPlaylistIE(GVDBlogBaseIE):
    IE_NAME = "gvdblog:playlist"  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?gvdblog\.(com|net)/search\?(?P<query>[^#]+)'
    _BASE_API = {
        'gvdblog.com': "https://www.gvdblog.com/feeds/posts/full?alt=json-in-script&max-results=99999",
        'gvdblog.net': "https://gvdblog.net/wp-json/wp/v2/posts?per_page=100"}

    def get_list_videos(self, res):

        if not res:
            raise ExtractorError("no res from api")

        if self.keyapi == 'gvdblog.com':
            data = try_get(
                re.search(r"gdata.io.handleScriptLoaded\((?P<data>.*)\);", res.text.replace(',,', ',')),
                lambda x: x.group('data'))
            if not data:
                raise ExtractorError("no data from api")
            info_json = json.loads(data)
            return traverse_obj(info_json, ('feed', 'entry'), default=None)
        else:
            return res.json()

    def send_api_search(self, query):

        try:
            assert hasattr(self, 'keyapi') and isinstance(self.keyapi, str)
            # _urlquery = f"{self._BASE_API[self.keyapi]}{query}"
            # self.logger_debug(_urlquery)
            video_entries = try_get(
                self._send_request(self._BASE_API[self.keyapi], params=query),
                lambda x: self.get_list_videos(x))

            if not video_entries:
                raise ExtractorError("no video entries")
            else:
                self.logger_debug(f'[entries result] videos entries [{len(video_entries)}]')

                return video_entries
        except Exception as e:
            logger.debug(repr(e))
            raise

    def get_blog_posts_search(self, url):

        # just in case, get keyapi
        self.keyapi = cast(str, get_domain(url))

        try:

            query = try_get(re.search(self._VALID_URL, url), lambda x: x.group('query'))

            if query:
                if self.keyapi == 'gvdblog.com':
                    query = query.replace('date', 'published')
                    if 'orderby' not in query:
                        query += '&orderby=published'
                else:
                    query = query.replace('published', 'date')
                    if 'orderby' not in query:
                        query += '&orderby=date'

                params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&') if el.count('=') == 1}
            else:
                params = {}

            urlquery = []

            for key, val in params.items():

                if key == 'published':
                    urlquery.append(f"published-max={val}T23:59:59&published-min={val}T00:00:00")
                elif key == 'date':
                    urlquery.append(f"before={val}T23:59:59&after={val}T00:00:00")
                else:
                    urlquery.append(f"{key}={val}")

            post_blog_entries_search = self.send_api_search('&'.join(urlquery))

            _nentries = int_or_none(params.get('entries'))
            _from = int(params.get('from', 1))

            if _nentries is not None and _nentries >= 0:
                final_entries = post_blog_entries_search[_from - 1:_from - 1 + _nentries]
            else:
                final_entries = post_blog_entries_search[_from - 1:]

            return final_entries
        except Exception as e:
            logger.exception(f"{repr(e)}")
            raise

    def iter_get_entries_search(self, url, check=True):

        blog_posts_list = self.get_blog_posts_search(url)

        if len(blog_posts_list) > 50:
            GVDBlogBaseIE._SLOW_DOWN = True
            check = False

        self.logger_debug(f'[blog_post_list] {blog_posts_list}')

        if self.keyapi == 'gvdblog.com':
            posts_vid_url = [try_get(
                traverse_obj(post_entry, ('link', -1, 'href')),
                lambda x: unquote(x) if x is not None else None) for post_entry in blog_posts_list]
        else:
            posts_vid_url = [try_get(
                post_entry.get('link'),
                lambda x: unquote(x) if x is not None else None) for post_entry in blog_posts_list]

        if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):
            for _post_blog in blog_posts_list:
                yield try_get(self.get_entries_from_blog_post(_post_blog, check=check), lambda x: x[0][0])
        else:
            for _url in posts_vid_url:
                yield self.url_result(_url if check else f"{_url}?check=no", ie=GVDBlogPostIE.ie_key())

    def get_entries_search(self, url, check=True):

        try:
            blog_posts_list = self.get_blog_posts_search(url)

            logger.info(f'[blog_post_list] len[{len(blog_posts_list)}]')

            if len(blog_posts_list) >= 100:
                GVDBlogBaseIE._SLOW_DOWN = True
                check = False

            self.logger_debug(f'[blog_post_list] {blog_posts_list}')

            if self.keyapi == 'gvdblog.com':
                posts_vid_url = [try_get(
                    traverse_obj(post_entry, ('link', -1, 'href')),
                    lambda x: unquote(x) if x is not None else None) for post_entry in blog_posts_list]
            else:
                posts_vid_url = [try_get(
                    post_entry.get('link'),
                    lambda x: unquote(x) if x is not None else None) for post_entry in blog_posts_list]

            self.logger_debug(f'[posts_vid_url] {posts_vid_url}')

            _entries = []

            if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

                with ThreadPoolExecutor(thread_name_prefix="gvdpl") as ex:

                    futures = {
                        ex.submit(self.get_entries_from_blog_post, _post_blog, check=check): _post_url
                        for (_post_blog, _post_url) in zip(blog_posts_list, posts_vid_url)}

                for fut in futures:
                    try:

                        if (_res := try_get(fut.result(), lambda x: x[0])):
                            _entries += _res
                        else:
                            logger.warning(f'[get_entries] no entry, fails fut {futures[fut]}')
                    except Exception as e:
                        logger.exception(f'[get_entries] fails fut {futures[fut]} {repr(e)}')

            else:
                _entries = [self.url_result(_post_url if check else f"{_post_url}?check=no", ie=GVDBlogPostIE.ie_key())
                            for _post_url in posts_vid_url]

            self.logger_debug(f'[entries] {_entries}')

            return _entries
        except Exception as e:
            logger.exception(f"{repr(e)} - {str(e)}")
            raise

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
        self.keyapi = cast(str, get_domain(url))
        _check = True
        _iter = False
        query = try_get(re.search(self._VALID_URL, url), lambda x: x.group('query'))
        if query:
            params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&') if el.count('=') == 1}

            if params.get('check', 'yes').lower() == 'no':
                _check = False

            if params.get('iter', 'no').lower() == 'yes':
                _iter = True
        if _iter:
            entries = self.iter_get_entries_search(url, check=_check)
        else:
            entries = self.get_entries_search(url, check=_check)

        self.logger_debug(entries)

        return self.playlist_result(
            entries, playlist_id=f'{sanitize_filename(query, restricted=True)}'.replace('%23', ''),
            playlist_title="Search")
