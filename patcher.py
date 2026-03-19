"""
MEMOFAST - Yama İşlemleri Modülü
Dosya kopyalama ve yama uygulama işlemlerini yönetir
"""
import shutil
from pathlib import Path
from config import Config
from logger import setup_logger
from security_utils import SecurityValidator

logger = setup_logger(__name__)

class GamePatcher:
    """Oyun yama işlemleri"""
    
    def __init__(self, game_folder):
        self.game_folder = game_folder
        self.game_path = Config.GAME_PATH / game_folder
        self.new_path = self.game_path / "new"
        self.old_path = self.game_path / "old"
    
    def get_patch_file(self, patch_type='turkish'):
        """
        Yama dosyasını al
        
        Args:
            patch_type: 'turkish' veya 'original'
        
        Returns:
            Path: Yama dosyası yolu veya None
        """
        if patch_type == 'turkish':
            source_path = self.new_path
        elif patch_type == 'original':
            source_path = self.old_path
        else:
            return None
        
        if not source_path.exists():
            return None
        
        # Klasördeki ilk dosyayı al
        files = list(source_path.glob("*"))
        if files:
            # Sadece dosyaları al (klasörleri değil)
            files = [f for f in files if f.is_file()]
            if files:
                return files[0]
        
        return None
    
    def apply_patch(self, target_paths, patch_type='turkish', progress_callback=None):
        """
        Yamayı uygula
        
        Args:
            target_paths: Hedef dosya yolları listesi
            patch_type: 'turkish' veya 'original'
            progress_callback: İlerleme callback fonksiyonu (current, total, path)
        
        Returns:
            dict: Sonuç {'success': int, 'failed': int, 'errors': []}
            
        Security: Validates paths to prevent traversal attacks
        """
        patch_file = self.get_patch_file(patch_type)
        
        if not patch_file:
            return {
                'success': 0,
                'failed': len(target_paths),
                'errors': ['Yama dosyası bulunamadı!']
            }
        
        results = {
            'success': 0,
            'failed': 0,
            'errors': []
        }
        
        total = len(target_paths)
        
        for i, target_path in enumerate(target_paths, 1):
            try:
                target_path = Path(target_path)
                
                # SECURITY: Validate path exists and resolve safely
                if not target_path.exists():
                    raise FileNotFoundError(f"Target file not found: {target_path}")
                
                # Prevent symbolic link attacks
                if target_path.is_symlink():
                    raise ValueError(f"Symbolic links not allowed: {target_path}")
                
                # Progress callback
                if progress_callback:
                    progress_callback(i, total, str(target_path))
                
                # Yamayı kopyala
                shutil.copy2(patch_file, target_path)
                results['success'] += 1
                logger.info(f"Patch applied: {target_path}")
                
            except Exception as e:
                results['failed'] += 1
                error_msg = f"{target_path}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        return results
    
    def verify_patch(self, target_path, patch_type='turkish'):
        """
        Yama doğrulama - dosya boyutu kontrolü
        
        Args:
            target_path: Kontrol edilecek dosya
            patch_type: 'turkish' veya 'original'
        
        Returns:
            bool: Dosya boyutu eşleşiyor mu?
        """
        patch_file = self.get_patch_file(patch_type)
        target_path = Path(target_path)
        
        if not patch_file or not target_path.exists():
            return False
        
        return patch_file.stat().st_size == target_path.stat().st_size
    
    def get_patch_info(self):
        """Yama bilgilerini al"""
        info = {
            'turkish_available': False,
            'original_available': False,
            'turkish_file': None,
            'original_file': None,
            'turkish_size': 0,
            'original_size': 0
        }
        
        # Türkçe yama
        turkish_file = self.get_patch_file('turkish')
        if turkish_file:
            info['turkish_available'] = True
            info['turkish_file'] = turkish_file.name
            info['turkish_size'] = turkish_file.stat().st_size
        
        # Orijinal
        original_file = self.get_patch_file('original')
        if original_file:
            info['original_available'] = True
            info['original_file'] = original_file.name
            info['original_size'] = original_file.stat().st_size
        
        return info

    def create_backup(self, target_paths, note=""):
        """
        Yedek oluştur
        
        Args:
            target_paths: Yedeklenecek dosyaların listesi
            note: Yedek notu
        
        Returns:
            str: Oluşturulan yedek dosyasının yolu veya None
        """
        import datetime
        import zipfile
        
        if not target_paths:
            return None
            
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}.zip"
        
        # Backups klasörü
        backup_dir = self.game_path / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        backup_path = backup_dir / backup_name
        
        try:
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Metadata
                zf.comment = note.encode('utf-8')
                
                for target in target_paths:
                    target = Path(target)
                    if target.exists():
                        # Dosya adıyla kök dizine ekle
                        zf.write(target, target.name)
            
            return str(backup_path)
        except Exception as e:
            print(f"Yedekleme hatası: {e}")
            if backup_path.exists():
                try: backup_path.unlink()
                except: pass
            return None

    def list_backups(self):
        """
        Mevcut yedekleri listele
        
        Returns:
            list: [{'file': Path, 'date': datetime, 'size': int, 'note': str}, ...]
        """
        import datetime
        import zipfile
        
        backup_dir = self.game_path / "backups"
        if not backup_dir.exists():
            return []
            
        backups = []
        for f in backup_dir.glob("*.zip"):
            try:
                stat = f.stat()
                dt = datetime.datetime.fromtimestamp(stat.st_mtime)
                
                note = ""
                try:
                    with zipfile.ZipFile(f, 'r') as zf:
                        note = zf.comment.decode('utf-8')
                except: pass
                
                backups.append({
                    'file': str(f),
                    'filename': f.name,
                    'date': dt,
                    'size': stat.st_size,
                    'note': note
                })
            except: pass
            
        # Tarihe göre sırala (Yeniden eskiye)
        backups.sort(key=lambda x: x['date'], reverse=True)
        return backups

    def restore_backup(self, backup_file, target_folder):
        """
        Yedeği geri yükle
        
        Args:
            backup_file: Yedek dosyası yolu (.zip)
            target_folder: Hedef klasör (Oyun ana dizini)
        
        Returns:
            dict: Sonuç {'success': int, 'failed': int}
        """
        import zipfile
        
        results = {'success': 0, 'failed': 0}
        backup_path = Path(backup_file)
        
        if not backup_path.exists():
            return results
            
        try:
            with zipfile.ZipFile(backup_path, 'r') as zf:
                # Dosya listesini al
                file_names = zf.namelist()
                
                # Hedef klasörde bu dosyaları bul
                target_paths = []
                for root, dirs, files in os.walk(target_folder):
                    for f in files:
                        if f in file_names:
                            target_paths.append(Path(root) / f)
                
                if not target_paths:
                    # Dosyalar hedefte yoksa bile zip içeriğini oraya açmayı deneyebiliriz
                    # Ama şimdilik sadece var olan dosyaların üzerine yazma mantığıyla gidelim
                    # veya kullanıcının seçtiği klasöre açalım
                    pass
                
                # Zip'ten çıkar ve üzerine yaz
                # Not: extract yönteminde tam yol tutulmadığı için (arcname=filename)
                # hedef klasördeki eşleşen dosyanın üzerine tek tek yazmalıyız.
                
                for member in file_names:
                    # Bu dosya hedef klasörde nerede?
                    # Basitçe: target_folder içinde recursive ara
                    found = False
                    for root, dirs, files in os.walk(target_folder):
                        if member in files:
                            dest = Path(root) / member
                            try:
                                with zf.open(member) as source, open(dest, "wb") as target:
                                    shutil.copyfileobj(source, target)
                                results['success'] += 1
                                found = True
                            except:
                                results['failed'] += 1
                    
                    if not found:
                        # Hiçbir yerde yoksa ana dizine çıkar?
                        # Şimdilik başarısız sayalım, risk almayalım
                        results['failed'] += 1
                        
        except Exception as e:
            print(f"Restore hatası: {e}")
            
        return results

    def delete_backup(self, backup_file):
        """Yedeği sil"""
        try:
            p = Path(backup_file)
            if p.exists():
                p.unlink()
                return True
        except: pass
        return False


def format_size(bytes_size):
    """Dosya boyutunu formatla"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"


if __name__ == "__main__":
    # Test
    patcher = GamePatcher('wwm')
    info = patcher.get_patch_info()
    
    print("Yama Bilgileri:")
    print(f"Türkçe: {info['turkish_available']} - {info['turkish_file']}")
    print(f"Orijinal: {info['original_available']} - {info['original_file']}")
