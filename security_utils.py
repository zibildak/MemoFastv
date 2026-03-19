"""
MEMOFAST - Security Utilities
Input validation, path safety, and credential protection
"""
import re
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from logger import setup_logger

logger = setup_logger(__name__)


class SecurityValidator:
    """Input validation and security checks"""
    
    # Dangerous patterns
    DANGEROUS_KEYWORDS = {
        '__import__', 'eval', 'exec', 'compile', '__code__',
        'open', 'os.system', 'subprocess', 'input', '__builtins__'
    }
    
    # Safe file extensions
    SAFE_GAME_EXTENSIONS = {
        '.txt', '.pak', '.uasset', '.uexp', '.ubulk', 
        '.zip', '.exe', '.dll', '.so', '.json', '.xml',
        '.csv', '.bin'
    }
    
    @staticmethod
    def validate_python_code(code: str) -> bool:
        """
        Check if Python code is safe to execute.
        
        Args:
            code: Python code string
            
        Returns:
            bool: True if safe, False otherwise
        """
        code_lower = code.lower()
        
        for keyword in SecurityValidator.DANGEROUS_KEYWORDS:
            if keyword in code_lower:
                logger.warning(f"Dangerous keyword detected: {keyword}")
                return False
        
        # Check for suspicious patterns
        suspicious_patterns = [
            r'os\.',
            r'sys\.',
            r'__[a-z]+__',
            r'globals\(',
            r'locals\(',
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, code_lower):
                logger.warning(f"Suspicious pattern detected: {pattern}")
                return False
        
        return True
    
    @staticmethod
    def safe_path_join(base: Path, relative: str) -> Path:
        """
        Safely join paths, prevent path traversal attacks.
        
        Args:
            base: Base directory (must be absolute)
            relative: Relative path from user input
            
        Returns:
            Path: Safe absolute path
            
        Raises:
            ValueError: If path traversal detected
        """
        base = Path(base).resolve()
        
        # Prevent absolute paths in relative
        if relative.startswith('/') or relative.startswith('\\'):
            raise ValueError(f"Absolute path not allowed: {relative}")
        
        # Remove null bytes
        if '\x00' in relative:
            raise ValueError("Null byte detected in path")
        
        # Join paths
        target = (base / relative).resolve()
        
        # Ensure target is within base directory
        try:
            target.relative_to(base)
        except ValueError:
            raise ValueError(
                f"Path traversal detected: {relative} resolves outside {base}"
            )
        
        return target
    
    @staticmethod
    def validate_file_size(file_path: Path, max_size_mb: int = 500) -> bool:
        """
        Check if file size is within limits.
        
        Args:
            file_path: Path to file
            max_size_mb: Maximum size in MB
            
        Returns:
            bool: True if valid size
            
        Raises:
            ValueError: If file too large or not found
        """
        max_bytes = max_size_mb * 1024 * 1024
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_size = file_path.stat().st_size
        
        if file_size > max_bytes:
            raise ValueError(
                f"File too large: {file_size/(1024*1024):.1f}MB "
                f"(max {max_size_mb}MB)"
            )
        
        return True
    
    @staticmethod
    def validate_file_extension(file_path: Path, allowed: set = None) -> bool:
        """
        Check if file has allowed extension.
        
        Args:
            file_path: Path to file
            allowed: Set of allowed extensions (with dot)
            
        Returns:
            bool: True if valid
            
        Raises:
            ValueError: If extension not allowed
        """
        if allowed is None:
            allowed = SecurityValidator.SAFE_GAME_EXTENSIONS
        
        extension = file_path.suffix.lower()
        
        if extension not in allowed:
            raise ValueError(
                f"Invalid file type: {extension} "
                f"(allowed: {', '.join(allowed)})"
            )
        
        return True
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Basic URL validation.
        
        Args:
            url: URL string
            
        Returns:
            bool: True if appears valid
        """
        if not url or not isinstance(url, str):
            return False
        
        # Must start with http/https or be relative
        if not (url.startswith('http://') or url.startswith('https://') or 
                url.startswith('.') or url.startswith('/')):
            return False
        
        # No control characters
        if any(ord(c) < 32 for c in url):
            return False
        
        return True


class CredentialSanitizer:
    """Remove sensitive data from logs and output"""
    
    # Patterns for sensitive data
    PATTERNS = [
        # API Keys
        (r'api[_-]?key["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', '***REDACTED_API_KEY***'),
        # Tokens
        (r'token["\']?\s*[:=]\s*["\']?Bearer\s+([^\s,}]+)', '***REDACTED_TOKEN***'),
        # Authorization headers
        (r'Authorization["\']?\s*[:=]\s*Bearer\s+([^\s,}]+)', '***REDACTED_AUTH***'),
        # Passwords
        (r'password["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', '***REDACTED_PASSWORD***'),
        # Path with user home
        (r'C:\\Users\\[^\\]+', '***USER_PATH_REDACTED***'),
        # Paths with sensitive dirs
        (r'/home/[^/]+', '***USER_PATH_REDACTED***'),
    ]
    
    @staticmethod
    def sanitize(text: str) -> str:
        """
        Remove sensitive data from text.
        
        Args:
            text: Text to sanitize
            
        Returns:
            str: Sanitized text
        """
        if not isinstance(text, str):
            return str(text)
        
        result = text
        for pattern, replacement in CredentialSanitizer.PATTERNS:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        
        return result
    
    @staticmethod
    def sanitize_dict(data: Dict) -> Dict:
        """
        Recursively sanitize dictionary (for logging).
        
        Args:
            data: Dictionary with potential sensitive data
            
        Returns:
            dict: Sanitized copy
        """
        if not isinstance(data, dict):
            return data
        
        result = {}
        sensitive_keys = {'api_key', 'token', 'password', 'secret', 'auth', 'apikey'}
        
        for key, value in data.items():
            if key.lower() in sensitive_keys:
                result[key] = '***REDACTED***'
            elif isinstance(value, dict):
                result[key] = CredentialSanitizer.sanitize_dict(value)
            elif isinstance(value, str):
                result[key] = CredentialSanitizer.sanitize(value)
            else:
                result[key] = value
        
        return result


class RateLimiter:
    """API rate limiting helper"""
    
    def __init__(self, calls_per_second: float = 1.0):
        """
        Initialize rate limiter.
        
        Args:
            calls_per_second: Maximum number of calls per second
        """
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second if calls_per_second > 0 else 0
        self.last_call_time = 0
    
    def wait_if_needed(self):
        """Sleep if necessary to maintain rate limit"""
        import time
        elapsed = time.time() - self.last_call_time
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self.last_call_time = time.time()
    
    def __enter__(self):
        """Context manager support"""
        self.wait_if_needed()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup"""
        pass


class FileOperationHelper:
    """Safe file operations with validation"""
    
    @staticmethod
    def safe_read(file_path: Path, max_size_mb: int = 500, 
                  binary: bool = True) -> Optional[bytes]:
        """
        Read file with validation.
        
        Args:
            file_path: Path to file
            max_size_mb: Maximum file size in MB
            binary: Read as binary or text
            
        Returns:
            bytes or str or None on error
        """
        try:
            # Validate
            SecurityValidator.validate_file_size(file_path, max_size_mb)
            
            if binary:
                return file_path.read_bytes()
            else:
                return file_path.read_text(encoding='utf-8')
        
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return None
    
    @staticmethod
    def safe_write(file_path: Path, content: Any, 
                   binary: bool = True, backup: bool = True) -> bool:
        """
        Write file safely (atomic).
        
        Args:
            file_path: Path to write to
            content: Data to write
            binary: Write as binary or text
            backup: Create .bak before overwriting
            
        Returns:
            bool: Success status
        """
        try:
            # Ensure directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create backup if file exists
            if backup and file_path.exists():
                backup_path = file_path.with_suffix(file_path.suffix + '.bak')
                file_path.replace(backup_path)
                logger.debug(f"Created backup: {backup_path}")
            
            # Atomic write (write to temp, then rename)
            temp_path = file_path.with_suffix(file_path.suffix + '.tmp')
            
            if binary:
                if isinstance(content, str):
                    content = content.encode('utf-8')
                temp_path.write_bytes(content)
            else:
                if not isinstance(content, str):
                    content = str(content)
                temp_path.write_text(content, encoding='utf-8')
            
            # Atomic rename (on same filesystem)
            temp_path.replace(file_path)
            logger.debug(f"Safely wrote: {file_path}")
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {e}")
            return False
