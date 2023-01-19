import sys
import traceback


from ..utils import ExtractorError
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_1


class TrafficDePotIE(SeleniumInfoExtractor):
    IE_NAME = 'trafficdepot'
    _VALID_URL = r'https?://trafficdepot\.xyz/v/(?P<id>.*)'

    def _get_video_info(self, url):
        self.logger_debug(f"[get_video_info] {url}")
        return self.get_info_for_format(url)

    def _send_request(self, driver, url):
        self.logger_debug(f"[send_request] {url}")
        driver.get(url)

    @dec_on_exception
    @limiter_1.ratelimit("trafficdepot", delay=True)
    def request_to_host(self, _type, *args, **kwargs):

        if _type == "video_info":
            return self._get_video_info(*args)
        elif _type == "url_request":
            self._send_request(*args)
        elif _type == "post":
            res = TrafficDePotIE._CLIENT.post(*args, **kwargs)
            res.raise_for_status()
            return (res.json())

    def _get_video_entry(self, url):

        _headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Referer': url,
            'Origin': 'https://trafficdepot.xyz'
        }
        _data = {"r": "https://porndune.com/", "d": "trafficdepot.xyz"}

        videoid = self._match_id(url)

        try:

            videojson = self.request_to_host("post", f"https://trafficdepot.xyz/api/source/{videoid}", data=_data, headers=_headers)

            _entry_video = {}

            if videojson.get('data'):
                self.to_screen(videojson['data'])

                _formats = []
                for _format in videojson['data']:
                    _videourl = _format.get('file')
                    if not _videourl:
                        continue
                    _info = self.request_to_host("video_info", _videourl)
                    if not _info:
                        continue
                    _desc = _format.get('label', 'mp4')
                    _format_video = {
                        'format_id': f"http-{_desc}",
                        'url': _info.get('url'),
                        'filesize': _info.get('filesize'),
                        'ext': 'mp4'
                    }

                    if _desc != 'mp4':
                        _format_video.update(
                            {
                                'resolution': _desc,
                                'height': int(_desc[:-1])
                            }
                        )

                    _formats.append(_format_video)

                if _formats:
                    self._sort_formats(_formats)

                    _entry_video = {
                        'id': videoid,
                        'formats': _formats,
                        'ext': "mp4"
                    }

                    return _entry_video

            if not _entry_video:
                raise ExtractorError("no entry video")

        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(repr(e))

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        try:

            return self._get_video_entry(url)

        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
