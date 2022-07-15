from __future__ import unicode_literals

import re


from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_1
from ..utils import (
    extract_attributes,
    int_or_none,
    str_to_int,
    unified_strdate,
    url_or_none,
    try_get,
    ExtractorError
)




class YouPornGayIE(SeleniumInfoExtractor):
    _VALID_URL = r'https?://(?:www\.)?youporngay\.com/(?:watch|embed)/(?P<id>\d+)(?:/(?P<display_id>[^/?#&]+))?'
    
    

    @staticmethod
    def _extract_urls(webpage):
        return re.findall(
            r'<iframe[^>]+\bsrc=["\']((?:https?:)?//(?:www\.)?youporngay\.com/embed/\d+)',
            webpage)
        
    @dec_on_exception
    @limiter_1.ratelimit("yourporngay", delay=True)
    def _send_request(self, url, *args, **kwargs):        
        
        self.logger_debug(f"[_send_request] {self._get_url_print(url)}") 
        return(self.send_http_request(url, *args, **kwargs))

    def _real_initialize(self):
        super()._real_initialize()
   
    def _real_extract(self, url):
        mobj = self._match_valid_url(url)
        video_id = mobj.group('id')
        display_id = mobj.group('display_id') or video_id

        definitions = try_get(self._send_request(
            'https://www.youporngay.com/api/video/media_definitions/%s/' % video_id,
            headers={'referer': url}), lambda x: x.json())
        if not definitions: raise ExtractorError("no video info")
        formats = []
        for definition in definitions:
            if not isinstance(definition, dict):
                continue
            video_url = url_or_none(definition.get('videoUrl'))
            if not video_url:
                continue
            f = {
                'url': video_url,
                'filesize': int_or_none(definition.get('videoSize')),
            }
            height = int_or_none(definition.get('quality'))

            mobj = re.search(r'(?P<height>\d{3,4})[pP]_(?P<bitrate>\d+)[kK]_\d+', video_url)
            if mobj:
                if not height:
                    height = int(mobj.group('height'))
                bitrate = int(mobj.group('bitrate'))
                f.update({
                    'format_id': '%dp-%dk' % (height, bitrate),
                    'tbr': bitrate,
                })
            f['height'] = height
            formats.append(f)
        self._sort_formats(formats)

        webpage = try_get(self._send_request(
            'http://www.youporngay.com/watch/%s' % video_id), lambda x: x.text)

        if not webpage: raise ExtractorError('no webpage')
        title = self._html_search_regex(
            r'(?s)<div[^>]+class=["\']watchVideoTitle[^>]+>(.+?)</div>',
            webpage, 'title', fatal=False, default=None) or self._og_search_title(
            webpage, default=None) or self._html_search_meta(
            'title', webpage, fatal=True)

        description = self._html_search_regex(
            r'(?s)<div[^>]+\bid=["\']description["\'][^>]*>(.+?)</div>',
            webpage, 'description',
            fatal=False, default=None) or self._og_search_description(
            webpage, default=None)
        thumbnail = self._search_regex(
            r'(?:imageurl\s*=|poster\s*:)\s*(["\'])(?P<thumbnail>.+?)\1',
            webpage, 'thumbnail', fatal=False, group='thumbnail')
        duration = int_or_none(self._html_search_meta(
            'video:duration', webpage, 'duration', fatal=False))

        uploader = self._html_search_regex(
            r'(?s)<div[^>]+class=["\']submitByLink["\'][^>]*>(.+?)</div>',
            webpage, 'uploader', fatal=False)
        upload_date = unified_strdate(self._html_search_regex(
            [r'UPLOADED:\s*<span>([^<]+)',
             r'Date\s+[Aa]dded:\s*<span>([^<]+)',
             r'(?s)<div[^>]+class=["\']videoInfo(?:Date|Time)["\'][^>]*>(.+?)</div>'],
            webpage, 'upload date', fatal=False))

        age_limit = self._rta_search(webpage)

        view_count = None
        views = self._search_regex(
            r'(<div[^>]+\bclass=["\']js_videoInfoViews["\']>)', webpage,
            'views', fatal=False, default=None)
        if views:
            view_count = str_to_int(extract_attributes(views).get('data-value'))
        comment_count = str_to_int(self._search_regex(
            r'>All [Cc]omments? \(([\d,.]+)\)',
            webpage, 'comment count', fatal=False, default=None))

        def extract_tag_box(regex, title):
            tag_box = self._search_regex(regex, webpage, title,fatal=False, default=None)
            if not tag_box:
                return []
            return re.findall(r'<a[^>]+href=[^>]+>([^<]+)', tag_box)

        categories = extract_tag_box(
            r'(?s)Categories:.*?</[^>]+>(.+?)</div>', 'categories')
        tags = extract_tag_box(
            r'(?s)Tags:.*?</div>\s*<div[^>]+class=["\']tagBoxContent["\'][^>]*>(.+?)</div>',
            'tags')

        return {
            'id': video_id,
            'display_id': display_id,
            'title': title,
            'description': description,
            'thumbnail': thumbnail,
            'duration': duration,
            'uploader': uploader,
            'upload_date': upload_date,
            'view_count': view_count,
            'comment_count': comment_count,
            'categories': categories,
            'tags': tags,
            'age_limit': age_limit,
            'formats': formats,
        }
