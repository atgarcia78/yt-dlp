import html
import re
from datetime import datetime


from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import (
    dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_1, limiter_5, HTTPStatusError, ConnectError)


class GaygoIE(SeleniumInfoExtractor):

    IE_NAME = 'gaygo'
    _VALID_URL = r'https?://(.+\.)?gaygo\.tv/(?:view|embed)/(?P<id>\d+)'
    _SITE_URL = 'https://gaygo.tv/'

    @dec_on_exception2
    @dec_on_exception3
    @limiter_5.ratelimit("gaygo2", delay=True)
    def _get_video_info(self, url, **kwargs):

        headers = kwargs.get('headers', None)

        self.logger_debug(f"[get_video_info] {url}")
        _headers = {'Range': 'bytes=0-', 'Referer': headers['Referer'],
                    'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
                    'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
        try:
            # _host = get_domain(url)

            # with self.get_param('lock'):
            #     if not (_sem:=traverse_obj(self.get_param('sem'), _host)):
            #         _sem = Lock()
            #         self.get_param('sem').update({_host: _sem})

            # with _sem:

            return self.get_info_for_format(url, headers=_headers)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    @dec_on_exception
    @dec_on_exception2
    @dec_on_exception3
    @limiter_1.ratelimit("gaygo", delay=True)
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

        check = kwargs.get('check', False)

        videoid = self._match_id(url)
        _url = f'{self._SITE_URL}/view/{videoid}'
        webpage = try_get(self._send_request(_url), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)) if x else None)

        if not webpage:
            raise ExtractorError("no webpage")

        _title = self._html_search_regex((r'>([^<]+)</h3>', r'(?s)<title\b[^>]*>([^<]+)</title>'), webpage, 'title', fatal=False)
        videourl = try_get(re.findall(r'data-videolink\s*=\s*"([^\"]+)"', webpage), lambda x: x[0])
        videourl += f'?rnd={int(datetime.timestamp(datetime.now())*1000)}'

        headers = {'Referer': self._SITE_URL}

        _format = {
            'format_id': 'http-mp4',
            'url': videourl,
            'http_headers': headers,
            'ext': 'mp4'
        }

        if check:
            _videoinfo = self._get_video_info(videourl, headers=headers)
            if not _videoinfo:
                raise ExtractorError("error 404: no video info")
            else:
                _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})

        _entry_video = {
            'id': videoid,
            'title': sanitize_filename(_title, restricted=True),
            'formats': [_format],
            'extractor_key': self.ie_key(),
            'extractor': self.IE_NAME,
            'ext': 'mp4',
            'webpage_url': _url
        }

        return _entry_video

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
