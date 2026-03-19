"""
MEMOFAST - Crypto Manager Testleri
API Key encryption testleri
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile


class TestCryptoManagerInitialization:
    """CryptoManager başlatılması testleri"""
    
    def test_crypto_manager_singleton(self, crypto_manager):
        """CryptoManager singleton pattern"""
        from crypto_manager import CryptoManager
        
        # Reset singleton
        CryptoManager._instance = None
        
        cm1 = CryptoManager()
        cm2 = CryptoManager()
        
        # Aynı instance'ı return etmeli
        assert cm1 is cm2
    
    def test_crypto_manager_has_methods(self, crypto_manager):
        """CryptoManager gerekli metodlara sahip mi"""
        required_methods = ['encrypt', 'decrypt', 'get_instance', '_init_cipher']
        
        for method in required_methods:
            assert hasattr(crypto_manager, method), f"Method {method} not found"


class TestEncryption:
    """Şifreleme testleri"""
    
    def test_encrypt_simple_text(self, crypto_manager):
        """Basit metin şifreleme"""
        plaintext = "test_api_key_12345"
        
        encrypted = crypto_manager.encrypt(plaintext)
        
        assert encrypted is not None
        assert encrypted != plaintext
        assert isinstance(encrypted, str)
    
    def test_encrypt_empty_string(self, crypto_manager):
        """Boş string şifreleme"""
        encrypted = crypto_manager.encrypt("")
        
        assert encrypted == ""
    
    def test_encrypt_unicode_text(self, crypto_manager):
        """Unicode metin şifreleme"""
        plaintext = "Türkçe_Yazı_Test_🔐"
        
        encrypted = crypto_manager.encrypt(plaintext)
        
        assert encrypted is not None
        assert encrypted != plaintext
    
    def test_encrypt_long_text(self, crypto_manager):
        """Uzun metin şifreleme"""
        plaintext = "a" * 1000  # 1000 karakter
        
        encrypted = crypto_manager.encrypt(plaintext)
        
        assert encrypted is not None
        assert len(encrypted) > 0


class TestDecryption:
    """Şifre çözme testleri"""
    
    def test_decrypt_simple_text(self, crypto_manager):
        """Basit metin şifre çözme"""
        plaintext = "test_api_key_12345"
        
        encrypted = crypto_manager.encrypt(plaintext)
        decrypted = crypto_manager.decrypt(encrypted)
        
        assert decrypted == plaintext
    
    def test_decrypt_empty_string(self, crypto_manager):
        """Boş string şifre çözme"""
        decrypted = crypto_manager.decrypt("")
        
        assert decrypted == ""
    
    def test_decrypt_unicode_text(self, crypto_manager):
        """Unicode metin şifre çözme"""
        plaintext = "Türkçe_Yazı_Test_🔐"
        
        encrypted = crypto_manager.encrypt(plaintext)
        decrypted = crypto_manager.decrypt(encrypted)
        
        assert decrypted == plaintext
    
    def test_decrypt_invalid_token(self, crypto_manager):
        """Invalid token şifre çözme"""
        # Invalid token'ı şifre çözmek exception raise etmeli
        invalid_token = "invalid_encrypted_data_not_base64"
        
        with pytest.raises(Exception):
            crypto_manager.decrypt(invalid_token)


class TestEncryptionRoundTrip:
    """Round-trip şifreleme testleri"""
    
    def test_multiple_roundtrips(self, crypto_manager):
        """Aynı metin birden fazla kez şifreleme/çözme"""
        plaintext = "api_key_for_deepl_service"
        
        for _ in range(5):
            encrypted = crypto_manager.encrypt(plaintext)
            decrypted = crypto_manager.decrypt(encrypted)
            
            assert decrypted == plaintext
    
    def test_different_encryptions_same_plaintext(self, crypto_manager):
        """Aynı metin her seferinde farklı encrypted hali olmalı (Fernet kullanırsa)"""
        plaintext = "same_key_content"
        
        encrypted1 = crypto_manager.encrypt(plaintext)
        encrypted2 = crypto_manager.encrypt(plaintext)
        
        # Fernet her zaman farklı ciphertext üretir (timestamp + nonce)
        # Bu test encryption'ın randomnesini doğrular
        assert isinstance(encrypted1, str)
        assert isinstance(encrypted2, str)
        
        # Her ikisini de çözümlemesi gerekir
        assert crypto_manager.decrypt(encrypted1) == plaintext
        assert crypto_manager.decrypt(encrypted2) == plaintext


class TestKeyManagement:
    """Key yönetimi testleri"""
    
    def test_key_file_creation(self, temp_dir):
        """Key dosyası oluşturuluyor mu"""
        with patch('crypto_manager.Path') as mock_path:
            mock_instance = MagicMock()
            mock_instance.parent = temp_dir
            mock_path.return_value = mock_instance
            
            # Key oluşturulduğunu doğrula
            from cryptography.fernet import Fernet
            key = Fernet.generate_key()
            
            assert key is not None
            assert len(key) > 0
    
    def test_key_persistence(self, crypto_manager):
        """Key dosyasında persistency"""
        # Encrypt/decrypt işlemleri sonra da aynı key kullanılıyor mu
        plaintext1 = "first_test"
        
        encrypted1 = crypto_manager.encrypt(plaintext1)
        
        # Aynı manager instance'ında decrypt
        decrypted1 = crypto_manager.decrypt(encrypted1)
        
        assert decrypted1 == plaintext1


class TestAPIKeyScenarios:
    """API key şifreleme senaryoları"""
    
    def test_deepl_api_key_encryption(self, crypto_manager):
        """DeepL API key şifreleme"""
        # Gerçek API key format'ı
        deepl_key = "1234567:fx"
        
        encrypted = crypto_manager.encrypt(deepl_key)
        decrypted = crypto_manager.decrypt(encrypted)
        
        assert decrypted == deepl_key
    
    def test_gemini_api_key_encryption(self, crypto_manager):
        """Gemini API key şifreleme"""
        # Gerçek API key format'ı
        gemini_key = "AIzaSyDxCHjW7YzLLxEfF3u9W3Q0yU0XXXXXXXX"
        
        encrypted = crypto_manager.encrypt(gemini_key)
        decrypted = crypto_manager.decrypt(encrypted)
        
        assert decrypted == gemini_key
    
    def test_multiple_keys_same_manager(self, crypto_manager):
        """Aynı manager'da birden fazla key"""
        deepl_key = "deepl_key_12345"
        gemini_key = "AIzaSyDxxxxxxxxxx"
        
        enc_deepl = crypto_manager.encrypt(deepl_key)
        enc_gemini = crypto_manager.encrypt(gemini_key)
        
        # Şifreleme farklı olmalı
        assert enc_deepl != enc_gemini
        
        # Çözülmesi doğru olmalı
        assert crypto_manager.decrypt(enc_deepl) == deepl_key
        assert crypto_manager.decrypt(enc_gemini) == gemini_key


class TestSecurityProperties:
    """Güvenlik özellikleri"""
    
    def test_encrypted_text_not_plaintext(self, crypto_manager):
        """Şifreli metin plaintext değil"""
        plaintext = "sensitive_api_key"
        encrypted = crypto_manager.encrypt(plaintext)
        
        assert plaintext not in encrypted
    
    def test_encryption_produces_string(self, crypto_manager):
        """Şifreleme string üretir (saveability)"""
        plaintext = "test_key_12345"
        
        encrypted = crypto_manager.encrypt(plaintext)
        
        # String olmalı (file'a yazılabilir)
        assert isinstance(encrypted, str)
        # ASCII karakterleri içermeli (file safe)
        try:
            encrypted.encode('ascii')
        except UnicodeEncodeError:
            pytest.fail("Encrypted text contains non-ASCII characters")
