from .youporn import YouPornIE


class YouPornGayIE(YouPornIE):
    _VALID_URL = r'https?://(?:www\.)?youporngay\.com/(?:watch|embed)/(?P<id>\d+)(?:/(?P<display_id>[^/?#&]+))?'
    _EMBED_REGEX = [r'<iframe[^>]+\bsrc=["\'](?P<url>(?:https?:)?//(?:www\.)?youporngay\.com/embed/\d+)']
    IE_NAME = 'youporngay'
