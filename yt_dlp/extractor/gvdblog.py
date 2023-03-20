import re
from datetime import datetime
import html
from threading import Lock
from ..utils import (
    ExtractorError,
    try_get,
    sanitize_filename,
    traverse_obj,
    int_or_none,
    unsmuggle_url)
from .commonwebdriver import (
    unquote,
    dec_on_exception2,
    dec_on_exception3,
    SeleniumInfoExtractor,
    limiter_1,
    limiter_0_1,
    HTTPStatusError,
    ConnectError,
    Tuple)

from concurrent.futures import ThreadPoolExecutor

import logging

logger = logging.getLogger("gvdblog")

_ie_names = ('highload', 'doodstream')
_ie_urls = ('//highload.', '//dood.')
_ie_data = {key: value for key, value in zip(_ie_names, _ie_urls)}


class GVDBlogBaseIE(SeleniumInfoExtractor):
    _SLOW_DOWN: bool = False
    _LOCK = Lock()

    def get_entry_video(self, x, **kwargs):

        check = kwargs.get('check', True)
        lazy = kwargs.get('lazy', False)
        premsg = '[get_entry_video]'
        if (msg := kwargs.get('msg', None)):
            premsg = f'{msg}{premsg}'

        _x = x if isinstance(x, list) else [x]

        urldict = {
            _ie.IE_NAME: {'url': _url, 'ie': _ie}
            for _url in _x
            if (_ie := self._get_extractor(_url)) and hasattr(_ie, '_get_entry') and _ie.IE_NAME in _ie_data
        }

        if not urldict:
            logger.warning(f'{premsg} couldnt get any video from:\n{_x}')
            return

        _videos = []
        for key in _ie_data:
            if key in urldict:
                try:
                    _ch = check
                    if key == 'doodstream':
                        _ch = False
                    if not lazy:
                        _entry = urldict[key]['ie']._get_entry(urldict[key]['url'], check=_ch, msg=premsg)
                        if _entry:
                            logger.debug(f"{premsg}[{self._get_url_print(urldict[key]['url'])}] OK got entry video")
                            return _entry
                        else:
                            logger.debug(f"{premsg}[{self._get_url_print(urldict[key]['url'])}] WARNING not entry video")
                    else:
                        _entry = urldict[key]['ie']._get_metadata(urldict[key]['url'])
                        _entry['webpage_url'] = urldict[key]['url']
                        _entry['extractor'] = key
                        return _entry
                except Exception as e:
                    logger.debug(f"{premsg}[{self._get_url_print(urldict[key]['url'])}] WARNING error entry video {repr(e)}")
                _videos.append(urldict[key]['url'])
        _msg = f'{premsg} couldnt get any working video from original list:\n{_x}\n'
        _msg += f'that was filter to final list videos:\n{_videos}'
        logger.warning(_msg)

    def get_urls(self, webpage, msg=None):

        _pattern = r'<iframe ([^>]+)>|button2["\']>([^<]+)<|target=["\']_blank["\']>([^>]+)<'
        p1 = re.findall(_pattern, webpage, flags=re.IGNORECASE)
        p2 = [(l1[0].replace("src=''", "src=\"DUMMY\""), l1[1], l1[2])
              for l1 in p1 if any(
            [(l1[0] and 'src=' in l1[0]), (l1[1] and not any([_ in l1[1].lower() for _ in ['subtitle', 'imdb']])),
             (l1[2] and not any([_ in l1[2].lower() for _ in ['subtitle', 'imdb']]))])]
        p3 = [{_el.split('="')[0]:_el.split('="')[1].strip('"')
               for _el in l1[0].split(' ') if len(_el.split('="')) == 2} for l1 in p2]

        list_urls = []

        def _get_url(el):
            _res = 'DUMMY'
            for key in el.keys():
                if 'src' in key:
                    if any([_ in el[key] for _ in _ie_urls]):
                        return el[key]
                    else:
                        _res = el[key]
            return _res

        _th = False
        _td = False
        for el in p3:
            _url = _get_url(el)

            if '//highload.' in _url:
                if _th:
                    list_urls.append(None)
                    _td = False
                else:
                    _th = True
                list_urls.append(_url)
            elif "//dood." in _url:
                if _td:
                    list_urls.append(None)
                    _th = False
                else:
                    _td = True
                list_urls.append(_url)

        if any([_th, _td]):
            list_urls.append(None)

        _subvideo = []
        list1 = []
        for el in list_urls:
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

            title = self._html_search_meta(('og:title', 'twitter:title'), post, default=None)
            if not title:
                title = try_get(self._html_extract_title(post), lambda x: x.replace(' – GVDBlog', ''))

            _pattern = r"(?:(class='entry-time mi'><time class='published' datetime='[^']+'>(?P<date1>[^<]+)<)|(calendar[\"']></i> Date: (?P<date2>[^<]+)<))"
            postdate = try_get(
                re.search(_pattern, post),
                lambda x: try_get(
                    traverse_obj(x.groupdict(), ('date1'), ('date2')),
                    lambda y: datetime.strptime(y, '%B %d, %Y') if y else None) if x else None)

            return (postdate, title, postid)

        else:

            postid = post.get('id')
            title = traverse_obj(post, ('title', 'rendered'))
            postdate = try_get(post.get('date'), lambda x: datetime.fromisoformat(x.split('T')[0]))
            return (postdate, title, postid)

    def get_entries_from_blog_post(self, post, **kwargs):

        check = kwargs.get('check', True)
        progress_bar = kwargs.get('progress_bar', None)
        lazy = kwargs.get('lazy', False)
        url = None
        post_content = None
        postdate = None
        title = None
        postid = None
        list_candidate_videos = None

        try:

            try:

                if isinstance(post, str) and post.startswith('http'):
                    url = unquote(post)
                    self.report_extraction(url)
                    post_content = try_get(
                        self._send_request(url),
                        lambda x: re.sub('[\t\n]', '', html.unescape(x.text)) if x else None)
                    if post_content:
                        postdate, title, postid = self.get_info(post_content)

                        list_candidate_videos = self.get_urls(post_content, msg=url)

                elif isinstance(post, dict):

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
                premsg = f'[get_entries][{self._get_url_print(url)}]'
                self.logger_debug(f"{premsg} {postid} - {title} - {postdate} - {list_candidate_videos}")
                if not postdate or not title or not postid or not list_candidate_videos:
                    raise ExtractorError(f"[{url} no video info")

            entries = []

            try:

                if len(list_candidate_videos) > 1:
                    with ThreadPoolExecutor(thread_name_prefix="gvdblog_pl") as exe:
                        futures = {
                            exe.submit(self.get_entry_video, _el, check=check, msg=premsg, lazy=lazy): _el
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
                        _entry = self.get_entry_video(list_candidate_videos[0], check=check, msg=premsg, lazy=lazy)
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
        finally:
            if progress_bar:
                with GVDBlogBaseIE._LOCK:
                    self._done += 1
                    progress_bar.print(f'Entry OK {self._done}/{self._total}')  # type: ignore

    def _get_metadata(self, post):
        return self.get_entries_from_blog_post(post, lazy=True)

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
        self._done = 0
        self._total: int


class GVDBlogPostIE(GVDBlogBaseIE):
    IE_NAME = "gvdblogpost:playlist"  # type: ignore
    _VALID_URL = r'''(?x)
        https?://(www\.)?gvdblog\.(?:(com/\d{4}/\d+/.+\.html)|(net/(?!search\?)[^\/\?]+))
        (\?(?P<nocheck>check=no))?'''

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):
        url, _ = unsmuggle_url(url)

        _check = True
        if try_get(re.search(self._VALID_URL, url), lambda x: x.group('nocheck')):
            _check = False

        entries, title, postid = self.get_entries_from_blog_post(url, check=_check)
        if not entries:
            raise ExtractorError("no videos")

        return self.playlist_result(
            entries, playlist_id=postid, playlist_title=sanitize_filename(title, restricted=True),
            webpage_url=url, original_url=url)


class GVDBlogPlaylistIE(GVDBlogBaseIE):
    IE_NAME = "gvdblog:playlist"  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?gvdblog\.(com|net)/search\?(?P<query>[^#]+)'
    _BASE_API = {'gvdblog.net': "https://gvdblog.net/wp-json/wp/v2/posts?per_page=100"}

    def send_api_search(self, query):

        try:
            video_entries = try_get(
                self._send_request(self._BASE_API['gvdblog.net'], params=query),
                lambda x: x.json())

            if not video_entries:
                raise ExtractorError("no video entries")
            else:
                self.logger_debug(f'[entries result] videos entries [{len(video_entries)}]')

                return video_entries
        except Exception as e:
            logger.debug(repr(e))
            raise

    def get_blog_posts_search(self, url):

        try:

            query = try_get(re.search(self._VALID_URL, url), lambda x: x.group('query'))

            if query:
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

        if len(blog_posts_list) > 100:
            GVDBlogBaseIE._SLOW_DOWN = True
            check = False

        self.logger_debug(f'[blog_post_list] {blog_posts_list}')

        posts_vid_url = [try_get(
            post_entry.get('link'),
            lambda x: unquote(x) if x is not None else None) for post_entry in blog_posts_list]

        if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):
            for _post_blog in blog_posts_list:
                yield try_get(self.get_entries_from_blog_post(_post_blog, check=check), lambda x: x[0][0])
        else:
            for _url in posts_vid_url:
                yield self.url_result(_url if check else f"{_url}?check=no", ie=GVDBlogPostIE.ie_key())

    def get_entries_search(self, url, check=True, lazy=False):

        pre = f'[get_entries][{self._get_url_print(url)}]'

        try:
            blog_posts_list = self.get_blog_posts_search(url)

            self._total = len(blog_posts_list)

            self.logger_info(f'{pre}[blog_post_list] len[{self._total}]')

            if len(blog_posts_list) >= 100:
                GVDBlogBaseIE._SLOW_DOWN = True
                check = False

            self.logger_debug(f'{pre}[blog_post_list] {blog_posts_list}')

            posts_vid_url = [try_get(
                post_entry.get('link'),
                lambda x: unquote(x) if x is not None else None) for post_entry in blog_posts_list]

            self.logger_debug(f'{pre}[posts_vid_url] {posts_vid_url}')

            _entries = []

            if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

                with self.create_progress_bar(msg=pre) as progress_bar:

                    with ThreadPoolExecutor(thread_name_prefix="gvdpl") as ex:

                        futures = {
                            ex.submit(self.get_entries_from_blog_post, _post_blog, check=check, lazy=lazy, progress_bar=progress_bar): _post_url
                            for (_post_blog, _post_url) in zip(blog_posts_list, posts_vid_url)}

                for fut in futures:
                    try:
                        if (_res := try_get(fut.result(), lambda x: x[0])):
                            _entries += _res
                        else:
                            self.report_warning(f'{pre} no entry, fails fut {futures[fut]}')
                    except Exception as e:
                        self.report_warning(f'{pre} fails fut {futures[fut]} {repr(e)}')

            else:
                _entries = [self.url_result(_post_url if check else f"{_post_url}?check=no", ie=GVDBlogPostIE.ie_key())
                            for _post_url in posts_vid_url]

            self.logger_debug(f'{pre}[entries] {_entries}')

            return _entries

        except Exception as e:
            logger.exception(f"{repr(e)}")
            raise

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
        _check = True
        _iter = False
        _lazy = False
        query = try_get(re.search(self._VALID_URL, url), lambda x: x.group('query'))
        if query:
            params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&') if el.count('=') == 1}

            if params.get('check', 'yes').lower() == 'no':
                _check = False

            if params.get('iter', 'no').lower() == 'yes':
                _iter = True

            if params.get('lazy', 'no').lower() == 'yes':
                _lazy = True

        if _iter:
            entries = self.iter_get_entries_search(url, check=_check)
        else:
            entries = self.get_entries_search(url, check=_check, lazy=_lazy)

        self.logger_debug(entries)

        return self.playlist_result(
            entries, playlist_id=f'{sanitize_filename(query, restricted=True)}'.replace('%23', ''),
            playlist_title="Search")
