
import re

from ..utils import sanitize_filename
from .commonwebdriver import SeleniumInfoExtractor


class RealPythonIE(SeleniumInfoExtractor):
    IE_NAME = "realpythonplaylist"
    _VALID_URL = r'https://realpython.com/courses/.+'
    _SITE_URL = 'https://realpython.com'

    def _real_initialize(self):
        super()._real_initialize()

    def _real_extract(self, url):

        self.report_extraction(url)

        webpage = self._download_webpage(url, None)
        lessons = [self.url_result(f'{self._SITE_URL}{el}', ie='Generic') for el in re.findall(r'0\"><a\s+href=\"([^"]+)\"', webpage)]
        self.to_screen(lessons)

        return self.playlist_result(
            lessons,
            playlist_id=f'{sanitize_filename(self._generic_id(url), restricted=True)}',
            playlist_title='Course')
