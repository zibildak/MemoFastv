"""
MEMOFAST - Konfigürasyon ve Yardımcı Fonksiyonlar
"""
import sys
from pathlib import Path


class Constants:
    """Uygulamadaki sabit değerler (Magic Numbers)"""
    
    # Timeout'lar (saniye)
    PROCESS_TIMEOUT = 60
    NETWORK_TIMEOUT = 10
    SCANNER_TIMEOUT = 300
    DEEPL_TIMEOUT = 10
    GOOGLE_TIMEOUT = 15
    GEMINI_TIMEOUT = 30
    SUBPROCESS_TIMEOUT = 60  # Subprocess execution timeout
    
    # Thread/Worker
    MAX_WORKERS = 50
    MAX_RETRIES = 3
    
    # Scanner
    CACHE_TTL = 3600  # 1 saat
    SCAN_BATCH_SIZE = 100
    EXCLUDED_FOLDERS = [
        "Windows", "Program Files", "System32", 
        "ProgramData", "AppData", ".cache",
        "System Volume Information", "Recovery",
        "$Recycle.Bin", "pagefile.sys"
    ]
    
    # OCR
    OCR_CONFIDENCE_THRESHOLD = 0.7
    OCR_LANG_DEFAULT = "eng"
    
    # Çeviri
    TRANSLATION_SPEED_MIN = 5
    TRANSLATION_SPEED_MAX = 100
    TRANSLATION_SPEED_DEFAULT = 15
    
    # UI
    UI_THEME_COLOR = "#8b5cf6"
    UI_WINDOW_WIDTH = 1200
    UI_WINDOW_HEIGHT = 800
    UI_SCALE_DEFAULT = 100 # Yüzde
    UI_FONT_SIZE_DEFAULT = 10 # Manuel punto
    
    # API
    MAX_API_RETRIES = 3
    API_RATE_LIMIT_DELAY = 0.5  # saniye
    
    # Memory Scanning
    AES_KEY_PATTERN_LENGTH = 64  # Hex karakteri
    MEMORY_SCAN_BUFFER_SIZE = 1024 * 1024 * 10  # 10MB
    MEMORY_SCAN_MAX_REGIONS = 10000
    MEMORY_SCAN_MAX_RESULTS = 100000  # Maksimum tarama sonucu
    MEMORY_SCAN_MAX_SYSTEM_PERCENT = 80  # Maksimum sistem belleği %'si
    MEMORY_SCAN_MAX_PROCESS_MB = 2048  # Tek process'te maksimum tarama (MB)
    
    # File Operations
    BACKUP_SUFFIX = ".bak"
    MAX_FILE_SIZE = 1024 * 1024 * 500  # 500MB
    
    # Cache
    CACHE_CLEANUP_INTERVAL = 86400  # 24 saat


class Config:
    """Uygulama ayarları"""
    
    # [YENİ] PyInstaller Uyumluluğu
    if getattr(sys, 'frozen', False):
        BASE_PATH = Path(sys.executable).parent
    else:
        BASE_PATH = Path(__file__).parent

    GAME_PATH = BASE_PATH / "game"
    CACHE_PATH = BASE_PATH / ".cache"
    
    # YouTube kanalı
    YOUTUBE_URL = "https://www.youtube.com/@MehmetariTv"
    
    # Platform ikonları
    PLATFORM_ICONS = {
        'steam': '🎮',
        'epic': '🎯',
        'custom': '🚀',
        'manual': '📁'
    }

    # Güncelleme URL (Google Drive JSON)
    UPDATE_URL = "https://drive.google.com/file/d/1gF4XEFQ0s-19myUsEYwWoz0iuVR7Jd0t/view?usp=sharing"
    VERSION = "1.1.2" # Mevcut versiyonu burada tutalım
    THEME_COLOR = "#00aaff" # Varsayılan tema rengi

    @staticmethod
    def get_gemini_key():
        """Settings.json'dan Gemini/DeepL API Key'i oku"""
        try:
            import json
            settings_file = Config.BASE_PATH / "settings.json"
            if settings_file.exists():
                with open(settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Hem deepl hem gemini key'lerine bak (legacy support)
                    return data.get("deepl_api_key", "") or data.get("gemini_api_key", "")
        except:
            pass
        return ""
    
    # Platform isimleri
    PLATFORM_NAMES = {
        'steam': 'Steam',
        'epic': 'Epic Games',
        'custom': 'Özel Launcher',
        'manual': 'Manuel Klasör Seç'
    }

    # Çeviri Ayarları
    DEEPL_API_KEY = ""
    TRANSLATOR_SERVICE = "google" # 'google' veya 'deepl'
    
    @staticmethod
    def init():
        """Gerekli klasörleri oluştur"""
        Config.CACHE_PATH.mkdir(exist_ok=True)
    
    @staticmethod
    def get_game_info(game_folder):
        """Oyun bilgilerini al"""
        game_path = Config.GAME_PATH / game_folder
        info_file = game_path / "info.txt"
        
        info = {
            'name': game_folder,
            'description': '',
            'cover': ''
        }
        
        # info.txt'den oku
        if info_file.exists():
            try:
                with open(info_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if '=' in line:
                            key, value = line.split('=', 1)
                            if key == 'name':
                                info['name'] = value
                            elif key == 'description':
                                info['description'] = value
            except:
                pass
        
        # Kapak resmini bul
        cover_path = game_path / "assets" / "cover.png"
        if not cover_path.exists():
            cover_path = game_path / "assets" / "cover.jpg"
        
        if cover_path.exists():
            info['cover'] = str(cover_path)
        
        return info
    
    @staticmethod
    def get_all_games():
        """Tüm oyunları listele"""
        if not Config.GAME_PATH.exists():
            return []
        
        games = []
        for game_folder in Config.GAME_PATH.iterdir():
            if game_folder.is_dir():
                info = Config.get_game_info(game_folder.name)
                games.append({
                    'folder': game_folder.name,
                    'name': info['name'],
                    'description': info['description'],
                    'cover': info['cover']
                })
        
        return games
