import base64
import json
import subprocess

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    determine_ext,
    float_or_none,
    int_or_none,
    js_to_json,
    qualities,
    remove_end,
    remove_start,
    traverse_obj,
    try_get,
)


class RTVEALaCartaIE(InfoExtractor):
    IE_NAME = 'rtve.es:alacarta'  # type: ignore
    IE_DESC = 'RTVE a la carta'
    _VALID_URL = r'https?://(?:www\.)?rtve\.es/(m/)?((play|alacarta)/videos|filmoteca)/[^/]+/[^/]+/(?P<id>\d+)'

    _TESTS = [{
        'url': 'http://www.rtve.es/alacarta/videos/balonmano/o-swiss-cup-masculina-final-espana-suecia/2491869/',
        'md5': '2c70aacf8a415d1b4e7fcc0525951162',
        'info_dict': {
            'id': '2491869',
            'ext': 'mp4',
            'title': 'Final de la Swiss Cup masculina: España-Suecia',
            'description': 'Swiss Cup masculina, Final: España-Suecia.',
            'duration': 5024.566,
            'series': 'Balonmano',
        },
        'expected_warnings': ['Failed to download MPD manifest', 'Failed to download m3u8 information'],
    }, {
        'note': 'Live stream',
        'url': 'http://www.rtve.es/alacarta/videos/television/24h-live/1694255/',
        'info_dict': {
            'id': '1694255',
            'ext': 'mp4',
            'title': 're:^24H LIVE [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}$',
            'description': '24H LIVE',
            'is_live': True,
        },
        'params': {
            'skip_download': 'live stream',
        },
    }, {
        'url': 'http://www.rtve.es/alacarta/videos/servir-y-proteger/servir-proteger-capitulo-104/4236788/',
        'md5': '30b8827cba25f39d1af5a7c482cc8ac5',
        'info_dict': {
            'id': '4236788',
            'ext': 'mp4',
            'title': 'Capítulo 104',
            'description': 'md5:caae29ae04291875e611dd667fe84641',
            'duration': 3222.0,
        },
        'expected_warnings': ['Failed to download MPD manifest', 'Failed to download m3u8 information'],
    }, {
        'url': 'http://www.rtve.es/m/alacarta/videos/cuentame-como-paso/cuentame-como-paso-t16-ultimo-minuto-nuestra-vida-capitulo-276/2969138/?media=tve',
        'only_matching': True,
    }, {
        'url': 'http://www.rtve.es/filmoteca/no-do/not-1-introduccion-primer-noticiario-espanol/1465256/',
        'only_matching': True,
    }]

    def _real_initialize(self):
        if _ua := try_get(self.get_param('http_headers'), lambda x: x['User-agent'].encode('utf-8')):
            user_agent_b64 = base64.b64encode(_ua).decode('utf-8')
            self._manager = self._download_json(
                'http://www.rtve.es/odin/loki/' + user_agent_b64,
                None, 'Fetching manager info')['manager']  # type: ignore

    @staticmethod
    def _decrypt_url(png):
        cmd0 = f'node /Users/antoniotorres/.config/yt-dlp/rtve_decrypt_png.js {png}'
        res0 = subprocess.run(cmd0.split(' '), capture_output=True, encoding='utf-8').stdout.strip('\n')
        return json.loads(js_to_json(res0))

    def _extract_png_formats(self, video_id):
        formats = []

        png = self._download_webpage(
            f'http://ztnr.rtve.es/ztnr/movil/thumbnail/{self._manager}/videos/{video_id}.png',
            video_id, 'Downloading url information', query={'q': 'v2'}, fatal=False)
        if not png:
            return formats
        q = qualities(['Media', 'Alta', 'HQ', 'HD_READY', 'HD_FULL'])
        info = self._decrypt_url(png)
        self.write_debug(info)
        for quality, video_url in zip(info['calidades'], info['sources']):
            ext = determine_ext(video_url)
            try:
                if ext == 'm3u8':
                    formats.extend(self._extract_m3u8_formats(
                        video_url, video_id, 'mp4', 'm3u8_native',
                        m3u8_id='hls', fatal=False))
                elif ext == 'mp4':
                    filesize = None
                    if urlh := self._request_webpage(video_url, video_id):
                        filesize = int_or_none(urlh.headers.get('Content-Length'))
                    formats.append({
                        'format_id': quality if quality else 'http-mp4',
                        'url': video_url,
                        'filesize': filesize,
                        **({'quality': q(quality)} if quality else {})})
            except Exception as e:
                self.report_warning(f'error with [{ext}][{video_url}] - {e!r}')
        return formats

    def _extract_drm_mpd_formats_and_duration(self, video_id, info):
        _duration = float_or_none(info.get('duration'), 1000)
        _drm = {}
        _mpd_fmts = []
        _headers = {'referer': 'https://www.rtve.es/', 'origin': 'https://www.rtve.es'}

        _mpd_fmts, _ = self._extract_mpd_formats_and_subtitles(
                f'http://ztnr.rtve.es/ztnr/{video_id}.mpd', video_id, 'dash', headers=_headers, fatal=False)

        if _mpd_fmts:
            _lic_drm = traverse_obj(self._download_json(
                f'https://api.rtve.es/api/token/{video_id}', video_id, headers=_headers), 'widevineURL')

            _drm = {'licurl': _lic_drm}

            if not _duration:

                _duration = self._extract_mpd_vod_duration(
                    f'http://ztnr.rtve.es/ztnr/{video_id}.mpd', video_id, headers=_headers)

        return (_mpd_fmts, _drm, _duration)

    def _real_extract(self, url):
        video_id = self._match_id(url)
        if (
            info := try_get(
                self._download_json(
                    f'https://api-ztnr.rtve.es/api/videos/{video_id}.json',
                    video_id),
                lambda x: x['page']['items'][0])
        ):
            if info.get('state') == 'DESPU' or (info.get('pubState') or {}).get('code') == 'DESPU':
                raise ExtractorError('The video is no longer available', expected=True)
            title = info['title'].strip()
            formats = self._extract_png_formats(video_id)
            subtitles = None
            if (sbt_file := info.get('subtitleRef')):
                subtitles = self.extract_subtitles(video_id, sbt_file)
            is_live = info.get('consumption') == 'live'

            _mpd_fmts, _info_drm, _duration = self._extract_drm_mpd_formats_and_duration(video_id, info)

            if _mpd_fmts:
                formats.extend(_mpd_fmts)

            return {
                'id': video_id,
                'title': self._live_title(title) if is_live else title,
                'formats': formats,
                '_drm': _info_drm,
                'thumbnail': info.get('image'),
                'subtitles': subtitles,
                'duration': _duration,
                'is_live': is_live,
                'series': (info.get('programInfo') or {}).get('title'),
            }

    def _get_subtitles(self, video_id, sub_file):
        if (
            subs := try_get(self._download_json(
                sub_file + '.json', video_id,
                'Downloading subtitles info'),
                lambda x: x['page']['items'])
        ):
            return dict(
                (s['lang'], [{'ext': 'vtt', 'url': s['src']}])
                for s in subs)


class RTVEAudioIE(RTVEALaCartaIE):  # XXX: Do not subclass from concrete IE
    IE_NAME = 'rtve.es:audio'
    IE_DESC = 'RTVE audio'
    _VALID_URL = r'https?://(?:www\.)?rtve\.es/(alacarta|play)/audios/[^/]+/[^/]+/(?P<id>[0-9]+)'

    _TESTS = [{
        'url': 'https://www.rtve.es/alacarta/audios/a-hombros-de-gigantes/palabra-ingeniero-codigos-informaticos-27-04-21/5889192/',
        'md5': 'ae06d27bff945c4e87a50f89f6ce48ce',
        'info_dict': {
            'id': '5889192',
            'ext': 'mp3',
            'title': 'Códigos informáticos',
            'thumbnail': r're:https?://.+/1598856591583.jpg',
            'duration': 349.440,
            'series': 'A hombros de gigantes',
        },
    }, {
        'url': 'https://www.rtve.es/play/audios/en-radio-3/ignatius-farray/5791165/',
        'md5': '072855ab89a9450e0ba314c717fa5ebc',
        'info_dict': {
            'id': '5791165',
            'ext': 'mp3',
            'title': 'Ignatius Farray',
            'thumbnail': r're:https?://.+/1613243011863.jpg',
            'duration': 3559.559,
            'series': 'En Radio 3',
        },
    }, {
        'url': 'https://www.rtve.es/play/audios/frankenstein-o-el-moderno-prometeo/capitulo-26-ultimo-muerte-victor-juan-jose-plans-mary-shelley/6082623/',
        'md5': '0eadab248cc8dd193fa5765712e84d5c',
        'info_dict': {
            'id': '6082623',
            'ext': 'mp3',
            'title': 'Capítulo 26 y último: La muerte de Victor',
            'thumbnail': r're:https?://.+/1632147445707.jpg',
            'duration': 3174.086,
            'series': 'Frankenstein o el moderno Prometeo',
        },
    }]

    def _extract_png_formats(self, audio_id):
        """
        This function retrieves media related png thumbnail which obfuscate
        valuable information about the media. This information is decrypted
        via base class _decrypt_url function providing media quality and
        media url
        """
        png = self._download_webpage(
            f'http://www.rtve.es/ztnr/movil/thumbnail/{self._manager}/audios/{audio_id}.png',
            audio_id, 'Downloading url information', query={'q': 'v2'})
        q = qualities(['Media', 'Alta', 'HQ', 'HD_READY', 'HD_FULL'])
        formats = []
        for quality, audio_url in self._decrypt_url(png):
            ext = determine_ext(audio_url)
            if ext == 'm3u8':
                formats.extend(self._extract_m3u8_formats(
                    audio_url, audio_id, 'mp4', 'm3u8_native',
                    m3u8_id='hls', fatal=False))
            elif ext == 'mpd':
                formats.extend(self._extract_mpd_formats(
                    audio_url, audio_id, 'dash', fatal=False))
            else:
                formats.append({
                    'format_id': quality,
                    'quality': q(quality),
                    'url': audio_url,
                })
        return formats

    def _real_extract(self, url):
        audio_id = self._match_id(url)
        if (
            info := try_get(
                self._download_json(
                f'https://www.rtve.es/api/audios/{audio_id}.json',
                audio_id),
                lambda x: x['page']['items'][0])
        ):
            return {
                'id': audio_id,
                'title': info['title'].strip(),
                'thumbnail': info.get('thumbnail'),
                'duration': float_or_none(info.get('duration'), 1000),
                'series': try_get(info, lambda x: x['programInfo']['title']),
                'formats': self._extract_png_formats(audio_id),
            }


class RTVEInfantilIE(RTVEALaCartaIE):  # XXX: Do not subclass from concrete IE
    IE_NAME = 'rtve.es:infantil'
    IE_DESC = 'RTVE infantil'
    _VALID_URL = r'https?://(?:www\.)?rtve\.es/infantil/serie/[^/]+/video/[^/]+/(?P<id>[0-9]+)/'

    _TESTS = [{
        'url': 'http://www.rtve.es/infantil/serie/cleo/video/maneras-vivir/3040283/',
        'md5': '5747454717aedf9f9fdf212d1bcfc48d',
        'info_dict': {
            'id': '3040283',
            'ext': 'mp4',
            'title': 'Maneras de vivir',
            'thumbnail': r're:https?://.+/1426182947956\.JPG',
            'duration': 357.958,
        },
        'expected_warnings': ['Failed to download MPD manifest', 'Failed to download m3u8 information'],
    }]


class RTVELiveIE(RTVEALaCartaIE):  # XXX: Do not subclass from concrete IE
    IE_NAME = 'rtve.es:live'
    IE_DESC = 'RTVE.es live streams'
    _VALID_URL = r'https?://(?:www\.)?rtve\.es/directo/(?P<id>[a-zA-Z0-9-]+)'

    _TESTS = [{
        'url': 'http://www.rtve.es/directo/la-1/',
        'info_dict': {
            'id': 'la-1',
            'ext': 'mp4',
            'title': 're:^La 1 [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}$',
        },
        'params': {
            'skip_download': 'live stream',
        },
    }]

    def _real_extract(self, url):
        video_id = self._match_id('id')

        webpage = self._download_webpage(url, video_id)
        title = remove_end(self._og_search_title(webpage), ' en directo en RTVE.es')
        title = remove_start(title, 'Estoy viendo ')

        vidplayer_id = self._search_regex(
            (r'playerId=player([0-9]+)',
             r'class=["\'].*?\blive_mod\b.*?["\'][^>]+data-assetid=["\'](\d+)',
             r'data-id=["\'](\d+)'),
            webpage, 'internal video ID')

        return {
            'id': video_id,
            'title': title,
            'formats': self._extract_png_formats(vidplayer_id),
            'is_live': True,
        }


class RTVETelevisionIE(InfoExtractor):
    IE_NAME = 'rtve.es:television'  # type: ignore
    _VALID_URL = r'https?://(?:www\.)?rtve\.es/television/[^/]+/[^/]+/(?P<id>\d+).shtml'

    _TEST = {
        'url': 'http://www.rtve.es/television/20160628/revolucion-del-movil/1364141.shtml',
        'info_dict': {
            'id': '3069778',
            'ext': 'mp4',
            'title': 'Documentos TV - La revolución del móvil',
            'duration': 3496.948,
        },
        'params': {
            'skip_download': True,
        },
    }

    def _real_extract(self, url):
        page_id = self._match_id(url)
        webpage = self._download_webpage(url, page_id)

        alacarta_url = self._search_regex(
            r'data-location="alacarta_videos"[^<]+url&quot;:&quot;(http://www\.rtve\.es/alacarta.+?)&',
            webpage, 'alacarta url', default=None)  # type: ignore
        if alacarta_url is None:
            raise ExtractorError(
                'The webpage doesn\'t contain any video', expected=True)

        return self.url_result(alacarta_url, ie=RTVEALaCartaIE.ie_key())
