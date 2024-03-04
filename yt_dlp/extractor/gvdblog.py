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
from pathlib import Path
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
from .filemoon import FilemoonIE
from .streamhide import StreamHideIE
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
               for _ie in (DoodStreamIE, StreamHideIE, FilemoonIE, VoeIE, StreamSBIE, XFileShareIE)},
    'alt': {_ie.IE_NAME: _ie._VALID_URL
            for _ie in (VoeIE, StreamSBIE, XFileShareIE, FilemoonIE, StreamHideIE, DoodStreamIE)}
}

on_exception_req = my_dec_on_exception(
    TimeoutError, raise_on_giveup=False, max_tries=3, interval=1)

logger = logging.getLogger("gvdblog")


def upt_dict(info_dict: dict | list, **kwargs) -> None:
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
    def keyapi(self) -> str:
        return self._keyapi

    @keyapi.setter
    def keyapi(self, url: str):
        if _res := get_domain(url):
            self._keyapi = _res

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
        # else:
        #     _fmt = None
        self.altkey = 'legacy' if _fmt == 'http' else 'alt'
        _type = params.pop('type', None)
        name = params.pop('name', None)

        if _type and name:
            params[_type] = name

        self.query_upt = _query_upt

        self._conf_args_gvd = {
            'check': _check, 'fmt': _fmt, 'entries': _entries, 'from': _from,
            'type': _type, 'name': name, 'query': params}

    def get_entry_video(self, x, **kwargs):

        def _process_entry(x) -> dict:
            with contextlib.suppress(Exception):
                if self._downloader:
                    return self._downloader.sanitize_info(
                        self._downloader.process_ie_result(x, download=False))
            return {}

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
                        if fmt != 'best' and _entry.get('subtitles') and not _entries:
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

        if _entries:
            if len(_entries) == 2:
                _subtitles_0 = _entries[0].get('subtitles')
                _subtitles_1 = _entries[1].get('subtitles')
                if not _subtitles_0 and _subtitles_1:
                    _entries[0]['subtitles'] = _subtitles_1
                if not _subtitles_1 and _subtitles_0:
                    _entries[1]['subtitles'] = _subtitles_0

            if fmt != 'best' or len(_entries) == 1:
                return _entries[0]

            if self._downloader:
                entalt, entleg = _process_entry(_entries[0]), _process_entry(_entries[1])
                entaltfilesize = entalt.get('filesize_approx') or (
                    entalt.get('tbr', 0) * entalt.get('duration', 0) * 1024 / 8)
                entlegfilesize = entleg.get('filesize')
                if entlegfilesize and entaltfilesize and all(
                        [entaltfilesize >= 2 * entlegfilesize,
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
                    lambda y: datetime.strptime(y, '%B %d, %Y')))

        else:
            postid = post.get('id')
            title = traverse_obj(post, ('title', 'rendered', {unescape}))
            postdate = try_get(
                post.get('date'), lambda x: datetime.fromisoformat(x.split('T')[0]))

        if isinstance(title, str):
            title = sanitize_filename(
                re.sub(r'\s*-*\s*(GVDBlog|GayLeakTV)[^\s]*', '', title, flags=re.IGNORECASE),
                restricted=True).replace('_-_', '_')
        else:
            title = None

        return (postdate, title, postid)

    def _get_metadata(self, post, premsg) -> tuple:
        url = postdate = title = postid = list_candidate_videos = None

        if isinstance(post, str) and post.startswith('http'):
            url = unquote(post)
            premsg += f'[{url}]'
            self.report_extraction(url)
            if (
                post_content := try_get(
                    self._send_request(url),
                    lambda x: re.sub('[\t\n]', '', unescape(x.text)))
            ):
                postdate, title, postid = self.get_info(post_content)
                list_candidate_videos = self.get_urls(post_content, msg=url)
        elif isinstance(post, dict):
            url = try_get(post.get('link'), lambda x: unquote(x))
            post_content = traverse_obj(post, ('content', 'rendered', {unescape}))
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

            for i, _el in enumerate(entries):
                if len(entries) > 1:
                    _original_url = f'{url}#{i + 1}'
                    _comment = f'{url} [{i + 1}]'
                else:
                    _original_url = url
                    _comment = url
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

    @classmethod
    @on_exception_req
    def _klass_send_request(cls, url, **kwargs):

        pre = f'[send_req][{cls._get_url_print(url)}]'
        if (msg := kwargs.get('msg', None)):
            pre = f'{msg}{pre}'
        _limiter = limiter_1 if cls._SLOW_DOWN else limiter_0_1

        with _limiter.ratelimit("gvdblog", delay=True):
            try:
                return cls._send_http_request(url, **kwargs)
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
            (gayleaktv\.com/[^/_\?]+)|
            (fxggxt\.com/[^/_\?]+)|
            (gvdblog\.cc/video/[^\?/]+)|
            (gvdblog\.net/[^/\?]+))
        /?(\?(?P<query>[^#]+))?$'''

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):
        self.report_extraction(url)
        self.keyapi = url

        params = {}
        if query := try_get(
            re.search(self._VALID_URL, url), lambda x: x.group('query')
        ):
            params = {
                el.split('=')[0]: el.split('=')[1]
                for el in query.split('&') if el.count('=') == 1}

        self.conf_args_gvd = params

        _url = update_url(url, query='')

        entries, title, _ = self.get_entries_from_blog_post(_url)
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
            (gayleaktv\.com/(?P<type4>(actor|category))/(?P<name4>[^\?/]+))|
            (fxggxt\.com/(?:_search|(?P<type3>(actor|category))/(?P<name3>[^\?/]+)))|
            (gvdblog\.net/(?:_search|(?P<type>(actor|category|tag))/(?P<name>[^\?/]+)))|
            (gvdblog\.cc/(?:(actors|categories)/(?P<name2>[^\?/]+))))
        /?(\?(?P<query>[^#]+))?$'''

    _BASE_API = {
        'gvdblog.net': "https://gvdblog.net/wp-json/wp/v2/posts?per_page=100",
        'fxggxt.com': "https://fxggxt.com/wp-json/wp/v2/posts?per_page=100",
        'gayleaktv.com': "https://gayleaktv.com/wp-json/wp/v2/posts?per_page=100"}

    _BASE_CONF = {
        'gvdblog.net': "https://gvdblog.net/wp-json/wp/v2/%s?per_page=100&page=",
        'fxggxt.com': "https://fxggxt.com/wp-json/wp/v2/%s?per_page=100&page=",
        'gayleaktv.com': "https://gayleaktv.com/wp-json/wp/v2/%s?per_page=100&page=",
    }

    _FILE_CONF = "/Users/antoniotorres/.config/yt-dlp/%s_conf.json"

    @classmethod
    def update_conf(cls, api=None):
        if not api:
            list_keys = list(cls._BASE_CONF.keys())
        else:
            list_keys = [api]

        for keyapi in list_keys:
            total_json = {}
            for _key in ['actors', 'categories', 'tags']:
                el = []
                i = 0
                while True:
                    i += 1
                    _url = cls._BASE_CONF[keyapi] % _key
                    if (res := try_get(cls._klass_send_request(f'{_url}{i}'), lambda x: x.json())):
                        el.extend(res)
                    else:
                        break
                if el:
                    el_dict = {_el['slug']: _el for _el in el}
                    total_json[_key] = el_dict
            if total_json:
                with open(cls._FILE_CONF % keyapi.split('.')[0], 'w') as f:
                    json.dump(total_json, f)

    def get_conf(self):
        _file_conf = GVDBlogPlaylistIE._FILE_CONF % self.keyapi.split('.')[0]
        if (datetime.now() - datetime.fromtimestamp(Path(_file_conf).stat().st_mtime)).days > 1:
            self.to_screen(f'Updating configuration file for {self.keyapi}...')
            GVDBlogPlaylistIE.update_conf(api=self.keyapi)
        with open(_file_conf, 'r') as f:
            return json.load(f)

    def get_id(self, label, name):
        data = self.get_conf()
        _map = {
            'actor': 'tags' if self.keyapi == 'gayleaktv.com' else 'actors',
            'category': 'categories', 'tag': 'tags'}
        attribute = _map[label]
        return (attribute, traverse_obj(data[attribute], (name, 'id')))

    def send_api_search(self, query):
        if not (video_entries := try_get(
            self._send_request(GVDBlogPlaylistIE._BASE_API[self.keyapi], params=query),
            lambda x: x.json())
        ):
            raise_extractor_error("no video entries")
        else:
            self.logger_debug(
                f'[entries result] videos entries [{len(video_entries)}]')
            return video_entries

    def get_blog_posts_search(self) -> list:
        if (_query := self.conf_args_gvd['query']):
            query = '&'.join([f'{key}={value}' for key, value in _query.items()])
            query = query.replace('published', 'date')
            if 'orderby' not in query:
                query += '&orderby=date'
            params = {
                el.split('=')[0]: el.split('=')[1]
                for el in query.split('&') if el.count('=') == 1}
            self._conf_args_gvd['query'] = params
        else:
            params = {}

        urlquery = []

        for key, val in params.items():
            if key == 'published':
                urlquery.append(
                    f"published-max={val}T23:59:59&published-min={val}T00:00:00")
            elif key == 'date':
                urlquery.append(
                    f"before={val}T23:59:59&after={val}T00:00:00")
            elif key not in ('entries', 'from'):
                urlquery.append(f"{key}={val}")

        if post_blog_entries_search := self.send_api_search('&'.join(urlquery)):
            _nentries = int_or_none(params.get('entries'))
            _from = int(params.get('from', 1))
            return (
                post_blog_entries_search[_from - 1: _from - 1 + _nentries]
                if _nentries is not None and _nentries >= 0
                else post_blog_entries_search[_from - 1:])
        else:
            return []

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
                post_entry.get('link'),
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

        def _temp(start: int, step: int):
            try:
                for i in itertools.count(start, step=step):
                    self._pointer = i
                    if (webpage := try_get(
                            self._send_request(update_url_query(f"{baseurl}{i}", self.conf_args_gvd["query"])),
                            lambda x: unescape(x.text))):
                        if 'link rel="next"' not in webpage:
                            return i
                    else:
                        return -1
            except Exception:
                return -1

        if (_aux := _temp(1, 5)) and _aux > 0:
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
                lambda x: get_element_by_id('us_grid_1', unescape(x.text)))

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
        if (last_page := self._get_last_page(baseurl)) and last_page > 1:
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

        if not isinstance(items, list):
            raise ExtractorError('no video links')

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

    def _real_extract(self, url: str):

        self.report_extraction(url)
        self.keyapi = url

        params = {}
        query, _typenet, _typefx, _typegl, namenet, namecc, namefx, namegl = try_get(
            re.search(self._VALID_URL, url),
            lambda x: x.group('query', 'type', 'type3', 'type4', 'name', 'name2', 'name3', 'name4')) or [None] * 8
        if query:
            params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&')
                      if el.count('=') == 1}

        def _upt_params(arg0, arg1):
            if _res := self.get_id(arg0, arg1):
                params['name'] = _res[1]
                params['type'] = _res[0]

        if namenet and _typenet:
            _upt_params(_typenet, namenet)
        elif namefx and _typefx:
            _upt_params(_typefx, namefx)
        elif namegl and _typegl:
            _upt_params(_typegl, namegl)
        self.conf_args_gvd = params

        if (_name := namenet or namecc or namefx or namegl):
            playlist_title = _name
            playlist_id = _name

        else:
            playlist_id = f'{sanitize_filename(query, restricted=True)}'.replace('%23', '')
            playlist_title = "Search"

        if self.keyapi in ('gvdblog.cc'):
            entries = self.get_entries(url)
        else:
            entries = self.get_entries_search(url)

        return self.playlist_result(
            entries, playlist_id=playlist_id,
            playlist_title=playlist_title)
