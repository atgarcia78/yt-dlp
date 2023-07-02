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
    get_element_html_by_id,
    update_url_query,
    update_url)
from .commonwebdriver import (
    unquote,
    SeleniumInfoExtractor,
    limiter_1,
    limiter_0_1,
    ReExtractInfo,
    my_dec_on_exception,
    Tuple,
    cast,
    raise_extractor_error)


from concurrent.futures import (
    ThreadPoolExecutor,
    wait
)

import logging
from functools import partial

from .doodstream import DoodStreamIE
from .streamsb import StreamSBIE

_ie_data = {
    'legacy': {_ie.IE_NAME: _ie._VALID_URL for _ie in (DoodStreamIE, StreamSBIE)},
    'alt': {_ie.IE_NAME: _ie._VALID_URL for _ie in (StreamSBIE, DoodStreamIE)}
}


on_exception_req = my_dec_on_exception(TimeoutError, raise_on_giveup=False, max_tries=3, interval=1)
logger = logging.getLogger("gvdblog")


class GVDBlogBaseIE(SeleniumInfoExtractor):
    _SLOW_DOWN: bool = False
    _LOCK = Lock()

    def _real_initialize(self):
        super()._real_initialize()

        self._keyapi = ''
        self._altkey = ''
        self._query_upt = {}
        self._conf_args_gvd = {}

        for cookie in self._COOKIES_JAR:
            if 'gvdblog.net' in cookie.domain and 'cf_clearance' in cookie.name:
                self.to_screen(f"cookie: {cookie}")
                self._CLIENT.cookies.set(name='cf_clearance', value=cookie.value, domain='gvdblog.net')  # type: ignore
                break

    @property
    def keyapi(self):
        return self._keyapi

    @keyapi.setter
    def keyapi(self, url):
        self._keyapi = cast(str, get_domain(url))

    @property
    def altkey(self):
        return self._altkey

    @altkey.setter
    def altkey(self, key):
        self._altkey = key

    @property
    def query_upt(self):
        return self._query_upt

    @query_upt.setter
    def query_upt(self, upt):
        self._query_upt = upt

    @property
    def conf_args_gvd(self):
        return self._conf_args_gvd

    @conf_args_gvd.setter
    def conf_args_gvd(self, kwargs):
        params = kwargs.copy()
        _query_upt = {}

        _check = True
        if params.pop('check', 'yes').lower() == 'no':
            _check = False
            _query_upt['check'] = 'no'

        _iter = False
        if params.pop('iter', 'no').lower() == 'yes':
            _iter = True

        _lazy = False
        if params.pop('lazy', 'no').lower() == 'yes':
            _lazy = True

        _fmt = params.pop('fmt', 'hls').lower()
        if _fmt in ['hls', 'http', 'best']:
            _query_upt['fmt'] = _fmt
        else:
            raise ExtractorError('fmt not valid')

        if _fmt == 'http':
            self.altkey = 'legacy'
        else:
            self.altkey = 'alt'

        self.query_upt = _query_upt

        self._conf_args_gvd = {'check': _check, 'iter': _iter, 'lazy': _lazy, 'fmt': _fmt, 'query': params}

    def get_entry_video(self, x, **kwargs):

        premsg = '[get_entry_video]'
        if (msg := kwargs.get('msg', None)):
            premsg = f'{msg}{premsg}'

        _x = x if isinstance(x, list) else [x]

        urldict = {
            _ie.IE_NAME: {'url': _url, 'ie': _ie}
            for _url in _x
            if (_ie := self._get_extractor(_url)) and _ie.IE_NAME in _ie_data[self.altkey]
        }

        if not urldict:
            self.logger_debug(f'{premsg} couldnt get any video from:\n{_x}')
            return

        check = self.conf_args_gvd['check']
        lazy = self.conf_args_gvd['lazy']
        fmt = self.conf_args_gvd['fmt']

        _videos = []
        _entries = []
        for key in _ie_data[self.altkey]:
            if key in urldict:
                try:
                    if not lazy:
                        _entry = urldict[key]['ie']._get_entry(urldict[key]['url'], check=check, msg=premsg)
                        if _entry:
                            self.logger_debug(f"{premsg}[{self._get_url_print(urldict[key]['url'])}] OK got entry video\n{_entry}")
                            if fmt != 'best':
                                return _entry
                            else:
                                _entries.append(_entry)
                                continue
                        else:
                            self.logger_debug(f"{premsg}[{self._get_url_print(urldict[key]['url'])}] WARNING not entry video")

                    else:
                        _entry = urldict[key]['ie']._get_metadata(urldict[key]['url'])
                        _entry['webpage_url'] = urldict[key]['url']
                        _entry['extractor'] = key
                        return _entry
                except Exception as e:
                    self.logger_debug(f"{premsg}[{self._get_url_print(urldict[key]['url'])}] WARNING error entry video {repr(e)}")

                _videos.append(urldict[key]['url'])

        if fmt == 'best' and _entries:
            ytdl = self._downloader
            assert ytdl
            _process_entry = lambda x: ytdl.sanitize_info(ytdl.process_ie_result(x, download=False))
            if len(_entries) == 2:
                entalt, entleg = _process_entry(_entries[0]), _process_entry(_entries[1])
                entaltfilesize = entalt.get('filesize_approx') or (entalt.get('tbr', 0) * entalt.get('duration', 0) * 1024 / 8)
                entlegfilesize = entleg.get('filesize')
                if entlegfilesize and entaltfilesize and entaltfilesize >= 2 * entlegfilesize and (entaltfilesize > 786432000 or entlegfilesize < 157286400):
                    return _entries[0]
                else:
                    return _entries[1]
            else:
                return _entries[0]

        _msg = f'{premsg} couldnt get any working video from original list:\n{_x}\n'
        _msg += f'that was filter to final list videos:\n{_videos}'
        self.logger_debug(_msg)

    def get_urls(self, webpage, msg=None):

        premsg = '[get_urls]'
        if msg:
            premsg = f'{msg}{premsg}'

        _pattern = r'<iframe ([^>]+)>|button2["\']>([^<]+)<|target=["\']_blank["\']>([^>]+)<'
        p1 = re.findall(_pattern, webpage, flags=re.IGNORECASE)
        # self.logger_debug(f"{premsg} p1:\n{p1}")
        p2 = [(l1[0].replace("src=''", "src=\"DUMMY\""), l1[1], l1[2])
              for l1 in p1 if any(
            [(l1[0] and 'src=' in l1[0]), (l1[1] and not any([_ in l1[1].lower() for _ in ['subtitle', 'imdb']])),
             (l1[2] and not any([_ in l1[2].lower() for _ in ['subtitle', 'imdb']]))])]
        # self.logger_debug(f"{premsg} p2:\n{p2}")
        p3 = [{_el.split('="')[0]:_el.split('="')[1].strip('"')
               for _el in l1[0].split(' ') if len(_el.split('="')) == 2} for l1 in p2]
        # self.logger_debug(f"{premsg} p3:\n{p3}")

        list_urls = []

        def _get_url(el):
            _res = 'DUMMY'
            for key in el.keys():
                if 'src' in key:
                    if any([re.search(_, el[key]) for _ in _ie_data[self.altkey].values()]):
                        return el[key]
                    else:
                        _res = el[key]
            return _res

        _check = {iename: False for iename in _ie_data[self.altkey]}

        for el in p3:
            if not el:
                continue
            _url = _get_url(el)
            if _url == 'DUMMY':
                continue
            for key, value in _ie_data[self.altkey].items():
                if re.search(value, _url):
                    if _check[key]:
                        list_urls.append(None)
                        _check.update({iename: False for iename in _ie_data[self.altkey] if iename != key})
                    else:
                        _check[key] = True
                    list_urls.append(_url)
                    break

        if any([_check[iename] for iename in _ie_data[self.altkey]]):
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

        progress_bar = kwargs.get('progress_bar', None)

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
                    premsg += f'[{self._get_url_print(update_url(url, query_update=self._query_upt))}]'
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
                    with ThreadPoolExecutor(max_workers=min(len(list_candidate_videos), 8), thread_name_prefix="gvdblog_pl") as exe:
                        futures = {
                            exe.submit(partial(self.get_entry_video, msg=premsg), _el): _el
                            for _el in list_candidate_videos}

                        wait(futures)

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
                        _entry = self.get_entry_video(list_candidate_videos[0], msg=premsg)
                        if _entry:
                            entries.append(_entry)
                        else:
                            raise ExtractorError("no entry")
                    except Exception as e:
                        logger.debug(f'{premsg} {repr(e)}')

                if not entries:
                    raise ExtractorError(f"{premsg} no video entries")

                _entryupdate = {}

                if postdate:
                    _entryupdate.update({
                        'release_date': postdate.strftime('%Y%m%d'),
                        'release_timestamp': int(postdate.timestamp())})

                for i, _el in enumerate(entries):
                    _el.update(_entryupdate)
                    _el.update({'__gvd_playlist_index': i + 1, '__gvd_playlist_count': len(entries)})

                    _url = update_url_query(url, self._query_upt)

                    if len(entries) > 1:
                        _original_url = f'{_url}#{i + 1}'
                        _comment = f'{_url} [{i + 1}]'
                    else:
                        _original_url = _url
                        _comment = f'{_url}'

                    _el.update({'original_url': _original_url,
                                'meta_comment': _comment})

                return (entries, title, postid)

            except ExtractorError:
                raise
            except Exception as e:
                logger.debug(f'{premsg} {repr(e)}')
                raise ExtractorError(f'{premsg} {repr(e)}')
        finally:
            if progress_bar:
                with GVDBlogBaseIE._LOCK:
                    progress_bar.update()
                    progress_bar.print('Entry OK')  # type: ignore

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


class GVDBlogPostIE(GVDBlogBaseIE):
    IE_NAME = "gvdblogpost:playlist"  # type: ignore
    _VALID_URL = r'''(?x)
        https?://(www\.)?gvdblog\.(?:(com/\d{4}/\d+/.+\.html)|(net/(?!search\?)[^\/\?]+))
        (\?(?P<query>[^#]+))?'''

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):
        url, _ = unsmuggle_url(url)

        self.keyapi = url

        params = {}
        query = try_get(re.search(self._VALID_URL, url), lambda x: x.group('query'))
        if query:
            params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&') if el.count('=') == 1}

        self.conf_args_gvd = params

        _url = update_url(url, query='')

        entries, title, postid = self.get_entries_from_blog_post(_url)
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
                return traverse_obj(info_json, ('feed', 'entry'))
            else:
                return res.json()

        try:

            video_entries = try_get(self._send_request(self._BASE_API[self.keyapi], params=query), lambda x: get_list_videos(x))

            if not video_entries:
                raise_extractor_error("no video entries")
            else:
                self.logger_debug(f'[entries result] videos entries [{len(video_entries)}]')

                return video_entries

        except Exception as e:
            logger.debug(repr(e))
            raise

    def get_blog_posts_search(self) -> list:

        try:
            if (_query := self.conf_args_gvd['query']):

                query = '&'.join([f'{key}={value}' for key, value in _query.items()])

                if self.keyapi == 'gvdblog.com':
                    query = query.replace('date', 'published')
                    if 'orderby' not in query:
                        query += '&orderby=published'
                else:
                    query = query.replace('published', 'date')
                    if 'orderby' not in query:
                        query += '&orderby=date'

                params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&') if el.count('=') == 1}
                self._conf_args_gvd['query'] = params

            else:
                params = {}

            urlquery = []

            for key, val in params.items():

                if key == 'published':
                    urlquery.append(f"published-max={val}T23:59:59&published-min={val}T00:00:00")
                elif key == 'date':
                    urlquery.append(f"before={val}T23:59:59&after={val}T00:00:00")
                elif key not in ('entries', 'from'):
                    urlquery.append(f"{key}={val}")

            post_blog_entries_search = cast(list, self.send_api_search('&'.join(urlquery)))

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

    def iter_get_entries_search(self):

        blog_posts_list = self.get_blog_posts_search()

        if len(blog_posts_list) > 100:
            GVDBlogBaseIE._SLOW_DOWN = True
            self._conf_args_gvd.update({'check': False})

        if self.keyapi == 'gvdblog.com':
            posts_vid_url = [try_get(traverse_obj(post_entry, ('link', -1, 'href')), lambda x: unquote(x) if x is not None else None) for post_entry in blog_posts_list]
        else:
            posts_vid_url = [try_get(
                post_entry.get('link'),
                lambda x: unquote(x) if x is not None else None) for post_entry in blog_posts_list]

        if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):
            for _post_blog in blog_posts_list:
                yield try_get(self.get_entries_from_blog_post(_post_blog), lambda x: x[0][0])
        else:
            for _url in posts_vid_url:
                yield self.url_result(update_url(_url, query_update=self.query_upt), ie=GVDBlogPostIE.ie_key())

    def get_entries_search(self):

        pre = '[get_entries_search]'

        try:
            blog_posts_list = self.get_blog_posts_search()

            _total = len(blog_posts_list)

            self.logger_info(f'{pre}[blog_post_list] len[{_total}]')

            if len(blog_posts_list) >= 100:
                GVDBlogBaseIE._SLOW_DOWN = True
                self._conf_args_gvd.update({'check': False})

            if self.keyapi == 'gvdblog.com':
                posts_vid_url = cast(list, [try_get(
                    traverse_obj(post_entry, ('link', -1, 'href')),
                    lambda x: unquote(x)) for post_entry in blog_posts_list])
            else:
                posts_vid_url = cast(list, [try_get(
                    post_entry.get('link'),
                    lambda x: unquote(x)) for post_entry in blog_posts_list])

            _entries = []

            if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

                with self.create_progress_bar(_total, msg=pre) as progress_bar:

                    with ThreadPoolExecutor(max_workers=16, thread_name_prefix="gvdpl") as ex:

                        futures = {
                            ex.submit(
                                partial(self.get_entries_from_blog_post, progress_bar=progress_bar), _post_blog): _post_url
                            for (_post_blog, _post_url) in zip(blog_posts_list, posts_vid_url)}

                        wait(futures)

                    for fut in futures:
                        try:
                            if (_res := try_get(fut.result(), lambda x: x[0])):
                                _entries += _res
                            else:
                                self.logger_debug(f'{pre} no entry, fails fut {futures[fut]}')
                        except Exception as e:
                            self.logger_debug(f'{pre} fails fut {futures[fut]} {repr(e)}')

            else:
                _entries = [self.url_result(update_url(_post_url, query_update=self._query_upt), ie=GVDBlogPostIE.ie_key())
                            for _post_url in posts_vid_url]

            return _entries

        except Exception as e:
            logger.debug(f"{repr(e)}")
            raise

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
        self.keyapi = url

        params = {}
        query = try_get(re.search(self._VALID_URL, url), lambda x: x.group('query'))
        if query:
            params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&') if el.count('=') == 1}

        self.conf_args_gvd = params

        if (_query := self.conf_args_gvd['query']):
            _query = '&'.join([f"{key}={val}" for key, val in params.items()])
            self.logger_info(_query)

        if self.conf_args_gvd['iter']:
            entries = self.iter_get_entries_search()
        else:
            entries = self.get_entries_search()

        # self.logger_debug(entries)

        return self.playlist_result(
            entries, playlist_id=f'{sanitize_filename(query, restricted=True)}'.replace('%23', ''),
            playlist_title="Search")
