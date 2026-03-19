"""
MEMOFAST - Özel İstisna (Exception) Sınıfları
Uygulamadaki hataları kategorize etmek için kullanılır.
"""


class MemoFastException(Exception):
    """
    Tüm MemoFast istisnalarının temel sınıfı.
    
    Örnek:
        try:
            something()
        except MemoFastException as e:
            logger.error(f"MemoFast Error: {e}")
    """
    pass


class ProcessError(MemoFastException):
    """Process tarama/ekleme hatası"""
    pass


class ProcessNotFound(ProcessError):
    """İstenen process bulunamadı"""
    pass


class ProcessAlreadyAttached(ProcessError):
    """Process zaten ekliydi"""
    pass


class MemoryError(MemoFastException):
    """Bellek tarama/okuma/yazma hatası"""
    pass


class MemoryScanError(MemoryError):
    """Bellek tarama başarısız"""
    pass


class MemoryReadError(MemoryError):
    """Bellek okuma başarısız"""
    pass


class MemoryWriteError(MemoryError):
    """Bellek yazma başarısız"""
    pass


class ScannerError(MemoFastException):
    """Oyun tarama hatası"""
    pass


class GameNotFound(ScannerError):
    """Oyun kurulumu bulunamadı"""
    pass


class TargetFileNotFound(ScannerError):
    """Hedef dosya bulunamadı"""
    pass


class TranslationError(MemoFastException):
    """Çeviri hatası"""
    pass


class TranslatorManagerError(TranslationError):
    """TranslatorManager operasyon hatası"""
    pass


class BepInExInstallError(TranslatorManagerError):
    """BepInEx kurulumu başarısız"""
    pass


class BepInExRemovalError(TranslatorManagerError):
    """BepInEx kaldırması başarısız"""
    pass


class TranslatorInstallError(TranslatorManagerError):
    """XUnity.AutoTranslator kurulumu başarısız"""
    pass


class GameTranslationError(TranslationError):
    """Oyun çevirisi başarısız"""
    pass


class FileOperationError(MemoFastException):
    """Dosya işlemi hatası"""
    pass


class FileNotFound(FileOperationError):
    """Dosya bulunamadı"""
    pass


class FileReadError(FileOperationError):
    """Dosya okuma hatası"""
    pass


class FileWriteError(FileOperationError):
    """Dosya yazma hatası"""
    pass


class APIError(MemoFastException):
    """API isteği hatası"""
    pass


class APITimeoutError(APIError):
    """API zaman aşımı"""
    pass


class APIAuthenticationError(APIError):
    """API kimlik doğrulama hatası"""
    pass


class APIRateLimitError(APIError):
    """API rate limit aşıldı"""
    pass


class ConfigurationError(MemoFastException):
    """Konfigürasyon hatası"""
    pass


class InvalidConfigError(ConfigurationError):
    """Geçersiz konfigürasyon"""
    pass


class MissingConfigError(ConfigurationError):
    """Eksik konfigürasyon"""
    pass


class ValidationError(MemoFastException):
    """Doğrulama hatası"""
    pass


class InvalidInputError(ValidationError):
    """Geçersiz giriş"""
    pass


class ArchitectureDetectionError(MemoFastException):
    """Mimari tespit hatası (x86 vs x64)"""
    pass


class EncryptionError(MemoFastException):
    """Şifreleme/şifre çözme hatası"""
    pass
