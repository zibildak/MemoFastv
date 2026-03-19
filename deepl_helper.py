
import json
import ssl
import urllib.request
import urllib.parse
from PyQt5.QtCore import QThread, pyqtSignal
from logger import setup_logger
from security_utils import CredentialSanitizer

logger = setup_logger(__name__)

class DeepLUsageChecker(QThread):
    finished = pyqtSignal(dict)
    
    def __init__(self, api_key, is_encrypted=False):
        super().__init__()
        self.api_key = api_key
        self.is_encrypted = is_encrypted
        
    def run(self):
        if not self.api_key:
            self.finished.emit({"error": "API anahtarı boş!"})
            return

        # Anahtarı decrypt et (gerekirse)
        key = self._decrypt_key_if_needed(self.api_key)
        if not key:
            self.finished.emit({"error": "API anahtarı şifresi çözülemedi!"})
            return
            
        key = key.strip()

        # DeepL API URL'leri (Free ve Pro)
        if key.endswith(":fx"):
            url = "https://api-free.deepl.com/v2/usage"
        else:
            url = "https://api.deepl.com/v2/usage"
            
        try:
            # SSL Bağlamı - Sertifika Doğrulama Etkin
            ctx = ssl.create_default_context()
            
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"DeepL-Auth-Key {key}")
            req.add_header("User-Agent", "MEMOFAST/1.0")
            
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    self.finished.emit(data)
                else:
                    self.finished.emit({"error": f"HTTP {response.status}"})
                    
        except urllib.error.HTTPError as e:
            if e.code == 403:
                self.finished.emit({"error": "Yetkisiz (403). Anahtar yanlış."})
            elif e.code == 429:
                self.finished.emit({"error": "Çok fazla istek (429)."})
            elif e.code == 456:
                self.finished.emit({"error": "Kota doldu (456)."})
            else:
                self.finished.emit({"error": f"Sunucu: {e.code}"})
                
        except Exception as e:
            logger.error(f"DeepL Usage Check Error: {e}")
            self.finished.emit({"error": f"Hata: {str(e)}"})

    def _decrypt_key_if_needed(self, key):
        """Şifreli anahtarı decrypt et"""
        if not self.is_encrypted:
            return key
        try:
            from crypto_manager import CryptoManager
            crypto = CryptoManager()
            return crypto.decrypt(key)
        except Exception as e:
            logger.error(f"API key decryption error: {e}")
            return None

def get_deepl_usage_sync(api_key, is_encrypted=False):
    """Senkronize kullanım kontrolü (Unreal manager vs için)"""
    if not api_key: 
        return None
    
    # Anahtarı decrypt et (gerekirse)
    if is_encrypted:
        try:
            from crypto_manager import CryptoManager
            crypto = CryptoManager()
            api_key = crypto.decrypt(api_key)
        except:
            return None
    
    if api_key.endswith(":fx"):
        url = "https://api-free.deepl.com/v2/usage"
    else:
        url = "https://api.deepl.com/v2/usage"
        
    try:
        ctx = ssl.create_default_context()
        
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"DeepL-Auth-Key {api_key}")
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            if response.status == 200:
                return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        logger.debug(f"DeepL usage check failed: {e}")
        return None

class DeepLTranslator:
    """DeepL API Translator for Unity/Unreal managers"""
    def __init__(self, api_key, target_lang="tr", is_encrypted=False):
        # Anahtarı decrypt et (gerekirse)
        if is_encrypted:
            try:
                from crypto_manager import CryptoManager
                crypto = CryptoManager()
                api_key = crypto.decrypt(api_key)
            except Exception as e:
                logger.warning(f"API key decryption failed: {e}")
        
        self.api_key = api_key.strip() if api_key else ""
        self.target_lang = target_lang.upper()
        # [FIX] DeepL requires EN-US, EN-GB or PT-BR, PT-PT
        if self.target_lang == "EN": self.target_lang = "EN-US"
        elif self.target_lang == "PT": self.target_lang = "PT-BR"
        
        if self.api_key.endswith(":fx"):
            self.url = "https://api-free.deepl.com/v2/translate"
        else:
            self.url = "https://api.deepl.com/v2/translate"

    def translate(self, text):
        if not text or not text.strip(): 
            return text
        
        if not self.api_key:
            logger.warning("DeepL API key not available")
            return text
        
        try:
            ctx = ssl.create_default_context()
            data = urllib.parse.urlencode({
                'text': text,
                'target_lang': self.target_lang,
                'source_lang': 'EN'
            }).encode('utf-8')
            
            req = urllib.request.Request(self.url, data=data)
            req.add_header("Authorization", f"DeepL-Auth-Key {self.api_key}")
            
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                if response.status == 200:
                    result = json.loads(response.read().decode('utf-8'))
                    return result['translations'][0]['text']
        except Exception as e:
            logger.error(f"DeepL Translate Error: {e}")
        return text  # Fail-safe: return original text
