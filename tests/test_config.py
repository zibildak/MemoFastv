"""
MEMOFAST - Config ve Constants Testleri
Constants sınıfı ve ayarların doğrulanması
"""
import pytest
from pathlib import Path


class TestConstants:
    """Constants sınıfı testleri"""
    
    def test_constants_exist(self, constants):
        """Constants sınıfı var mı"""
        assert constants is not None
    
    def test_timeout_values(self, constants):
        """Timeout değerleri set mi"""
        assert hasattr(constants, 'PROCESS_TIMEOUT')
        assert constants.PROCESS_TIMEOUT == 60
        assert constants.NETWORK_TIMEOUT == 10
        assert constants.SCANNER_TIMEOUT == 300
    
    def test_cache_settings(self, constants):
        """Cache ayarları doğru mu"""
        assert constants.CACHE_TTL == 3600
        assert constants.SCAN_BATCH_SIZE == 100
        assert isinstance(constants.EXCLUDED_FOLDERS, (list, tuple))
        assert len(constants.EXCLUDED_FOLDERS) > 0
    
    def test_excluded_folders_contain_system_dirs(self, constants):
        """Excluded folders sistem klasörlerini içeriyor mu"""
        excluded_upper = [f.upper() for f in constants.EXCLUDED_FOLDERS]
        assert any('WINDOWS' in f for f in excluded_upper)
        assert any('SYSTEM' in f for f in excluded_upper)
        assert any('APPDATA' in f for f in excluded_upper)
    
    def test_max_workers(self, constants):
        """Threading ayarları doğru mu"""
        assert constants.MAX_WORKERS == 50
        assert constants.MAX_RETRIES == 3
    
    def test_ocr_settings(self, constants):
        """OCR ayarları set mi"""
        assert hasattr(constants, 'OCR_CONFIDENCE_THRESHOLD')
        assert 0 <= constants.OCR_CONFIDENCE_THRESHOLD <= 1
        assert constants.OCR_LANG_DEFAULT == "eng"
    
    def test_memory_settings(self, constants):
        """Memory scanning ayarları set mi"""
        assert constants.AES_KEY_PATTERN_LENGTH == 64
        assert constants.MEMORY_SCAN_BUFFER_SIZE > 0
        assert constants.MEMORY_SCAN_MAX_REGIONS > 0
    
    def test_file_operation_limits(self, constants):
        """Dosya işlem limitleri set mi"""
        assert hasattr(constants, 'BACKUP_SUFFIX')
        assert constants.BACKUP_SUFFIX == ".bak"
        assert constants.MAX_FILE_SIZE > 0
        assert constants.CACHE_CLEANUP_INTERVAL > 0


class TestConfigImport:
    """Config modülü importu testleri"""
    
    def test_config_module_imports(self):
        """Config modülü import edilebiliyor mu"""
        from config import Config, Constants
        assert Config is not None
        assert Constants is not None
    
    def test_config_has_cache_path(self):
        """Config CACHE_PATH property'si var mı"""
        from config import Config
        assert hasattr(Config, 'CACHE_PATH')
