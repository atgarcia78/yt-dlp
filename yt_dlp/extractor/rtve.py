import base64
import json
import re
import subprocess

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    determine_ext,
    float_or_none,
    int_or_none,
    js_to_json,
    qualities,
    traverse_obj,
    try_get,
)


class RTVEPlayIE(InfoExtractor):
    IE_NAME = 'rtve.es:play'  # type: ignore
    IE_DESC = 'RTVE Play'
    _VALID_URL = r'https?://(?:www\.)?rtve\.es/(?P<kind>(?:playz?|(?:m/)?alacarta)/(?:audios|videos)|filmoteca)/[^/]+/[^/]+/(?P<id>\d+)'

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
    }, {
        'url': 'http://www.rtve.es/alacarta/audios/a-hombros-de-gigantes/palabra-ingeniero-codigos-informaticos-27-04-21/5889192/',
        'md5': 'ae06d27bff945c4e87a50f89f6ce48ce',
        'info_dict': {
            'id': '5889192',
            'ext': 'mp3',
            'title': 'Códigos informáticos',
            'description': 'md5:72b0d7c1ca20fd327bdfff7ac0171afb',
            'thumbnail': r're:https?://.+/1598856591583.jpg',
            'duration': 349.440,
        },
    }]

    def _real_initialize(self):
        if _ua := try_get(self.get_param('http_headers'), lambda x: x['User-agent'].encode('utf-8')):
            user_agent_b64 = base64.b64encode(_ua).decode('utf-8')
            self._manager = self._download_json(
                'http://www.rtve.es/odin/loki/' + user_agent_b64,
                None, 'Fetching manager info')['manager']  # type: ignore

    @staticmethod
    def _decrypt_url(png):
        cmd0 = "node /Users/antoniotorres/.config/yt-dlp/rtve_decrypt_png.js " + png
        res0 = subprocess.run(cmd0.split(' '), capture_output=True, encoding="utf-8").stdout.strip('\n')
        return json.loads(js_to_json(res0))

    def _extract_png_formats(self, video_id):
        formats = []

        png = self._download_webpage(
            'http://ztnr.rtve.es/ztnr/movil/thumbnail/%s/videos/%s.png' % (self._manager, video_id),
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
                else:
                    filesize = None
                    if urlh := self._request_webpage(video_url, video_id):
                        filesize = int_or_none(urlh.headers.get('Content-Length'))
                    formats.append({
                        'format_id': 'http-mp4' if not quality else quality,
                        'url': video_url,
                        'filesize': filesize,
                        **({'quality': q(quality)} if quality else {})})
            except Exception as e:
                self.report_warning(f"error with [{ext}][{video_url}] - {repr(e)}")
        return formats

    def _extract_drm_mpd_formats(self, video_id):
        _headers = {'referer': 'https://www.rtve.es/', 'origin': 'https://www.rtve.es'}

        if (
            _mpd_fmts := self._extract_mpd_formats(
                f"http://ztnr.rtve.es/ztnr/{video_id}.mpd", video_id, 'dash', headers=_headers, fatal=False)
        ):
            _lic_drm = traverse_obj(self._download_json(
                f"https://api.rtve.es/api/token/{video_id}", video_id, headers=_headers), "widevineURL")

            return (_mpd_fmts, {"licurl": _lic_drm})

    def _real_extract(self, url):
        if groups := try_get(re.match(self._VALID_URL, url), lambda x: x.groupdict()):
            is_audio = groups.get('kind') == 'play/audios'
            return self._real_extract_from_id(groups['id'], is_audio)

    def _real_extract_from_id(self, video_id, is_audio=False):
        kind = 'audios' if is_audio else 'videos'
        info = self._download_json(
            'http://www.rtve.es/api/%s/%s.json' % (kind, video_id),
            video_id)['page']['items'][0]  # type: ignore
        if (info.get('pubState') or {}).get('code') == 'DESPU':
            raise ExtractorError('The video is no longer available', expected=True)
        title = info['title'].strip()
        formats = self._extract_png_formats(video_id)

        subtitles = None
        if (sbt_file := info.get('subtitleRef')):
            subtitles = self.extract_subtitles(video_id, sbt_file)

        is_live = info.get('consumption') == 'live'

        _mpd_fmts, _info_drm = try_get(
            self._extract_drm_mpd_formats(video_id),
            lambda x: x if x else (None, None))  # type: ignore

        if _mpd_fmts:
            formats.extend(_mpd_fmts)

        return {
            'id': video_id,
            'title': self._live_title(title) if is_live else title,
            'formats': formats,
            '_drm': _info_drm,
            'url': info.get('htmlUrl'),
            'description': (info.get('description')),
            'thumbnail': info.get('thumbnail'),
            'subtitles': subtitles,
            'duration': float_or_none(info.get('duration'), 1000),
            'is_live': is_live,
            'series': (info.get('programInfo') or {}).get('title'),
        }

    def _get_subtitles(self, video_id, sub_file):
        subs = traverse_obj(self._download_json(
            sub_file + '.json', video_id,
            'Downloading subtitles info'), ('page', 'items'))
        if not isinstance(subs, list):
            return {}
        else:
            return dict(
                (s['lang'], [{'ext': 'vtt', 'url': s['src']}])
                for s in subs)


class RTVEInfantilIE(RTVEPlayIE):
    IE_NAME = 'rtve.es:infantil'
    IE_DESC = 'RTVE infantil'
    _VALID_URL = r'https?://(?:www\.)?rtve\.es/infantil/serie/[^/]+/video/[^/]+/(?P<id>[0-9]+)/'

    _TESTS = [{
        'url': 'https://www.rtve.es/infantil/serie/dino-ranch/video/pequeno-gran-ayudante/6693248/',
        'md5': '06d3f57eec593ad93fe9dcf079fbd940',
        'info_dict': {
            'id': '6693248',
            'ext': 'mp4',
            'title': 'Un pequeño gran ayudante',
            'description': 'md5:144ca351e31f9ee99a637ab9fc2787d5',
            'thumbnail': r're:https?://.+/1663318364501\.jpg',
            'duration': 691.44,
        },
        'expected_warnings': ['Failed to download MPD manifest', 'Failed to download m3u8 information'],
    }]


class RTVELiveIE(RTVEPlayIE):
    IE_NAME = 'rtve.es:live'
    IE_DESC = 'RTVE.es live streams'
    _VALID_URL = r'https?://(?:www\.)?rtve\.es/play/videos/directo/(?P<id>.+)'

    _TESTS = [{
        'url': 'https://www.rtve.es/play/videos/directo/la-1/',
        'info_dict': {
            'id': '1688877',
            'ext': 'mp4',
            'title': 're:^La 1 [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}$',
            'description': 'La 1',
        },
        'params': {
            'skip_download': 'live stream',
        }
    }, {
        'url': 'https://www.rtve.es/play/videos/directo/canales-lineales/la-1/',
        'info_dict': {
            'id': '1688877',
            'ext': 'mp4',
            'title': 're:^La 1 [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}$',
            'description': 'La 1',
        },
        'params': {
            'skip_download': 'live stream',
        }
    }, {
        'url': 'https://www.rtve.es/play/videos/directo/canales-lineales/capilla-ardiente-isabel-westminster/10886/',
        'info_dict': {
            'id': '1938028',
            'ext': 'mp4',
            'title': 're:^Mas24 - 1 [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}$',
            'description': 'Mas24 - 1',
        },
        'params': {
            'skip_download': 'live stream',
        }
    }]

    def _real_extract(self, url):
        webpage = self._download_webpage(url, self._match_id(url))
        asset_id = self._search_regex(
            r'class=["\'].*?\bvideoPlayer\b.*?["\'][^>]+data-setup=[^>]+?(?:"|&quot;)idAsset(?:"|&quot;)\s*:\s*(?:"|&quot;)(\d+)(?:"|&quot;)',
            webpage, 'internal video ID')
        return self._real_extract_from_id(asset_id)


class RTVETelevisionIE(InfoExtractor):
    IE_NAME = 'rtve.es:television'  # type: ignore
    # https://www.rtve.es/SECTION/YYYYMMDD/CONTENT_SLUG/CONTENT_ID.shtml
    _VALID_URL = r'https?://(?:www\.)?rtve\.es/[^/]+/\d{8}/[^/]+/(?P<id>\d+)\.shtml'

    _TESTS = [{
        'url': 'https://www.rtve.es/television/20220916/destacados-festival-san-sebastian-rtve-play/2395620.shtml',
        'info_dict': {
            'id': '6668919',
            'ext': 'mp4',
            'title': 'Las películas del Festival de San Sebastián en RTVE Play',
            'description': 'El\xa0Festival de San Sebastián vuelve a llenarse de artistas. Y en su honor,\xa0RTVE Play\xa0destacará cada viernes una\xa0película galardonada\xa0con la\xa0Concha de Oro\xa0en su catálogo.',
            'duration': 20.048,
        },
        'params': {
            'skip_download': True,
        },
    }, {
        'url': 'https://www.rtve.es/noticias/20220917/penelope-cruz-san-sebastian-premio-nacional/2402565.shtml',
        'info_dict': {
            'id': '6694087',
            'ext': 'mp4',
            'title': 'Penélope Cruz recoge el Premio Nacional de Cinematografía: "No dejen nunca de proteger nuestro cine"',
            'description': 'md5:eda9e6baa78dbbbcc7708c0cc8150a91',
            'duration': 388.2,
        },
        'params': {
            'skip_download': True,
        },
    }, {
        'url': 'https://www.rtve.es/deportes/20220917/motogp-bagnaia-pole-marquez-decimotercero-motorland-aragon/2402566.shtml',
        'info_dict': {
            'id': '6694142',
            'ext': 'mp4',
            'title': "Bagnaia logra su quinta 'pole' del año y Márquez partirá decimotercero",
            'description': 'md5:07e2ccb983a046cb42f896cce225f0a7',
            'duration': 153.44,
        },
        'params': {
            'skip_download': True,
        },
    }, {
        'url': 'https://www.rtve.es/playz/20220807/covaleda-fest-final/2394809.shtml',
        'info_dict': {
            'id': '6665408',
            'ext': 'mp4',
            'title': 'Covaleda Fest (Soria) - Día 3 con Marc Seguí y Paranoid 1966',
            'description': 'Festivales Playz viaja a Covaleda, Soria, para contarte todo lo que sucede en el Covaleda Fest. Entrevistas, challenges a los artistas, juegos... Khan, Adriana Jiménez y María García no dejarán pasar ni una. ¡No te lo pierdas!',
            'duration': 12009.92,
        },
        'params': {
            'skip_download': True,
        },
    }]

    def _real_extract(self, url):
        page_id = self._match_id(url)
        webpage = self._download_webpage(url, page_id)

        alacarta_url = self._search_regex(
            r'data-location="alacarta_videos"[^<]+url&quot;:&quot;(https?://www\.rtve\.es/play.+?)&',
            webpage, 'alacarta url', default=None)  # type: ignore
        if alacarta_url is None:
            raise ExtractorError(
                'The webpage doesn\'t contain any video', expected=True)

        return self.url_result(alacarta_url, ie=RTVEPlayIE.ie_key())
