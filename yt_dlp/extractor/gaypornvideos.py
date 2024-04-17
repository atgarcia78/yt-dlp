import re

from yt_dlp_plugins.extractor.commonwebdriver import (
    ConnectError,
    HTTPStatusError,
    SeleniumInfoExtractor,
    dec_on_exception2,
    dec_on_exception3,
    limiter_1,
)

from ..utils import ExtractorError, sanitize_filename, try_get


class GayPornVideosIE(SeleniumInfoExtractor):
    IE_NAME = "gaypornvideos"
    _VALID_URL = r'https?://(www\.)?gaypornvideos\.cc/[^/]+/?$'
    _SITE_URL = 'https://gaypornvideos.cc/'

    @dec_on_exception3
    @dec_on_exception2
    def _get_video_info(self, url, **kwargs):

        pre = f'[get_video_info][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'

        _headers = {'Range': 'bytes=0-', 'Referer': self._SITE_URL,
                    'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors',
                    'Sec-Fetch-Site': 'cross-site', 'Pragma': 'no-cache',
                    'Cache-Control': 'no-cache'}

        with limiter_1.ratelimit(self.IE_NAME, delay=True):
            try:
                self.logger_debug(pre)
                return self.get_info_for_format(url, headers=_headers)
            except (HTTPStatusError, ConnectError) as e:
                _msg_error = f"{repr(e)}"
                self.logger_debug(f"{pre}: {_msg_error}")
                return {"error_res": _msg_error}

    @dec_on_exception3
    @dec_on_exception2
    def _send_request(self, url, **kwargs):

        driver = kwargs.get('driver', None)
        pre = f'[send_request][{self._get_url_print(url)}]'
        if (msg := kwargs.get('msg')):
            pre = f'{msg}{pre}'

        with limiter_1.ratelimit(f"{self.IE_NAME}2", delay=True):
            self.logger_debug(pre)
            if driver:
                driver.get(url)
            else:
                try:
                    return self.send_http_request(url)
                except (HTTPStatusError, ConnectError) as e:
                    _msg_error = f"{repr(e)}"
                    self.logger_debug(f"{pre}: {_msg_error}")
                    return {"error_res": _msg_error}

    def _get_entry(self, url, **kwargs):

        check = kwargs.get('check', False)
        msg = kwargs.get('msg', None)

        try:
            pre = f'[get_entry][{self._get_url_print(url)}]'
            if msg:
                pre = f'{msg}{pre}'
            webpage = try_get(self._send_request(url, msg=pre), lambda x: x.text.replace("\n", "") if not isinstance(x, dict) else x)
            self.raise_from_res(webpage, "no webpage")
            title, videoid, videourl = try_get(re.search(r'og:title["\'] content=["\']([^"\']+)["\'].*gaypornvideos\.cc/\?p=([^"\']+)["\'].*contentURL["\'] content=["\']([^"\']+)["\']', webpage), lambda x: x.groups()) or ("", "", "")

            if not videourl:
                raise ExtractorError("no video url")

            # self.to_screen(videourl)

            _format = {
                'format_id': 'http-mp4',
                'url': videourl,
                'http_headers': {'Referer': self._SITE_URL},
                'ext': 'mp4'
            }

            if check:
                _video_info = self._get_video_info(videourl)
                self.to_screen(_video_info)
                self.raise_from_res(_video_info, "no video info")
                _format.update(_video_info)

            _entry = {
                'id': videoid,
                'title': sanitize_filename(title.split(' - GayPornVideos')[0], restricted=True),
                'formats': [_format],
                'ext': 'mp4',
                'extractor_key': 'GayPornVideos',
                'extractor': 'gaypornvideos',
                'webpage_url': url}

            return _entry

        except Exception:
            raise

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
            self.to_screen(f"{repr(e)}")
            raise ExtractorError(repr(e))
