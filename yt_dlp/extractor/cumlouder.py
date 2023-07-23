import re
import html
from .commonwebdriver import (
    SeleniumInfoExtractor,
    HTTPStatusError,
    ConnectError,
    ReExtractInfo,
    dec_on_driver_timeout,
    dec_on_exception2,
    limiter_1,
    my_dec_on_exception,
    raise_reextract_info,
    cast,
    get_host
)
from ..utils import (
    ExtractorError,
    sanitize_filename,
    try_get,
    traverse_obj,
    int_or_none
)

import logging
logger = logging.getLogger('cumlouder')

on_exception = my_dec_on_exception(
    (TimeoutError, ExtractorError, ReExtractInfo), raise_on_giveup=False, max_tries=3, jitter="my_jitter", interval=1)

on_retry_vinfo = my_dec_on_exception(
    ReExtractInfo, raise_on_giveup=True, max_tries=3, jitter="my_jitter", interval=1)


class CumlouderIE(SeleniumInfoExtractor):
    IE_NAME = 'cumlouder'  # type: ignore
    _VALID_URL = r'https?://(www\.)?cumlouder\.com/(?:(embed/(?P<id>\d+)/?)|(\w+/videos/(?P<title>[\w\-\_]+)))'

    @on_exception
    @dec_on_exception2
    @limiter_1.ratelimit("cumlouder", delay=True)
    def _get_video_info(self, url, **kwargs):

        msg = kwargs.get('msg')
        pre = f'[get_video_info][{self._get_url_print(url)}]'
        if msg:
            pre = f'{msg}{pre}'

        _headers = kwargs.get('headers', {})
        headers = {'Range': 'bytes=0-', 'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'cors',
                   'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}

        headers.update(_headers)

        try:
            return self.get_info_for_format(url, headers=headers)
        except (HTTPStatusError, ConnectError) as e:
            self.logger_debug(f"{pre}: error - {repr(e)}")
        except ReExtractInfo as e:
            self.logger_debug(f"{pre}: error - {repr(e)}, will retry")
            raise

    @on_exception
    @dec_on_exception2
    @dec_on_driver_timeout
    @limiter_1.ratelimit("cumlouder2", delay=True)
    def _send_request(self, url, **kwargs):

        pre = f'[send_request][{self._get_url_print(url)}]'
        _kwargs = kwargs.copy()
        if (msg := _kwargs.pop('msg', None)):
            pre = f'{msg}{pre}'

        driver = _kwargs.pop('driver', None)

        self.logger_debug(pre)
        if driver:
            driver.get(url)
        else:
            try:
                return self.send_http_request(url, **_kwargs)
            except (HTTPStatusError, ConnectError) as e:
                _msg_error = f"{repr(e)}"
                self.logger_debug(f"{pre}: {_msg_error}")
                return {"error_res": _msg_error}

    def _real_extract(self, url):

        webpage = cast(str, try_get(self._send_request(url), lambda x: html.unescape(re.sub('[\t\n]', '', x.text))))
        title = try_get(self._html_extract_title(webpage), lambda x: x.split(" | ")[0].replace(" ", "_").replace(",", ""))
        video_id = try_get(re.search(r"'id'\s*:\s*'cumlouder_(?P<video_id>\d+)'", webpage), lambda x: x.group('video_id'))

        info = cast(dict, try_get(re.search(r'<source src="(?P<videourl>.*)" type="video/mp4" label="(?P<w>\d+)p" res="(?P<h>\d+)"', webpage), lambda x: x.groupdict()))

        videourl = try_get(traverse_obj(info, "videourl"), lambda x: x.replace("&amp;", "&"))
        weight = try_get(traverse_obj(info, "w"), lambda x: int_or_none(x))
        height = try_get(traverse_obj(info, "h"), lambda x: int_or_none(x))
        if not videourl:
            raise ExtractorError("video not found")

        _format = {
            'format_id': 'http-mp4',
            'url': videourl,
            'weight': weight,
            'height': height,
            'ext': 'mp4'}

        _host = cast(str, get_host(videourl))
        with self.get_ytdl_sem(_host):
            _videoinfo = cast(dict, self._get_video_info(videourl))
        if not _videoinfo:
            raise_reextract_info("no video info")

        _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize'], 'accept_ranges': _videoinfo['accept_ranges']})

        entry_video = {
            'id': video_id,
            'title': sanitize_filename(title, restricted=True),
            'formats': [_format],
            'ext': 'mp4'
        }

        return entry_video
