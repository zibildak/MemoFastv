"""
MEMOFAST - Merkezi Logging Sistemi
Tüm modüllerin log dosyalarını merkezi olarak yönetir.
"""
import logging
import sys
from pathlib import Path
from datetime import datetime


class LoggerManager:
    """Merkezi logger yöneticisi"""
    
    # Singleton pattern
    _instance = None
    _loggers = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.log_dir = Path(__file__).parent / ".logs"
        self.log_dir.mkdir(exist_ok=True)
        
        # Ana log dosyası
        self.main_log_file = self.log_dir / f"memofast_{datetime.now().strftime('%Y%m%d')}.log"
        
        self._initialized = True
    
    def get_logger(self, name, level=logging.INFO):
        """
        Belirli bir modül için logger döndür.
        
        Args:
            name: Logger adı (genelde __name__)
            level: Loglama seviyesi (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            
        Returns:
            logging.Logger: Yapılandırılmış logger
        """
        if name in self._loggers:
            return self._loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        # Console Handler (Kullanıcıya göster)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        
        # File Handler (Dosyaya yaz)
        file_handler = logging.FileHandler(self.main_log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        
        # Module-specific file handler (İsteğe bağlı)
        module_log_file = self.log_dir / f"{name}.log"
        module_handler = logging.FileHandler(module_log_file, encoding='utf-8')
        module_handler.setLevel(logging.DEBUG)
        module_handler.setFormatter(file_formatter)
        
        # Handler'ları ekle
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        logger.addHandler(module_handler)
        
        # Propagation'ı kapat (Duplicate logging önle)
        logger.propagate = False
        
        self._loggers[name] = logger
        return logger


# Global logger instance
_manager = LoggerManager()


def setup_logger(name, level=logging.INFO):
    """
    Hızlı logger kurulumu.
    
    Args:
        name: Logger adı (__name__ genelde)
        level: Loglama seviyesi
        
    Returns:
        logging.Logger: Yapılandırılmış logger
    """
    return _manager.get_logger(name, level)


# Sık kullanılan shortcut
def get_logger(name):
    """Logger al (kısayol)"""
    return _manager.get_logger(name)


# Logging seviyeleri
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL
