# coding: utf-8

# ⚠ Don't use relative imports
from yt_dlp.postprocessor.common import PostProcessor


# ℹ️ See the docstring of yt_dlp.postprocessor.common.PostProcessor
class ReinitPluginPP(PostProcessor):
    def __init__(self, downloader=None, **kwargs):
        # ⚠ Only kwargs can be passed from the CLI, and all argument values will be string
        # Also, "downloader", "when" and "key" are reserved names
        super().__init__(downloader)
        self._kwargs = kwargs
        
    def run(self, info):
    
        ie = self._downloader.get_info_extractor("SeleniumInfoExtractor")
        if not ie._MASTER_INIT:
            self.to_screen(f"[{ie}] Initialize")
            ie._real_initialize()        
       
                
        return [], info
        
    

