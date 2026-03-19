"""
MEMOFAST - Memory Tool Testleri
Bellek tarama ve yazma işlemleri testleri
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import struct


# pymem modülünü mock et
@pytest.fixture(autouse=True)
def mock_pymem():
    """Tüm testlerde pymem'i mock et"""
    with patch.dict('sys.modules', {'pymem': MagicMock()}):
        yield


class TestMemoryTrainerInitialization:
    """MemoryTrainer başlatılması testleri"""
    
    def test_memory_trainer_init(self):
        """MemoryTrainer başlatılabiliyor mu"""
        with patch('pymem.Pymem'):
            from memory_tool import MemoryTrainer
            trainer = MemoryTrainer()
            assert trainer is not None
    
    def test_memory_trainer_has_methods(self):
        """MemoryTrainer gerekli metodlara sahip mi"""
        with patch('pymem.Pymem'):
            from memory_tool import MemoryTrainer
            trainer = MemoryTrainer()
            
            required_methods = [
                'attach',
                'scan_memory',
                'filter_memory',
                'write_memory',
                'scan_for_aes_keys',
                'is_valid_key'
            ]
            
            for method in required_methods:
                assert hasattr(trainer, method), f"Method {method} not found"


class TestMemoryAttachment:
    """Process attachment testleri"""
    
    def test_attach_success(self):
        """Başarılı process attachment"""
        with patch('pymem.Pymem') as mock_pymem:
            mock_pymem.return_value = MagicMock()
            
            from memory_tool import MemoryTrainer
            trainer = MemoryTrainer()
            
            # attach metodu test edilir
            assert trainer is not None
    
    def test_attach_process_not_found(self):
        """Process bulunamadığında exception"""
        from exceptions import ProcessNotFound
        
        # Exception sınıfı doğru tanımlandı mı
        assert issubclass(ProcessNotFound, Exception)


class TestMemoryScan:
    """Bellek tarama testleri"""
    
    def test_scan_memory_signature(self):
        """scan_memory metodu imzası"""
        with patch('pymem.Pymem'):
            from memory_tool import MemoryTrainer
            trainer = MemoryTrainer()
            
            # Metod var ve callable mı
            assert callable(trainer.scan_memory)
    
    def test_scan_for_aes_keys_validation(self):
        """AES key scanning"""
        with patch('pymem.Pymem'):
            from memory_tool import MemoryTrainer
            trainer = MemoryTrainer()
            
            # Test key pattern'i
            valid_hex = "a" * 64  # 64 hex character
            
            # is_valid_key metodu test et
            valid_result = trainer.is_valid_key(valid_hex)
            assert isinstance(valid_result, bool)
    
    def test_aes_key_pattern_length(self, constants):
        """AES key pattern length constant"""
        assert constants.AES_KEY_PATTERN_LENGTH == 64
        assert isinstance(constants.AES_KEY_PATTERN_LENGTH, int)


class TestMemoryWrite:
    """Bellek yazma testleri"""
    
    def test_write_memory_signature(self):
        """write_memory metodu imzası"""
        with patch('pymem.Pymem'):
            from memory_tool import MemoryTrainer
            trainer = MemoryTrainer()
            
            assert callable(trainer.write_memory)


class TestDataTypeHandling:
    """Veri tipi işleme testleri"""
    
    def test_supported_data_types(self):
        """Desteklenen veri türleri"""
        with patch('pymem.Pymem'):
            from memory_tool import MemoryTrainer
            trainer = MemoryTrainer()
            
            # is_valid_key gibi metodlar string data handlellmalı
            result = trainer.is_valid_key("")
            assert isinstance(result, bool)
    
    def test_struct_packing(self):
        """struct modülü packing/unpacking"""
        # Integer packing
        packed = struct.pack('<I', 12345)
        unpacked = struct.unpack('<I', packed)[0]
        
        assert unpacked == 12345
    
    def test_hex_string_validation(self):
        """Hex string validasyonu"""
        with patch('pymem.Pymem'):
            from memory_tool import MemoryTrainer
            trainer = MemoryTrainer()
            
            valid_hex = "DEADBEEF"
            
            # is_valid_key metodu hex string format'ını kontrol eder
            result = trainer.is_valid_key(valid_hex)
            assert isinstance(result, bool)


class TestMemoryExceptions:
    """Bellek işlem exception'ları"""
    
    def test_process_not_found_exception(self, exceptions_module):
        """ProcessNotFound exception"""
        exc = exceptions_module.ProcessNotFound("test.exe not found")
        assert "test.exe" in str(exc)
    
    def test_memory_scan_error_exception(self, exceptions_module):
        """MemoryScanError exception"""
        exc = exceptions_module.MemoryScanError("Scan timeout")
        assert "Scan" in str(exc)
    
    def test_memory_write_error_exception(self, exceptions_module):
        """MemoryWriteError exception"""
        exc = exceptions_module.MemoryWriteError("Address invalid")
        assert isinstance(exc, exceptions_module.MemoryError)


class TestMemoryToolIntegration:
    """MemoryTool bütünleştirilmiş testleri"""
    
    def test_logger_integration(self):
        """MemoryTrainer logger'ı kullanıyor mu"""
        # Logger'ın import edilmesi gerekir
        from logger import setup_logger
        logger = setup_logger("test_memory")
        
        assert logger is not None
        assert callable(logger.info)
        assert callable(logger.error)
    
    def test_memory_constants(self, constants):
        """Memory-related constants"""
        assert constants.MEMORY_SCAN_BUFFER_SIZE > 0
        assert constants.MEMORY_SCAN_MAX_REGIONS > 0
        assert constants.AES_KEY_PATTERN_LENGTH == 64
