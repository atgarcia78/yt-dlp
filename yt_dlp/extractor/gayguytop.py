import sys
import traceback

from ..utils import ExtractorError, try_get
from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_0_1, By, ec


class GayGuyTopIE(SeleniumInfoExtractor):

    IE_NAME = 'gayguytop'
    _VALID_URL = r'https?://(?:www\.)?gayguy\.top/'

    @dec_on_exception
    @limiter_0_1.ratelimit("gayguytop", delay=True)
    def _send_request(self, url, driver):
        self.logger_debug(f"[send_request] {url}")
        driver.get(url)

    def _get_entry(self, url, **kwargs):

        try:
            driver = self.get_driver()
            self._send_request(url, driver)

            el_ifr = self.wait_until(driver, 30, ec.any_of(ec.presence_of_all_elements_located((By.TAG_NAME, "iframe")), ec.presence_of_element_located((By.CSS_SELECTOR, ".error-404"))))

            if not el_ifr or not isinstance(el_ifr, list):
                raise ExtractorError("404 video doesnt exist")

            _ifrsrc = None

            for el in el_ifr:
                if 'fembed.com/v/' in (_ifrsrc := (try_get(el.get_attribute('src'), lambda x: x if x else ""))):
                    self.logger_debug(f"[iframe] {_ifrsrc}")
                    break

            if not _ifrsrc:
                raise ExtractorError("iframe fembed.com not found")
            ie = self._downloader.get_info_extractor('Fembed')
            ie._real_initialize()

            return ie._get_entry(_ifrsrc, **kwargs)

        except Exception:
            raise
        finally:
            self.rm_driver(driver)

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
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
