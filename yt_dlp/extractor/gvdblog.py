from __future__ import annotations

import contextlib
import itertools
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime
from functools import partial
from html import unescape
from threading import Lock

from .commonwebdriver import (
    ConnectError,
    HTTPStatusError,
    ReExtractInfo,
    SeleniumInfoExtractor,
    limiter_0_1,
    limiter_1,
    my_dec_on_exception,
    raise_extractor_error,
    unquote,
)
from .doodstream import DoodStreamIE
from .streamsb import StreamSBIE
from .voe import VoeIE
from .xfileshare import XFileShareIE
from ..utils import (  # get_element_html_by_id,
    ExtractorError,
    get_domain,
    get_element_by_id,
    get_element_text_and_html_by_tag,
    int_or_none,
    orderedSet,
    sanitize_filename,
    traverse_obj,
    try_get,
    update_url,
    update_url_query,
)

_ie_data = {
    'legacy': {_ie.IE_NAME: _ie._VALID_URL
               for _ie in (DoodStreamIE, VoeIE, StreamSBIE, XFileShareIE)},
    'alt': {_ie.IE_NAME: _ie._VALID_URL
            for _ie in (VoeIE, StreamSBIE, XFileShareIE, DoodStreamIE)}
}

on_exception_req = my_dec_on_exception(
    TimeoutError, raise_on_giveup=False, max_tries=3, interval=1)
logger = logging.getLogger("gvdblog")


def upt_dict(info_dict: dict | list, **kwargs) -> dict | list:
    info_dict_list = [info_dict] if isinstance(info_dict, dict) else info_dict
    for _el in info_dict_list:
        _el.update(**kwargs)


class GVDBlogBaseIE(SeleniumInfoExtractor):
    _SLOW_DOWN: bool = False
    _LOCK = Lock()

    def _real_initialize(self):
        super()._real_initialize()

        self._keyapi = ''
        self._altkey = ''
        self._query_upt = {}
        self._conf_args_gvd = {}

        for cookie in self._FF_COOKIES_JAR:
            if 'gvdblog.' in cookie.domain and 'cf_clearance' in cookie.name:
                self.to_screen(f"cookie: {cookie}")
                self._CLIENT.cookies.set(
                    name='cf_clearance', value=cookie.value,
                    domain=cookie.domain)  # type: ignore
                break

    @property
    def keyapi(self):
        return self._keyapi

    @keyapi.setter
    def keyapi(self, url):
        self._keyapi = get_domain(url)

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

        _fmt = params.pop('fmt', 'best').lower()
        if _fmt not in ['hls', 'http', 'best']:
            raise ExtractorError('fmt not valid')

        _entries = int_or_none(params.pop('entries', None))
        _from = int(params.pop('from', '1'))
        _query_upt.update({'from': _from, 'entries': _entries})

        if self.keyapi == 'gvdblog.net':
            _query_upt['fmt'] = _fmt
        else:
            _fmt = None
        self.altkey = 'legacy' if _fmt in ('http', None) else 'alt'
        _type = params.pop('type', None)
        name = params.pop('name', None)

        if _type and name:
            params[_type] = name

        self.query_upt = _query_upt

        self._conf_args_gvd = {
            'check': _check, 'fmt': _fmt, 'entries': _entries, 'from': _from,
            'type': _type, 'name': name, 'query': params}

    def get_entry_video(self, x, **kwargs):

        premsg = '[get_entry_video]'
        if (msg := kwargs.get('msg', None)):
            premsg = f'{msg}{premsg}'

        _x = x if isinstance(x, list) else [x]

        urldict = {
            _ie.IE_NAME: {'url': _url, 'ie': _ie} for _url in _x
            if (_ie := self._get_extractor(_url)) and _ie.IE_NAME in _ie_data[self.altkey]}

        if not urldict:
            self.logger_debug(f'{premsg} couldnt get any video from:\n{_x}')
            return

        check = self.conf_args_gvd['check']
        fmt = self.conf_args_gvd['fmt']

        _videos = []
        _entries = []
        for key in _ie_data[self.altkey]:
            if key in urldict:
                try:
                    if _entry := urldict[key]['ie']._get_entry(
                        urldict[key]['url'], check=check, msg=premsg
                    ):
                        self.logger_debug(
                            "".join([
                                f"{premsg}[{self._get_url_print(urldict[key]['url'])}] ",
                                f"OK got entry video\n{_entry}"]))
                        if fmt != 'best':
                            return _entry
                        _entries.append(_entry)
                        continue
                    else:
                        self.logger_debug(
                            "".join([
                                f"{premsg}[{self._get_url_print(urldict[key]['url'])}] ",
                                "WARNING not entry video"]))

                except Exception as e:
                    self.logger_debug(
                        "".join([
                            f"{premsg}[{self._get_url_print(urldict[key]['url'])}] ",
                            f"WARNING error entry video {repr(e)}"]))

                _videos.append(urldict[key]['url'])

        def _process_entry(x):
            with contextlib.suppress(Exception):
                return self._downloader.sanitize_info(
                    self._downloader.process_ie_result(x, download=False))

        if fmt == 'best' and _entries:
            if len(_entries) == 2:
                entalt, entleg = _process_entry(_entries[0]), _process_entry(_entries[1])
                entaltfilesize = entalt.get('filesize_approx') or (
                    entalt.get('tbr', 0) * entalt.get('duration', 0) * 1024 / 8)
                entlegfilesize = entleg.get('filesize')
                if all([entlegfilesize, entaltfilesize, entaltfilesize >= 2 * entlegfilesize,
                        (entaltfilesize > 786432000 or entlegfilesize < 157286400)]):
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
        p1 = list(map(
            lambda x: (x[0].lower(), x[1], x[2]),
            re.findall(_pattern, webpage, flags=re.IGNORECASE)))
        p2 = [
            (l1[0].replace("src=''", "src=\"DUMMY\""), l1[1], l1[2])
            for l1 in p1
            if any(
                [
                    (l1[0] and 'src=' in l1[0]),
                    l1[1]
                    and all(_ not in l1[1].lower() for _ in ['subtitle', 'imdb']),
                    l1[2]
                    and all(_ not in l1[2].lower() for _ in ['subtitle', 'imdb']),
                ]
            )
        ]
        p3 = [{_el.split('="')[0]: _el.split('="')[1].strip('"')
               for _el in l1[0].split(' ') if len(_el.split('="')) == 2} for l1 in p2]

        list_urls = []

        def _get_url(el):
            _res = 'DUMMY'
            for key in el.keys():
                if 'src' in key:
                    if any(
                        re.search(_, el[key])
                        for _ in _ie_data[self.altkey].values()
                    ):
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

        if any(_check[iename] for iename in _ie_data[self.altkey]):
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

    def get_info(self, post: str | dict) -> tuple[datetime | None, str | None, str | None]:

        if isinstance(post, str):
            _patt1 = r"(?:(class='related-tag' data-id='(?P<id1>\d+)')|(wp-json/wp/v2/posts/(?P<id2>\d+)))"
            postid = try_get(
                re.search(_patt1, post),
                lambda x: traverse_obj(x.groupdict(), ('id1'), ('id2')))

            title = self._html_search_meta(
                ('og:title', 'twitter:title'), post, default=None) or self._html_extract_title(post)

            _patt2 = r'''(?x)
                (?:
                    (class='entry-time mi'><time class='published' datetime='[^']+'>(?P<date1>[^<]+)<)|
                    (calendar[\"']></i> Date: (?P<date2>[^<]+)<))'''
            postdate = try_get(
                re.search(_patt2, post),
                lambda x: try_get(
                    traverse_obj(x.groupdict(), ('date1'), ('date2')),
                    lambda y: datetime.strptime(y, '%B %d, %Y') if y else None) if x else None)

        elif self.keyapi == 'gvdblog.com':
            postid = try_get(traverse_obj(post, ('id', '$t')), lambda x: x.split('post-')[-1])
            title = traverse_obj(post, ('title', '$t'))
            postdate = try_get(
                traverse_obj(post, ('published', '$t')),
                lambda x: datetime.fromisoformat(x.split('T')[0]))
        else:
            postid = post.get('id')
            title = traverse_obj(post, ('title', 'rendered'))
            postdate = try_get(
                post.get('date'), lambda x: datetime.fromisoformat(x.split('T')[0]))

        if title:
            title = sanitize_filename(
                re.sub(r'\s*-*\s*GVDBlog[^\s]+', '', title, flags=re.IGNORECASE), restricted=True)
        return (postdate, title, postid)

    def _get_metadata(self, post, premsg) -> list:
        url = postdate = title = postid = list_candidate_videos = None

        if isinstance(post, str) and post.startswith('http'):
            url = unquote(post)
            premsg += f'[{url}]'
            self.report_extraction(url)
            if (post_content := try_get(
                    self._send_request(url),
                    lambda x: re.sub('[\t\n]', '', unescape(x.text)) if x else None)):
                postdate, title, postid = self.get_info(post_content)
                # if self.keyapi == 'gvdblog.com':
                #     post_content = get_element_html_by_id('post-body', post_content)
                list_candidate_videos = self.get_urls(post_content, msg=url)
        elif isinstance(post, dict):
            # if self.keyapi == 'gvdblog.com':
            #     url = try_get(
            #         traverse_obj(post, ('link', -1, 'href')),
            #         lambda x: unquote(x) if x is not None else None)
            #     post_content = traverse_obj(post, ('content', '$t'))
            # else:
            #     url = try_get(
            #         post.get('link'),
            #         lambda x: unquote(x) if x is not None else None)
            #     post_content = traverse_obj(post, ('content', 'rendered'))
            url = try_get(
                post.get('link'),
                lambda x: unquote(x) if x is not None else None)
            post_content = traverse_obj(post, ('content', 'rendered'))
            premsg += f'[{self._get_url_print(url)}]'
            self.report_extraction(url)
            if post_content:
                postdate, title, postid = self.get_info(post)
                list_candidate_videos = self.get_urls(post_content, msg=url)

        self.logger_debug(
            f"{premsg} {postid} - {title} - {postdate} - {list_candidate_videos}")
        if not title or not list_candidate_videos:
            raise_extractor_error(f"{premsg} no video info")
        return (url, postdate, title, postid, list_candidate_videos, premsg)

    def get_entries_from_blog_post(self, post, **kwargs):

        progress_bar = kwargs.get('progress_bar', None)
        premsg = f'[{self.keyapi}][get_entries_from_post]'

        try:
            (url, postdate, title, postid,
             list_candidate_videos, premsg) = self._get_metadata(post, premsg)

            entries = []

            if list_candidate_videos:
                with ThreadPoolExecutor(thread_name_prefix="gvdblog_pl") as exe:
                    if futures := {
                            exe.submit(partial(self.get_entry_video, msg=premsg), _el): _el
                            for _el in list_candidate_videos}:
                        wait(list(futures.keys()))

                for fut in futures:
                    try:
                        if (_res := fut.result()):
                            entries.append(_res)
                        else:
                            logger.debug(f'{premsg} entry [{futures[fut]}] no entry')
                    except Exception as e:
                        logger.debug(f'{premsg} entry [{futures[fut]}] {repr(e)}')

            if not entries:
                raise_extractor_error(f"{premsg} no video entries")

            _entryupdate = {}

            if postdate:
                _entryupdate.update({
                    'release_date': postdate.strftime('%Y%m%d'),
                    'release_timestamp': int(postdate.timestamp())})

            _url = update_url_query(
                url, self.query_upt) if self.keyapi == 'gvdblog.com' else url

            for i, _el in enumerate(entries):
                if len(entries) > 1:
                    _original_url = f'{_url}#{i + 1}'
                    _comment = f'{_url} [{i + 1}]'
                else:
                    _original_url = _url
                    _comment = _url
                    if _el.pop('_try_title', None) or title.split(_el['title'])[0]:
                        _el['_legacy_title'] = _el['title']
                        _el['title'] = title

                _el.update({**_entryupdate, **{
                    '__gvd_playlist_index': i + 1,
                    '__gvd_playlist_count': len(entries),
                    'original_url': _original_url,
                    'meta_comment': _comment}})

            return (entries, title, postid)

        except ExtractorError:
            raise
        except Exception as e:
            logger.debug(f'{premsg} {repr(e)}')
            raise_extractor_error(f'{premsg} {repr(e)}', _from=e)
        finally:
            if progress_bar:
                with GVDBlogBaseIE._LOCK:
                    progress_bar.update()
                    progress_bar.print('Entry OK')

    @on_exception_req
    def _send_request(self, url, **kwargs):

        pre = f'[send_req][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'
        _limiter = limiter_1 if GVDBlogBaseIE._SLOW_DOWN else limiter_0_1

        with _limiter.ratelimit("gvdblog", delay=True):
            try:
                return self.send_http_request(url, **kwargs)
            except ReExtractInfo as e:
                logger.debug(f"{pre}: error - {repr(e)}")
                raise_extractor_error(str(e), _from=e)
            except (HTTPStatusError, ConnectError) as e:
                logger.debug(f"{pre}: error - {repr(e)}")
            except Exception as e:
                logger.debug(f"{pre}: error - {repr(e)}")
                raise


class GVDBlogPostIE(GVDBlogBaseIE):
    IE_NAME = "gvdblogpost:playlist"  # type: ignore
    _VALID_URL = r'''(?x)
        https?://(www\.)?(?:
            (fxggxt\.com/[^/_\?]+)|
            (gvdblog\.(?:
                (com/\d{4}/\d+/.+\.html)|
                (cc/video/[^\?/]+)|(net/[^/\?]+))))
        /?(\?(?P<query>[^#]+))?'''

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):
        self.report_extraction(url)
        self.keyapi = url

        params = {}
        query = try_get(
            re.search(self._VALID_URL, url), lambda x: x.group('query'))
        if query:
            params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&')
                      if el.count('=') == 1}

        self.conf_args_gvd = params

        _url = update_url(url, query='')

        entries, title, postid = self.get_entries_from_blog_post(_url)
        if not entries:
            raise ExtractorError("no videos")

        if len(entries) == 1:
            return {**entries[0], **{'original_url': url}}

        return self.playlist_result(
            entries, playlist_title=sanitize_filename(title, restricted=True),
            webpage_url=url, original_url=url)


class GVDBlogPlaylistIE(GVDBlogBaseIE):
    IE_NAME = "gvdblog:playlist"  # type: ignore
    _VALID_URL = r'''(?x)
        https?://(?:www\.)?(?:
            (fxggxt\.com/(?:_search|(?P<type3>(actor|category))/(?P<name3>[^\?/]+)))|
            (gvdblog\.(?:
                ((com|net)/(?:_search|(?P<type>(actor|category|tag))/(?P<name>[^\?/]+)))|
                (cc/(?:(actors|categories)/(?P<name2>[^\?/]+))))))
        (\?(?P<query>[^#]+))?'''

    _BASE_API = {
        'gvdblog.com': "https://www.gvdblog.com/feeds/posts/full?alt=json-in-script&max-results=99999",
        'gvdblog.net': "https://gvdblog.net/wp-json/wp/v2/posts?per_page=100",
        'fxggxt.com': "https://fxggxt.com/wp-json/wp/v2/posts?per_page=100"}

    _MAP = {'actor': 'actors', 'category': 'categories', 'tag': 'tags'}

    def get_id(self, label, name):
        webpage = try_get(
            self._send_request(f"https://{self.keyapi}/{label}/{name}"),
            lambda x: re.sub('[\t\n]', '', unescape(x.text)) if x else None)
        attribute = self._MAP[label]
        if (_id := try_get(
                re.findall(rf'{attribute}/(\d+)', webpage),
                lambda x: x[0])):
            return (attribute, _id)

    def send_api_search(self, query):

        def get_list_videos(res):
            if not res:
                return None
            if self.keyapi == 'gvdblog.com':
                if data := try_get(
                        re.search(
                            r"gdata.io.handleScriptLoaded\((?P<data>.*)\);",
                            res.text.replace(',,', ',')),
                        lambda x: x.group('data')):
                    info_json = json.loads(data)
                    return traverse_obj(info_json, ('feed', 'entry'))
            else:
                return res.json()

        video_entries = try_get(
            self._send_request(self._BASE_API[self.keyapi], params=query),
            lambda x: get_list_videos(x))

        if not video_entries:
            raise_extractor_error("no video entries")
        else:
            self.logger_debug(
                f'[entries result] videos entries [{len(video_entries)}]')

            return video_entries

    def get_blog_posts_search(self) -> list:

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

        if self.query_upt:
            urlquery.extend([f"{key}={value}" for key, value in self.query_upt.items()])

        post_blog_entries_search = self.send_api_search('&'.join(urlquery))

        _nentries = int_or_none(params.get('entries'))
        _from = int(params.get('from', 1))
        return (
            post_blog_entries_search[_from - 1: _from - 1 + _nentries]
            if _nentries is not None and _nentries >= 0
            else post_blog_entries_search[_from - 1:])

    # TODO Rename this here and in `get_entries_search`
    def get_entries_search(self, url):
        pre = f'[get_entries_search][{url}]'

        blog_posts_list = self.get_blog_posts_search()
        _total = len(blog_posts_list)

        self.logger_info(f'{pre}[blog_post_list] len[{_total}]')

        if len(blog_posts_list) >= 100:
            GVDBlogBaseIE._SLOW_DOWN = True
            self._conf_args_gvd.update({'check': False})

        posts_vid_url = [
            try_get(
                traverse_obj(post_entry, ('link', -1, 'href')) if self.keyapi == 'gvdblog.com'
                else post_entry.get('link'),
                lambda x: unquote(x))
            for post_entry in blog_posts_list
        ]

        _entries = []

        if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

            with self.create_progress_bar(_total, block_logging=False, msg=pre) as progress_bar:

                with ThreadPoolExecutor(thread_name_prefix="gvdpl") as ex:

                    futures = {
                        ex.submit(
                            partial(self.get_entries_from_blog_post, progress_bar=progress_bar),
                            _post_blog): _post_url
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
            _entries = [self.url_result(
                update_url(_post_url, query_update=self.query_upt), ie=GVDBlogPostIE.ie_key())
                for _post_url in posts_vid_url]

        if _entries:
            upt_dict(_entries, playlist_url=url)
            return _entries

    def _get_last_page(self, baseurl):
        self._pointer = 1

        def _temp(start, step):
            for i in itertools.count(start, step=step):
                self._pointer = i
                try:
                    if (webpage := try_get(
                            self._send_request(update_url_query(f"{baseurl}{i}", self.conf_args_gvd["query"])),
                            lambda x: unescape(x.text))):
                        if 'link rel="next"' not in webpage:
                            return i
                    else:
                        return -1
                except Exception:
                    return -1
        if (_aux := _temp(1, 5)) > 0:
            return _aux
        else:
            return _temp(self._pointer - 5 + 1, 1)

    def _get_entries_page(self, baseurl, npage: int = 1):
        partial_element_re = r'''(?x)
        <(?P<tag>article)
        (?:\s(?:[^>"']|"[^"]*"|'[^']*')*)?
        '''
        try:
            _htmlpage = try_get(
                self._send_request(
                    update_url_query(f"{baseurl}{npage}", query=self.conf_args_gvd['query'])),
                lambda x: get_element_by_id('us_grid_1', unescape(x.text)) if x else None)

            if not _htmlpage:
                raise ExtractorError("no webpage")

            _items = []
            for m in re.finditer(partial_element_re, _htmlpage):
                content, _ = get_element_text_and_html_by_tag(
                    m.group('tag'), _htmlpage[m.start():])
                _items.append(re.findall(r'a href=[\'"]([^\'"]+)[\'"]', content)[0])
            return _items
        except Exception as e:
            self.logger_debug(f'[get_entries_page][{baseurl}] {npage} no entries {repr(e)}')

    def get_entries(self, url: str, **kwargs):

        baseurl = f"{update_url(url, query='')}/page/"
        pre = f"[get_entries][{baseurl}]"

        self.logger_debug(f'{pre} baseurl[{baseurl}] query[{self.conf_args_gvd["query"]}]')

        items = []
        _nentries = self.conf_args_gvd['entries']
        _from = self.conf_args_gvd['from']
        if (last_page := self._get_last_page(baseurl)) > 1:
            if _from == 1 and _nentries:
                last_page = _nentries // 60 or 1
            with ThreadPoolExecutor(thread_name_prefix="gvditems") as exe:
                futures = [exe.submit(self._get_entries_page, baseurl, npage=pn) for pn in range(1, last_page + 1)]

            for fut in futures:
                if (_res := fut.result()):
                    items.extend(_res)
        elif last_page == 1:
            if _res := self._get_entries_page(baseurl, npage=1):
                items.extend(_res)

        if not items:
            raise ExtractorError('no video links')

        items = orderedSet(items)

        _nentries = _nentries or len(items)

        final_items = items[_from - 1:_from - 1 + _nentries]

        _entries = []

        if self.get_param('embed') or (self.get_param('extract_flat', '') != 'in_playlist'):

            with self.create_progress_bar(len(final_items), block_logging=False, msg=pre) as progress_bar:

                with ThreadPoolExecutor(thread_name_prefix="gvdpl") as ex:

                    futures = {ex.submit(
                        partial(
                            self.get_entries_from_blog_post, progress_bar=progress_bar), _post_url): _post_url
                        for _post_url in final_items}

                    wait(futures)

                for fut in futures:
                    try:
                        if (_res := try_get(fut.result(), lambda x: x[0])):
                            _entries += _res
                        else:
                            self.report_warning(f'{pre} no entry, fails fut {futures[fut]}')
                    except Exception as e:
                        self.report_warning(f'{pre} fails fut {futures[fut]} {str(e)}')

        else:
            _entries = [self.url_result(_post_url, ie=GVDBlogPostIE.ie_key()) for _post_url in final_items]

        if _entries:
            upt_dict(_entries, playlist_url=url)
            return _entries

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)
        self.keyapi = url

        params = {}
        query, _typenet, _typefx, namenet, namecc, namefx = try_get(
            re.search(self._VALID_URL, url),
            lambda x: x.group('query', 'type', 'type3', 'name', 'name2', 'name3'))
        if query:
            params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&')
                      if el.count('=') == 1}

        def _upt_params(arg0, arg1):
            _name_api, _id, = self.get_id(arg0, arg1)
            params['name'] = _id
            params['type'] = _name_api

        if namenet and _typenet:
            _upt_params(_typenet, namenet)
        elif namefx and _typefx:
            _upt_params(_typefx, namefx)
        self.conf_args_gvd = params

        if (_name := namenet or namecc or namefx):
            playlist_title = _name
            playlist_id = _name

        else:
            playlist_id = f'{sanitize_filename(query, restricted=True)}'.replace('%23', '')
            playlist_title = "Search"

        if self.keyapi == 'gvdblog.cc':
            entries = self.get_entries(url)
        else:
            entries = self.get_entries_search(url)

        return self.playlist_result(
            entries, playlist_id=playlist_id,
            playlist_title=playlist_title)
