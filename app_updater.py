"""
MEMOFAST - Uygulama Güncelleme Modülü
Modern, JSON tabanlı ve dosya bazlı güncelleme sistemi.
"""
import os
import sys
import json
import urllib.request
import subprocess
from pathlib import Path
import re
from logger import setup_logger

logger = setup_logger(__name__)

class AppUpdater:
    """
    Uygulama, oyun ve araçların uzaktan güncellenmesini yöneten sınıf.
    Google Drive veya doğrudan URL destekler.
    """
    
    def __init__(self, current_version, update_url, base_path, installed_yamas=None):
        """
        Args:
            current_version: "1.0.0" formatında mevcut versiyon
            update_url: Güncelleme JSON dosyasının linki
            base_path: Uygulamanın kurulu olduğu ana dizin
        """
        self.current_version = current_version
        self.update_url = update_url
        self.base_path = Path(base_path)
        self.installed_yamas = installed_yamas or []
        
        # Temizlik ve hazırlık
        self.cache_path = self.base_path / ".cache"
        self.cache_path.mkdir(exist_ok=True)

    def check_all_updates(self):
        """
        Sunucudaki güncellemeyi kontrol et.
        
        Returns:
            dict: {
                'update_available': bool,
                'version': str,
                'changelog': list,
                'files': list,
                'force_update': bool,
                'bulletin': str,
                'bulletin_type': str,
                'error': str
            }
        """
        result = {
            'update_available': False,
            'version': None,
            'force_update': False,
            'changelog': [],
            'files': [],
            'bulletin': None,
            'bulletin_type': 'info',
            'error': None
        }
        
        try:
            # 1. JSON Verisini Çek
            data = self._fetch_update_json()
            if not data:
                result['error'] = "Güncelleme sunucusuna erişilemedi."
                return result
            
            # Bülten verilerini al
            result['bulletin'] = data.get('bulletin')
            result['bulletin_type'] = data.get('bulletin_type', 'info')
            
            # Version verisi al
            remote_ver = str(data.get('version', '0.0.0')).strip()

            # Normal Versiyon Kıyasla
            self.current_version = self.current_version.strip()
            
            is_semantic = self._is_semantic_version(remote_ver)
            
            if is_semantic:
                if self._is_newer_version(remote_ver):
                    result['update_available'] = True
                    result['is_yama'] = False
                    result['version'] = remote_ver
                    result['force_update'] = data.get('force_update', False)
                    result['changelog'] = data.get('changelog', [])
                    result['files'] = data.get('files', [])
            else:
                # Oyun adı/Yama durumu (Örn: "Skyrim")
                if remote_ver and remote_ver != self.current_version:
                    # [YENİ] Daha önce kurulmuş mu?
                    if remote_ver in self.installed_yamas:
                        result['update_available'] = False
                        print(f"Yama zaten kurulu: {remote_ver}")
                    else:
                        result['update_available'] = True
                        result['is_yama'] = True
                        result['version'] = remote_ver
                        result['changelog'] = data.get('changelog', [])
                        result['files'] = data.get('files', [])
                
        except Exception as e:
            result['error'] = f"Beklenmeyen hata: {str(e)}"
            
        return result

    def download_and_install_files(self, files_list, progress_callback=None, cancel_check=None, extract_zips=True):
        """
        Dosya listesini indir ve belirtilen yerlere kur.
        """
        try:
            logger.debug("download_and_install_files called with extract_zips=%s", extract_zips)
            total_files = len(files_list)
            if total_files == 0:
                if progress_callback: progress_callback(100, "Dosya listesi boş.")
                return True
            
            for idx, file_info in enumerate(files_list):
                if cancel_check and cancel_check():
                    raise InterruptedError("Kullanıcı işlemi iptal etti.")

                url = file_info.get('url')
                rel_path = file_info.get('target_path')
                
                if not url or not rel_path:
                    continue
                
                target_path = self.base_path / rel_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                def _file_internal_progress(pct):
                    if cancel_check and cancel_check():
                        raise InterruptedError("Kullanıcı işlemi iptal etti.")
                    if progress_callback:
                        global_pct = int(((idx * 100) + pct) / total_files)
                        progress_callback(global_pct, f"İndiriliyor: {rel_path} ({pct}%)")

                self._download_single_file(url, target_path, _file_internal_progress, cancel_check, extract_zips=extract_zips)
            
            if progress_callback: progress_callback(100, "Güncelleme Tamamlandı!")
            return True, "İşlem Başarılı"
            
        except Exception as e:
            msg = f"Hata: {str(e)}"
            if progress_callback: progress_callback(0, msg)
            return False, str(e)

    def download_update(self, url, progress_callback=None):
        """Uygulama güncellemesini (ZIP) indirir ve yolunu döner."""
        try:
            filename = url.split('/')[-1].split('?')[0] or "update.zip"
            if not filename.endswith('.zip'): filename += ".zip"
            target_path = self.cache_path / filename
            
            import urllib.request
            def reporthook(blocknum, blocksize, totalsize):
                if progress_callback and totalsize > 0:
                    pct = int(blocknum * blocksize * 100 / totalsize)
                    progress_callback(min(pct, 100))
            
            urllib.request.urlretrieve(url, str(target_path), reporthook)
            return str(target_path)
        except Exception as e:
            print(f"App download error: {e}")
            raise e

    def apply_update(self, zip_path):
        """İndirilen güncellemeyi uygular."""
        try:
            zip_path = Path(zip_path)
            if not zip_path.exists(): return False
            
            temp_extract = self.base_path / "temp_update"
            if temp_extract.exists():
                import shutil
                shutil.rmtree(temp_extract)
            temp_extract.mkdir()
            
            import zipfile
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(temp_extract)
                
            bat_script = self.base_path / "update_installer.bat"
            with open(bat_script, 'w') as f:
                f.write(f'@echo off\n')
                f.write(f'timeout /t 2 /nobreak >nul\n') 
                f.write(f'xcopy "{temp_extract}\\*" "{self.base_path}\\" /E /H /Y\n')
                f.write(f'rmdir /s /q "{temp_extract}"\n')
                f.write(f'start "" "{self.base_path}\\memofast_gui.py"\n') 
                f.write(f'del "%~f0"\n') 
                
            import subprocess
            CREATE_NO_WINDOW = 0x08000000
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            subprocess.Popen([str(bat_script)], shell=True, startupinfo=si, creationflags=CREATE_NO_WINDOW)
            sys.exit(0) 
            
            return True
        except Exception as e:
            print(f"Apply update error: {e}")
            return False

    def _fetch_update_json(self):
        """Uzak JSON dosyasını indirip parse eder."""
        try:
            url = self._convert_drive_link(self.update_url)
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read().decode('utf-8')
                return json.loads(content)
        except Exception as e:
            print(f"JSON Çekme Hatası: {e}")
            return None
    
    def _is_newer_version(self, remote_ver):
        """Semantik versiyon kontrolü."""
        try:
            def parse_ver(v_str):
                parts = str(v_str).strip().lower().replace('v', '').split('.')
                return [int(re.sub(r'\D', '', p)) if re.sub(r'\D', '', p) else 0 for p in parts]
            
            current_parts = parse_ver(self.current_version)
            remote_parts = parse_ver(remote_ver)
            
            max_len = max(len(current_parts), len(remote_parts))
            current_parts += [0] * (max_len - len(current_parts))
            remote_parts += [0] * (max_len - len(remote_parts))
            
            return remote_parts > current_parts
        except Exception as e:
            print(f"Versiyon kıyaslama hatası: {e}")
            return False

    def _is_semantic_version(self, v_str):
        """Sürüm numarası kontrolü."""
        v_str = str(v_str).strip().lower()
        return bool(re.match(r'^v?\d+(\.\d+)*$', v_str))

    def _download_stream(self, url, target_path, progress_callback=None, cancel_check=None):
        """Bufferlı indirme."""
        import time
        last_time = 0
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = int(response.getheader('Content-Length') or 0)
                chunk_size = 1024 * 128
                downloaded = 0
                last_pct = -1
                with open(target_path, 'wb') as f:
                    while True:
                        if cancel_check and cancel_check():
                            raise InterruptedError("İndirme iptal edildi.")
                        chunk = response.read(chunk_size)
                        if not chunk: break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and progress_callback:
                            pct = int(downloaded * 100 / total_size)
                            cur_time = time.time()
                            if pct != last_pct and (cur_time - last_time > 0.1 or pct == 100):
                                progress_callback(pct)
                                last_pct = pct
                                last_time = cur_time
        except Exception as e:
            raise Exception(f"Download Error: {e} ({url})")

    def _download_single_file(self, url, target_path, progress_callback=None, cancel_check=None, extract_zips=True):
        """Linkteki dosyayı indirir."""
        import zipfile 
        url = self._convert_drive_link(url)
        temp_path = str(target_path) + f".tmp_{os.getpid()}" 
        try:
            opener = urllib.request.build_opener()
            opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
            urllib.request.install_opener(opener)
            self._download_stream(url, temp_path, progress_callback, cancel_check)
            
            if extract_zips and zipfile.is_zipfile(temp_path):
                with zipfile.ZipFile(temp_path, 'r') as z:
                    extract_dir = target_path
                    if target_path.exists() and target_path.is_file():
                        extract_dir = target_path.parent
                    extract_dir.mkdir(parents=True, exist_ok=True)
                    z.extractall(extract_dir)
            else:
                final_path = target_path
                if final_path.is_dir():
                    fname = url.split('/')[-1].split('?')[0] or "update_file"
                    final_path = final_path / fname
                if final_path.exists():
                    try: os.remove(final_path)
                    except: pass
                os.rename(temp_path, final_path)
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception as e:
            if os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass
            raise e

    def _convert_drive_link(self, url):
        """Google Drive linklerini çevirir."""
        if "drive.google.com" in url:
            file_id = None
            match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
            if match:
                file_id = match.group(1)
            elif "id=" in url:
                match_id = re.search(r'id=([a-zA-Z0-9_-]+)', url)
                if match_id:
                    file_id = match_id.group(1)
            if file_id:
                return f"https://drive.google.com/uc?export=download&id={file_id}"
        return url

    def restart_application(self):
        """Uygulamayı yeniden başlatır."""
        try:
            python = sys.executable
            script = self.base_path / "memofast_gui.py"
            CREATE_NO_WINDOW = 0x08000000
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            start_bat = self.base_path / "start.bat"
            if start_bat.exists():
                subprocess.Popen([str(start_bat)], shell=True, startupinfo=si, creationflags=CREATE_NO_WINDOW)
            else:
                subprocess.Popen([python, str(script)], startupinfo=si, creationflags=CREATE_NO_WINDOW)
            sys.exit(0)
        except Exception as e:
            print(f"Restart hatası: {e}")

def format_file_size(size_mb):
    """Dosya boyutunu okunabilir stringe çevirir."""
    if size_mb < 1:
        return f"{size_mb * 1024:.0f} KB"
    elif size_mb < 1024:
        return f"{size_mb:.1f} MB"
    else:
        return f"{size_mb / 1024:.1f} GB"
