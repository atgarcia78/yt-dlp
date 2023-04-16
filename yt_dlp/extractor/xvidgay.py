import sys
import traceback
import re
import time


from ..utils import try_get, ExtractorError, sanitize_filename
from .commonwebdriver import dec_on_exception, dec_on_exception2, dec_on_exception3, SeleniumInfoExtractor, limiter_5, By, ec, HTTPStatusError, ConnectError
import hashlib


class getvideourl:
    def __call__(self, driver):
        el_ifr = driver.find_element(By.CSS_SELECTOR, 'iframe')
        _type_player_id = try_get(re.search(r'play.php\?id=(?P<id>.+)', el_ifr.get_attribute('src')), lambda x: x.group('id') if x else None)
        driver.switch_to.frame(el_ifr)
        time.sleep(1)
        if not _type_player_id:
            el_li = driver.find_elements(By.CSS_SELECTOR, 'li')
            _videoid = None
            for el in el_li:
                if (_videoid := (try_get(re.search(r'https://xvidgay.site/v/(?P<id>[^\"\']+)[\'\"]', el.get_attribute('onclick')), lambda x: x.group('id') if x else None))):
                    try:
                        el.click()
                        time.sleep(1)
                        el.click()
                        time.sleep(1)
                    except Exception:
                        pass
                    break
                elif 'https://xvidgay.xyz' in el.get_attribute('onclick'):
                    try:
                        el.click()
                        time.sleep(1)

                    except Exception:
                        pass
                    break

            el_ifr = driver.find_element(By.CSS_SELECTOR, 'iframe')
            driver.switch_to.frame(el_ifr)
            time.sleep(5)
            if _videoid:
                el_div = driver.find_elements(By.CSS_SELECTOR, 'div')
                try:
                    el_div[-1].click()
                    time.sleep(1)
                    el_div[-1].click()
                    time.sleep(1)
                except Exception:
                    pass

                try:
                    el_div[-2].click()
                    time.sleep(1)
                    el_div[-2].click()
                    time.sleep(1)
                except Exception:
                    pass

                el_but = driver.find_elements(By.CSS_SELECTOR, 'button')
                if el_but:
                    for el in el_but:
                        if 'NO' in el.text:
                            el.click()

                time.sleep(5)
                el_video = driver.find_element(By.CSS_SELECTOR, 'video')
                el_video.click()
                if (_vidurl := el_video.get_attribute('src')):
                    return (_videoid, _vidurl)
                else:
                    return False
            else:
                el_video = driver.find_element(By.CSS_SELECTOR, 'video')
                if (_vidurl := el_video.get_attribute('src')):
                    return (None, _vidurl)

        else:
            el_vp = driver.find_element(By.ID, 'video_player')
            for _ in range(4):
                try:
                    el_vp.click()
                    time.sleep(1)
                except Exception:
                    pass
            el_video_check = try_get(driver.find_elements(By.CSS_SELECTOR, 'video'), lambda x: x[0].get_attribute('src') if x else None)

            if not el_video_check:
                el_div = el_vp.find_elements(By.CSS_SELECTOR, 'div')
                el_ifr2 = el_div[0].find_element(By.CSS_SELECTOR, 'iframe')
                driver.switch_to.frame(el_ifr2)
                time.sleep(3)

            el_video = driver.find_element(By.CSS_SELECTOR, 'video')
            if (_vidurl := el_video.get_attribute('src')):
                if len(_type_player_id) > 10:
                    _videoid = str(int(hashlib.sha256(_type_player_id.encode('utf-8')).hexdigest(), 16) % 10**10)
                else:
                    _videoid = _type_player_id
                return (_videoid, _vidurl)
            else:
                return False


class XvidgayIE(SeleniumInfoExtractor):

    IE_NAME = 'xvidgay'
    _VALID_URL = r'https?://xvidgay\.xyz/videos/(?P<title>.+)'
    _SITE_URL = 'https://xvidgay.site/'

    @dec_on_exception3
    @dec_on_exception2
    @limiter_5.ratelimit("xvidgay", delay=True)
    def _get_video_info(self, url):

        self.logger_debug(f"[get_video_info] {url}")
        headers = {
            'Range': 'bytes=0-', 'Referer': self._SITE_URL,
            'Sec-Fetch-Dest': 'video', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site',
            'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}
        try:
            return self.get_info_for_format(url, headers=headers)
        except (HTTPStatusError, ConnectError) as e:
            self.report_warning(f"[get_video_info] {self._get_url_print(url)}: error - {repr(e)}")

    @dec_on_exception
    @limiter_5.ratelimit("xvidgay", delay=True)
    def _send_request(self, url, driver):
        self.logger_debug(f"[send_request] {url}")
        driver.get(url)

    def _get_entry(self, url, **kwargs):

        check = kwargs.get('check', False)
        msg = kwargs.get('msg', None)

        pre = f'[get_entry][{self._get_url_print(url)}]'
        if msg:
            pre = f'{msg}{pre}'

        driver = self.get_driver()

        try:

            self._send_request(url, driver)

            _title = try_get(self.wait_until(driver, 30, ec.presence_of_element_located((By.CSS_SELECTOR, 'h1'))), lambda x: x.text)
            _videoid, _videourl = self.wait_until(driver, 60, getvideourl())

            if not _videourl:
                raise ExtractorError('no videourl')

            _format = {
                'format_id': 'http-mp4',
                'url': _videourl,
                'http_headers': {'Referer': self._SITE_URL},
                'ext': 'mp4'
            }

            if not _videoid:
                _videoid = str(int(hashlib.sha256(_videourl.split('video=')[1].encode('utf-8')).hexdigest(), 16) % 10**10)

            if check:
                _videoinfo = self._get_video_info(_videourl)
                if not _videoinfo:
                    raise ExtractorError("error 404: no video info")
                else:
                    assert isinstance(_videoinfo, dict)
                    _format.update({'url': _videoinfo['url'], 'filesize': _videoinfo['filesize']})

            return ({
                'id': _videoid,
                'title': sanitize_filename(_title, restricted=True),
                'formats': [_format],
                'ext': 'mp4',
                'extractor_key': 'Xvidgay',
                'extractor': 'xvidgay',
                'webpage_url': url
            })

        except Exception:
            raise
        finally:
            self.rm_driver(driver)

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        try:

            return self._get_entry(url, check=True)

        except ExtractorError:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
