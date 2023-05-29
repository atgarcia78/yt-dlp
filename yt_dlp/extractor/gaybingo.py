import html

from ..utils import ExtractorError, sanitize_filename, try_get
from .commonwebdriver import dec_on_exception3, SeleniumInfoExtractor, limiter_5, HTTPStatusError, ConnectError


class GayBingoIE(SeleniumInfoExtractor):

    _SITE_URL = 'https://gay.bingo'
    IE_NAME = 'gaybingo'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?gay.bingo/video/(?P<id>\d+)(?:\?|$)'

    @dec_on_exception3
    @limiter_5.ratelimit("gaybingo2", delay=True)
    def _send_request(self, url, **kwargs):

        _kwargs = kwargs.copy()
        pre = f'[send_req][{self._get_url_print(url)}]'
        if (msg := _kwargs.pop('msg', None)):
            pre = f'{msg}{pre}'

        try:
            return self.send_http_request(url, **_kwargs)
        except (HTTPStatusError, ConnectError) as e:
            _msg_error = f"{repr(e)}"
            self.logger_debug(f"{pre}: {_msg_error}")

    def _real_extract(self, url):

        self.report_extraction(url)

        webpage = try_get(self._send_request(url), lambda x: html.unescape(x.text))

        assert self._downloader

        iehtml5 = self._downloader.get_info_extractor('HTML5MediaEmbed')
        gen = iehtml5.extract_from_webpage(self._downloader, url, webpage)
        _entry = next(gen)

        if not _entry:
            ExtractorError("no video formats")

        _entry = self._downloader.sanitize_info(_entry)
        title = self._search_regex(r'title="([^"]+)"', webpage, 'title')
        videoid = self._match_id(url)
        duration = try_get(self._search_regex(r'\sduration="([^"]+)"', webpage, 'duration'), lambda x: int(x))

        _entry.update({
            'id': videoid,
            'title': sanitize_filename(title, restricted=True),
            'webpage_url': url,
            'duration': duration,
            'extractor': self.IE_NAME,
            'extractor_key': self.ie_key()})

        return _entry
