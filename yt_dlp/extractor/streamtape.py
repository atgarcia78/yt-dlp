import re
import sys
import time
import traceback
import html

from ..utils.networking import normalize_url as escape_url
from ..utils import ExtractorError, sanitize_filename, try_get, get_domain
from .commonwebdriver import raise_extractor_error, dec_on_exception2, dec_on_exception3, HTTPStatusError, ConnectError, SeleniumInfoExtractor, limiter_0_1, limiter_1, By
import logging
import subprocess

logger = logging.getLogger("streamtape")


class video_or_error_streamtape:

    def __call__(self, driver):

        elh1 = driver.find_elements(By.CSS_SELECTOR, "h1")
        if elh1:  # error
            errormsg = elh1[0].get_attribute('innerText').strip("!")
            return ("error", errormsg)

        elover = driver.find_elements(By.CLASS_NAME, "play-overlay")
        if elover:
            for _ in range(5):
                try:
                    elover[0].click()
                    time.sleep(1)
                except Exception:
                    break

        if (el_vid := driver.find_elements(By.CSS_SELECTOR, "video")):
            if (_src := el_vid[0].get_attribute('src')):
                _title = try_get(driver.find_elements(By.CSS_SELECTOR, 'h2'), lambda x: x[0].text)
                return (_src, _title)
        return False


class StreamtapeIE(SeleniumInfoExtractor):

    IE_NAME = 'streamtape'  # type: ignore

    _VALID_URL = r'https?://(www.)?(?:streamtape|streamta)\.[^/]+/(?:d|e|v)/(?P<id>[a-zA-Z0-9_-]+)/?'
    _EMBED_REGEX = [r'<iframe[^>]+?src=([\"\'])(?P<url>https?://(www\.)?streamtape\.[^/]+/(?:e|v|d)/.+?)\1']

    @dec_on_exception3
    @dec_on_exception2
    @limiter_1.ratelimit("streamtape", delay=True)
    def _get_video_info(self, url, headers=None, msg=None):

        if msg:
            pre = f'{msg}[get_video_info]'
        else:
            pre = '[get_video_info]'
        self.logger_debug(f"{pre} {self._get_url_print(url)}")
        _headers = {'Range': 'bytes=0-',
                    'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
                    'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
        if headers:
            _headers.update(headers)
        try:
            return self.get_info_for_format(url, headers=_headers)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {str(e)}")

    @dec_on_exception3
    @dec_on_exception2
    def _send_request(self, url, **kwargs):

        driver = kwargs.get('driver', None)
        msg = kwargs.get('msg', None)
        if msg:
            pre = f'{msg}[send_req]'
        else:
            pre = '[send_req]'
        lim = kwargs.get('lim', limiter_1)

        with lim.ratelimit("streamtape2", delay=True):

            self.logger_debug(f"{pre} {self._get_url_print(url)}")
            if driver:
                driver.get(url)
            else:
                try:
                    return self.send_http_request(url)
                except (HTTPStatusError, ConnectError) as e:
                    self.logger_debug(f"[send_request] {self._get_url_print(url)}: error - {repr(e)}")
                    return {"error_sendreq": f"{str(e).split(' for url')[0]}"}

    def _get_entry(self, url, **kwargs):

        check = kwargs.get('check', True)
        msg = kwargs.get('msg', None)
        webpage = kwargs.get('webpage', None)
        videoid = self._match_id(url)
        _url = url.split(videoid)[0] + videoid

        try:

            _url = _url.replace('/e/', '/v/')
            pre = f'[get_entry][{self._get_url_print(_url)}]'
            if msg:
                pre = f'{msg}{pre}'
            if not webpage:
                webpage = try_get(self._send_request(_url, msg=pre, lim=limiter_0_1), lambda x: x if isinstance(x, dict) else html.unescape(x.text))

            _msg_error = ""
            if not webpage or (isinstance(webpage, dict) and (_msg_error := webpage.get('error_sendreq'))):
                raise_extractor_error(f"{_msg_error} no webpage")
            assert isinstance(webpage, str)
            el_node = try_get(re.findall(r'var srclink\s+=\s+\$\([\'\"]#([^\'\"]+)[\'\"]', webpage), lambda x: x[0])
            if not el_node:
                raise_extractor_error("error when retrieving video url")
            _code = try_get(re.findall(r'ById\([\'\"]%s[\'\"]\)\.innerHTML\s+=\s+([^;]+;)' % (el_node), webpage), lambda x: "const res = " + x[0])
            # self.to_screen(_code)

            video_url = None
            try:
                _res = subprocess.run(["node", "-e", f"{_code}console.log(res)"], capture_output=True, encoding="utf-8").stdout.strip('\n')
                video_url = 'https:' + _res + '&stream=1'
            except Exception as e:
                logger.exception(repr(e))
                raise_extractor_error("error video url")

            _title = self._html_search_regex((r'>([^<]+)</h2>', r'(?s)<title\b[^>]*>([^<]+)</title>'), webpage, 'title', fatal=False)

            if not _title:
                _title = self._html_search_meta(('og:title', 'twitter:title'), webpage, None)
                if not _title:
                    raise_extractor_error("error title")

            _title = _title.split('@')[0].replace('.mp4', '').strip('\n_ .-')

            _headers = {'Referer': f'https://{get_domain(url)}/', 'Origin': f'https://{get_domain(url)}'}
            _format = {
                'format_id': 'http-mp4',
                'url': video_url,
                'ext': 'mp4',
                'http_headers': _headers
            }

            if check:
                _videoinfo = self._get_video_info(video_url, headers=_headers, msg=pre)
                if not _videoinfo:
                    raise_extractor_error("error 404: no video info")
                assert isinstance(_videoinfo, dict)
                _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})

            _entry_video = {
                'id': videoid,
                'title': sanitize_filename(_title, restricted=True),
                'formats': [_format],
                'ext': 'mp4',
                'extractor_key': 'Streamtape',
                'extractor': 'streamtape',
                'webpage_url': escape_url(url)
            }

            return _entry_video

        except Exception as e:
            self.logger_debug(f"[{url}] error {repr(e)}")
            # _entry_video = {
            #     'id': videoid,
            #     'title': videoid,
            #     'formats': [],
            #     'extractor_key': 'Streamtape',
            #     'extractor': 'streamtape',
            #     'webpage_url': escape_url(url),
            #     'error': str(e)
            # }
            # return _entry_video
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
            lines = traceback.format_exception(*sys.exc_info())
            self.report_warning(f"{repr(e)}\n{'!!'.join(lines)}")
            raise_extractor_error(repr(e))
