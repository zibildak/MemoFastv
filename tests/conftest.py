"""
MEMOFAST - Test Konfigürasyonu ve Fixtures
Pytest konfigürasyonu ve tüm testlerde kullanılan common fixtures
"""
import pytest
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# MemoFast root dizinini sys.path'e ekle
MEMOFAST_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(MEMOFAST_ROOT))


@pytest.fixture
def temp_dir():
    """Geçici test dizini oluştur"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_logger():
    """Mock logger fixture"""
    logger = Mock()
    logger.info = Mock()
    logger.error = Mock()
    logger.warning = Mock()
    logger.debug = Mock()
    return logger


@pytest.fixture
def mock_config():
    """Mock Config sınıfı"""
    with patch('config.Config') as mock:
        mock.CACHE_PATH = Path(tempfile.gettempdir()) / "test_cache"
        mock.CACHE_PATH.mkdir(exist_ok=True)
        yield mock


@pytest.fixture
def constants():
    """Constants sınıfını yükle"""
    from config import Constants
    return Constants


@pytest.fixture
def exceptions_module():
    """Exceptions modülünü yükle"""
    import exceptions
    return exceptions


@pytest.fixture
def crypto_manager(temp_dir):
    """CryptoManager singleton'ını test et"""
    from cryptography.fernet import Fernet
    from crypto_manager import CryptoManager
    
    # Singleton'u reset et
    CryptoManager._instance = None
    
    # Mock CryptoManager'ı oluştur
    cm = MagicMock(spec=CryptoManager)
    cm.key_dir = temp_dir / ".secure"
    cm.key_dir.mkdir(exist_ok=True)
    
    # Real Fernet cipher'ı kullan
    test_key = Fernet.generate_key()
    cm.cipher = Fernet(test_key)
    cm._initialized = True
    
    # Gerçek encrypt/decrypt metodlarını ekle
    cm.encrypt = lambda plaintext: (
        plaintext if not plaintext else 
        Fernet(test_key).encrypt(
            plaintext.encode('utf-8') if isinstance(plaintext, str) else plaintext
        ).decode('utf-8')
    )
    
    cm.decrypt = lambda ciphertext: (
        ciphertext if not ciphertext else
        Fernet(test_key).decrypt(
            ciphertext.encode('utf-8') if isinstance(ciphertext, str) else ciphertext
        ).decode('utf-8')
    )
    
    yield cm


@pytest.fixture
def scanner(temp_dir, mock_config):
    """PlatformScanner fixture"""
    with patch('scanner.Config', mock_config):
        from scanner import PlatformScanner
        return PlatformScanner()


@pytest.fixture
def memory_trainer():
    """MemoryTrainer fixture (mock Pymem)"""
    with patch('pymem.Pymem'):
        from memory_tool import MemoryTrainer
        return MemoryTrainer()
