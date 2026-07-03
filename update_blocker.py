"""
RST Güncelleme Koruma Modülü
GitHub'dan otomatik güncelleme almasını engelle (Hosts dosyası yöntemi)
"""
import os
import sys
import platform
from pathlib import Path

# Logger'ı güvenli şekilde import et
try:
    from logger import setup_logger
    logger = setup_logger(__name__)
except ImportError:
    # Logger yoksa basit print kullan (topluluğun farklı setupları için)
    import logging
    logger = logging.getLogger(__name__)
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())

class UpdateBlocker:
    """Yazılımın güncelleme almasını engelle"""
    
    # Bloke edilecek GitHub adresleri
    BLOCKED_HOSTS = [
        "github.com",
        "api.github.com",
        "releases.github.com",
        "codeload.github.com",
        "raw.githubusercontent.com",
    ]
    
    def __init__(self):
        self.hosts_path = self._get_hosts_path()
    
    def _get_hosts_path(self):
        """İşletim sistemine göre hosts dosyası yolunu döner"""
        if platform.system() == "Windows":
            return Path("C:\\Windows\\System32\\drivers\\etc\\hosts")
        elif platform.system() == "Linux":
            return Path("/etc/hosts")
        elif platform.system() == "Darwin":  # macOS
            return Path("/etc/hosts")
        return None
    
    def is_update_blocked(self):
        """Güncellemelerin bloke edilip edilmediğini kontrol et"""
        if not self.hosts_path or not self.hosts_path.exists():
            return False
        
        try:
            with open(self.hosts_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # En az bir GitHub adresi varsa engellendi
                return any(host in content for host in self.BLOCKED_HOSTS)
        except Exception as e:
            logger.warning(f"Hosts dosyası okunamadı: {e}")
            return False
    
    def block_updates(self):
        """Hosts dosyasına GitHub adreslerini ekleyerek güncellemeleri engelle"""
        if not self.hosts_path:
            logger.error("Bu işletim sistemi desteklenmiyor")
            return False, "İşletim sistemi desteklenmiyor"
        
        if not self.hosts_path.exists():
            logger.error(f"Hosts dosyası bulunamadı: {self.hosts_path}")
            return False, "Hosts dosyası bulunamadı"
        
        # Zaten engellendi mi kontrol et
        if self.is_update_blocked():
            logger.info("Güncellemeler zaten engellendi")
            return True, "Güncellemeler zaten engellendi"
        
        try:
            # Hosts dosyasını oku
            with open(self.hosts_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Güncelleme engeli açıklaması
            blocker_header = "\n# === MEMOFAST UPDATE BLOCKER ===\n"
            blocker_lines = [f"127.0.0.1 {host}\n" for host in self.BLOCKED_HOSTS]
            blocker_footer = "# === MEMOFAST UPDATE BLOCKER END ===\n"
            
            # Zaten var mı kontrol et (çift kayıt olmasın)
            hosts_content = ''.join(lines)
            if blocker_header.strip() in hosts_content:
                logger.info("Blokaj zaten yapılı")
                return True, "Blokaj zaten yapılı"
            
            # Hosts dosyasının sonuna ekle
            with open(self.hosts_path, 'a', encoding='utf-8') as f:
                f.write(blocker_header)
                f.writelines(blocker_lines)
                f.write(blocker_footer)
            
            logger.info(f"Güncellemeler başarıyla engellendi. {len(self.BLOCKED_HOSTS)} adres bloke edildi.")
            return True, f"Başarılı! {len(self.BLOCKED_HOSTS)} GitHub adresi engellendi"
        
        except PermissionError:
            logger.error("Hosts dosyasını yazma hakkı yok. Admin modunda çalıştır gerekli.")
            return False, "❌ Hosts dosyasını yazmak için Admin hakkı gerekli"
        except Exception as e:
            logger.error(f"Hosts dosyası yazılırken hata: {e}")
            return False, f"Hata: {str(e)}"
    
    def unblock_updates(self):
        """Blokaj kaldır (seçenek)"""
        if not self.hosts_path or not self.hosts_path.exists():
            return False, "Hosts dosyası bulunamadı"
        
        try:
            with open(self.hosts_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # MEMOFAST UPDATE BLOCKER arasındaki satırları kaldır
            new_lines = []
            skip = False
            for line in lines:
                if "MEMOFAST UPDATE BLOCKER" in line:
                    if "END" in line:
                        skip = False
                    else:
                        skip = True
                    continue
                if not skip:
                    new_lines.append(line)
            
            with open(self.hosts_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            
            logger.info("Blokaj kaldırıldı")
            return True, "Blokaj kaldırıldı"
        
        except PermissionError:
            return False, "Admin hakkı gerekli"
        except Exception as e:
            return False, f"Hata: {str(e)}"
