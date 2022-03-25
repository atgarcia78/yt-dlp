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
        

    # ℹ️ See docstring of yt_dlp.postprocessor.common.PostProcessor.run
    def run(self, info):
        
        self.write_debug(info)
        #ies_to_close = ['NakedSwordScene', 'NetDNA', 'GayBeeg', 'GayBeegPlaylist', 'GayBeegPlaylistPage', 'BoyFriendTVEmbed', 'BoyFriendinfoTV']
        
        if info.get('_type', 'video') != 'video' or not info.get('playlist'):
            ies = self._downloader._ies_instances
            
            for ie, ins in ies.items():
                
                if (close:=getattr(ins, 'close', None)):
                    try:
                        close()
                        self.to_screen(f"[{ie}] Close OK")
                    except Exception as e:
                        self.to_screen(f"[{ie}] {repr(e)}")
                
        return [], info


