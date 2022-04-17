# coding: utf-8

from yt_dlp.postprocessor.common import PostProcessor
class ClosePluginPP(PostProcessor):
    
    def __init__(self, downloader=None, **kwargs):

        super().__init__(downloader)
        self._kwargs = kwargs
        self.to_screen(self._kwargs)        

    
    def run(self, info):
        
        def _close_ies():
            ies = self._downloader._ies_instances
            
            for ie, ins in ies.items():
                
                if (close:=getattr(ins, 'close', None)):
                    try:
                        close()
                        self.to_screen(f"[{ie}] Close OK")
                        break
                    except Exception as e:
                        self.to_screen(f"[{ie}] {repr(e)}")
            
        
        #self.to_screen(f' {info}')
        
        
        if info.get('_type', 'video') != 'video' and info.get('original_url') == self._kwargs['url']:
            _close_ies()
        
        elif info.get('_type', 'video') == 'video' and not info.get('playlist'):
            _close_ies() 
                
        return [], info


