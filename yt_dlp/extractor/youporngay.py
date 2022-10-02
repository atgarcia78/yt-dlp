# import re
# import html

# from .commonwebdriver import dec_on_exception, SeleniumInfoExtractor, limiter_1
# from ..utils import (
#     extract_attributes,
#     int_or_none,
#     str_to_int,
#     unified_strdate,
#     url_or_none,
#     try_get,
#     ExtractorError
# )
#from urllib.parse import unquote

from .youporn import YouPornIE



class YouPornGayIE(YouPornIE):
    _VALID_URL = r'https?://(?:www\.)?youporngay\.com/(?:watch|embed)/(?P<id>\d+)(?:/(?P<display_id>[^/?#&]+))?'
    _EMBED_REGEX = [r'<iframe[^>]+\bsrc=["\'](?P<url>(?:https?:)?//(?:www\.)?youporngay\.com/embed/\d+)']
    IE_NAME = 'youporngay'
    


# class YouPornGayIE(SeleniumInfoExtractor):
#     _VALID_URL = r'https?://(?:www\.)?youporngay\.com/(?:watch|embed)/(?P<id>\d+)(?:/(?P<display_id>[^/?#&]+))?'
#     _EMBED_REGEX = [r'<iframe[^>]+\bsrc=["\'](?P<url>(?:https?:)?//(?:www\.)?youporngay\.com/embed/\d+)']
    
        
#     @dec_on_exception
#     @limiter_1.ratelimit("yourporngay", delay=True)
#     def _send_request(self, url, *args, **kwargs):        
        
#         self.logger_debug(f"[send_req] {self._get_url_print(url)}") 
#         return(self.send_http_request(url, *args, **kwargs))

#     def _real_initialize(self):
#         super()._real_initialize()
   
#     def _real_extract(self, url):
#         mobj = self._match_valid_url(url)
#         video_id = mobj.group('id')
#         display_id = mobj.group('display_id') or video_id

#         urlh, webpage = try_get(self._send_request(
#             f'https://www.youporngay.com/watch/{video_id}'), lambda x: (str(x.url), html.unescape(re.sub('[\t\n]', '', x.text))))

#         if not webpage: raise ExtractorError('no webpage')

#         res = try_get(self._send_request(
#             f'https://www.youporngay.com/api/video/media_definitions/{video_id}/',
#             headers={'Referer':  urlh}), lambda x: x)
                    
#         if not res: raise ExtractorError("no video info")
#         formats = []

#         self.logger_debug(res.text)

#         definitions = res.json()

#         self.logger_debug(definitions)

#         _headers = {'Referer': 'https://www.youporngay.com/', 'Origin': 'https://www.youporngay.com'}
#         for definition in definitions:
#             if not isinstance(definition, dict):
#                 continue
#             video_url = url_or_none(unquote(definition.get('videoUrl')))
#             if not video_url:
#                 continue
#             if not definition.get('format') == 'hls': continue

#             if isinstance(definition.get('quality'), list):

#                 formats = self._extract_m3u8_formats(video_url + '&=', video_id, 'mp4', 'm3u8_native', m3u8_id='hls', headers=_headers, fatal=False)


#         if not formats: raise ExtractorError("no formats")
#         for f in formats:
#             f['http_headers'] = _headers
#             f['url'] += '&='
#             f['manifest_url'] += '&='
#         self.logger_debug(formats)

#         self._sort_formats(formats)
        


        
#         title = self._html_search_regex(
#             r'(?s)<div[^>]+class=["\']watchVideoTitle[^>]+>(.+?)</div>',
#             webpage, 'title', fatal=False, default=None) or self._og_search_title(
#             webpage, default=None) or self._html_search_meta(
#             'title', webpage, fatal=True)

#         description = self._html_search_regex(
#             r'(?s)<div[^>]+\bid=["\']description["\'][^>]*>(.+?)</div>',
#             webpage, 'description',
#             fatal=False, default=None) or self._og_search_description(
#             webpage, default=None)
#         thumbnail = self._search_regex(
#             r'(?:imageurl\s*=|poster\s*:)\s*(["\'])(?P<thumbnail>.+?)\1',
#             webpage, 'thumbnail', fatal=False, group='thumbnail')
#         duration = int_or_none(self._html_search_meta(
#             'video:duration', webpage, 'duration', fatal=False))

#         uploader = self._html_search_regex(
#             r'(?s)<div[^>]+class=["\']submitByLink["\'][^>]*>(.+?)</div>',
#             webpage, 'uploader', fatal=False)
#         upload_date = unified_strdate(self._html_search_regex(
#             [r'UPLOADED:</label><span>([^<]+)',
#              r'Date\s+[Aa]dded:\s*<span>([^<]+)',
#              r'(?s)<div[^>]+class=["\']videoInfo(?:Date|Time)["\'][^>]*>(.+?)</div>'],
#             webpage, 'upload date', default=None, fatal=False, flags=re.IGNORECASE))

#         age_limit = self._rta_search(webpage)

#         view_count = None
#         views = self._search_regex(
#             r'(<div[^>]+\bclass=["\']js_videoInfoViews["\']>)', webpage,
#             'views', fatal=False, default=None)
#         if views:
#             view_count = str_to_int(extract_attributes(views).get('data-value'))
#         comment_count = str_to_int(self._search_regex(
#             r'>All [Cc]omments? \(([\d,.]+)\)',
#             webpage, 'comment count', fatal=False, default=None))


#         categories = re.findall(r'data-espnode="category_tag"[^>]+href=[^>]+>([^<]+)', webpage)
#         tags = re.findall(r'data-espnode="category_tag"[^>]+href=[^>]+>([^<]+)', webpage)

#         return {
#             'id': video_id,
#             'display_id': display_id,
#             'title': title,
#             'description': description,
#             'thumbnail': thumbnail,
#             'duration': duration,
#             'uploader': uploader,
#             'upload_date': upload_date,
#             'view_count': view_count,
#             'comment_count': comment_count,
#             'categories': categories,
#             'tags': tags,
#             'age_limit': age_limit,
#             'formats': formats,
#             'ext': 'mp4'
#         }

