import html
import re


from ..utils import ExtractorError, sanitize_filename, try_get, get_domain, traverse_obj, url_basename, base_url
from .commonwebdriver import (
    dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_5, HTTPStatusError, ConnectError)


class ThisvidgayIE(SeleniumInfoExtractor):

    IE_NAME = 'thisvidgay'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?thisvidgay\.com/[^/]+/?$'
    _SITE_URL = 'https://thisvidgay.com/'

    @dec_on_exception2
    @dec_on_exception3
    @limiter_5.ratelimit("thisvidgay2", delay=True)
    def _get_video_info(self, url, **kwargs):

        headers = kwargs.get('headers', {})

        self.logger_debug(f"[get_video_info] {url}")
        _headers = {'Range': 'bytes=0-',
                    'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
                    'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
        _headers.update(headers)
        try:
            return self.get_info_for_format(url, headers=_headers)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    @dec_on_exception
    @dec_on_exception2
    @dec_on_exception3
    @limiter_5.ratelimit("thisvidgay", delay=True)
    def _send_request(self, url, **kwargs):

        driver = kwargs.get('driver', None)

        if driver:
            self.logger_debug(f"[send_request] {url}")
            driver.get(url)
        else:
            try:
                return self.send_http_request(url)
            except (HTTPStatusError, ConnectError) as e:
                self.report_warning(f"[send_requests] {self._get_url_print(url)}: error - {repr(e)}")

    def _get_entry(self, url, **kwargs):

        if '/wp-content/plugins/clean-tube-player/' not in url:

            webpage = try_get(self._send_request(url), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)) if x else None)

            if not webpage:
                raise ExtractorError("no webpage")

            _title = self._html_search_regex((r'>([^<]+)</h1>', r'(?s)<title\b[^>]*>([^<]+)</title>'), webpage, 'title', fatal=False)

            if self.IE_NAME != "biguz":

                _embedurl = self._html_search_regex(r'iframe src="(https?://%s/wp-content[^"]+)"' % get_domain(url), webpage, 'ifrurl', fatal=False)

                webpage_embeds = try_get(self._send_request(_embedurl), lambda x: html.unescape(x.text) if x else None)

                if not webpage_embeds:
                    raise ExtractorError("no webpage")

                _videoid = None

            else:

                query = try_get(re.search(self._VALID_URL, url), lambda x: x.group('query')) or ''
                params = {el.split('=')[0]: el.split('=')[1] for el in query.split('&')}
                if not (_videoid := params.get('id')):
                    raise ExtractorError("no video info")
                _embedurl = f"{self._SITE_URL}/embed.php?id={_videoid}"
                webpage_embeds = try_get(self._send_request(_embedurl), lambda x: html.unescape(x.text) if x else None)

                if not webpage_embeds:
                    raise ExtractorError("no webpage")

        else:

            webpage_embeds = try_get(self._send_request(url), lambda x: html.unescape(x.text) if x else None)
            if not webpage_embeds:
                raise ExtractorError("no webpage")
            _title = None
            _embedurl = url
            _videoid = None

        assert self._downloader
        iehtml5 = self._downloader._ies['HTML5MediaEmbed']
        gen = iehtml5.extract_from_webpage(self._downloader, _embedurl, webpage_embeds)

        _entry = next(gen)

        if not _entry:
            ExtractorError("no video formats")

        _entry = self._downloader.sanitize_info(_entry)

        self.logger_debug(_entry)

        if not _videoid:
            if (_thumb := _entry.get('thumbnail')):
                _videoid = _thumb.split('/')[-1].split('.')[0].strip('[ ._-\n]')
            elif (_url := traverse_obj(_entry, ('formats', 0, 'url'))):
                _videoid = try_get(re.findall(r'([a-zA-Z0-9]+)\.mp4', url_basename(_url)), lambda x: x[0])
                if not _videoid or len(_videoid) < 8:
                    _base = base_url(_url).strip('/').split('/')
                    _base.reverse()
                    for token in _base:
                        _tokens = re.findall(r'([a-zA-Z0-9]+)', token)
                        if _tokens:
                            _videoid = max(_tokens, key=len)
                            if _videoid and len(str(_videoid)) >= 8:
                                break
            if not _videoid or len(str(_videoid)) < 8:
                _videoid = self._generic_id(url)

        _entry.update({'id': _videoid, 'webpage_url': url, 'extractor': self.IE_NAME,
                       'extractor_key': self.ie_key()})

        if _title:
            _entry.update({'title': sanitize_filename(_title, restricted=True)})
        else:
            _entry['title'] = None

        for f in _entry['formats']:

            _host = get_domain(f['url'])
            _sem = self.get_ytdl_sem(_host)
            with _sem:
                _videoinfo = self._get_video_info(f['url'], headers=f['http_headers'])
            if _videoinfo and isinstance(_videoinfo, dict):
                f.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})

        return _entry

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        try:
            return self._get_entry(url)
        except ExtractorError:
            raise
        except Exception as e:

            self.to_screen(f"{repr(e)}")
            raise ExtractorError(repr(e))


class GaytubesIE(ThisvidgayIE):

    IE_NAME = 'gaytubes'

    _DOMAIN_REGEX = r'(?:gay.+tubes|twink-hub|twinksboys|gayfeet)\.[^/]+'
    _VALID_URL = r'https?://(?:www\.)?%s/(?:([^/]+/?$)|(wp-content/plugins/clean-tube-player/public/player-x.php\?.+))' % _DOMAIN_REGEX


class BiguzIE(ThisvidgayIE):

    IE_NAME = 'biguz'
    _VALID_URL = r'https?://(?:www\.)?biguz\.net/(?:embed|watch)\.php\?(?P<query>.+)'
    _SITE_URL = 'https://biguz.net'
