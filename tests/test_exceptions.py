"""
MEMOFAST - Exception Handling Testleri
Custom exception classes ve hiyerarşi testleri
"""
import pytest


class TestExceptionHierarchy:
    """Exception sınıf hiyerarşisinin testleri"""
    
    def test_memofast_exception_exists(self, exceptions_module):
        """MemoFastException base sınıfı var mı"""
        assert hasattr(exceptions_module, 'MemoFastException')
        base_exc = exceptions_module.MemoFastException
        assert issubclass(base_exc, Exception)
    
    def test_process_error_hierarchy(self, exceptions_module):
        """ProcessError ve alt sınıfları"""
        ProcessError = exceptions_module.ProcessError
        ProcessNotFound = exceptions_module.ProcessNotFound
        ProcessAlreadyAttached = exceptions_module.ProcessAlreadyAttached
        
        assert issubclass(ProcessError, exceptions_module.MemoFastException)
        assert issubclass(ProcessNotFound, ProcessError)
        assert issubclass(ProcessAlreadyAttached, ProcessError)
    
    def test_memory_error_hierarchy(self, exceptions_module):
        """MemoryError ve alt sınıfları"""
        MemoryError = exceptions_module.MemoryError
        MemoryScanError = exceptions_module.MemoryScanError
        MemoryReadError = exceptions_module.MemoryReadError
        MemoryWriteError = exceptions_module.MemoryWriteError
        
        assert issubclass(MemoryError, exceptions_module.MemoFastException)
        assert issubclass(MemoryScanError, MemoryError)
        assert issubclass(MemoryReadError, MemoryError)
        assert issubclass(MemoryWriteError, MemoryError)
    
    def test_scanner_error_hierarchy(self, exceptions_module):
        """ScannerError ve alt sınıfları"""
        ScannerError = exceptions_module.ScannerError
        GameNotFound = exceptions_module.GameNotFound
        TargetFileNotFound = exceptions_module.TargetFileNotFound
        
        assert issubclass(ScannerError, exceptions_module.MemoFastException)
        assert issubclass(GameNotFound, ScannerError)
        assert issubclass(TargetFileNotFound, ScannerError)
    
    def test_api_error_hierarchy(self, exceptions_module):
        """APIError ve alt sınıfları"""
        APIError = exceptions_module.APIError
        APITimeoutError = exceptions_module.APITimeoutError
        APIAuthenticationError = exceptions_module.APIAuthenticationError
        APIRateLimitError = exceptions_module.APIRateLimitError
        
        assert issubclass(APIError, exceptions_module.MemoFastException)
        assert issubclass(APITimeoutError, APIError)
        assert issubclass(APIAuthenticationError, APIError)
        assert issubclass(APIRateLimitError, APIError)
    
    def test_file_operation_error_hierarchy(self, exceptions_module):
        """FileOperationError ve alt sınıfları"""
        FileOperationError = exceptions_module.FileOperationError
        FileNotFound = exceptions_module.FileNotFound
        FileReadError = exceptions_module.FileReadError
        FileWriteError = exceptions_module.FileWriteError
        
        assert issubclass(FileOperationError, exceptions_module.MemoFastException)
        assert issubclass(FileNotFound, FileOperationError)
        assert issubclass(FileReadError, FileOperationError)
        assert issubclass(FileWriteError, FileOperationError)
    
    def test_translation_error_hierarchy(self, exceptions_module):
        """TranslationError ve alt sınıfları"""
        TranslationError = exceptions_module.TranslationError
        TranslatorManagerError = exceptions_module.TranslatorManagerError
        
        assert issubclass(TranslationError, exceptions_module.MemoFastException)
        assert issubclass(TranslatorManagerError, TranslationError)
    
    def test_configuration_error_hierarchy(self, exceptions_module):
        """ConfigurationError ve alt sınıfları"""
        ConfigurationError = exceptions_module.ConfigurationError
        InvalidConfigError = exceptions_module.InvalidConfigError
        MissingConfigError = exceptions_module.MissingConfigError
        
        assert issubclass(ConfigurationError, exceptions_module.MemoFastException)
        assert issubclass(InvalidConfigError, ConfigurationError)
        assert issubclass(MissingConfigError, ConfigurationError)


class TestExceptionCreation:
    """Exception nesnelerinin oluşturulması ve mesajları"""
    
    def test_exception_with_message(self, exceptions_module):
        """Exception mesajı tutabiliyor mu"""
        exc = exceptions_module.ProcessNotFound("Test process not found")
        assert str(exc) == "Test process not found"
    
    def test_exception_isinstance_checks(self, exceptions_module):
        """isinstance kontrolleri çalışıyor mu"""
        exc = exceptions_module.MemoryScanError("Scan failed")
        
        assert isinstance(exc, exceptions_module.MemoryError)
        assert isinstance(exc, exceptions_module.MemoFastException)
        assert isinstance(exc, Exception)
    
    def test_catching_parent_exception(self, exceptions_module):
        """Parent exception ile alt sınıfları yakalamak"""
        ProcessNotFound = exceptions_module.ProcessNotFound
        ProcessError = exceptions_module.ProcessError
        
        with pytest.raises(ProcessError):
            raise ProcessNotFound("Process not found")
    
    def test_catching_root_exception(self, exceptions_module):
        """Root MemoFastException ile tüm exceptions'ı yakalamak"""
        MemoFastException = exceptions_module.MemoFastException
        
        exceptions_to_test = [
            exceptions_module.ProcessNotFound("Test"),
            exceptions_module.MemoryScanError("Test"),
            exceptions_module.GameNotFound("Test"),
            exceptions_module.APITimeoutError("Test"),
            exceptions_module.FileReadError("Test"),
        ]
        
        for exc in exceptions_to_test:
            with pytest.raises(MemoFastException):
                raise exc
