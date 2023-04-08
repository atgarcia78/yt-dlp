import html
import re
import base64


from .commonwebdriver import (

    ConnectError,
    HTTPStatusError,
    SeleniumInfoExtractor,
    dec_on_exception,
    dec_on_exception2,
    dec_on_exception3,
    limiter_1,
)


from ..utils import (
    ExtractorError,
    get_domain,
    sanitize_filename,
    try_get,
    try_call)


class HexUploadIE(SeleniumInfoExtractor):

    IE_NAME = 'hexupload'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?hexupload\.net/(embed-)?(?P<id>[^\/$]+)(?:\/|$)'
    _SITE_URL = 'https://hexupload.net/'

    @dec_on_exception2
    @dec_on_exception3
    @limiter_1.ratelimit("hexupload", delay=True)
    def _get_video_info(self, url, msg=None):
        try:
            pre = '[get_video_info]'
            if msg:
                pre = f'{msg}{pre}'
            self.logger_debug(f"{pre} {self._get_url_print(url)}")
            _headers = {'Range': 'bytes=0-', 'Referer': self._SITE_URL,
                        'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
                        'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}

            return self.get_info_for_format(url, headers=_headers)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    @dec_on_exception
    @dec_on_exception3
    @dec_on_exception2
    def _send_request(self, url, **kwargs):

        driver = kwargs.get('driver', None)

        if driver:
            with limiter_1.ratelimit("hexupload2", delay=True):
                self.logger_debug(f"[send_request] {url}")
                driver.get(url)
        else:
            with limiter_1.ratelimit("hexupload2", delay=True):
                self.logger_debug(f"[send_request] {url}")
                try:
                    return self.send_http_request(url)
                except (HTTPStatusError, ConnectError) as e:
                    self.report_warning(f"[send_request] {self._get_url_print(url)}: error - {repr(e)}")

    def _get_entry(self, url, **kwargs):

        check = kwargs.get('check', False)
        msg = kwargs.get('msg', None)

        pre = f'[get_entry][{self._get_url_print(url)}]'
        if msg:
            pre = f'{msg}{pre}'

        webpage = try_get(self._send_request(url), lambda x: html.unescape(x.text) if not isinstance(x, dict) else x)
        if not webpage:
            raise ExtractorError("no webpage")
        video_url = try_get(re.search(r'b4aa\.buy\("([^"]+)"', webpage), lambda x: try_call(lambda: base64.b64decode(x.groups()[0]).decode('utf-8')))
        if not video_url:
            raise ExtractorError("no videourl")

        videoid = self._match_id(url)
        title = try_call(lambda: re.sub(r'(\s+-+\s+)?hexupload(\s+-+\s+)?|\.mp4', '', self._html_extract_title(webpage), flags=re.IGNORECASE))  # type: ignore

        _format = {
            'format_id': 'http-mp4',
            'url': video_url,
            'ext': 'mp4',
            'http_headers': {'Referer': self._SITE_URL}
        }

        if check:
            _host = get_domain(video_url)

            _sem = self.get_ytdl_sem(_host)

            with _sem:
                _videoinfo = self._get_video_info(video_url, msg=pre)
            if not _videoinfo:
                raise ExtractorError("error 404: no video info")
            assert isinstance(_videoinfo, dict)
            _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})

        _entry_video = {
            'id': videoid,
            'title': sanitize_filename(title, restricted=True),
            'formats': [_format],
            'extractor_key': self.ie_key(),
            'extractor': self.IE_NAME,
            'ext': 'mp4',
            'webpage_url': url
        }
        return _entry_video

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        try:

            if not self.get_param('embed'):
                _check = True
            else:
                _check = False

            return self._get_entry(url, check=_check)

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))
