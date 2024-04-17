import html
import json
import re
from urllib.parse import unquote

from yt_dlp_plugins.extractor.commonwebdriver import (
    ConnectError,
    HTTPStatusError,
    SeleniumInfoExtractor,
    dec_on_exception2,
    dec_on_exception3,
    limiter_5,
)

from ..utils import (
    ExtractorError,
    get_domain,
    js_to_json,
    sanitize_filename,
    try_get,
)


class VidozaIE(SeleniumInfoExtractor):
    IE_NAME = 'vidoza'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?vidoza\.net/(?P<id>[^.]+).html'
    _SITE_URL = 'https://vidoza.net/'

    @dec_on_exception2
    @dec_on_exception3
    @limiter_5.ratelimit("vidoza", delay=True)
    def _get_video_info(self, url, **kwargs):

        try:
            msg = kwargs.get('msg', None)
            pre = '[get_video_info]'
            if msg:
                pre = f'{msg}{pre}'
            self.logger_debug(f"{pre} {self._get_url_print(url)}")
            _headers = {'Range': 'bytes=0-', 'Referer': self._SITE_URL,
                        'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'cross-site',
                        'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}

            return self.get_info_for_format(url, headers=_headers, **kwargs)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    @dec_on_exception2
    @dec_on_exception3
    @limiter_5.ratelimit("vidoza", delay=True)
    def _send_request(self, url, **kwargs):

        try:
            self.logger_debug(f"[send_req] {self._get_url_print(url)}")
            return (self.send_http_request(url, **kwargs))
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    def _get_entry(self, url, **kwargs):

        try:
            check = kwargs.get('check', False)
            msg = kwargs.get('msg', None)
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg:
                pre = f'{msg}{pre}'
            webpage = try_get(self._send_request(url), lambda x: re.sub('[\t\n]', '', html.unescape(x.text)))
            if not webpage:
                raise ExtractorError("no video webpage")
            info_sources = try_get(re.findall(r'sourcesCode: (\[\{.*\}\])\,', webpage), lambda x: json.loads(js_to_json(x[0])))
            _formats = []
            _headers = {'Referer': self._SITE_URL}
            if info_sources:
                for source in info_sources:
                    video_url = unquote(source.get('src'))
                    res = source.get('height', '') or source.get('res', '')
                    _format = {
                        'format-id': f'http{res}',
                        'url': video_url,
                        'ext': 'mp4',
                        'http_headers': _headers

                    }
                    if res:
                        _format.update({'height': int(res)})
                    if check:
                        _host = get_domain(video_url)
                        _sem = self.get_ytdl_sem(_host)
                        with _sem:
                            _videoinfo = self._get_video_info(video_url, msg=pre)
                        if not _videoinfo:
                            self.report_warning(f"{pre}[{_format['format-id']}] {video_url} - error 404: no video info")
                        else:
                            assert isinstance(_videoinfo, dict)
                            _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})
                            _formats.append(_format)
                    else:
                        _formats.append(_format)

            if not _formats:
                raise ExtractorError("No formats found")

            self._sort_formats(_formats)

            _videoid = self._match_id(url)
            _title = try_get(re.findall(r'<h1>([^\<]+)\<', webpage), lambda x: x[0].strip('[_,-, ]'))

            entry_video = {
                'id': _videoid,
                'title': sanitize_filename(_title, restricted=True),
                'formats': _formats,
                'extractor_key': 'Vidoza',
                'extractor': 'vidoza',
                'ext': 'mp4',
                'webpage_url': url
            }

            return entry_video

        except Exception as e:
            self.to_screen(e)
            raise

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        try:

            # if not self.get_param('embed'): _check = True
            # else: _check = False

            _check = True

            return self._get_entry(url, check=_check)

        except ExtractorError:
            raise
        except Exception as e:

            self.to_screen(f"{repr(e)}")
            raise ExtractorError(repr(e))
