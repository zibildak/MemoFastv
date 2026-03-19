"""
MEMOFAST - Şifreleme Yöneticisi (Cryptography)
API anahtarları ve hassas verileri güvenli şekilde şifreler/şifre çözer.
"""
import os
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    Fernet = None

from logger import setup_logger

logger = setup_logger(__name__)

if not CRYPTO_AVAILABLE:
    logger.warning("cryptography kütüphanesi bulunamadı! CryptoManager devre dışı.")


class CryptoManager:
    """
    Şifreleme/Şifre çözme işlemlerini yönetir.
    
    Özellikleri:
    - Fernet (simetrik şifreleme) kullanır
    - Key otomatik üretilir ve .key dosyasında saklanır
    - Singleton pattern
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CryptoManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        if not CRYPTO_AVAILABLE:
            logger.error("CryptoManager kullanılamıyor: cryptography kütüphanesi eksik!")
            self._initialized = True
            self.cipher = None
            return
        
        self.key_dir = Path(__file__).parent / ".secure"
        self.key_dir.mkdir(exist_ok=True, mode=0o700)  # Sadece sahibi erişebilir
        
        self.key_file = self.key_dir / ".key"
        self.cipher = self._init_cipher()
        
        self._initialized = True
        logger.info("CryptoManager başlatıldı")
    
    def _init_cipher(self):
        """Şifreleme anahtarını yönet ve cipher oluştur"""
        if self.key_file.exists():
            try:
                key = self.key_file.read_bytes()
                logger.debug("Mevcut şifreleme anahtarı yüklendi")
            except Exception as e:
                logger.error(f"Key dosyası okunamadı: {e}")
                raise
        else:
            # Yeni key üret
            key = Fernet.generate_key()
            try:
                self.key_file.write_bytes(key)
                # Dosya izinlerini sadece sahibi için ayarla
                os.chmod(self.key_file, 0o600)
                logger.info("Yeni şifreleme anahtarı oluşturuldu")
            except Exception as e:
                logger.error(f"Key dosyası yazılamadı: {e}")
                raise
        
        return Fernet(key)
    
    def encrypt(self, plaintext):
        """
        Metin'i şifrele.
        
        Args:
            plaintext: Şifrelenmek istenen metin (str)
            
        Returns:
            str: Şifrelenmiş metin (base64 encoded)
        """
        if not plaintext:
            return ""
        
        try:
            if isinstance(plaintext, str):
                plaintext = plaintext.encode('utf-8')
            
            encrypted = self.cipher.encrypt(plaintext)
            logger.debug(f"Metin şifrelendi ({len(plaintext)} byte)")
            return encrypted.decode('utf-8')
        except Exception as e:
            logger.error(f"Şifreleme başarısız: {e}")
            raise
    
    def decrypt(self, ciphertext):
        """
        Şifrelenmiş metin'i çöz.
        
        Args:
            ciphertext: Şifreli metin (str, base64 encoded)
            
        Returns:
            str: Orijinal metin
            
        Raises:
            Exception: Şifre çözme başarısız ise
        """
        if not ciphertext:
            return ""
        
        try:
            if isinstance(ciphertext, str):
                ciphertext = ciphertext.encode('utf-8')
            
            decrypted = self.cipher.decrypt(ciphertext)
            logger.debug(f"Metin şifre çözüldü ({len(decrypted)} byte)")
            return decrypted.decode('utf-8')
        except Exception as e:
            logger.error(f"Şifre çözme başarısız: {e}")
            raise
    
    @staticmethod
    def get_instance():
        """CryptoManager singleton'ını al"""
        return CryptoManager()
