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
        
        ie = self._downloader._ies_instances.get('NetDNA')
        if ie:
            self.to_screen(f'Postprocessor: Closing NetDNA client')
            ie.close()
                
        return [], info  # return list_of_files_to_delete, info_dict
