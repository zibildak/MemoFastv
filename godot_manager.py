import os
import struct

class GodotManager:
    """Sadece oyunun Godot olup olmadığını tespit eden sınırlı modül"""
    MAGIC = 0x43504447 # GDPC
    
    @staticmethod
    def is_godot_game(file_path):
        """Dosyanın bir Godot PCK veya EXE gömülü PCK olup olmadığını kontrol eder"""
        try:
            if not os.path.exists(file_path): return False
            
            with open(file_path, 'rb') as f:
                # 1. Başlangıç Kontrolü
                if f.read(4) == struct.pack('<I', GodotManager.MAGIC):
                    return True
                
                # 2. EXE Trailer Kontrolü (Gömülü PCK)
                f.seek(0, os.SEEK_END)
                size = f.tell()
                if size > 12:
                    f.seek(-12, os.SEEK_END)
                    data = f.read(12)
                    if data[8:] == struct.pack('<I', GodotManager.MAGIC):
                        return True
                        
                # 3. Hızlı Tarama (İlk 1MB)
                f.seek(0)
                chunk = f.read(1024 * 1024)
                if struct.pack('<I', GodotManager.MAGIC) in chunk:
                    return True
                    
            return False
        except:
            return False

    @staticmethod
    def get_game_pck(game_path):
        # Scanner uyumluluğu için
        from pathlib import Path
        gp = Path(game_path)
        if gp.suffix.lower() == '.pck': return gp
        side_pck = gp.with_suffix('.pck')
        return side_pck if side_pck.exists() else gp
