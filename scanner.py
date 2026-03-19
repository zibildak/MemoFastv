"""
MEMOFAST - Platform Tarama Modülü
Sistemdeki oyun kurulumlarını bulur (Steam, Epic, Custom Launcher)
"""
import os
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from config import Config, Constants
from logger import setup_logger

logger = setup_logger(__name__)

class SmartCache:
    """Smart cache with TTL and validation"""
    
    def __init__(self, cache_dir: Path, ttl: int = 3600):
        self.cache_dir = cache_dir
        self.ttl = ttl
        self.cache_dir.mkdir(exist_ok=True)
    
    def _get_cache_file(self, key: str) -> Path:
        """Get cache file path for key"""
        return self.cache_dir / f"{hashlib.md5(key.encode()).hexdigest()}.cache"
    
    def get(self, key: str) -> Optional[Dict]:
        """Retrieve from cache"""
        cache_file = self._get_cache_file(key)
        
        if not cache_file.exists():
            return None
        
        try:
            # Check TTL
            cache_age = time.time() - cache_file.stat().st_mtime
            if cache_age > self.ttl:
                cache_file.unlink()  # Delete stale cache
                logger.debug(f"Cache expired ({cache_age:.0f}s): {key}")
                return None
            
            data = json.loads(cache_file.read_text(encoding='utf-8'))
            logger.debug(f"Cache hit ({cache_age:.0f}s old): {key}")
            return data
        
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
            try:
                cache_file.unlink()  # Remove corrupted cache
            except:
                pass
            return None
    
    def set(self, key: str, value: Dict) -> bool:
        """Store in cache (atomic write)"""
        cache_file = self._get_cache_file(key)
        temp_file = cache_file.with_suffix('.tmp')
        
        try:
            # Atomic write (prevent partial corruption)
            temp_file.write_text(json.dumps(value), encoding='utf-8')
            temp_file.replace(cache_file)
            logger.debug(f"Cache set: {key}")
            return True
        
        except Exception as e:
            logger.error(f"Cache write error: {e}")
            try:
                temp_file.unlink()
            except:
                pass
            return False
    
    def invalidate(self, key: str) -> bool:
        """Manually invalidate cache entry"""
        cache_file = self._get_cache_file(key)
        try:
            if cache_file.exists():
                cache_file.unlink()
            return True
        except Exception as e:
            logger.error(f"Cache invalidate error: {e}")
            return False

class PlatformScanner:
    """
    Platform tarayıcısı - sistemdeki oyun kurulumlarını bulur.
    
    Özellikleri:
    - Steam, Epic Games, Custom Launcher desteği
    - Multi-disk tarama
    - Smart cache sistemi (TTL ile)
    - Hızlı ve güvenilir arama
    """
    
    def __init__(self) -> None:
        """PlatformScanner'ı başlat"""
        self.cache_path: Path = Config.CACHE_PATH
        self.cache: SmartCache = SmartCache(self.cache_path, ttl=Constants.CACHE_TTL)
    
    def scan_for_game(self, game_folder: str, target_file: str) -> Dict[str, List[str]]:
        """
        Belirli bir oyun dosyasını tüm disklerde tara.
        
        Arar:
        - Steam kurulumları
        - Epic Games kurulumları
        - Diğer özel launcher kurulumları
        
        Args:
            game_folder: Oyun klasör adı (örn: 'wwm', 'game')
            target_file: Aranacak dosya (örn: 'game.pak', 'game.exe')
        
        Returns:
            dict: {
                'steam': ['/path/to/file1', ...],
                'epic': ['/path/to/file2', ...],
                'custom': ['/path/to/file3', ...]
            }
            
        Note:
            Sonuç cache'lenir ve TTL boyunca kullanılır (Constants.CACHE_TTL)
        """
        # Cache kontrol (SmartCache ile)
        cache_key = f"{game_folder}:{target_file}"
        cached_result = self.cache.get(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Tarama yap
        results = {
            'steam': [],
            'epic': [],
            'custom': []
        }
        
        # Tüm diskleri tara
        for drive in self._get_available_drives():
            logger.info(f"Taranıyor: {drive}")
            
            # Steam konumları
            steam_paths = [
                Path(drive) / "Program Files (x86)" / "Steam" / "steamapps" / "common",
                Path(drive) / "Program Files" / "Steam" / "steamapps" / "common",
                Path(drive) / "Steam" / "steamapps" / "common",
                Path(drive) / "SteamLibrary" / "steamapps" / "common",
            ]
            
            for steam_path in steam_paths:
                if steam_path.exists():
                    found_files = self._search_files(steam_path, target_file)
                    results['steam'].extend(found_files)
            
            # Epic Games konumları
            epic_paths = [
                Path(drive) / "Program Files" / "Epic Games",
                Path(drive) / "Epic Games",
            ]
            
            for epic_path in epic_paths:
                if epic_path.exists():
                    found_files = self._search_files(epic_path, target_file)
                    results['epic'].extend(found_files)
            
            # Diğer konumlar (özel launcher'lar)
            # Dışlanan klasörleri kullan (Constants.EXCLUDED_FOLDERS)
            root_folders = []
            try:
                root_folders = [f for f in Path(drive).iterdir() if f.is_dir()]
            except:
                pass
            
            for folder in root_folders:
                # Constants.EXCLUDED_FOLDERS'da kontrol
                if any(excluded.upper() in folder.name.upper() for excluded in Constants.EXCLUDED_FOLDERS):
                    logger.debug(f"Dışlanan klasör atlandı: {folder}")
                    continue
                
                # Steam ve Epic'te bulunanları atlama
                found_files = self._search_files(folder, target_file, max_depth=Constants.SCAN_BATCH_SIZE)
                
                # Steam veya Epic'te zaten bulunanları çıkar
                for file_path in found_files:
                    if not any(str(file_path) in str(x) for x in results['steam'] + results['epic']):
                        results['custom'].append(file_path)
        
        
        # Cache'e kaydet (SmartCache ile atomic write)
        try:
            cache_data = {
                'steam': [str(p) for p in results['steam']],
                'epic': [str(p) for p in results['epic']],
                'custom': [str(p) for p in results['custom']]
            }
            self.cache.set(cache_key, cache_data)
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")
        
        return results
    
    def get_cached_results(self, game_folder):
        """
        Belirli bir oyun için cache'den sonuçları al.
        
        Args:
            game_folder: Oyun klasör adı
            
        Returns:
            dict: Cache'den okunan sonuçlar, yoksa None
        """
        cache_file = self.cache_path / f"{game_folder}_scan.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        'steam': [Path(p) for p in data.get('steam', [])],
                        'epic': [Path(p) for p in data.get('epic', [])],
                        'custom': [Path(p) for p in data.get('custom', [])]
                    }
            except:
                pass
        return None
    
    def clear_cache(self, game_folder=None):
        """
        Cache'i temizle.
        
        Args:
            game_folder: Temizlenecek oyun adı (None ise tüm cache temizlenir)
        """
        if game_folder:
            cache_file = self.cache_path / f"{game_folder}_scan.json"
            if cache_file.exists():
                cache_file.unlink()
        else:
            # Tüm cache'i temizle
            for cache_file in self.cache_path.glob("*_scan.json"):
                cache_file.unlink()
    
    def _get_available_drives(self):
        """
        Sistemdeki mevcut diskleri al.
        
        Returns:
            list: Disk harfleri (C:, D:, vb.)
        """
        drives = []
        for letter in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                drives.append(drive)
        return drives
    
    def _search_files(self, root_path, filename, max_depth=5):
        """
        Belirli bir dosyayı klasörde ara (derinlik sınırlı, dışlama yapılır).
        
        Args:
            root_path: Arama kökü (Path objesi)
            filename: Aranacak dosya adı (case-insensitive)
            max_depth: Maksimum arama derinliği (default 5, Constants.SCAN_BATCH_SIZE'dan gelebilir)
            
        Returns:
            list: Bulunan dosyaların Path listesi
            
        Note:
            Constants.EXCLUDED_FOLDERS'daki klasörler otomatik olarak atlanır
        """
        found = []
        
        def _search_recursive(path, depth=0):
            if depth > max_depth:
                return
            
            try:
                for item in path.iterdir():
                    # Dışlanan klasörleri atla
                    if item.is_dir() and any(excluded.upper() in item.name.upper() for excluded in Constants.EXCLUDED_FOLDERS):
                        logger.debug(f"Dışlanan klasör: {item}")
                        continue
                    
                    if item.is_file() and item.name.lower() == filename.lower():
                        found.append(item)
                    elif item.is_dir():
                        _search_recursive(item, depth + 1)
            except (PermissionError, OSError) as e:
                logger.debug(f"Klasör erişim hatası: {path} - {e}")
        
        _search_recursive(root_path)
        return found
    
    def get_target_file(self, game_folder):
        """
        Oyun için aranacak hedef dosyayı belirle.
        
        Args:
            game_folder: Oyun klasör adı
            
        Returns:
            str: Aranacak dosya adı (örn: 'game.pak')
        """
        game_path = Config.GAME_PATH / game_folder / "new"
        
        if game_path.exists():
            files = list(game_path.glob("*"))
            if files:
                return files[0].name
        
        return None


def test_scanner():
    """Test fonksiyonu"""
    scanner = PlatformScanner()
    
    # WWM için tara
    target_file = scanner.get_target_file('wwm')
    if target_file:
        print(f"Aranacak dosya: {target_file}")
        results = scanner.scan_for_game('wwm', target_file)
        
        print(f"\nSteam: {len(results['steam'])} adet")
        print(f"Epic: {len(results['epic'])} adet")
        print(f"Custom: {len(results['custom'])} adet")
    else:
        print("Hedef dosya bulunamadı!")

class GameEngineScanner:
    """Oyun Motoru Tarayıcısı (Unity & Unreal)"""
    
    def __init__(self):
        self.found_games = []
        self.cache_path = Config.CACHE_PATH / "games_cache.json"

    def load_cache(self):
        """Cache'den oyun listesini yükle"""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Deduplicate while loading just in case
                    return self._deduplicate_games(data)
            except:
                pass
        return []

    def save_cache(self, games):
        """Sonuçları cache'e kaydet"""
        try:
            # Önce deduplicate yap
            unique_games = self._deduplicate_games(games)
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(unique_games, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Cache save error: {e}")

    def _deduplicate_games(self, games):
        """
        Aynı oyunları filtrele (Gelişmiş).
        Öncelik Sırası:
        1. EXE Yolu (Aynı dosya)
        2. Klasör Yolu (Aynı klasör)
        3. Exe Adı veya Oyun Adı Benzerliği
        """
        import os
        
        # Helper: Path Normalizasyonu
        def norm(p):
            if not p: return ""
            return os.path.normpath(str(p)).lower().strip()

        # Score Fonksiyonu (Gelişmiş)
        def score(item):
            s = 0
            # 1. Platform Puanı
            platform = item.get('platform', '').lower()
            if 'steam' in platform: s += 50
            elif 'epic' in platform: s += 40
            elif 'manuel' in platform: s += 45 # Manuel eklenenler değerlidir
            else: s += 10 # Diğer / Bilinmiyor
            
            # 2. EXE Kalite Puanı
            exe_path = norm(item.get('exe', ''))
            
            if exe_path:
                if os.path.exists(item['exe']):
                    s += 20
                
                # Unreal / Unity Standartları
                if "shipping" in exe_path: s += 15 # Kesinlikle oyunun kendisi
                if "binaries" in exe_path: s += 10 # Doğru klasör yapısı
                if "launcher" in exe_path: s -= 5  # Launcher istemiyoruz genelde
                if "crash" in exe_path: s -= 20    # CrashReporter kesinlikle değil
                
            # 3. İsim Puanı
            # Metadata ismi klasörden farklıysa (yani appmanifest vb. okunmuşsa)
            if item.get('name') != os.path.basename(item.get('path', '')):
                s += 5
                
            return s

        # 1. Aşama: EXE Yoluna Göre Birleştir (Kesin Eşleşme)
        unique_by_exe = {}
        
        for g in games:
            exe_key = norm(g.get('exe', ''))
            path_key = norm(g.get('path', ''))
            
            # Anahtar Exe ise Exe, yoksa Path
            primary_key = exe_key if exe_key else path_key
            if not primary_key: continue
            
            if primary_key in unique_by_exe:
                if score(g) > score(unique_by_exe[primary_key]):
                    unique_by_exe[primary_key] = g
            else:
                unique_by_exe[primary_key] = g
                
        # 2. Aşama: Klasör Yoluna Göre Birleştir
        # Aynı klasörde birden fazla exe bulunduysa (örn: Launcher.exe ve Game.exe)
        # En yüksek puanlı olanı (Shipping) seç.
        unique_by_folder = {}
        
        for g in unique_by_exe.values():
            folder_key = norm(g.get('path', ''))
            if not folder_key:
                # Klasör yoksa (nasıl olur?) direkt ekle veya exe'nin dir'ini al
                exe = g.get('exe')
                if exe: folder_key = norm(os.path.dirname(exe))
                else: continue
            
            if folder_key in unique_by_folder:
                # Puanı yüksek olan kazanır
                if score(g) > score(unique_by_folder[folder_key]):
                    unique_by_folder[folder_key] = g
            else:
                unique_by_folder[folder_key] = g
                
        # 3. Aşama: İsim Dedup (Opsiyonel ama riskli olabilir, kapalı tutalım veya çok sıkı yapalım)
        # Farklı klasörlerde aynı isimli oyun olabilir (örn: Biri Steam, biri Epic)
        # Kullanıcı ikisini de görmek isteyebilir. O yüzden isim dedup'ı KALDIRIYORUM.
        # Kullanıcı "C:\Steam\Game" ve "D:\Epic\Game" varsa ikisini de seçebilsin.
        # Ancak "Game" ve "Game " gibi aynı path ama farklı string ise zaten norm() ile folder'da yakalandı.
        
        return list(unique_by_folder.values())
    


    def _get_steam_libraries_from_vdf(self, base_steam_path):
        """Steam ana klasöründeki libraryfolders.vdf dosyasını okur"""
        libraries = []
        vdf_path = Path(base_steam_path) / "steamapps" / "libraryfolders.vdf"
        if vdf_path.exists():
            try:
                import re
                with open(vdf_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Regex ile path'leri çek ("path" "C:\\Program Files...")
                    matches = re.finditer(r'"path"\s+"([^"]+)"', content, re.IGNORECASE)
                    for match in matches:
                        path_str = match.group(1).replace("\\\\", "\\")
                        if os.path.exists(path_str):
                            libraries.append(str(Path(path_str) / "steamapps" / "common"))
            except:
                pass
        return libraries

    def get_library_paths(self):
        """Registry ve varsayılan yollardan kütüphane yollarını bul"""
        paths = set()
        
        # 1. Registry (Windows) - Ana Steam Yolu ve VDF Okuma
        main_steam_path = None
        try:
            import winreg
            try:
                hkey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\Valve\\Steam")
                main_steam_path = winreg.QueryValueEx(hkey, "SteamPath")[0]
                # Registry path bazen / kullanır, düzeltelim
                main_steam_path = str(Path(main_steam_path))
                
                paths.add(str(Path(main_steam_path) / "steamapps" / "common"))
                
                # VDF'den diğer kütüphaneleri oku
                vdf_libs = self._get_steam_libraries_from_vdf(main_steam_path)
                for lib in vdf_libs:
                    paths.add(str(lib))
                    
            except: pass
        except ImportError:
            pass

        # 2. Varsayılan Paths (Fallback)
        drives = [f"{d}:\\" for d in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{d}:\\")]
        for drive in drives:
            # Common Steam Paths (Registry bulamazsa diye)
            paths.add(str(Path(drive) / "Program Files (x86)" / "Steam" / "steamapps" / "common"))
            paths.add(str(Path(drive) / "Steam" / "steamapps" / "common")) # [YENİ] Klasik Steam yolu
            paths.add(str(Path(drive) / "SteamLibrary" / "steamapps" / "common"))
            # Common Epic Paths
            paths.add(str(Path(drive) / "Program Files" / "Epic Games"))
            paths.add(str(Path(drive) / "Epic Games"))
            # [YENİ] Genel Oyun Klasörleri
            paths.add(str(Path(drive) / "Games"))
            paths.add(str(Path(drive) / "Oyunlar"))
            paths.add(str(Path(drive) / "My Games"))

        return [p for p in paths if os.path.exists(p)]

    def _scan_epic_manifests(self):
        """Epic Games Manifest dosyalarını tara (ProgramData)"""
        epic_games = []
        try:
            # ProgramData içindeki Epic manifestleri
            prog_data = os.environ.get('ProgramData')
            if not prog_data:
                prog_data = "C:\\ProgramData"
            
            manifests_path = Path(prog_data) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
            if manifests_path.exists():
                for item_file in manifests_path.glob("*.item"):
                    try:
                        with open(item_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            
                        install_loc = data.get("InstallLocation")
                        display_name = data.get("DisplayName")
                        app_name = data.get("AppName")
                        
                        if install_loc and os.path.exists(install_loc):
                            epic_games.append({
                                'path': Path(install_loc),
                                'name': display_name,
                                'appid': app_name,
                                'platform': 'Epic Games'
                            })
                    except: pass
        except: pass
        return epic_games

    def _scan_gog(self):
        """GOG Galaxy kayıt defteri girişlerini tarar."""
        gog_games = []
        try:
            import winreg
            hkey = winreg.HKEY_LOCAL_MACHINE
            reg_path = r"SOFTWARE\WOW6432Node\GOG.com\Games"
            try:
                with winreg.OpenKey(hkey, reg_path) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            try:
                                name = winreg.QueryValueEx(subkey, "gameName")[0]
                                install_path = winreg.QueryValueEx(subkey, "path")[0]
                                if install_path and os.path.exists(install_path):
                                    gog_games.append({
                                        'path': Path(install_path),
                                        'name': name,
                                        'platform': 'GOG'
                                    })
                            except: continue
            except: pass
        except: pass
        return gog_games

    def _scan_xbox(self):
        """Xbox/UWP oyunlarını PowerShell üzerinden sorgular."""
        xbox_games = []
        try:
            import subprocess
            # Sadece Store uygulamalarını getir
            cmd = 'Get-AppxPackage | Where-Object { $_.SignatureKind -eq "Store" } | Select-Object Name, InstallLocation'
            proc = subprocess.Popen(['powershell', '-Command', cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=0x08000000)
            stdout, _ = proc.communicate()
            
            output_lines = stdout.splitlines()
            current_game = {}
            for line in output_lines:
                if "Name" in line and ":" in line:
                    current_game["name"] = line.split(":", 1)[1].strip()
                elif "InstallLocation" in line and ":" in line:
                    current_game["path_str"] = line.split(":", 1)[1].strip()
                    if current_game.get("name") and current_game.get("path_str"):
                        if os.path.exists(current_game["path_str"]):
                            if "WindowsApps" in current_game["path_str"] or "Xbox" in current_game["name"].lower():
                                xbox_games.append({
                                    'path': Path(current_game["path_str"]),
                                    'name': current_game["name"],
                                    'platform': 'Xbox / MS Store'
                                })
                        current_game = {}
        except: pass
        return xbox_games

    def _scan_ubisoft_ea(self):
        """Ubisoft ve EA App kayıt defteri girişlerini tarar."""
        other_games = []
        import winreg
        # Ubisoft
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs") as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    game_id = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, game_id) as subkey:
                        try:
                            install_path = winreg.QueryValueEx(subkey, "InstallDir")[0]
                            if install_path and os.path.exists(install_path):
                                other_games.append({
                                    'path': Path(install_path),
                                    'name': Path(install_path).name,
                                    'platform': 'Ubisoft Connect'
                                })
                        except: continue
        except: pass

        # EA App
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Electronic Arts\EA Desktop\Games") as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    game_id = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, game_id) as subkey:
                        try:
                            install_path = winreg.QueryValueEx(subkey, "install_dir")[0]
                            if install_path and os.path.exists(install_path):
                                other_games.append({
                                    'path': Path(install_path),
                                    'name': Path(install_path).name,
                                    'platform': 'EA App'
                                })
                        except: continue
        except: pass
        return other_games

    def _scan_registry_general(self):
        """Genel Uninstall kayıtlarını tarar ve oyunları filtreler."""
        reg_games = []
        try:
            import winreg
            reg_paths = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
            ]

            # Oyun belirteçleri (Daha spesifik)
            game_keywords = ["game", "playstation", "simulation", "simulator", "remastered", "edition", "trilogy", "bundle", "steam", "gog", "riot games", "rockstar games"]
            
            # Kesinlikle oyun olmayan kelimeler
            excluded_keywords = [
                "driver", "nvidia", "intel", "amd", "realtek", "microsoft", "office", "adobe", "google",
                "c++", "runtime", "software", "utility", "update", "service", "cleaner", "tweak", "optimizer",
                "browser", "chrome", "firefox", "vlc", "spotify", "discord", "zoom", "teams", "winrar", "7-zip",
                "python", "node.js", "java", "visual studio", "sdk", "framework", "antivirus", "malware",
                "cheat engine", "shadowplay", "overlay", "recorder", "bench", "redist", "kb\d+", "security"
            ]
            
            for hkey, reg_path in reg_paths:
                try:
                    with winreg.OpenKey(hkey, reg_path) as key:
                        for i in range(winreg.QueryInfoKey(key)[0]):
                            try:
                                subkey_name = winreg.EnumKey(key, i)
                                with winreg.OpenKey(key, subkey_name) as subkey:
                                    try:
                                        name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                        install_path = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                                        
                                        if name and install_path and os.path.exists(install_path):
                                            name_low = name.lower()
                                            
                                            # 1. Önce yasaklı kelime kontrolü
                                            if any(kw in name_low for kw in excluded_keywords):
                                                continue
                                                
                                            # 2. Oyun anahtar kelime kontrolü
                                            # Not: Play kelimesini Playstation veya tek başına 'game' olarak kısıtladık
                                            if any(kw in name_low for kw in game_keywords) or "games" in name_low:
                                                reg_games.append({
                                                    'path': Path(install_path),
                                                    'name': name,
                                                    'platform': 'Registry / Diğer'
                                                })
                                    except: continue
                            except: continue
                except: continue
        except: pass
        return reg_games

    def scan(self, callback=None):
        """Oyunları tara"""
        self.found_games = []
        
        # 1. PLATFORM MANIFEST TARAMALARI (Hızlı ve Kesin)
        manifest_sources = [
            ("Epic Games", self._scan_epic_manifests),
            ("GOG", self._scan_gog),
            ("Xbox / MS Store", self._scan_xbox),
            ("Ubisoft / EA", self._scan_ubisoft_ea),
            ("Registry", self._scan_registry_general)
        ]

        for platform_name, scan_func in manifest_sources:
            if callback: callback(f"{platform_name} kütüphanesi taranıyor...")
            try:
                results = scan_func()
                for game in results:
                    game_info = self._analyze_game_folder(
                        game['path'], 
                        platform=game.get('platform', platform_name),
                        metadata={'name': game.get('name'), 'appid': game.get('appid')}
                    )
                    
                    if game_info:
                        if not any(g['path'] == game_info['path'] for g in self.found_games):
                            self.found_games.append(game_info)
            except Exception as e:
                logger.error(f"{platform_name} tarama hatası: {e}")

            
        # 2. STANDART TARAMA (Steam + Diğer)
        library_paths = self.get_library_paths()
        
        # Disk köklerini de ekle (Özel kurulumlar için: C:/Games vb.)
        # Ancak Program Files zaten eklendi, onları tekrar eklemeyelim.
        # Sadece kök dizinleri tarayacağız (örn: D:/Oyunlar için D:/ library olur)
        drives = [f"{d}:\\" for d in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{d}:\\")]
        for drive in drives:
            library_paths.append(drive)

        # Tekrarları önle
        library_paths = list(set([str(p) for p in library_paths]))
        
        total_paths = len(library_paths)
        excluded_folders = ["Windows", "Boot", "System Volume Information", "$RECYCLE.BIN", "ProgramData", "Config.Msi", "Recovery"]
        # Program Files zaten library olarak eklendiyse, kök taramasında onları atlayalım ki çift tarama olmasın
        # Ama library_paths içinde C:/ olan da var, C:/Program Files da var.
        # Scan döngüsünde kontrol edeceğiz.

        for i, lib_path in enumerate(library_paths):
            if callback:
                callback(f"Taranıyor: {lib_path}")
            
            # Platform belirleme
            path_str = str(lib_path).lower()
            if "steam" in path_str:
                platform = "Steam"
            elif "epic" in path_str: # Manifest dışı Epic klasörleri
                platform = "Epic Games"
            else:
                platform = "Diğer"

            try:
                # Kütüphane içindeki klasörleri gez
                lib_p = Path(lib_path)
                if not lib_p.exists(): continue
                
                for item in lib_p.iterdir():
                    if item.is_dir():
                        # Sistem klasörlerini atla
                        if item.name in excluded_folders or item.name.startswith('.'):
                            continue
                        # Kullanıcı klasörünü atla (Çok uzun sürer)
                        if item.name == "Users":
                            continue

                        # Eğer bu klasör zaten bir kütüphane yolu ise, içeriğini ayrıca tarayacağız,
                        # burada analyze etmeye gerek yok (Örn: C:/ -> C:/Program Files)
                        is_library = False
                        for lp in library_paths:
                            if str(item).lower() == str(lp).lower():
                                is_library = True
                                break
                        if is_library:
                            continue

                        game_info = self._analyze_game_folder(item, platform)
                        if game_info:
                            # Tekrar kontrolü (Path'e göre)
                            if not any(g['path'] == game_info['path'] for g in self.found_games):
                                self.found_games.append(game_info)
            except Exception as e:
                # print(f"Hata ({lib_path}): {e}")
                pass
                
        return self.found_games

    def _analyze_game_folder(self, folder_path, platform="Bilinmiyor", metadata=None):
        """Klasörün Unity veya Unreal oyunu olup olmadığını analiz et"""
        # 1. ÖN ELEME: Yasaklı ve Sistem Klasörleri
        excluded_roots = [
            "Program Files", "Program Files (x86)", "Windows", "Users", 
            "AppData", "ProgramData", "Common Files", "Microsoft", "Intel",
            "Drivers", "Logs", "PerfLogs", "Boot", "Recovery",
            "pinokio", "pinokyo", "Launcher", "launcher"
        ]
        
        # Eğer klasör adı direkt yasaklı listesindeyse
        if folder_path.name in excluded_roots:
            return None

        # Steam Metadata (ACF) Kontrolü
        steam_metadata = metadata or {}
        if platform == "Steam" and not steam_metadata:
            try:
                common_dir = folder_path.parent
                if common_dir.name.lower() == "common":
                    steamapps_dir = common_dir.parent
                    for acf in steamapps_dir.glob("appmanifest_*.acf"):
                        try:
                            with open(acf, 'r', encoding='utf-8') as f:
                                content = f.read()
                                if f'"installdir"\t\t"{folder_path.name}"' in content or \
                                   f'"installdir"\t\t"{folder_path.name.lower()}"' in content:
                                    import re
                                    name_match = re.search(r'"name"\s+"([^"]+)"', content)
                                    appid_match = re.search(r'"appid"\s+"(\d+)"', content)
                                    if name_match: steam_metadata['name'] = name_match.group(1)
                                    if appid_match: steam_metadata['appid'] = appid_match.group(1)
                                    break
                        except: pass
            except: pass

        # Derinlik Desteği: Klasörün kendisini ve 1 seviye altını kontrol et
        search_candidates = [folder_path]
        try:
            for sub in folder_path.iterdir():
                if sub.is_dir() and sub.name not in excluded_roots:
                    search_candidates.append(sub)
        except: pass

        for target in search_candidates:
            try:
                # 1. GODOT KONTROLÜ
                pck_files = list(target.glob("*.pck"))
                if pck_files:
                    return self._create_game_info(target, "Godot", platform, steam_metadata)

                # 2. UNITY KONTROLÜ
                # a. GameName_Data klasörü
                for item in target.iterdir():
                    if item.is_dir() and item.name.lower().endswith("_data"):
                        return self._create_game_info(target, "Unity", platform, steam_metadata)

                # b. MonoBleedingEdge (Modern Unity)
                if (target / "MonoBleedingEdge").exists():
                    return self._create_game_info(target, "Unity", platform, steam_metadata)

                # c. UnityPlayer.dll kontrolü
                if (target / "UnityPlayer.dll").exists():
                    return self._create_game_info(target, "Unity", platform, steam_metadata)

                # 3. COBRA ENGINE KONTROLÜ (Frontier Developments - OVL/OVS)
                # win64/ovldata klasörü veya kök dizinde .ovl dosyası varsa Cobra Engine
                if (target / "win64" / "ovldata").exists():
                    return self._create_game_info(target, "Cobra Engine", platform, steam_metadata)
                if list(target.glob("*.ovl")) or list(target.glob("win64/*.ovl")):
                    return self._create_game_info(target, "Cobra Engine", platform, steam_metadata)

                # 4. UNREAL KONTROLÜ
                # a. Engine/Binaries yapısı
                if (target / "Engine" / "Binaries").exists():
                    return self._create_game_info(target, "Unreal", platform, steam_metadata)

                # b. Binaries/Win64 veya Binaries/Retail
                if (target / "Binaries" / "Retail").exists() or (target / "Binaries" / "Win64").exists():
                    return self._create_game_info(target, "Unreal", platform, steam_metadata)

                # c. Shipping exe
                for child in target.glob("*.exe"):
                    if "Shipping" in child.name:
                        return self._create_game_info(target, "Unreal", platform, steam_metadata)
            except:
                continue

        # [YENİ] Motor tespiti yapılamadıysa ama metadata gelmişse (Manifest oyunu)
        # Sadece güvenilir platformlardan (Steam, Epic, GOG, Xbox vb.) gelenleri kabul et.
        # Rastgele Registry yazılımlarını (VLC vb.) motor tespit edilemediyse listeye ekleme.
        safe_platforms = ["Steam", "Epic Games", "GOG", "Xbox / MS Store", "Ubisoft Connect", "EA App", "Ubisoft / EA"]
        if metadata and 'name' in metadata and platform in safe_platforms:
            return self._create_game_info(folder_path, "Bilinmiyor", platform, metadata)

        return None


    def _create_game_info(self, path, engine, platform="Bilinmiyor", metadata=None):
        """Oyun bilgi sözlüğü oluştur"""
        # Exe bulma (Gelişmiş - Recursive)
        exe_path = ""
        
        try:
            # Tüm exe'leri bul (alt klasörler dahil)
            candidates = list(path.rglob("*.exe"))
            
            # Filtreleme: Gereksiz exe'leri çıkar
            filtered_candidates = []
            for f in candidates:
                name_lower = f.name.lower()
                
                # Yasaklı kelimeler
                if any(x in name_lower for x in ["crashhandler", "unst", "unins", "config", "setup", "redist", "unitycrash"]):
                    continue
                    
                filtered_candidates.append(f)
            
            candidates = filtered_candidates
            
            # YENİ: Binaries/Retail Var mı? Varsa oradakileri öne al
            retail_path = path / "Binaries" / "Retail"
            if retail_path.exists():
                retail_exes = [f for f in candidates if str(retail_path) in str(f)]
                if retail_exes:
                    candidates = retail_exes  # Sadece bunları aday yap (Doğru olan budur)
            
            if candidates:
                # 1. En iyi eşleşme: Klasör adıyla aynı olan exe
                folder_name = path.name.lower()
                best_match = None
                
                for cand in candidates:
                    if cand.stem.lower() == folder_name:
                        best_match = cand
                        break
                        
                # 2. Eğer bulunamadıysa: "Shipping" içeren (Unreal için)
                if not best_match and engine == "Unreal":
                    for cand in candidates:
                        if "shipping" in cand.name.lower():
                            best_match = cand
                            break

                # 3. Hala yoksa: En büyük boyutlu exe (Muhtemelen oyun odur)
                if not best_match:
                    candidates.sort(key=lambda x: x.stat().st_size, reverse=True)
                    best_match = candidates[0]
                
                exe_path = str(best_match)
        except:
            pass
            
        game_name = path.name
        appid = ""
        
        if metadata:
            if 'name' in metadata: game_name = metadata['name']
            if 'appid' in metadata: appid = metadata['appid']
            
        return {
            "name": game_name,
            "path": str(path),
            "exe": exe_path,
            "engine": engine,
            "platform": platform,
            "icon": "🎮",
            "appid": appid
        }

if __name__ == "__main__":
    test_scanner()
    print("-" * 30)
    print("Motor Taraması Testi:")
    s = GameEngineScanner()
    games = s.scan(lambda x: print(x))
    for g in games:
        print(f"[{g['engine']}] {g['name']} -> {g['exe']}")
