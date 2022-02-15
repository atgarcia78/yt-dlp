# coding: utf-8
from __future__ import unicode_literals

import traceback
import sys

from ..utils import (
    ExtractorError,
    sanitize_filename,
    try_get
)

from .commonwebdriver import SeleniumInfoExtractor


from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By

import time

class get_video_data:
    def __init__(self, logger):
        self.logger = logger
    def __call__(self, driver):
        try:
            eldiv = driver.find_element(By.TAG_NAME, "div")
            for _ in range(5):
                try:
                    eldiv.click()
                except Exception as e:
                    print(f"div click {repr(e)}")
                    break

            elsett_list = driver.find_elements(By.CLASS_NAME, "fp-settings-list-item")

            if not elsett_list:
                return False
            n = len(elsett_list)

            _formats = {}
            elsett = driver.find_element(By.CSS_SELECTOR, "a.fp-settings")
            elvid = driver.find_element(By.CSS_SELECTOR, "video.fp-engine")

            for i in range(n):

                _key = elsett_list[i].get_attribute("innerText")
                elsett.click()
                elsett_list[i].click()
                time.sleep(5)
                _vidurl = elvid.get_attribute("src")
                self.logger(f"{_key}:{_vidurl}")
                _formats.update({_key: _vidurl})
                if i < n:
                    elsett_list = driver.find_elements(
                        By.CLASS_NAME, "fp-settings-list-item"
                    )

            if not _formats:
                return False
            _title = driver.find_element(By.TAG_NAME, "h1").get_attribute("innerText")

            return (_title, _formats)

        except Exception as e:
            self.logger(repr(e))
            return False


class GayQTIE(SeleniumInfoExtractor):
    IE_NAME = "gayqt"
    _VALID_URL = r'https?://(?:www\.)gayqt\.com/videos/(?P<id>[\d]+)/.*'
    
    def _real_initialize(self):
        super()._real_initialize()
        

    def _real_extract(self, url):
        
        self.report_extraction(url)
        videoid = self._match_id(url)
        driver = self.get_driver(usequeue=True)
        
        try:
            
            driver.get(url)            

            title, streams = self.wait_until(driver, 60, get_video_data(self.to_screen))
            #self.to_screen(title)
            #self.to_screen(streams)
            if not streams:
                raise ExtractorError("no video url")
            _formats = []
            
            for _id, _url in streams.items():
                _info_video = self.get_info_for_format(_url) or {}
                #self.to_screen(_info_video)
                _formats.append({
                    'format_id': f'http-{_id}',
                    'url': _info_video['url'],
                    'height': int(_id[:-1]),
                    'format_note': _id,
                    'filesize': _info_video['filesize'],
                    'ext': 'mp4'})
                    
            if not _formats: raise ExtractorError("no formats founnd")
            self._sort_formats(_formats)
            
            return({
                'id': videoid,
                'title': sanitize_filename(title,restricted=True),
                'formats': _formats,
                'ext': 'mp4'
            })
        
        except ExtractorError as e:
            raise
        except Exception as e:
            lines = traceback.format_exception(*sys.exc_info())
            self.to_screen(f"{repr(e)}\n{'!!'.join(lines)}")
            raise ExtractorError(repr(e))
        finally:
            self.put_in_queue(driver)
