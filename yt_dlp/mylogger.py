import logging
import re


def get_values_regex(str_reg_list, str_content, *_groups, not_found=None):
    
    for str_reg in str_reg_list:
    
        mobj = re.search(str_reg, str_content)
        if mobj:
            res = mobj.group(*_groups)
            return res
        
    return not_found

class MyLogger(logging.LoggerAdapter):
    """
    para ser compatible con el logging de yt_dlp: yt_dlp usa debug para enviar los debug y
    los info. Los debug llevan '[debug] ' antes.
    se pasa un logger de logging al crear la instancia 
    mylogger = MyLogger(logging.getLogger("name_ejemplo", {}))
    """
    _debug_phr = [
            'Falling back on generic information extractor',
            'Extracting URL:',
            'Media identified',
            'The information of all playlist entries will be held in memory',
            'Looking for video embeds',
            'Identified a HTML5 media',
            'Identified a KWS Player',
            ' unable to extract',
            'Looking for embeds',
            'Looking for Brightcove embeds',
            'Identified a html5 embed',
            'from cache',
            'to cache',
            'Downloading MPD manifest'
            'Downloading m3u8 information',
            'Downloading media selection JSON',
            'Loaded ',
            'Sort order given by user:',
            'Formats sorted by:'            
    ]
    
    _skip_phr = [
        'Downloading',
        'Extracting information',
        'Checking',
        'Logging'
    ]
    
    def __init__(self, logger, quiet=False, verbose=False, superverbose=False):
        super().__init__(logger, {})
        self.quiet = quiet
        self.verbose = verbose
        self.superverbose = superverbose
        
    
    def error(self, msg, *args, **kwargs):
        self.log(logging.DEBUG, msg, *args, **kwargs)
    
    def warning(self, msg, *args, **kwargs):
        if any(_ in msg for _ in self._debug_phr):
            self.log(logging.DEBUG, msg, *args, **kwargs)
        else:
            self.log(logging.WARNING, msg, *args, **kwargs)            
    
    def debug(self, msg, *args, **kwargs):
        mobj = get_values_regex([r'^(\[[^\]]+\])'], msg) or ""
        mobj2 = msg.split(': ')[-1]

        if self.quiet:
            self.log(logging.DEBUG, msg, *args, **kwargs)
        elif self.verbose and not self.superverbose:
            if (mobj in ('[redirect]', '[download]', '[debug+]', '[info]')) or (mobj in ('[debug]') and any(_ in msg for _ in self._debug_phr)) or any(_ in mobj2 for _ in self._skip_phr):
                self.log(logging.DEBUG, msg[len(mobj):].strip(), *args, **kwargs)
            else:
                self.log(logging.INFO, msg, *args, **kwargs)            
        elif self.superverbose:
            self.log(logging.INFO, msg, *args, **kwargs)
        else:    
            if mobj in ('[redirect]', '[debug]', '[info]', '[download]', '[debug+]') or any(_ in mobj2 for _ in self._skip_phr):
                self.log(logging.DEBUG, msg[len(mobj):].strip(), *args, **kwargs)
            else:                
                self.log(logging.INFO, msg, *args, **kwargs)
