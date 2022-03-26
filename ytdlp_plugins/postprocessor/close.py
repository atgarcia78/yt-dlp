# coding: utf-8

# ⚠ Don't use relative imports
from yt_dlp.postprocessor.common import PostProcessor


# ℹ️ See the docstring of yt_dlp.postprocessor.common.PostProcessor
class ClosePluginPP(PostProcessor):
    def __init__(self, downloader=None, **kwargs):
        # ⚠ Only kwargs can be passed from the CLI, and all argument values will be string
        # Also, "downloader", "when" and "key" are reserved names
        super().__init__(downloader)
        self._kwargs = kwargs
        self.to_screen(self._kwargs)        

    # ℹ️ See docstring of yt_dlp.postprocessor.common.PostProcessor.run
    def run(self, info):
        
        def _close_ies():
            ies = self._downloader._ies_instances
            
            for ie, ins in ies.items():
                
                if (close:=getattr(ins, 'close', None)):
                    try:
                        close()
                        self.to_screen(f"[{ie}] Close OK")
                    except Exception as e:
                        self.to_screen(f"[{ie}] {repr(e)}")
            
        
        self.write_debug(info)
        
        if info.get('_type', 'video') != 'video' and info.get('original_url') == self._kwargs['url']:
            _close_ies()
        elif info.get('_type', 'video') == 'video' and not info.get('playlist'):
            _close_ies() 
                
        return [], info


