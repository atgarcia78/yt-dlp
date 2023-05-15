import re
from datetime import datetime
import html
from threading import Lock
import json
from ..utils import (
    ExtractorError,
    try_get,
    sanitize_filename,
    traverse_obj,
    int_or_none,
    unsmuggle_url,
    get_domain,
    get_element_html_by_id)
from .commonwebdriver import (
    unquote,
    SeleniumInfoExtractor,
    limiter_1,
    limiter_0_1,
    ReExtractInfo,
    my_dec_on_exception,
    Tuple,
    cast)


from concurrent.futures import ThreadPoolExecutor

import logging

from .doodstream import DoodStreamIE
from .xfileshare import XFileShareIE
from .streamsb import StreamSBIE

_ie_data = {_ie.IE_NAME: _ie._VALID_URL for _ie in (DoodStreamIE, XFileShareIE, StreamSBIE)}

on_exception_req = my_dec_on_exception(TimeoutError, raise_on_giveup=False, max_tries=3, interval=1)
logger = logging.getLogger("gvdblog")


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
                    # if key == 'doodstream':
                    #     _ch = False
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
                    logger.exception(f"{premsg}[{self._get_url_print(urldict[key]['url'])}] WARNING error entry video {repr(e)}")
                _videos.append(urldict[key]['url'])
        _msg = f'{premsg} couldnt get any working video from original list:\n{_x}\n'
        _msg += f'that was filter to final list videos:\n{_videos}'
        logger.warning(_msg)

    def get_urls(self, webpage, msg=None):

        premsg = '[get_urls]'
        if msg:
            premsg = f'{msg}{premsg}'

        _pattern = r'<iframe ([^>]+)>|button2["\']>([^<]+)<|target=["\']_blank["\']>([^>]+)<'
        p1 = re.findall(_pattern, webpage, flags=re.IGNORECASE)
        self.logger_debug(f"{premsg} p1:\n{p1}")
        p2 = [(l1[0].replace("src=''", "src=\"DUMMY\""), l1[1], l1[2])
              for l1 in p1 if any(
            [(l1[0] and 'src=' in l1[0]), (l1[1] and not any([_ in l1[1].lower() for _ in ['subtitle', 'imdb']])),
             (l1[2] and not any([_ in l1[2].lower() for _ in ['subtitle', 'imdb']]))])]
        self.logger_debug(f"{premsg} p2:\n{p2}")
        p3 = [{_el.split('="')[0]:_el.split('="')[1].strip('"')
               for _el in l1[0].split(' ') if len(_el.split('="')) == 2} for l1 in p2]
        self.logger_debug(f"{premsg} p3:\n{p3}")

        list_urls = []

        def _get_url(el):
            _res = 'DUMMY'
            for key in el.keys():
                if 'src' in key:
                    if any([re.search(_, el[key]) for _ in _ie_data.values()]):
                        return el[key]
                    else:
                        _res = el[key]
            return _res

        _check = {iename: False for iename in _ie_data}

        for el in p3:
            if not el:
                continue
            _url = _get_url(el)
            if _url == 'DUMMY':
                continue
            for key, value in _ie_data.items():
                if re.search(value, _url):
                    if _check[key]:
                        list_urls.append(None)
                        _check.update({iename: False for iename in _ie_data if iename != key})
                    else:
                        _check[key] = True
                    list_urls.append(_url)
                    break

        if any([_check[iename] for iename in _ie_data]):
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
            if self.keyapi == 'gvdblog.com':
                postid = try_get(traverse_obj(post, ('id', '$t')), lambda x: x.split('post-')[-1])
                title = traverse_obj(post, ('title', '$t'))
                postdate = try_get(traverse_obj(post, ('published', '$t')), lambda x: datetime.fromisoformat(x.split('T')[0]))
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

            premsg = f'[{self.keyapi}][get_entries_from_post]'
            try:

                if isinstance(post, str) and post.startswith('http'):
                    url = unquote(post)
                    premsg += f'[{self._get_url_print(url)}]'
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
                        url = try_get(traverse_obj(post, ('link', -1, 'href')), lambda x: unquote(x) if x is not None else None)
                        post_content = traverse_obj(post, ('content', '$t'))
                    else:
                        url = try_get(post.get('link'), lambda x: unquote(x) if x is not None else None)
                        post_content = traverse_obj(post, ('content', 'rendered'))

                    premsg += f'[{self._get_url_print(url)}]'
                    self.report_extraction(url)

                    if post_content:
                        postdate, title, postid = self.get_info(post)
                        list_candidate_videos = self.get_urls(post_content, msg=url)

                else:
                    ExtractorError("incorrect type of data as post")

            except Exception as e:
                logger.debug(f"{premsg} {repr(e)}")
                raise

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

    @on_exception_req
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
                except ReExtractInfo as e:
                    logger.debug(f"{pre}: error - {repr(e)}")
                    raise ExtractorError(str(e))
                except Exception as e:
                    logger.warning(f"{pre}: error - {repr(e)}")
                    raise

    def _real_initialize(self):
        super()._real_initialize()
        self._done = 0
        self._total: int
        self.keyapi: str

        for cookie in self._COOKIES_JAR:
            if 'gvdblog.net' in cookie.domain and 'cf_clearance' in cookie.name:
                self.to_screen(f"cookie: {cookie}")
                self._CLIENT.cookies.set(name='cf_clearance', value=cookie.value, domain='gvdblog.net')  # type: ignore
                break


class GVDBlogPostIE(GVDBlogBaseIE):
    IE_NAME = "gvdblogpost:playlist"  # type: ignore
    _VALID_URL = r'''(?x)
        https?://(www\.)?gvdblog\.(?:(com/\d{4}/\d+/.+\.html)|(net/(?!search\?)[^\/\?]+))
        (\?(?P<nocheck>check=no))?'''

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):
        url, _ = unsmuggle_url(url)

        self.keyapi = cast(str, get_domain(url))
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
    _BASE_API = {'gvdblog.com': "https://www.gvdblog.com/feeds/posts/full?alt=json-in-script&max-results=99999",
                 'gvdblog.net': "https://gvdblog.net/wp-json/wp/v2/posts?per_page=100"}

    def send_api_search(self, query):

        def get_list_videos(res):
            if not res:
                raise ExtractorError("no res from api")

            if self.keyapi == 'gvdblog.com':
                data = try_get(re.search(r"gdata.io.handleScriptLoaded\((?P<data>.*)\);", res.text.replace(',,', ',')), lambda x: x.group('data'))
                if not data:
                    raise ExtractorError("no data from api")
                info_json = json.loads(data)
                return traverse_obj(info_json, ('feed', 'entry'), default=None)
            else:
                return res.json()

        assert hasattr(self, 'keyapi') and isinstance(self.keyapi, str)
        try:

            video_entries = try_get(self._send_request(self._BASE_API[self.keyapi], params=query), lambda x: get_list_videos(x))

            if not video_entries:
                raise ExtractorError("no video entries")
            else:
                self.logger_debug(f'[entries result] videos entries [{len(video_entries)}]')

                return video_entries

        except Exception as e:
            logger.debug(repr(e))
            raise

    def get_blog_posts_search(self, url):

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
            logger.debug(f"{repr(e)}")
            raise

    def iter_get_entries_search(self, url, check=True):

        blog_posts_list = self.get_blog_posts_search(url)

        if len(blog_posts_list) > 100:
            GVDBlogBaseIE._SLOW_DOWN = True
            check = False

        self.logger_debug(f'[blog_post_list] {blog_posts_list}')

        if self.keyapi == 'gvdblog.com':
            posts_vid_url = [try_get(traverse_obj(post_entry, ('link', -1, 'href')), lambda x: unquote(x) if x is not None else None) for post_entry in blog_posts_list]
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

            if self.keyapi == 'gvdblog.com':
                posts_vid_url = [try_get(traverse_obj(post_entry, ('link', -1, 'href')), lambda x: unquote(x) if x is not None else None) for post_entry in blog_posts_list]
            else:
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
            logger.debug(f"{repr(e)}")
            raise

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
        self.keyapi = cast(str, get_domain(url))
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
