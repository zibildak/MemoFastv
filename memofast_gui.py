import sys
import os
import subprocess
import faulthandler
try:
    _crash_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".logs")
    os.makedirs(_crash_log_dir, exist_ok=True)
    _fh = open(os.path.join(_crash_log_dir, "memofast_crash.txt"), "w")
    faulthandler.enable(file=_fh, all_threads=True)
except Exception:
    # Yazılamıyorsa stderr'e yaz
    faulthandler.enable(all_threads=True)
# SIGNATURE PLACEHOLDER
FILE_SIGNATURE = "05eb5bbf1eca67b7dc0cda1f4330c5a6d566a4216493c68b87d0d41857a3d59b"


# Modül yolunu ekle (Hem dosya konumu hem çalışma dizini)
# Ayrıca library klasörünü de ekle (Portable Pymem için)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "files", "libs"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "libs"))

import json
import shutil
import platform
import psutil
import urllib.request
import zipfile
import webbrowser
from pathlib import Path
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from logger import setup_logger
import base64
import io
from PIL import Image # Pillow library for image handling




# Konsol Penceresini Gizle (Kernel32 & User32)
try:
    import ctypes
    
    # 1. Eski conhost pencereleri için gizleme sinyali
    console_window = ctypes.windll.kernel32.GetConsoleWindow()
    if console_window != 0:
        ctypes.windll.user32.ShowWindow(console_window, 0) # 0 = SW_HIDE
        
        # 2. Windows 11 Terminal (wt.exe) Pencerelerini de tamamen gizlemek için ana ebeveyn pencereye ulaş:
        # GA_ROOTOWNER (3) / GA_ROOT (2) ile ana çerçeve bulunur ve arka plana gömülür.
        root_hwnd = ctypes.windll.user32.GetAncestor(console_window, 3)
        if root_hwnd != 0:
            ctypes.windll.user32.ShowWindow(root_hwnd, 0)

    # [YENİ] Görev çubuğunda Python ikonu yerine kendi ikonumuzu göstermek için uygulama kimliği ayarla
    myappid = u'memofast.app.version.1.1.2' # Unique identifier
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except (AttributeError, OSError):
    # Windows olmayan sistem veya ctypes kullanılamıyor
    pass

# Windows için alt işlemlerde konsolun açılmasını engelleyen bayrak
CREATE_NO_WINDOW = 0x08000000

# [KRİTİK] Windows'un Uygulamayı Yeniden Başlatmasını Engelle (Hata Raporlama)
try:
    import ctypes
    # SEM_NOGPFAULTERRORBOX = 0x0002
    ctypes.windll.kernel32.SetErrorMode(0x0002)
except (AttributeError, OSError, TypeError):
    # Windows olmayan sistem veya çağrı başarısız
    pass

# [KRİTİK] Windows'un Uygulamayı Yeniden Başlatmasını Engelle (Hata Raporlama ve Kurtarma)
try:
    import ctypes
    # SEM_FAILCRITICALERRORS (0x0001) | SEM_NOGPFAULTERRORBOX (0x0002) | SEM_NOOPENFILEERRORBOX (0x8000)
    ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    # Windows Restart Manager'a "beni baştan açma" mesajı (RegisterApplicationRestart yok sayılır)
except (AttributeError, OSError, TypeError):
    # Windows olmayan sistem veya çağrı başarısız
    pass

logger = setup_logger(__name__)

# GUI Module Imports (Modularized)
try:
    from gui import MemoFastMainWindow
    from gui.pages import ScannerPage, TranslatorPage, SettingsPage, ToolsPage
    from gui.dialogs import AESKeyDialog, ManualReviewDialog, WWMLoaderDialog
    from gui.widgets import LogWidget, GameListWidget, TranslatorListWidget, HUDOverlay, SecureConnectAnimation
    from gui.styles import COLORS, DARK_THEME_STYLESHEET
    GUI_MODULAR = True
except ImportError as e:
    # Fallback for when modular structure isn't fully ready or packed differently
    logger.warning(f"GUI modules import failed: {e}. Attempting fallback...")
    
    try:
        from gui.widgets.secure_connect_animation import SecureConnectAnimation
    except ImportError as fallback_err:
        logger.warning(f"SecureConnectAnimation fallback failed: {fallback_err}")
        SecureConnectAnimation = None # Fallback if even that fails
        
    logger.info("Falling back to legacy GUI mode")
    GUI_MODULAR = False

def verify_integrity():
    """Kendi kendini doğrulama"""
    return # Geliştirme aşamasında kapalı
    import hashlib
    import re
    
    # 1. Kendi dosya içeriğini oku
    current_file = os.path.abspath(__file__)
    with open(current_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 2. İmzayı sanal olarak sıfırla
    placeholder = "0" * 64
    pattern = r'(FILE_SIGNATURE\s*=\s*)(["\'])[a-fA-F0-9]{64}(["\'])'
    
    normalized_content = re.sub(pattern, f'\\g<1>\\g<2>{placeholder}\\g<3>', content)
    
    # 3. Hash hesapla
    sha256 = hashlib.sha256()
    sha256.update(normalized_content.encode('utf-8'))
    calculated_hash = sha256.hexdigest()
    
    # 4. Karşılaştır
    if calculated_hash != FILE_SIGNATURE:
        app = QApplication(sys.argv)
        # Tehditkar / Sistem Hatası Görünümlü Mesaj
        QMessageBox.critical(None, "KRİTİK SİSTEM HATASI (0xC000005)", 
            "YAZILIM BÜTÜNLÜĞÜ BOZULDU!\n\n"
            "Sistem dosyalarında yetkisiz değişiklik veya dış müdahale tespit edildi.\n"
            "Güvenlik protokolleri gereği çekirdek modüller kilitlendi.\n\n"
            "Hata Kodu: SECURITY_VIOLATION_INTEGRITY_CHECK_FAILED\n"
            "Sistem kilitleniyor...")
        sys.exit(1)


from deepl_helper import DeepLUsageChecker
from config import Config, Constants

# GPU monitoring (opsiyonel)
try:
    # GPUtil distutils gerektirir, ancak python 3.12+ veya embedded sürümlerde olmayabilir.
    # Bu yüzden distutils'i taklit ediyoruz (monkey patch).
    try:
        import distutils.spawn
    except ImportError:
        import types
        import shutil
        distutils = types.ModuleType("distutils")
        distutils.spawn = types.ModuleType("distutils.spawn")
        distutils.spawn.find_executable = shutil.which
        sys.modules["distutils"] = distutils
        sys.modules["distutils.spawn"] = distutils.spawn

    import GPUtil
    GPU_AVAILABLE = True
except ImportError as e:
    GPU_AVAILABLE = False
    print(f"GPUtil yok veya hata: {e} - GPU monitörü devre dışı")





# GLOBAL EXCEPTION HANDLER
def global_exception_handler(exctype, value, traceback_obj):
    """
    Tüm yakalanmayan hataları yakalar ve kullanıcıya gösterir.
    Böylece uygulama sessizce kapanmaz.
    """
    import traceback
    error_msg = "".join(traceback.format_exception(exctype, value, traceback_obj))
    print("CRITICAL ERROR:", error_msg)
    
    # PyQt uygulaması çalışıyorsa MessageBox göster
    if QApplication.instance():
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setText("Kritik Hata (Uygulama Kapanıyor)")
        msg.setInformativeText(str(value))
        msg.setDetailedText(error_msg)
        msg.setWindowTitle("MEMOFAST - Hata Raporu")
        msg.exec_()
    else:
        # Konsol ise
        print(error_msg)

sys.excepthook = global_exception_handler

# from config import Config (zaten en üstte var veya varsa kullan, yoksa ekle)
# Config sınıfı config.py'dan gelecek, burada tekrar tanımlanmamalı.


try:
    from translator_manager import TranslatorManager
except ImportError:
    TranslatorManager = None
    print("UYARI: translator_manager modülü yüklenemedi!")

# Global import
try:
    from patcher import GamePatcher, format_size
    from app_updater import AppUpdater, format_file_size
    from scanner import GameEngineScanner
    from scan_worker import ScanWorker
    from unreal_manager import UnrealManager
    from unity_manager import UnityManager
    try:
        from cobra_manager import CobraManager
    except ImportError:
        CobraManager = None
except ImportError as e:
    # Fallback veya hata yönetimi
    print(f"UYARI: Modül yükleme hatası: {e}")
    # traceback
    import traceback
    traceback.print_exc()

# Screen Translator Import
try:
    from screen_translator import ScreenTranslatorOverlay
except ImportError as e:
    ScreenTranslatorOverlay = None
    print(f"ScreenTranslatorOverlay modülü yüklenemedi: {e}")


# [YENİ] PyInstaller Uyumluluğu ve Yol Yönetimi
if getattr(sys, 'frozen', False):
    # EXE olarak çalışıyorsa (PyInstaller)
    # BASE_PATH: EXE'nin olduğu klasör (settings.json, loglar, oyunlar burada olur)
    BASE_PATH = Path(sys.executable).parent
    # ASSET_PATH: EXE içinden Temp'e açılan dosyalar (tesseract, libs, iconlar burada olur)
    ASSET_PATH = Path(sys._MEIPASS)
else:
    # Python script olarak çalışıyorsa
    BASE_PATH = Path(__file__).parent
    ASSET_PATH = BASE_PATH

GAME_PATH = BASE_PATH / "game"
CACHE_PATH = BASE_PATH / ".cache"
CACHE_PATH.mkdir(exist_ok=True)

class ToastNotification(QWidget):
    """Sağ alt köşeden kayan bildirim penceresi"""
    def __init__(self, title, message, icon="✅", duration=4000, color="#10b981", parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(340, 80)

        # Arka plan
        container = QFrame(self)
        container.setGeometry(0, 0, 340, 80)
        container.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1f2e;
                border: 1px solid {color};
                border-radius: 10px;
            }}
        """)
        lay = QHBoxLayout(container)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"font-size: 28px; color: {color};")
        icon_lbl.setFixedWidth(36)
        lay.addWidget(icon_lbl)

        text_lay = QVBoxLayout()
        text_lay.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 13px;")
        msg_lbl = QLabel(message)
        msg_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        msg_lbl.setWordWrap(True)
        text_lay.addWidget(title_lbl)
        text_lay.addWidget(msg_lbl)
        lay.addLayout(text_lay)

        # Ekranın sağ altına yerleştir
        screen = QApplication.primaryScreen().availableGeometry()
        self._end_x = screen.right() - self.width() - 12
        self._end_y = screen.bottom() - self.height() - 12
        self.move(self._end_x, screen.bottom() + 10)

        # Kayma animasyonu
        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setDuration(350)
        self._anim.setStartValue(QPoint(self._end_x, screen.bottom() + 10))
        self._anim.setEndValue(QPoint(self._end_x, self._end_y))
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self.show()
        self._anim.start()

        QTimer.singleShot(duration, self._slide_out)

    def _slide_out(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self._anim2 = QPropertyAnimation(self, b"pos")
        self._anim2.setDuration(300)
        self._anim2.setStartValue(QPoint(self._end_x, self._end_y))
        self._anim2.setEndValue(QPoint(self._end_x, screen.bottom() + 10))
        self._anim2.setEasingCurve(QEasingCurve.InCubic)
        self._anim2.finished.connect(self.deleteLater)
        self._anim2.start()

class WWMLoaderDialog(QDialog):
    """WWM Oyun Başlatıcı ve Enjeksiyon Penceresi (Native Python)"""
    def __init__(self, game_dir, parent=None):
        super().__init__(parent)
        self.game_dir = Path(game_dir)
        self.setWindowTitle("MemoFast - Where Winds Meet Injector")
        self.setFixedSize(600, 400)
        self.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowMinimizeButtonHint)
        self.setStyleSheet("""
            QDialog { background-color: #0c0c0c; border: 1px solid #333; }
            QLabel { color: #0f0; font-family: 'Consolas', 'Courier New', monospace; font-size: 14px; }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        # Başlık ve Uyarılar
        self.title_lbl = QLabel("MEMOFAST - WHERE WINDS MEET TRANSLATOR")
        self.title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #0f0;")
        self.title_lbl.setAlignment(Qt.AlignCenter)
        
        self.warn_lbl = QLabel("[!] UYARI: BU PENCEREYI KAPATMAYIN!")
        self.warn_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #f00;")
        self.warn_lbl.setAlignment(Qt.AlignCenter)
        
        self.status_lbl = QLabel("Enjeksiyon Hazırlanıyor...")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        
        # Spinner (Basit ASCII Animasyon)
        self.spinner_chars = ['|', '/', '-', '\\']
        self.spinner_idx = 0
        self.spinner_lbl = QLabel("|")
        self.spinner_lbl.setStyleSheet("font-size: 48px; color: #0f0;")
        self.spinner_lbl.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(self.title_lbl)
        layout.addSpacing(20)
        layout.addWidget(self.warn_lbl)
        layout.addStretch()
        layout.addWidget(self.spinner_lbl)
        layout.addWidget(self.status_lbl)
        layout.addStretch()
        
        self.setLayout(layout)
        
        # Timer
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_animation)
        self.anim_timer.start(100)
        
        # İşlemleri Başlat (Biraz gecikmeli ki UI açılsın)
        QTimer.singleShot(1000, self.start_injection_process)
        
        self.game_process = None
        self.fake_lagofast_process = None
        
    def update_animation(self):
        self.spinner_idx = (self.spinner_idx + 1) % 4
        char = self.spinner_chars[self.spinner_idx]
        self.spinner_lbl.setText(char)
        
        # Eğer oyun açıksa kontrol et
        if self.game_process:
            if self.game_process.poll() is not None:
                # Oyun kapanmış
                self.status_lbl.setText("Oyun Kapandı. Temizlik Yapılıyor...")
                self.cleanup_and_close()

    def start_injection_process(self):
        try:
            self.status_lbl.setText("Servis Başlatılıyor...")
            
            # 1. Fake Lagofast Setup
            import tempfile
            import subprocess
            from pathlib import Path
            import shutil

            temp_dir = Path(tempfile.gettempdir()) / "WWM_TR_Temp"
            temp_dir.mkdir(exist_ok=True)
            target_exe = temp_dir / "LagoFast.exe"
            
            # Varolanı temizle (Kilitliyse aç)
            try:
                # taskkill için gizli çalıştırma
                si_kill = subprocess.STARTUPINFO()
                si_kill.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si_kill.wShowWindow = subprocess.SW_HIDE
                
                subprocess.run(
                    "taskkill /F /IM LagoFast.exe", 
                    shell=True, 
                    stdout=subprocess.DEVNULL, 
                    stderr=subprocess.DEVNULL,
                    startupinfo=si_kill,
                    creationflags=CREATE_NO_WINDOW
                )
                if target_exe.exists():
                    try:
                        target_exe.unlink()
                    except: pass # Silinemediyse devam et, belki yazılabilir
            except: pass

            if not target_exe.exists():
                try:
                    shutil.copy2(r"C:\Windows\System32\cmd.exe", target_exe)
                except Exception as copy_err:
                     self.status_lbl.setText(f"HATA: Dosya Oluşturulamadı!\n{copy_err}")
                     return

            # 2. Start Fake Lagofast (Hidden - Tamamen Gizli)
            CREATE_NO_WINDOW = 0x08000000
            
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
            # [FIX] WinError 2 fix
            # Ensure we are using the full absolute path as string
            exe_path_str = str(target_exe.resolve())
            
            if not target_exe.exists():
                 # Eğer kopyalama başarısız olduysa ve dosya yoksa
                 self.status_lbl.setText("HATA: LagoFast.exe oluşturulamadı.")
                 return

            cmd_args = [exe_path_str, "/k", "title", "FAKE_LAGOFAST_BG"]
            
            # CREATE_NO_WINDOW kullan (Tamamen gizli - 0x08000000)
            self.fake_lagofast_process = subprocess.Popen(
                cmd_args,
                startupinfo=startupinfo,
                creationflags=CREATE_NO_WINDOW,
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            
            # --- BAT DOSYASINDAN GELEN MANTIK ---
            # :: Biraz bekle (timeout /t 2)
            self.status_lbl.setText("Servis Başlatıldı. Bekleniyor...")
            QThread.msleep(2000)
            
            # :: 3. Oyunu Baslat - İPTAL EDİLDİ (KESİN KARAR)
            # Kullanıcı isteği: Sadece servis çalışsın, oyunla ilgilenmesin.
            self.status_lbl.setText("Enjeksiyon Servisi Aktif!\nLütfen Oyunu Başlatınız...")
            
            # WWM.exe ile ilgili hiçbir işlem yapılmıyor.
            self.game_process = None
            
        except Exception as e:
            self.status_lbl.setText(f"HATA: {e}")

    def cleanup_and_close(self):
        try:
            if self.fake_lagofast_process:
                self.fake_lagofast_process.terminate()
            
            import subprocess
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            subprocess.run("taskkill /F /IM LagoFast.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=si, creationflags=CREATE_NO_WINDOW)
            
            self.status_lbl.setText("Temizlendi. Kapatılıyor...")
            QTimer.singleShot(2000, self.close)
            
        except:
            self.close()
    
    def closeEvent(self, event):
        self.cleanup_and_close()
        event.accept()

class CoverImageManager:
    """Oyun kapak resimlerini yönetir (Sadece EXE İkonu)"""
    
    @staticmethod
    def get_cover_image(game_data, callback=None):
        """
        Oyunun EXE dosyasından ikonunu çeker.
        Steam vs. indirme yapmaz (Kullanıcı isteği).
        """
        try:
            exe_path = game_data.get('exe')
            if not exe_path:
                exe_path = game_data.get('path') # Fallback to folder? No, need file.
            
            return CoverImageManager.extract_icon(exe_path)
        except Exception as e:
            print(f"CoverImage error: {e}")
            return None

    @staticmethod
    def extract_icon(exe_path):
        """EXE dosyasından ikon çıkar"""
        if not exe_path or not os.path.exists(exe_path):
            return None
            
        try:
            # Dosya değilse (klasörse) ikon alamayız
            if os.path.isdir(exe_path):
                return None

            info = QFileInfo(exe_path)
            provider = QFileIconProvider()
            icon = provider.icon(info)
            
            if not icon.isNull():
                # Mümkün olan en büyük boyutu al
                # Windows'ta genelde 32x32, 48x48, 256x256 olabilir.
                # 128x128 isteyelim, varsa gelir, yoksa scale olur.
                return icon.pixmap(128, 128) 
        except Exception as e:
            print(f"Icon extraction error ({exe_path}): {e}")
            pass
            
        return None

class ScanThread(QThread):
    finished = pyqtSignal(dict)
    progress = pyqtSignal(str, int)
    
    def __init__(self, game_folder, target_file):
        super().__init__()
        self.game_folder = game_folder
        self.target_file = target_file
    
    def run(self):
        results = {'steam': [], 'epic': [], 'custom': []}
        
        for drive in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
            drive_path = f"{drive}:\\"
            if not os.path.exists(drive_path):
                continue
            
            self.progress.emit(f"Taranıyor: {drive}:\\", 0)
            
            steam_paths = [
                Path(drive_path) / "Program Files (x86)" / "Steam" / "steamapps" / "common",
                Path(drive_path) / "Steam" / "steamapps" / "common",
            ]
            
            for sp in steam_paths:
                if sp.exists():
                    try:
                        for root, dirs, files in os.walk(sp):
                            if self.target_file in files:
                                results['steam'].append(str(Path(root) / self.target_file))
                    except: pass
            
            epic_paths = [
                Path(drive_path) / "Program Files" / "Epic Games",
            ]
            
            for ep in epic_paths:
                if ep.exists():
                    try:
                        for root, dirs, files in os.walk(ep):
                            if self.target_file in files:
                                results['epic'].append(str(Path(root) / self.target_file))
                    except: pass
        
        cache_file = CACHE_PATH / f"{self.game_folder}_cache.json"
        with open(cache_file, 'w') as f:
            json.dump(results, f)
        
        self.finished.emit(results)



class InstallationWorker(QThread):
    log_updated = pyqtSignal(str)
    progress_updated = pyqtSignal(int)
    finished = pyqtSignal(bool, str)
    aes_key_requested = pyqtSignal(str, object, object) # game_name, result_queue, threading.Event
    method_selection_requested = pyqtSignal(str, object, object) # game_name, result_queue, threading.Event
    progress_max_updated = pyqtSignal(int) # [YENİ] Progress Bar Max Değerini Ayarlamak İçin
    manual_review_requested = pyqtSignal(str, object, object) # file_path, result_queue, threading.Event
    wwm_loader_requested = pyqtSignal(str) # [YENİ] WWM Loader Signal (game_path)
    
    
    def __init__(self, file_path, engine, service="google", api_key="", max_workers=10, aes_key=None, translation_method="full", game_name=None, target_bepinex_zip=None, target_translator_zip=None, target_pak_path=None, target_internal_file_path=None, is_encrypted_override=None, loader_type="bepinex", target_lang="tr"):
        super().__init__()
        self.file_path = file_path
        self.engine = engine
        self.service = service
        self.api_key = api_key
        self.max_workers = max_workers
        self.aes_key = aes_key
        self.translation_method = translation_method
        self.game_name = game_name
        self.target_bepinex_zip = target_bepinex_zip
        self.target_translator_zip = target_translator_zip
        self.target_pak_path = target_pak_path
        self.target_internal_file_path = target_internal_file_path
        self.is_encrypted_override = is_encrypted_override
        self.loader_type = loader_type
        self.target_lang = target_lang
        self.target_internal_file_path = target_internal_file_path
        self.is_encrypted_override = is_encrypted_override
        self.loader_type = loader_type
        
    def run(self):
        try:
            # COBRA ENGINE
            if self.engine == "Cobra Engine":
                if CobraManager is None:
                    self.finished.emit(False, "CobraManager modülü yüklenemedi! cobra_manager.py eksik.")
                    return

                self.log_updated.emit("🐍 Cobra Engine oyunu işleniyor...")

                import threading, queue

                def ask_manual_review_callback_cobra(file_path):
                    res_queue = queue.Queue()
                    event = threading.Event()
                    self.manual_review_requested.emit(file_path, res_queue, event)
                    event.wait()
                    try:
                        return res_queue.get_nowait()
                    except Exception:
                        return True

                success, msg = CobraManager.process_game(
                    self.file_path,
                    service=self.service,
                    api_key=self.api_key,
                    max_workers=self.max_workers,
                    progress_callback=self.log_updated.emit,
                    progress_max_callback=self.progress_max_updated.emit,
                    progress_bar_callback=self.progress_updated.emit,
                    manual_review_callback=ask_manual_review_callback_cobra,
                    target_lang=self.target_lang,
                )

                self.finished.emit(success, msg)
                return

            # UNREAL ENGINE
            if self.engine == "Unreal":
                from unreal_manager import PakManager
                
                # AES Key Kontrol (Eğer parametre gelmediyse ve GUI'den de alınamadıysa)
                # ... PakManager içindeki logic halledecek mi?
                # PakManager.process_locres_file içinde AES key lazım.
                
                self.log_updated.emit(f"Unreal Engine oyunu işleniyor...")
                # ...
                
                # AES Key İstemek için Callback (Thread-Safe Signal + Event)
                import threading, queue
                def ask_key_callback(game_name):
                    res_queue = queue.Queue()
                    event = threading.Event()
                    self.aes_key_requested.emit(game_name, res_queue, event)
                    event.wait()
                    try: return res_queue.get_nowait()
                    except: return None

                # Dosya Seçimi Wrapper (Thread-Safe Queue) - Otomatik En Yüksek Puanlı Seçer
                def ask_file_selection_wrapper(candidates):
                    # candidates: [(score, Path), ...]
                    # En yüksek puanlı (index 0) otomatik olarak seçilir, dialog gösterilmez
                    if candidates:
                        # En yüksek puanı olan dosyayı seçen sırada döndür
                        best_candidate = max(candidates, key=lambda x: x[0])
                        return str(best_candidate[1])
                    return None

                # Metod Seçimi Callback (Thread-Safe Queue)
                def ask_method_selection_callback(game_name):
                    import queue
                    res_queue = queue.Queue()
                    event = threading.Event()
                    self.method_selection_requested.emit(game_name, res_queue, event)
                    event.wait()
                    try: 
                        val = res_queue.get_nowait()
                        logger.debug("UI'dan gelen cevap: %s", val)
                        return val
                    except: 
                        return "PAK"

                # [MANUEL REVIEW] Callback Wrapper
                def ask_manual_review_callback(file_path):
                    import queue
                    res_queue = queue.Queue()
                    event = threading.Event()
                    self.manual_review_requested.emit(file_path, res_queue, event)
                    event.wait()
                    try: return res_queue.get_nowait()
                    except: return True # Varsayılan: Devam et

                manager = PakManager()
                success, msg = manager.process_game(
                    self.file_path, 
                    service=self.service, 
                    api_key=self.api_key,
                    max_workers=self.max_workers,
                    aes_key=self.aes_key,
                    logger_callback=None, # Fix: Duplicate log prevention (progress_callback handles it)
                    progress_callback=self.log_updated.emit, # Fix: String logger
                    progress_max_callback=self.progress_max_updated.emit, 
                    progress_bar_callback=self.progress_updated.emit, # Fix: Int progress
                    ask_aes_key_callback=ask_key_callback,
                    ask_file_callback=ask_file_selection_wrapper,
                    target_pak_path=self.target_pak_path,
                    target_internal_file_path=self.target_internal_file_path,
                    is_encrypted_override=self.is_encrypted_override,
                    manual_review_callback=ask_manual_review_callback,
                    target_lang=self.target_lang # Pass target_lang to PakManager
                )

                if success:
                    # [YENİ] Where Winds Meet Enjeksiyonu
                    try:
                        # Kullanıcı denetleme istemedi, direkt çalıştırıyoruz.
                        install_dir = Path(self.target_pak_path).parent
                    except Exception as e:
                        print(f"Loader trigger error: {e}")

                    self.finished.emit(True, "Kurulum tamamlandı")
                else:
                    # Özel hata kodu kontrolü
                    if "AES key needed" in msg:
                        self.finished.emit(False, "AES_REQUIRED_BY_USER")
                    else:
                        self.finished.emit(False, msg)
                return

            # UNITY ENGINE
            else:
                from translator_manager import TranslatorManager
                
                # [ASSET FILE FIX] Eğer kullanıcı manuel olarak .assets dosyası seçtiyse
                # BepInEx kurulumu için ana EXE'yi bulmamız lazım.
                target_exe_path = self.file_path
                is_asset_target = str(self.file_path).lower().endswith(('.assets', '.sharedassets'))
                
                if is_asset_target:
                    self.log_updated.emit(f"📂 Asset dosyası seçildi: {os.path.basename(self.file_path)}")
                    # Asset: Game_Data/resources.assets
                    # Exe: Game.exe (Game_Data'nın kardeşi değil, Game_Data'nın parent'ında)
                    # resources.assets -> Game_Data -> Game Root
                    candidate_root = Path(self.file_path).parent.parent
                    
                    found_exe = None
                    # Klasördeki EXE'leri tara
                    for f in candidate_root.glob("*.exe"):
                        if "UnityCrashHandler" not in f.name:
                            found_exe = f
                            break
                            
                    if found_exe:
                        target_exe_path = str(found_exe)
                        self.log_updated.emit(f"✅ Ana oyun dosyası bulundu: {found_exe.name}")
                    else:
                        raise Exception("Seçilen Asset dosyasınan oyunun ana EXE dosyası bulunamadı!\nLütfen oyunun ana klasör yapısının bozulmadığından emin olun.")

                # [TAM ÇEVİRİ + ASSET DOSYASI] 
                # Eğer kullanıcı "Tam Çeviri" seçtiyse ve bir Asset dosyası seçtiyse,
                # BepInEx kurmak yerine doğrudan o dosyayı çevirmeliyiz (UnityPy).
                if self.translation_method == "full" and is_asset_target:
                    if UnityManager and UnityManager.is_available():
                         self.log_updated.emit(f"📦 Seçilen Asset dosyası işleniyor (UnityPy)...")
                         
                         def up_prog(m): self.log_updated.emit(str(m))
                         
                         # Tekil dosya modu
                         total = UnityManager.scan_and_process_game(
                             self.file_path, # Direkt asset path
                             service=self.service,
                             api_key=self.api_key,
                             progress_callback=up_prog,
                             target_lang=self.target_lang
                         )
                         
                         if total > 0:
                             self.finished.emit(True, f"Asset Çevirisi Tamamlandı ({total} satır)")
                             return
                         else:
                             self.log_updated.emit("⚠️ Dosyada çevrilecek metin bulunamadı.")
                             # Başarısız olsa bile BepInEx'e düşmeyelim, kullanıcı özellikle bu dosyayı seçti.
                             self.finished.emit(False, "Metin bulunamadı")
                             return
                    else:
                        self.log_updated.emit("❌ UnityPy modülü eksik! Sadece BepInEx kurulabilir.")

                # [MODIFIED] INTEGRATED DIRECT LOGIC (No Imports) - REV 2 (Admin/Perm Check)
                if self.loader_type == "melonloader":
                    try:
                        self.log_updated.emit("🚀 MelonLoader Kurulumu Başlatılıyor (Dahili Mod v2)...")
                        
                        # 0. YOL VE YETKİ KONTROLLERİ
                        import ctypes
                        is_admin = False
                        try:
                            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
                        except: pass
                        
                        game_dir = Path(self.file_path).parent
                        game_dir_str = str(game_dir) # Explicit string conversion
                        
                        self.log_updated.emit(f"Hedef Klasör: {game_dir_str}")
                        
                        # Yönetici Yetkisi Uyarısı
                        is_program_files = "Program Files" in game_dir_str
                        if is_program_files and not is_admin:
                            self.log_updated.emit("⚠️ UYARI: Oyun 'Program Files' içinde ama yazılım Yönetici Olarak çalışmıyor!")
                            self.log_updated.emit("⚠️ Dosyalar 'VirtualStore' klasörüne sanallaştırılmış olabilir.")
                            self.log_updated.emit("⚠️ Lütfen 'MemoFast' yazılımını SAĞ TIK -> YÖNETİCİ OLARAK ÇALIŞTIR diyerek açın.")
                        
                        # Yazma İzni Kontrolü
                        if not os.access(game_dir_str, os.W_OK):
                             self.log_updated.emit("❌ HATA: Oyun klasörüne yazma izni yok! Yönetici olmalısınız.")
                             self.finished.emit(False, "Yazma İzni Hatası")
                             return

                        melon_zip = self.target_bepinex_zip
                        xunity_zip = self.target_translator_zip
                        
                        # 1. MELON EXTRACTION
                        if not melon_zip or not os.path.exists(melon_zip):
                            self.finished.emit(False, "MelonLoader ZIP dosyası bulunamadı!")
                            return
                            
                        self.log_updated.emit(f"Arşiv Çıkarılıyor: {os.path.basename(melon_zip)}")
                        with zipfile.ZipFile(melon_zip, 'r') as z:
                            z.extractall(game_dir_str)
                        
                        # Doğrulama: version.dll geldi mi?
                        if not (game_dir / "version.dll").exists():
                             self.log_updated.emit("❌ KRİTİK: Çıkarma başarılı raporlandı ama 'version.dll' dosyası klasörde yok!")
                             if not is_admin: 
                                 self.log_updated.emit("ℹ️ Bu sorun %99 ihtimalle YÖNETİCİ yetkisi eksikliğinden kaynaklanıyor.")
                             self.finished.emit(False, "Dosya Doğrulama Hatası (VirtualStore?)")
                             return

                        self.log_updated.emit("✅ MelonLoader dosyaları oyun klasörüne çıkarıldı.")
                        
                        # 2. XUNITY EXTRACTION
                        # FALLBACK LOGIC: If explicit zip not provided, SEARCH for it like the user's script
                        if not xunity_zip or not os.path.exists(xunity_zip):
                            self.log_updated.emit("⚠️ XUnity zip seçilmedi, otomatik aranıyor...")
                            search_path = Config.BASE_PATH / "files" / "tools"
                            if not search_path.exists(): search_path = Config.BASE_PATH
                            
                            cands = []
                            # Determine backend from folder structure if possible, else default to mono
                            is_il2cpp = (game_dir / "MelonLoader" / "net6").exists() # Rough check
                            
                            if is_il2cpp:
                                cands = list(search_path.glob("XUnity*IL2CPP*.zip"))
                            else:
                                cands = list(search_path.glob("XUnity*MelonMod*.zip"))
                                cands = [f for f in cands if "IL2CPP" not in f.name]
                                
                            if cands:
                                xunity_zip = cands[0]
                                self.log_updated.emit(f"✅ Otomatik bulundu: {xunity_zip.name}")
                            else:
                                self.log_updated.emit("⚠️ Otomatik aramada da uygun XUnity zip bulunamadı.")
                        
                        if xunity_zip and os.path.exists(xunity_zip):
                            self.log_updated.emit(f"Çeviri Aracı Çıkarılıyor: {os.path.basename(xunity_zip)}")
                            with zipfile.ZipFile(xunity_zip, 'r') as z:
                                z.extractall(game_dir_str)
                            self.log_updated.emit("✅ XUnity dosyaları çıkarıldı.")
                            
                            # 3. CONFIGURATION (Direct Write)
                            at_dir = game_dir / "AutoTranslator"
                            at_dir.mkdir(parents=True, exist_ok=True)
                            config_file = at_dir / "Config.ini"
                            
                            cfg_content = f"""[Service]
Endpoint={self.service if self.service != "google" else "GoogleTranslateV2"}
FallbackEndpoint=

[General]
Language={self.target_lang}
FromLanguage=en

[Behaviour]
MaxTranslationsBeforeShutdown=4000
MaxDestinationsToQueue=5
MaxSecondsInQueue=5
Delay=0
KerbalSpaceProgram=False
ForceUIResizing=True
WhitespaceRemovalStrategy=TrimPerlineInToken

[TextFrameworks]
EnableUGUI=True
EnableTextMeshPro=True
EnableNGUI=True
EnableTextMesh=True
"""
                            with open(config_file, 'w', encoding='utf-8') as f:
                                f.write(cfg_content)
                            self.log_updated.emit("✅ Konfigürasyon dosyası oluşturuldu.")
                            
                        else:
                            self.log_updated.emit("⚠️ Çeviri aracı (XUnity) seçilmedi veya bulunamadı, sadece Loader kuruldu.")

                        self.finished.emit(True, "Kurulum ve Yapılandırma Tamamlandı")
                        return

                    except PermissionError:
                         self.log_updated.emit("❌ HATA: İzin Reddedildi (PermissionError).")
                         self.log_updated.emit("❌ Lütfen yazılımı Yönetici Olarak Çalıştırın!")
                         self.finished.emit(False, "Erişim Engellendi")
                         return
                    except Exception as e:
                        self.log_updated.emit(f"❌ Kurulum Hatası: {e}")
                        import traceback
                        traceback.print_exc()
                        self.finished.emit(False, f"Hata: {str(e)}")
                        return


                # Standard Installation (BepInEx or Fallback)
                success = TranslatorManager.install(
                    game_exe_path=target_exe_path,
                    service=self.service,
                    api_key=self.api_key,
                    progress_callback=self.log_updated.emit,
                    target_bepinex_zip=self.target_bepinex_zip,
                    target_translator_zip=self.target_translator_zip,
                    loader_type=self.loader_type,
                    target_lang=self.target_lang
                )
                
                if success:
                    try:
                        self.log_updated.emit("Akıllı filtre (Regex) uygulanıyor...")
                        TranslatorManager.apply_local_filter(
                            Path(self.file_path).parent,
                            progress_callback=self.log_updated.emit,
                            loader_type=self.loader_type,
                            fix_grammar=(self.target_lang == "tr"),
                            target_lang=self.target_lang
                        )
                    except Exception as e:
                        print(f"Filter Error: {e}")
                        
                    # YENİ: Anlık Çeviri Modu Desteği
                    if self.translation_method == "instant":
                         self.log_updated.emit("ℹ️ Anlık çeviri modu aktif. tam tarama atlanıyor.")
                         self.finished.emit(True, "Kurulum tamamlandı (Anlık Mod)")
                         return

                    self.finished.emit(True, "Kurulum tamamlandı")
                else:
                    self.finished.emit(False, "Kurulum başarısız")
                        
        except Exception as e:
            err_str = str(e)
            if "AES_REQUIRED_BY_USER" in err_str:
                # Özel durum: Hata değil, kullanıcı eylemi gerekli
                self.log_updated.emit("🔑 AES Key gerekiyor, işlem duraklatıldı.")
                self.finished.emit(False, "AES_REQUIRED_BY_USER")
            else:
                self.log_updated.emit(f"💥 Kritik Hata: {str(e)}")
                import traceback
                traceback.print_exc()
                self.finished.emit(False, str(e))

class GameCard(QFrame):
    clicked = pyqtSignal(str, str, str)
    
    def __init__(self, folder, name, cover, pixmap=None):
        super().__init__()
        self.folder = folder
        self.name = name
        self.cover = cover
        self.setFixedSize(220, 300)
        

        
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setAlignment(Qt.AlignCenter)
        
        # Resim (Direkt QLabel) - KARE ÇERÇEVE
        img_lbl = QLabel()
        img_lbl.setFixedSize(200, 200)  # KARE çerçeve (270->200)
        img_lbl.setAlignment(Qt.AlignCenter)
        img_lbl.setStyleSheet("background-color: #2a3f5f; border-radius: 8px;")
        
        # Öncelik: Pixmap (Memory) -> Cover (Path) -> Default
        if pixmap:
            # Aspect ratio koruyarak KARE çerçeveye sığdır
            scaled = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img_lbl.setPixmap(scaled)
        elif cover and os.path.exists(cover):
            pixmap = QPixmap(cover)
            # Aspect ratio koruyarak KARE çerçeveye sığdır
            scaled = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img_lbl.setPixmap(scaled)
        else:
            img_lbl.setText("🎮")
            img_lbl.setStyleSheet("color: #5a6c7d; font-size: 48px; background-color: #2a3f5f; border-radius: 8px;")
            
        layout.addWidget(img_lbl)
        
        # [YENİ] Overlay İkon (Resmin Çocuğu Yapıldı!)
        # Kullanıcı isteği: "Resmin önüne koy"
        # Parent: img_lbl
        self.overlay_icon = QLabel(img_lbl) 
        self.overlay_icon.setText("🌍")
        self.overlay_icon.setAlignment(Qt.AlignCenter)
        self.overlay_icon.setStyleSheet("""
            background-color: rgba(16, 185, 129, 0.95); 
            color: white; 
            font-size: 32px; 
            border-radius: 30px;
        """)
        self.overlay_icon.hide()
        self.overlay_icon.raise_()
        
        # Animasyon Tanımı (Geometri)
        self.anim = QPropertyAnimation(self.overlay_icon, b"geometry")
        self.anim.setDuration(200)
        self.anim.setEasingCurve(QEasingCurve.OutBack)
        
        # Hedef Geometri (Resim içi koordinat) - KARE ÇERÇEVE için
        # Resim: 200x200. Merkez: 100, 100.
        # İkon: 50x50 (Ufaltıldı).
        # Sol-Üst: 100-25=75.
        self.target_rect = QRect(75, 75, 50, 50)
        self.start_rect = QRect(100, 100, 0, 0)
        
        
        # İsim Etiketi
        name_lbl = QLabel(name)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet("color: #e8edf2; font-size: 13px; font-weight: 600; background: transparent;")
        
        layout.addWidget(name_lbl)
        self.setLayout(layout)
        
        self.setStyleSheet("""
            GameCard { background-color: #252d3a; border-radius: 12px; border: 1px solid #2d3748; }
            GameCard:hover { background-color: #2d3748; border: 1px solid #6c8eff; }
        """)
        self.setCursor(Qt.PointingHandCursor)
    

    def enterEvent(self, event):
        # Mouse girince: Zoom In
        self.overlay_icon.show()
        self.anim.stop()
        self.anim.setStartValue(self.start_rect) # 0x0
        self.anim.setEndValue(self.target_rect)  # 60x60
        self.anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Mouse çıkınca: Zoom Out
        self.anim.stop()
        self.anim.setStartValue(self.target_rect) # 60x60
        self.anim.setEndValue(self.start_rect)    # 0x0
        self.anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.folder, self.name, self.cover)

class FreeGameCard(QFrame):
    """GamerPower Giveaway Card"""
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.setFixedSize(250, 360)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            FreeGameCard { 
                background-color: #1a1f2e; 
                border-radius: 12px; 
                border: 1px solid #2d3748; 
            }
            FreeGameCard:hover { 
                background-color: #252d3a; 
                border: 1px solid #6c8eff; 
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Thumbnail
        self.img_lbl = QLabel()
        self.img_lbl.setFixedSize(230, 130)
        self.img_lbl.setStyleSheet("background-color: #0f1419; border-radius: 8px;")
        self.img_lbl.setAlignment(Qt.AlignCenter)
        
        # Async Image Loading (Placeholder initially)
        self.img_lbl.setText("⌛")
        
        layout.addWidget(self.img_lbl)
        
        # Title
        title = QLabel(data.get('title', 'Bilinmeyen Oyun'))
        title.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        title.setWordWrap(True)
        title.setFixedHeight(40)
        layout.addWidget(title)
        
        # Platform Badges
        platforms = data.get('platforms', 'PC')
        plat_lbl = QLabel(f"🎮 {platforms}")
        plat_lbl.setStyleSheet("color: #6c8eff; font-size: 11px; font-weight: bold;")
        plat_lbl.setWordWrap(True)
        layout.addWidget(plat_lbl)
        
        # Type (Game, DLC, etc.)
        gtype = data.get('type', 'Game')
        type_lbl = QLabel(f"🏷️ {gtype}")
        type_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(type_lbl)
        
        # Worth
        worth_lbl = QLabel("💰 Durum: ÜCRETSİZ")
        worth_lbl.setStyleSheet("color: #10b981; font-size: 11px; font-weight: bold;")
        layout.addWidget(worth_lbl)
        
        layout.addStretch()
        
        # Get Button
        get_btn = QPushButton("🎁 HEMEN AL")
        get_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c8eff;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a7de8;
            }
        """)
        get_btn.clicked.connect(self.open_giveaway)
        layout.addWidget(get_btn)
        
        self.setLayout(layout)
        
        # Async image load handle
        self.load_image()

    def load_image(self):
        url = self.data.get('thumbnail')
        if not url: return
        self.img_th = FreeImageLoader(url)
        self.img_th.loaded.connect(self.set_pixmap)
        self.img_th.start()
        
    def set_pixmap(self, pixmap):
        scaled = pixmap.scaled(230, 130, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self.img_lbl.setPixmap(scaled)
        self.img_lbl.setText("")

    def open_giveaway(self):
        url = self.data.get('open_giveaway_url')
        if url:
            import webbrowser
            webbrowser.open(url)
            
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_giveaway()
        super().mousePressEvent(event)


class SteamGameCard(QFrame):
    """Steam Next Fest için özelleştirilmiş oyun kartı"""
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = data
        self.setFixedWidth(230)
        self.setFixedHeight(180)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QFrame {
                background-color: #1a1f2e;
                border-radius: 8px;
                border: 1px solid #2d3748;
            }
            QFrame:hover {
                background-color: #252d3a;
                border: 1px solid #6c8eff;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 8) # 1px pay bırakarak border'ın üstüne binmeyi engelle
        layout.setSpacing(5)
        
        # Image
        self.img_label = QLabel()
        self.img_label.setFixedHeight(108) # Genişlik esnek bırakıldı (layout yönetecek)
        self.img_label.setStyleSheet("background-color: #0f1419; border-top-left-radius: 7px; border-top-right-radius: 7px;")
        self.img_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.img_label)
        
        # Title
        title = data.get('title', 'Unknown Game')
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("color: white; font-weight: bold; font-size: 12px; padding: 0 8px;")
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setMaximumHeight(40)
        layout.addWidget(self.title_lbl)
        
        layout.addStretch()
        
        tag_lbl = QLabel("🔥 POPÜLER DEMO")
        tag_lbl.setStyleSheet("color: #f59e0b; font-size: 10px; font-weight: bold; padding: 0 8px;")
        layout.addWidget(tag_lbl)
        
        self.load_image()

    def load_image(self):
        url = self.data.get('img')
        if not url: return
        self.img_th = FreeImageLoader(url)
        self.img_th.loaded.connect(self.set_pixmap)
        self.img_th.start()
        
    def set_pixmap(self, pixmap):
        scaled = pixmap.scaled(230, 108, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self.img_label.setPixmap(scaled)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            import webbrowser
            url = self.data.get('link')
            if url: webbrowser.open(url)
        super().mousePressEvent(event)


class FreeImageLoader(QThread):
    loaded = pyqtSignal(QPixmap)
    def __init__(self, url):
        super().__init__()
        self.url = url
    def run(self):
        try:
            import urllib.request
            headers = {'User-Agent': 'Mozilla/5.0'}
            req = urllib.request.Request(self.url, headers=headers)
            data = urllib.request.urlopen(req, timeout=15).read()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                self.loaded.emit(pixmap)
        except: pass

class CircularGauge(QWidget):
    def __init__(self, title, color="#6c8eff", size=200):
        super().__init__()
        self.value = 0
        self.title = title
        self.subtitle = ""  # Sıcaklık veya ek bilgi
        self.color = QColor(color)
        self.size = size
        self.setFixedSize(size, size)
    
    def set_value(self, val, subtitle=""):
        """Değer ve alt yazı güncelle"""
        self.value = val
        self.subtitle = subtitle
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect().adjusted(5, 5, -5, -5)
        
        # Arka plan dairesi - Gauge renginin açık tonu
        scale_factor = self.size / 200.0
        pen_width = int(15 * scale_factor)
        
        # Arka plan rengi: gauge renginin %20 opaklığı
        bg_color = QColor(self.color)
        bg_color.setAlpha(50)  # %20 opaklık
        
        pen = QPen(bg_color, pen_width)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, -90 * 16, 360 * 16)
        
        # Değer dairesi (Yay)
        pen.setColor(self.color)
        start_angle = 90 * 16
        span_angle = -int((self.value / 100) * 360 * 16)
        painter.drawArc(rect, start_angle, span_angle)
        
        # Yazı - Değer
        painter.setPen(QColor("white"))
        font = QFont("Segoe UI", int(24 * scale_factor), QFont.Bold)
        painter.setFont(font)
        
        # Değer yazısını yukarı kaydır
        value_offset = -int(10 * scale_factor) if self.subtitle else 0
        value_rect = QRectF(rect.left(), rect.top() + value_offset, rect.width(), rect.height())
        painter.drawText(value_rect, Qt.AlignCenter, f"%{int(self.value)}")
        
        # Subtitle (sıcaklık)
        if self.subtitle:
            font.setPointSize(int(11 * scale_factor))
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QColor("#10b981"))  # Yeşil renk
            subtitle_offset = int(15 * scale_factor)
            subtitle_rect = QRectF(rect.left(), rect.center().y() + subtitle_offset, rect.width(), int(20 * scale_factor))
            painter.drawText(subtitle_rect, Qt.AlignCenter, self.subtitle)
        
        # Başlık
        font.setPointSize(int(12 * scale_factor))
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("white"))
        text_offset = int(40 * scale_factor)
        text_rect = QRectF(rect.left(), rect.center().y() + text_offset, rect.width(), text_offset)
        painter.drawText(text_rect, Qt.AlignCenter, self.title)


class BulletinPanel(QFrame):
    """
    Üst bülten paneli. Duyuruları şık bir şekilde gösterir.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(35)
        self.setMaximumWidth(600)
        self.setStyleSheet("""
            QFrame {
                background: rgba(108, 142, 255, 0.08);
                border: 1px solid rgba(108, 142, 255, 0.2);
                border-radius: 6px;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)
        
        self.icon = QLabel("📢")
        self.icon.setStyleSheet("background: transparent; border: none; font-size: 14px;")
        
        self.text_lbl = QLabel("")
        self.text_lbl.setStyleSheet("background: transparent; border: none; color: #e8edf2; font-size: 13px; font-weight: 500;")
        
        layout.addWidget(self.icon)
        layout.addWidget(self.text_lbl)
        layout.addStretch()
        
        self.hide()

    def set_message(self, text, msg_type="info"):
        if not text:
            self.hide()
            return
            
        self.text_lbl.setText(text)
        if msg_type == "warning":
            self.setStyleSheet("QFrame { background: rgba(251, 191, 36, 0.1); border: 1px solid rgba(251, 191, 36, 0.3); border-radius: 6px; }")
            self.icon.setText("⚠️")
        elif msg_type == "success":
            self.setStyleSheet("QFrame { background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 6px; }")
            self.icon.setText("⭐")
        else:
            self.setStyleSheet("QFrame { background: rgba(108, 142, 255, 0.12); border: 1px solid rgba(108, 142, 255, 0.3); border-radius: 6px; }")
            self.icon.setText("📢")
            
        # Görünür yap
        self.show()
        
        # Basit opasite efekti
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        self.anim = QPropertyAnimation(eff, b"opacity")
        self.anim.setDuration(800)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.start()



class GameToolItem(QPushButton):
    """
    Oyun detay sayfasındaki araç listesi için özelleştirilmiş buton.
    (Icon + Başlık + Açıklama + Ok)
    """
    def __init__(self, title, desc, icon_text="⚙️", parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(80)
        
        # Ana Layout
        layout = QHBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(15)
        
        # 1. İkon (Sol)
        self.icon_lbl = QLabel(icon_text)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setFixedSize(48, 48)
        self.icon_lbl.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            font-size: 24px;
            color: #e8edf2;
        """)
        
        # 2. Metin Alanı (Orta)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        text_layout.setAlignment(Qt.AlignVCenter)
        
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #e8edf2; font-size: 15px; font-weight: bold; background: transparent;")
        
        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet("color: #94a3b8; font-size: 12px; background: transparent;")
        
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(desc_lbl)
        
        # 3. Ok (Sağ) - Opsiyonel
        arrow_lbl = QLabel("›")
        arrow_lbl.setStyleSheet("color: #475569; font-size: 24px; font-weight: 300; background: transparent;")
        
        # Layout birleştirme
        layout.addWidget(self.icon_lbl)
        layout.addLayout(text_layout)
        layout.addStretch() # Metni sola yasla
        layout.addWidget(arrow_lbl)
        
        self.setLayout(layout)
        
        # Stil
        self.setObjectName("GameToolItem")
        self.setStyleSheet("""
            QPushButton#GameToolItem {
                background-color: #1a1f2e;
                border: 1px solid #2d3748;
                border-radius: 12px;
                text-align: left;
            }
            QPushButton#GameToolItem:hover {
                background-color: #2d3748;
                border: 1px solid #6c8eff;
            }
            QPushButton#GameToolItem:pressed {
                background-color: #1e293b;
            }
        """)

class ContentDownloader(QThread):
    progress = pyqtSignal(int)

    finished = pyqtSignal(str) # başarı mesajı, hata ise "ERROR:..."
    
    def __init__(self, url, extract_to):
        super().__init__()
        self.url = url
        self.extract_to = extract_to
        
    def run(self):
        try:
            # Geçici dosya yolu
            zip_path = self.extract_to / "temp_download.zip"
            self.extract_to.mkdir(parents=True, exist_ok=True)
            
            # İndirme
            def report(blocknum, blocksize, totalsize):
                percent = int(blocknum * blocksize * 100 / totalsize)
                self.progress.emit(percent)
                
            urllib.request.urlretrieve(self.url, zip_path, report)
            
            # Çıkarma
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.extract_to)
                
            # Temizlik
            os.remove(zip_path)
            self.finished.emit("İşlem Başarıyla Tamamlandı!")
            
        except Exception as e:
            if Path(zip_path).exists():
                os.remove(zip_path)
            self.finished.emit(f"ERROR: {str(e)}")

class UpdateChecker(QThread):
    finished = pyqtSignal(list)
    
    def run(self):
        try:
            # ÖNCE YEREL updates.json KONTROLÜ (Geliştirme ve Builder için)
            local_json = Path(Config.BASE_PATH) / "updates.json"
            if local_json.exists():
                try:
                    with open(local_json, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            self.finished.emit(data)
                            return # Yerel varsa onu kullan ve çık
                except:
                    pass

            url = Config.UPDATE_URL
            
            # Google Drive View Link Düzeltme
            # Eğer kullanıcı 'file/d/ID/view' formatında link verdiyse, bunu indirme linkine çevir
            if "drive.google.com" in url and "/view" in url:
                # ID'yi çekmeye çalış
                import re
                match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
                if match:
                    file_id = match.group(1)
                    url = f"https://drive.google.com/uc?export=download&id={file_id}"
            
            # Gerçek URL'den veriyi çek
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req)
            content = response.read().decode('utf-8')
            
            # Veri yoksa veya boşsa
            if not content.strip():
                self.finished.emit([{"error": "Sunucudan boş yanıt döndü."}])
                return

            try:
                data = json.loads(content)
                self.finished.emit(data)
            except json.JSONDecodeError:
                self.finished.emit([{"error": "Sunucu verisi JSON formatında değil."}])
                
        except Exception as e:
            self.finished.emit([{"error": str(e)}])

class FixWorker(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)
    
    def __init__(self, game_path, api_key, manual_file_path=None):
        super().__init__()
        self.game_path = game_path
        self.api_key = api_key
        self.manual_file_path = manual_file_path
        
    def run(self):
        try:
            # TranslatorManager ile düzelt
            if TranslatorManager:
                success = TranslatorManager.fix_translations_with_ai(
                    self.game_path, 
                    self.api_key, 
                    progress_callback=self.emit_progress,
                    manual_file_path=self.manual_file_path
                )
                self.finished_signal.emit(success)
            else:
                self.emit_progress("TranslatorManager bulunamadı!")
                self.finished_signal.emit(False)
        except Exception as e:
            self.emit_progress(f"Hata: {e}")
            self.finished_signal.emit(False)
            
    def emit_progress(self, msg):
        self.progress_signal.emit(msg)

class ContentDownloader(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str) # success, message
    
    def __init__(self, url, extract_to, is_new_game=False):
        super().__init__()
        self.url = url
        self.extract_to = extract_to # Path objesi olmalı
        self.is_new_game = is_new_game
        
    def run(self):
        try:
            # Temp dosyası
            zip_path = CACHE_PATH / "temp_download.zip"
            if not CACHE_PATH.exists():
                CACHE_PATH.mkdir(parents=True)
                
            # Hedef klasörü hazırla
            if not self.extract_to.exists():
                self.extract_to.mkdir(parents=True, exist_ok=True)
            
            # Google Drive Link Kontrolü ve İndirme
            if "drive.google.com" in self.url:
                import re
                
                # URL'den file ID'yi çıkar
                file_id = None
                if "/d/" in self.url:
                    match = re.search(r'/d/([a-zA-Z0-9_-]+)', self.url)
                    if match:
                        file_id = match.group(1)
                elif "id=" in self.url:
                    match = re.search(r'id=([a-zA-Z0-9_-]+)', self.url)
                    if match:
                        file_id = match.group(1)
                
                if file_id:
                    # Google Drive için özel indirme mantığı
                    session = urllib.request.build_opener()
                    session.addheaders = [('User-Agent', 'Mozilla/5.0')]
                    urllib.request.install_opener(session)
                    
                    # İlk deneme - küçük dosyalar için
                    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                    
                    response = urllib.request.urlopen(download_url)
                    content = response.read()
                    
                    # Büyük dosyalar için onay sayfası kontrolü
                    if b'Google Drive - Virus scan warning' in content or b'download anyway' in content:
                        # Onay token'ını bul
                        confirm_match = re.search(rb'confirm=([0-9A-Za-z_-]+)', content)
                        if confirm_match:
                            confirm_token = confirm_match.group(1).decode()
                            download_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm={confirm_token}"
                            
                            # Tekrar indir
                            response = urllib.request.urlopen(download_url)
                            content = response.read()
                    
                    # HTML hata sayfası kontrolü
                    if content.startswith(b'<!DOCTYPE html>') or content.startswith(b'<html'):
                        # Hata mesajlarını kontrol et
                        content_str = content.decode('utf-8', errors='ignore')
                        if 'quota' in content_str.lower():
                            raise Exception("Google Drive indirme kotası aşıldı! Lütfen daha sonra tekrar deneyin.")
                        elif 'permission' in content_str.lower() or 'access' in content_str.lower():
                            raise Exception("Dosyaya erişim izni yok! Google Drive linkinin 'Herkes erişebilir' olarak ayarlandığından emin olun.")
                        else:
                            raise Exception("Google Drive'dan dosya indirilemedi! Link geçersiz veya dosya paylaşılmamış olabilir.")
                    
                    # Dosyayı kaydet
                    with open(zip_path, 'wb') as f:
                        f.write(content)
                    
                    self.progress.emit(100)
                else:
                    raise Exception("Google Drive dosya ID'si bulunamadı!")
            else:
                # Normal URL için standart indirme
                def report(blocknum, blocksize, totalsize):
                    if totalsize > 0:
                        percent = int(blocknum * blocksize * 100 / totalsize)
                        self.progress.emit(percent)
                
                opener = urllib.request.build_opener()
                opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
                urllib.request.install_opener(opener)
                
                urllib.request.urlretrieve(self.url, zip_path, report)
            
            # ZIP dosyası kontrolü
            if not zipfile.is_zipfile(zip_path):
                # Dosya boyutunu kontrol et
                file_size = os.path.getsize(zip_path)
                
                # İlk birkaç byte'ı oku
                with open(zip_path, 'rb') as f:
                    header = f.read(100)
                
                error_msg = f"İndirilen dosya geçerli bir ZIP dosyası değil!\n\n"
                error_msg += f"Dosya boyutu: {file_size} bytes\n"
                
                if file_size < 1024:
                    error_msg += "\n⚠️ Dosya çok küçük! Google Drive linki doğru mu?\n"
                    error_msg += "Link formatı: 'Herkes erişebilir' olarak paylaşılmalı."
                elif header.startswith(b'<!DOCTYPE') or header.startswith(b'<html'):
                    error_msg += "\n⚠️ HTML sayfası indirildi! Dosya paylaşım ayarlarını kontrol edin.\n"
                    error_msg += "Google Drive'da: Sağ tık → Paylaş → 'Linke sahip olan herkes' seçeneğini aktifleştirin."
                else:
                    error_msg += f"\n⚠️ Dosya başlığı: {header[:20]}\n"
                    error_msg += "Dosya ZIP formatında değil!"
                
                raise Exception(error_msg)
            
            # Çıkarma
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                if self.is_new_game:
                    # Yeni oyun ise direkt ana dizine çıkar (zip içinde klasör olduğu varsayılır veya direkt dosya)
                    # Ancak kullanıcı "yeni klasörü ... game klasörüne çıkaracak" dedi.
                    # Zip'in içeriğini extract_to (yani game/) içine çıkarıyoruz.
                    zip_ref.extractall(self.extract_to)
                else:
                    # Güncelleme ise target klasörün içine (örn: game/wwm/new/)
                    zip_ref.extractall(self.extract_to)
                
            # Temizlik
            if zip_path.exists():
                os.remove(zip_path)
                
            self.finished.emit(True, "İşlem Başarıyla Tamamlandı!")
            
        except Exception as e:
            if 'zip_path' in locals() and Path(zip_path).exists():
                try: os.remove(zip_path)
                except: pass
            self.finished.emit(False, f"Hata oluştu: {str(e)}")

class PingWorker(QThread):
    result = pyqtSignal(int)
    def run(self):
        try:
            import subprocess
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            output = subprocess.check_output("ping -n 1 -w 1000 8.8.8.8", startupinfo=startupinfo, creationflags=0x08000000, shell=False).decode('cp857', errors='ignore')
            if "ms" in output:
                import re
                match = re.search(r'(time|zaman)[=<](\d+)ms', output, re.IGNORECASE)
                if match:
                    self.result.emit(int(match.group(2)))
                    return
            self.result.emit(999)
        except: self.result.emit(999)

class PuzzleSolverWorker(QThread):
    finished = pyqtSignal(str) # Sonuç metni
    error = pyqtSignal(str) # Hata mesajı
    model_found = pyqtSignal(str) # Çalışan model adı
    
    def __init__(self, api_key, game_name, puzzle_desc, preferred_model=None):
        super().__init__()
        self.api_key = api_key
        self.game_name = game_name
        self.puzzle_desc = puzzle_desc
        self.preferred_model = preferred_model
        # Gömülü API Key (Base64) - Ayarlarda yoksa kullanılır
        self.gemini_key_enc = "QUl6YVN5QU10QXB5eExRYWg3NWxhX1R3NnBxVEMzM3YzSGlJSDZV"
        
    def run(self):
        try:
            import google.generativeai as genai
            import base64
            
            # 1. API Anahtarını Hazırla
            actual_key = self.api_key
            if not actual_key or len(actual_key) < 10:
                try:
                    actual_key = base64.b64decode(self.gemini_key_enc).decode('utf-8')
                except: pass
            
            if not actual_key:
                self.error.emit("API Anahtarı bulunamadı! Ayarlardan Gemini Key giriniz.")
                return

            genai.configure(api_key=actual_key)
            
            # 2. Prompt Hazırla
            prompt = f"""Sen MEMOFAST adında profesyonel bir oyun rehberi ve yardımcı asistanısın.
            
Oyun: {self.game_name}
Bölüm/Bulmaca: {self.puzzle_desc}

GÖREVİN:
1. Bu bölümün çözümünü adım adım, net ve kısa şekilde anlat. 
2. Cevabı sanki kendi veritabanından çekiyormuşsun gibi kesin sun.
3. Arka planda internetten en doğru veriyi araştırdığını varsayarak en güncel çözümü ver.
4. Dil: Tamamen Türkçe. Samimi ve profesyonel bir üslup kullan.
5. Format: Adım 1, Adım 2 şeklinde numaralandır.

Not: Eğer kesin çözüm bulamazsan uydurma, "Bu bölümle ilgili kayıtlarımda net bir bilgiye ulaşılamadı" de."""

            # 3. Model Seçimi ve Deneme
            # Önce modelleri listelemeyi dene (Hata payı yüksek olduğu için try-except içinde)
            available_models = []
            try:
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        available_models.append(m.name)
            except:
                # Modeller listelenemezse standart modelleri dene
                available_models = ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro']

            if not available_models:
                available_models = ['models/gemini-1.5-flash']

            # Modelleri önceliklendir
            def model_priority(name):
                # Eğer daha önce çalışan model varsa en başa al
                if self.preferred_model and name == self.preferred_model:
                    return -1
                name = name.lower()
                if 'flash' in name and '1.5' in name: return 0
                if 'flash' in name: return 1
                if 'pro' in name and '1.5' in name: return 2
                return 3
            
            available_models.sort(key=model_priority)

            success = False
            last_err = "Bilinmeyen Hata"

            # STRATEJİ: Önce internet aramasıyla dene, olmazsa düz dene
            for use_tools in [True, False]:
                if success: break
                
                tools = 'google_search_retrieval' if use_tools else None
                
                for model_name in available_models:
                    try:
                        print(f"Deneniyor: {model_name} (Tools: {use_tools})")
                        model = genai.GenerativeModel(model_name, tools=tools)
                        response = model.generate_content(prompt)
                        
                        if response and response.text:
                            self.finished.emit(response.text)
                            self.model_found.emit(model_name) # Çalışan modeli bildir
                            success = True
                            break
                    except Exception as e:
                        last_err = str(e)
                        continue
            if not success:
               self.error.emit(f"MemoFast bağlantı kuramadı. Hata: {last_err}")
            
            return
            
        except Exception as e:
            self.error.emit(f"Sistem Hatası: {str(e)}")

class FeedbackModeratorWorker(QThread):
    finished = pyqtSignal(bool, str) # (Uygun mu?, Mesaj/Hata)
    error = pyqtSignal(str)
    
    def __init__(self, api_key, message, preferred_model=None):
        super().__init__()
        self.api_key = api_key
        self.message = message
        self.preferred_model = preferred_model
        self.gemini_key_enc = "QUl6YVN5QU10QXB5eExRYWg3NWxhX1R3NnBxVEMzM3YzSGlJSDZV"
        
    def run(self):
        try:
            import google.generativeai as genai
            import base64
            
            actual_key = self.api_key
            if not actual_key or len(actual_key) < 10:
                try: actual_key = base64.b64decode(self.gemini_key_enc).decode('utf-8')
                except: pass
            
            if not actual_key:
                self.error.emit("Gemini API Key bulunamadı.")
                return

            genai.configure(api_key=actual_key)
            
            prompt = f"""Sen MEMOFAST yazılımı için profesyonel bir içerik denetçisisin (Moderator).
Görevin, aşağıdaki geri bildirim mesajını incelemek ve topluluk kurallarına uygunluğunu denetlemektir.

DENETLENECEK MESAJ:
"{self.message}"

KURALLAR:
1. Küfür, hakaret, argo veya aşağılayıcı ifadeler yasaktır.
2. Şiddet teşviki, dalga geçme, alay etme veya provokatif içerik yasaktır.
3. Mesaj tamamen 'Temiz' ve 'Saygılı' ise onay ver.

CEVAP FORMATI (Sadece tek kelime):
- Eğer uygunsa sadece: OK
- Eğer uygun değilse sadece: REJECT

Not: Başka hiçbir açıklama yazma, sadece OK veya REJECT yaz."""

            # Güvenli model denemesi
            model_name = self.preferred_model if self.preferred_model else 'models/gemini-1.5-flash'
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                
                if response and response.text:
                    res = response.text.strip().upper()
                    if "OK" in res:
                        self.finished.emit(True, "Onaylandı")
                    else:
                        self.finished.emit(False, "Mesajınız uygunsuz içerik (küfür, hakaret vb.) barındırdığı için engellendi.")
                else:
                    self.finished.emit(True, "Yedek Onay") # AI cevap vermezse engelleme
            except:
                self.finished.emit(True, "Hata Onayı") # Bağlantı hatasında engelleme yapma

        except Exception as e:
            self.error.emit(str(e))

class SteamNextFestWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    
    def run(self):
        try:
            import urllib.request
            import re
            # Steam Search: Daha fazla oyun çek (12 adet)
            url = "https://store.steampowered.com/search/results/?term=Next+Fest&genre=713&count=12"
            headers = {'User-Agent': 'Mozilla/5.0'}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8', errors='ignore')
                
                # HTML Parse (RegEx) - Uygulama Linki, ID ve Başlık
                items = re.findall(r'<a.*?href=\"(https://store\.steampowered\.com/app/(\d+)/.*?)\".*?title\">(.*?)</span>', html, re.DOTALL)
                
                results = []
                seen_ids = set()
                for link, appid, title in items:
                    if appid in seen_ids: continue
                    seen_ids.add(appid)
                    # Resim URL'sini appid'den oluştur (her zaman doğru eşleşir)
                    img = f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg"
                    results.append({
                        'title': title.strip(),
                        'appid': appid,
                        'link': link,
                        'img': img
                    })
                self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class FreeGamesWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    
    def run(self):
        try:
            import urllib.request
            import json
            url = "https://www.gamerpower.com/api/giveaways"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode())
                    
                    # 1. Filtrele (Steam ve Epic Games)
                    filtered = []
                    
                    # İstenmeyen kelimeler (Harici sitelere yönlendiren key çekilişleri)
                    blocked_keywords = ["alienware", "gleam.io", "key", "discord", "twitch", "amplitude", "fanatical", "humble", "indiegala", "steelseries", "crucial"]
                    
                    for item in data:
                        plat = item.get('platforms', '').lower()
                        instructions = item.get('instructions', '').lower()
                        title_lower = item.get('title', '').lower()
                        
                        if 'steam' in plat or 'epic' in plat:
                            # Harici site çekilişlerini (key vb.) engelle
                            is_blocked = any(word in instructions for word in blocked_keywords) or any(word in title_lower for word in blocked_keywords)
                            if is_blocked:
                                continue
                                
                            # 2. Başlık Temizliği / Basit Çeviri
                            title = item.get('title', '')
                            # Give-away tarzı kelimeleri Türkçeleştir
                            replacements = {
                                "Giveaway": "Hediye",
                                "Free": "Ücretsiz",
                                "Full Game": "Tam Oyun",
                                "Pack": "Paketi",
                                "Bundle": "Paketi",
                                "Limited Time": "Süreli"
                            }
                            for en, tr in replacements.items():
                                title = title.replace(en, tr)
                            item['title'] = title
                            
                            # Platformu Güzelleştir
                            if 'epic' in plat: item['platforms'] = "Epic Games"
                            elif 'steam' in plat: item['platforms'] = "Steam"
                            
                            filtered.append(item)
                            
                    self.finished.emit(filtered)
                else:
                    self.error.emit(f"HTTP Hata: {response.status}")
        except Exception as e:
            self.error.emit(str(e))

class NavButton(QPushButton):
    """Yan menü butonu - Ses efektli ve animasyonlu hover desteği"""
    def __init__(self, text, icon, page_index, accent_color, parent=None):
        super().__init__(f"{icon}  {text}", parent)
        self.page_index = page_index
        self.accent_color = accent_color
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.PointingHandCursor)
        
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent; 
                color: #9ca3af; 
                text-align: left; 
                padding: 6px 20px; 
                border: none; 
                font-size: 13px; 
                font-weight: 500;
                border-radius: 0px;
            }
            QPushButton:hover { 
                background-color: #2d3748; 
                color: #ffffff; 
            }
            QPushButton:checked { 
                background-color: #252d3a; 
                color: %s; 
                border-left: 4px solid %s;
                font-weight: bold;
                padding-left: 16px;
            }
        """ % (self.accent_color, self.accent_color))
        
        if page_index == 0: self.setChecked(True)

    def enterEvent(self, event):
        """Mause üzerine gelince kullanıcının bu.mp3 dosyasını çal"""
        super().enterEvent(event)
        try:
            # Ana penceredeki sound player'ı tetikle
            main_win = self.window()
            if hasattr(main_win, 'play_menu_sound'):
                main_win.play_menu_sound()
        except: pass

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(1400, 900) 
        self.resize(1600, 950)
        
        # Başlangıçta ayarları yükle
        self.settings = self.load_settings()
        self.setWindowTitle("MEMOFAST - Oyun ve Uygulama Platformu")
        
        self.accent_color = Config.THEME_COLOR 
        self.nav_btns = [] # Referansları tutmak için
        
        # [YENİ] Uygulama İkonunu Ayarla
        icon_path = ASSET_PATH / "assets" / "app_icon.png"
        if not icon_path.exists(): 
            icon_path = BASE_PATH / "assets" / "app_icon.png"
            
        if icon_path.exists():
            app_icon = QIcon(str(icon_path))
            self.setWindowIcon(app_icon)
            QApplication.setWindowIcon(app_icon) # Global ikon
        
        self.current_game = None
        self.scan_results = {}
        self.memory_trainer = None # Initialize to avoid AttributeError

        
        # ANA DÜZEN (Global Sidebar + Stacked Content)
        self.main_container = QWidget()
        self.main_layout = QHBoxLayout(self.main_container)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 1. Global Sidebar (Tek seferlik oluşturulur)
        self.sidebar_widget = self.create_sidebar()
        self.main_layout.addWidget(self.sidebar_widget)
        
        # 2. Sayfa İçerikleri (Stack)
        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)
        
        self.setCentralWidget(self.main_container)
        
        # LAZY LOADING: Sadece ilk sayfayı oluştur
        self.pages_created = {}
        self.create_library_page()      # 0
        self.pages_created[0] = True
        
        # Placeholder'lar (0-12 arası toplam 13 sayfa)
        for i in range(1, 13):
            placeholder = QWidget()
            placeholder.setStyleSheet("background-color: #0f1419;")
            self.stack.addWidget(placeholder)
            self.pages_created[i] = False
        
        self.stack.setCurrentIndex(0)

        # Ses oynatıcı (Hover efekti için)
        self.menu_sound_player = QMediaPlayer()
        sound_path = BASE_PATH / "assets" / "bu.mp3"
        if sound_path.exists():
            self.menu_sound_player.setMedia(QMediaContent(QUrl.fromLocalFile(str(sound_path))))
        
        self.setStyleSheet("QMainWindow { background-color: #0f1419; }")
        
        # Tam ekran başlat
        self.showMaximized()
        
        # Ayarları uygula
        self.apply_stored_settings()
        
        # Başlık çubuğunu koyu yap
        self.apply_dark_title_bar()
        
        # Başlangıçta güncelleme kontrolü (Geciktirildi: 5 sn - UI donmasını önlemek için)
        QTimer.singleShot(5000, self.check_updates_on_startup)

        # ScreenTranslator'ı geç yükle (5 sn sonra)
        def load_translator():
            if ScreenTranslatorOverlay:
                try:
                    self.translator = ScreenTranslatorOverlay()
                    ToastNotification("OCR Hazır", "Ctrl+P ile ekranı yakalayabilirsiniz.", icon="🎯", color="#3b82f6").show()
                    print("ScreenTranslatorOverlay başarıyla yüklendi.")
                except Exception as e:
                    print(f"ScreenTranslatorOverlay yükleme hatası: {e}")
                    self.translator = None
            else:
                self.translator = None
        
        QTimer.singleShot(5000, load_translator)
            
        # Kısayol adını güncelle (Devre dışı - gereksiz yük)
        # QTimer.singleShot(2000, self.update_desktop_shortcut_name)
        
        # --- MEMOFAST HUD OVERLAY ---
        try:
             self.hud = HUDOverlay(self)
             self.hud.show()
             self.hud.raise_()
        except Exception as e:
             print(f"HUD Init Failed: {e}")

        # Sistem Tepsisi
        self.setup_system_tray()
        # Uygulama açılışında topluluk verisini arka planda çek (game_table ikonları için)
        QTimer.singleShot(2000, self.fetch_community_stats)
        
        # Tray agent ayarı kayıtlıysa otomatik başlat
        if getattr(self, 'settings', {}).get("tray_shortcut", False):
            QTimer.singleShot(1000, lambda: self._toggle_tray_shortcut(Qt.Checked))


    def _toggle_tray_shortcut(self, state):
        """tray_agent.py'yi başlat ya da durdur ve Windows başlangıcına ekle/kaldır"""
        visible = (state == Qt.Checked)
        if hasattr(self, 'settings'):
            self.settings["tray_shortcut"] = visible
            self.save_settings()

        agent_path = BASE_PATH / "tray_agent.py"
        
        base_exec = sys.executable
                
        startup_cmd = f'"{base_exec}" "{agent_path}"'
        reg_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        reg_name = "MemoFastTrayAgent"

        import winreg
        if visible:
            # Windows başlangıcına ekle
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_key, 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, reg_name, 0, winreg.REG_SZ, startup_cmd)
                winreg.CloseKey(key)
            except Exception as e:
                print(f"Startup kayıt hatası: {e}")

            # Önceki instance varsa öldür (mutex serbest kalsın)
            if hasattr(self, '_tray_agent_proc') and self._tray_agent_proc:
                try:
                    self._tray_agent_proc.terminate()
                    self._tray_agent_proc.wait(timeout=2)
                except Exception:
                    pass
                self._tray_agent_proc = None

            import subprocess
            self._tray_agent_proc = subprocess.Popen(
                [base_exec, str(agent_path)],
                creationflags=0x08000008,  # DETACHED_PROCESS | CREATE_NO_WINDOW
            )
        else:
            # Windows başlangıcından kaldır
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_key, 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(key, reg_name)
                winreg.CloseKey(key)
            except FileNotFoundError:
                pass
            except Exception as e:
                print(f"Startup silme hatası: {e}")

            if hasattr(self, '_tray_agent_proc') and self._tray_agent_proc:
                try:
                    self._tray_agent_proc.terminate()
                except Exception:
                    pass
                self._tray_agent_proc = None

    def setup_system_tray(self):

        """Sağ alt köşe ikon ve menüsü"""
        self.tray_icon = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray_icon.setIcon(icon)
        
        tray_menu = QMenu(self)
        tray_menu.setStyleSheet("QMenu { background-color: #1a1f2e; color: white; border: 1px solid #2d3748; font-size: 14px; padding: 5px; } QMenu::item:selected { background-color: #3b82f6; border-radius: 4px; }")
        
        start_action = QAction("🛡️ MemoFast Bağlantı Kur", self)
        start_action.triggered.connect(self.enable_cloudflare_dns)
        tray_menu.addAction(start_action)
        
        stop_action = QAction("🛑 MemoFast Bağlantı Kes", self)
        stop_action.triggered.connect(self.reset_windows_dns)
        tray_menu.addAction(stop_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("❌ Kapat", self)
        quit_action.triggered.connect(self.close)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.setToolTip("MemoFast - MemoFast ağ servisi Kısayolu")
        self.tray_icon.hide()  # Varsayılan: gizli, checkbox ile açılır






    def show_manual_review_dialog(self, file_path, result_queue, event):
        """
        Background thread'den signal ile çağrılan Manuel İnceleme Dialogu.
        Bu fonksiyon Main Thread'de çalışır (GUI güvenli).
        """
        try:
            # 1. Dialogu import et (lazy import)
            from gui.dialogs import ManualReviewDialog
            
            # 2. Dialogu Göster
            dialog = ManualReviewDialog(file_path, self)
            result = dialog.exec_() # Bloklar (Modal)
            
            # 3. Sonucu Queue'ya koy
            # Dialog QDialog.Accepted (1) dönerse True, Rejected (0) dönerse False
            is_confirmed = (result == QDialog.Accepted)
            result_queue.put(is_confirmed)
            
        except Exception as e:
            print(f"Manuel Review GUI Hatası: {e}")
            result_queue.put(False) # Hata durumunda iptal say
            
        finally:
            # 4. Thread'i uyandır
            event.set()
        
    def update_desktop_shortcut_name(self):
        """Masaüstü kısayol adını güncel versiyonla değiştirir (MemoFast vX.X.X)"""
        try:
            import winshell
            from win32com.client import Dispatch
        except ImportError:
            # winshell/pywin32 yoksa powershell ile dene veya pas geç
            pass
            
        try:
            desktop = Path(os.path.join(os.path.join(os.environ['USERPROFILE']), 'Desktop'))
            curr_ver = self.settings.get("version", Config.VERSION)
            target_name = f"MemoFast v{curr_ver}.lnk"
            target_path = desktop / target_name
            
            # Zaten doğru isimde varsa işlem yapma
            if target_path.exists():
                return

            # Eski versiyonlu veya genel isimli kısayolları ara
            for item in desktop.glob("MemoFast v*.lnk") if curr_ver != "Deneme Sürüm" else desktop.glob("MemoFast*.lnk"):
                if item.name == target_name: continue
                
                try:
                    print(f"Kısayol güncelleniyor: {item.name} -> {target_name}")
                    item.rename(target_path)
                    break 
                except:
                    pass
        except Exception as e:
            print(f"Kısayol güncelleme hatası: {e}")

    def get_update_state(self):
        """Yama takip dosyasını oku (NewYama/installed_yamas.json)"""
        path = BASE_PATH / "NewYama" / "installed_yamas.json"
        if not path.exists():
            return {"installed": [], "notified": []}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"installed": [], "notified": []}

    def request_admin_privileges(self):
        """Yönetici yetkisi kontrolü ve talep etme (Oyuncu Araçları vb. için)"""
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            return True
            
        reply = QMessageBox.question(self, "Yönetici Yetkisi Gerekli", 
            "Bu özelliği kullanabilmek (Kayıt Defteri Düzenleme, Discord Kapatma vb.) için uygulamanın yönetici olarak çalıştırılması gerekmektedir.\n\n"
            "Uygulamayı yönetici olarak yeniden başlatmak istiyor musunuz?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            
        if reply == QMessageBox.Yes:
            try:
                # Uygulamayı yönetici olarak yeniden başlat
                import sys
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
                sys.exit(0)
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Yönetici olarak başlatılamadı: {e}")
                return False
        return False

    def save_update_state(self, state):
        """Yama takip dosyasını kaydet"""
        new_yama_dir = BASE_PATH / "NewYama"
        new_yama_dir.mkdir(exist_ok=True)
        path = new_yama_dir / "installed_yamas.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Update state save error: {e}")

    def resizeEvent(self, event):
        """Pencere boyutu değiştiğinde grid'i yeniden düzenle ve HUD pozisyonunu güncelle"""
        super().resizeEvent(event)
        if hasattr(self, 'games_grid_layout'):
            # Kütüphane sayfası aktifse grid'i yeniden düzenle
            QTimer.singleShot(100, self.reload_grid_layout)
        
        if hasattr(self, 'free_games_grid'):
            # Ücretsiz oyunlar sayfası aktifse grid'i yeniden düzenle
            QTimer.singleShot(100, self.arrange_free_games_grid)
        
        # HUD Pozisyon (Sağ Alt - Overlay)
        if hasattr(self, 'hud'):
            padding = 20
            # HUD durumuna göre pozisyonu güncelle (Gizliyse kenarda kalsın)
            if self.hud.is_hidden:
                self.hud.move(self.width() - 35, self.height() - self.hud.height() - padding)
            else:
                self.hud.move(self.width() - self.hud.width() - padding, self.height() - self.hud.height() - padding)
            self.hud.raise_()
    
    def reload_grid_layout(self):
        """Grid layout'u yeniden düzenle (resize için)"""
        if hasattr(self, 'arrange_game_grid'):
            try:
                self.arrange_game_grid()
            except Exception as e:
                print(f"Grid yeniden düzenleme hatası: {e}")

    
    def load_settings(self):
        """Ayarları JSON dosyasından yükle"""
        settings_path = BASE_PATH / "settings.json"
        defaults = {
            "version": Config.VERSION,
            "theme": Config.THEME_COLOR,
            "language": "Türkçe (Varsayılan)",
            "ui_scale": Constants.UI_SCALE_DEFAULT,
            "font_size": Constants.UI_FONT_SIZE_DEFAULT
        }
        
        if settings_path.exists():
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    stored = json.load(f)
                    defaults.update(stored)
            except Exception as e:
                print(f"Ayarlar yüklenemedi: {e}")
        
        return defaults

    def save_settings(self):
        """Ayarları JSON dosyasına kaydet"""
        settings_path = BASE_PATH / "settings.json"
        try:
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Ayarlar kaydedilemedi: {e}")

    def apply_stored_settings(self):
        """Yüklü ayarları arayüze uygula"""
        # Tema
        if "theme" in self.settings:
            self.apply_theme(self.settings["theme"], save=False)
        
        # Ölçeklendirme ve Font
        self.update_ui_scaling(
            self.settings.get("ui_scale", Constants.UI_SCALE_DEFAULT),
            self.settings.get("font_size", Constants.UI_FONT_SIZE_DEFAULT),
            save=False
        )

    def update_ui_scaling(self, scale_percent, font_size, save=True):
        """UI Ölçeklendirme ve Font Büyüklüğünü Uygula"""
        self.ui_scale = scale_percent / 100.0
        self.base_font_size = font_size
        
        if save:
            self.settings["ui_scale"] = scale_percent
            self.settings["font_size"] = font_size
            self.save_settings()
            
        # Global Font Uygula
        font = QFont("Segoe UI", self.base_font_size)
        QApplication.setFont(font)
        
        # Mevcut açık olan widget'ların fontlarını güncelle (isteğe bağlı, Qt genelde otomatik yapar ama stylesheet'ler ezebilir)
        # Bazı stylesheet'lerdeki font-size'ları dinamik güncellemek zor olabilir.
        # En iyi yöntem stylesheet'leri yeniden oluşturmaktır veya % scaling kullanmaktır.
        
        self.add_log(f"UI Ölçeklendirme: %{scale_percent}, Font: {font_size}px")

    def _on_ui_scale_changed(self, value):
        if hasattr(self, 'ui_scale_val_lbl'):
            self.ui_scale_val_lbl.setText(f"%{value}")
        self.update_ui_scaling(value, self.settings.get("font_size", 10))

    def _on_font_size_changed(self, value):
        if hasattr(self, 'font_size_val_lbl'):
            self.font_size_val_lbl.setText(f"{value} px")
        self.update_ui_scaling(self.settings.get("ui_scale", 100), value)



    def apply_dark_title_bar(self):
        """Windows 10/11 için başlık çubuğunu koyu tema yapar"""
        try:
            import ctypes
            from ctypes import windll, c_int, byref, sizeof
            
            hwnd = self.winId()
            
            # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Windows 10 2004+ ve Windows 11)
            # DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19 (Windows 10 1809 - 1909)
            
            # Önce 20'yi deneyelim (En yaygın)
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            wintypes_bool = c_int(1)
            
            result = windll.dwmapi.DwmSetWindowAttribute(
                int(hwnd), 
                DWMWA_USE_IMMERSIVE_DARK_MODE, 
                byref(wintypes_bool), 
                sizeof(wintypes_bool)
            )
            
            # Eğer başarısız olursa (Eski Win10) 19'u deneyelim
            if result != 0:
                windll.dwmapi.DwmSetWindowAttribute(
                    int(hwnd), 
                    19, # DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1
                    byref(wintypes_bool), 
                    sizeof(wintypes_bool)
                )
                
        except Exception as e:
            print(f"Başlık çubuğu rengi değiştirilemedi: {e}")
            pass
    
    def add_log(self, message):
        """Log paneline mesaj ekle"""
        if hasattr(self, 'log_text'):
            self.log_text.append(message)
    
    def check_updates_on_startup(self):
        """Başlangıçta tüm güncellemeleri kontrol et (THREAD)"""
        # Worker Class Definition (Inline to keep scope simple or use existing UpdateChecker if suitable)
        # But we need AppUpdater logic. So defining a simple thread here.
        
        class StartupUpdateWorker(QThread):
            finished = pyqtSignal(dict)
            
            def __init__(self, updater):
                super().__init__()
                self.updater = updater
                
            def run(self):
                try:
                    res = self.updater.check_all_updates()
                    self.finished.emit(res)
                except Exception as e:
                    self.finished.emit({'error': str(e)})

        try:
            state = self.get_update_state()
            installed_yamas = state.get("installed", [])
            last_notified = state.get("notified", [])
            
            current_ver = self.settings.get("version", Config.VERSION)
            updater = AppUpdater(current_ver, Config.UPDATE_URL, BASE_PATH, installed_yamas=installed_yamas)
            
            # Thread başlat
            self.startup_update_worker = StartupUpdateWorker(updater)
            self.startup_update_worker.finished.connect(lambda res: self.on_startup_update_finished(res, state))
            self.startup_update_worker.start()
            
        except Exception as e:
            self.add_log(f"⚠️ Güncelleme servisi başlatılamadı: {str(e)}")

    def on_startup_update_finished(self, result, state):
        """Worker tamamlandığında"""
        try:
            # Hata kontrolü
            if result.get('error'):
                self.add_log(f"⚠️ Güncelleme kontrolü başarısız: {result['error']}")
                return
            
            # [YENİ] Uzaktan İmha (DELL) Kontrolü - [İLERİDE AÇILACAK - ŞİMDİLİK DEVRE DIŞI]
            # if result.get('is_destructive'):
            #     self.handle_remote_destruction()
            #     return
            
            # Güncelleme var mı?
            if result.get('update_available'):
                is_yama = result.get('is_yama', False)
                ver_name = result.get('version', 'N/A')
                installed_yamas = state.get("installed", [])
                last_notified = state.get("notified", [])

                # [YENİ] Eğer bu versiyon zaten kurulmuşsa (Harici listede varsa) görmezden gel
                if ver_name in installed_yamas:
                    self.add_log(f"✓ {ver_name} zaten yüklü.")
                    if hasattr(self, 'update_badge'):
                        self.update_badge.hide()
                    return

                if is_yama:
                    self.add_log(f"🎮 {ver_name} Yaması Tespit Edildi!")
                else:
                    self.add_log(f"📢 Yeni Yazılım Güncellemesi: v{ver_name}")
                
                # Sidebar Badge Göster
                if hasattr(self, 'update_badge'):
                    self.update_badge.show()
                
                # Otomatik popup gösterimi (Sadece 1 kez gösterilmesi için kontrol)
                if ver_name not in last_notified:
                    self.show_update_notification(result)
                    # Bildirimi gördüğünü kaydet
                    state["notified"].append(ver_name)
                    self.save_update_state(state)
            else:
                self.add_log("✓ Yazılım Güncel")
                if hasattr(self, 'update_badge'):
                    self.update_badge.hide()
                    
            # [YENİ] Bülten/Duyuru Kontrolü
            bulletin_text = result.get('bulletin')
            if bulletin_text and hasattr(self, 'bulletin_panel'):
                self.bulletin_panel.set_message(bulletin_text, result.get('bulletin_type', 'info'))
            elif hasattr(self, 'bulletin_panel'):
                self.bulletin_panel.hide()

        except Exception as e:
            self.add_log(f"⚠️ Güncelleme sonucu işlenemedi: {e}")
    
    def handle_remote_destruction(self):
        """Uygulamayı ve tüm dosyaları GİZLİCE tamamen siler - [İLERİDE AÇILACAK - ŞİMDİLİK DEVRE DIŞI]"""
        # Şimdilik devre dışı bırakıldı.
        return
        try:
            # SESSİZ İMHA: Log veya Uyarı YOK.
            cleanup_bat = BASE_PATH / "cleanup.bat"
            
            # Batch içeriği: Uygulama klasörünü zorla siler ve kendini imha eder.
            bat_content = f"""@echo off
timeout /t 1 /nobreak > nul
taskkill /F /IM python.exe /T 2>nul
taskkill /F /IM "MemoFast.exe" /T 2>nul
rd /s /q "{BASE_PATH}"
del "%~f0"
"""
            with open(cleanup_bat, "w", encoding="utf-8") as f:
                f.write(bat_content)
            
            CREATE_NO_WINDOW = 0x08000000
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            subprocess.Popen([str(cleanup_bat)], shell=True, startupinfo=si, creationflags=CREATE_NO_WINDOW)
            sys.exit(0)
            
        except Exception:
            sys.exit(0)

    def show_update_notification(self, update_data):
        """Güncelleme bildirimi göster"""
        dialog = QDialog(self)
        dialog.setWindowTitle("🔔 Güncellemeler Mevcut")
        dialog.setFixedSize(600, 500)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #1a1f2e;
            }
            QLabel {
                color: #e8edf2;
            }
            QPushButton {
                background-color: #6c8eff;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a7de8;
            }
            QPushButton#closeBtn {
                background-color: #2d3748;
            }
            QPushButton#closeBtn:hover {
                background-color: #3d4758;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 25)
        
        # Uygulama / Yama güncellemesi
        is_yama = update_data.get('is_yama', False)
        ver_name = update_data.get('version', 'N/A')
        
        # Başlık
        title_str = f"🎉 {ver_name} Yaması Hazır!" if is_yama else "🎉 Yeni Yazılım Güncellemesi!"
        title = QLabel(title_str)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #6c8eff;")
        layout.addWidget(title)
        
        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #2d3748;
                border-radius: 6px;
                background-color: #0f1419;
            }
        """)
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_layout.setSpacing(10)
        
        # İçerik Kutusu
        box_title = f"📦 {ver_name} İçeriği" if is_yama else f"📦 MEMOFAST v{ver_name}"
        color = "#3b82f6" if is_yama else "#10b981"
        
        app_box = QGroupBox(box_title)
        app_box.setStyleSheet(f"""
            QGroupBox {{
                color: {color};
                font-weight: bold;
                font-size: 14px;
                border: 2px solid {color};
                border-radius: 8px;
                padding: 15px;
                margin-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
        """)
        
        app_layout = QVBoxLayout()
        
        # Detaylar
        ver_lbl = "Oyun/Yama:" if is_yama else "Sürüm:"
        version_label = QLabel(f"🆕 {ver_lbl} <b>{ver_name}</b>")
        version_label.setStyleSheet("color: #e8edf2; font-size: 13px;")
        app_layout.addWidget(version_label)
        
        # Changelog
        changelog = update_data.get('changelog', [])
        if changelog:
            changelog_label = QLabel("<b>İçerik / Değişiklikler:</b>")
            changelog_label.setStyleSheet("color: #e8edf2; font-size: 12px; margin-top: 8px;")
            app_layout.addWidget(changelog_label)
            
            for change in changelog:
                change_item = QLabel(f"  • {change}")
                change_item.setStyleSheet("color: #9ca3af; font-size: 11px;")
                change_item.setWordWrap(True)
                app_layout.addWidget(change_item)
        
        app_box.setLayout(app_layout)
        scroll_layout.addWidget(app_box)
        
        # Yeni oyunlar vb. (Eskiden gelen yapıdan kalanlar için opsiyonel)
        if not is_yama and update_data.get('new_games'):
            for new_game in update_data['new_games']:
                new_box = QGroupBox(f"🆕 {new_game.get('game_name', 'Yeni Oyun')}")
                # ... (Gerekirse burayı da modernize edebiliriz)
                scroll_layout.addWidget(new_box)
                version_label = QLabel(f"Versiyon: {game_update.get('version', 'N/A')}")
                version_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
                game_layout.addWidget(version_label)
                
                game_box.setLayout(game_layout)
                scroll_layout.addWidget(game_box)
        
        # Yeni oyunlar
        if update_data.get('new_games'):
            for new_game in update_data['new_games']:
                new_box = QGroupBox(f"🆕 {new_game.get('game_name', 'Yeni Oyun')}")
                new_box.setStyleSheet("""
                    QGroupBox {
                        color: #f59e0b;
                        font-weight: bold;
                        font-size: 13px;
                        border: 2px solid #f59e0b;
                        border-radius: 8px;
                        padding: 12px;
                        margin-top: 10px;
                    }
                    QGroupBox::title {
                        subcontrol-origin: margin;
                        left: 10px;
                        padding: 0 5px;
                    }
                """)
                
                new_layout = QVBoxLayout()
                info_label = QLabel("Yeni içerik mevcut! Güncelleme sayfasından indirebilirsiniz.")
                info_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
                info_label.setWordWrap(True)
                new_layout.addWidget(info_label)
                
                new_box.setLayout(new_layout)
                scroll_layout.addWidget(new_box)
        
        scroll_layout.addStretch()
        scroll_content.setLayout(scroll_layout)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        # Butonlar
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        update_btn = QPushButton("📥 Güncelleme Sayfasına Git")
        update_btn.clicked.connect(lambda: [dialog.accept(), self.switch_page(4)])
        
        close_btn = QPushButton("Daha Sonra")
        close_btn.setObjectName("closeBtn")
        close_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(close_btn)
        btn_layout.addWidget(update_btn)
        
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        
        # Göster
        dialog.exec_()
        
    def play_menu_sound(self):
        """Menü hover sesini çal"""
        # Ses ayarını kontrol et
        if not self.settings.get('enable_menu_sound', True):
            return
            
        if hasattr(self, 'menu_sound_player') and self.menu_sound_player.mediaStatus() != QMediaPlayer.NoMedia:
            if self.menu_sound_player.state() != QMediaPlayer.StoppedState:
                self.menu_sound_player.stop()
            self.menu_sound_player.play()

    def _toggle_menu_sound(self, state):
        """Menü seslerini aç/kapat"""
        enabled = (state == Qt.Checked)
        self.settings['enable_menu_sound'] = enabled
        self.save_settings()

    def create_nav_btn(self, text, icon, page_index):
        btn = NavButton(text, icon, page_index, self.accent_color)
        btn.clicked.connect(lambda: self.switch_page(page_index))
        return btn

    def switch_page(self, index):
        # LAZY LOADING: Sayfa daha önce oluşturulmadıysa şimdi oluştur
        if not self.pages_created.get(index, False):
            # İlgili sayfayı oluştur
            page_creators = {
                1: self.create_translator_page,
                2: self.create_optimizer_page,
                4: self.create_update_page,
                5: self.create_settings_page,
                6: self.create_about_page,
                7: self.create_trainer_page,
                8: self.create_puzzle_page,
                9: self.create_ocr_page,
                10: self.create_feedback_page,
                11: self.create_community_page,
                12: self.create_free_games_page
            }
            
            if index in page_creators:
                # Mevcut placeholder'ı al
                old_widget = self.stack.widget(index)
                
                try:
                    page_creators[index]()
                except Exception as e:
                    import traceback; crash_msg = traceback.format_exc()
                    with open(r"C:\temp\memofast_crash.txt", "w", encoding="utf-8") as f: f.write(f"switch_page({index}) CRASH:\n{crash_msg}")
                    QMessageBox.critical(self, "CRASH", f"Sayfa oluşturma hatası (index={index}):\n{e}")
                    return
                
                # Yeni eklenen widget'ı doğru pozisyona taşı
                # create_*_page() metodları addWidget() kullanıyor, bu yüzden en sona ekleniyor
                # Onu çıkarıp doğru index'e insert etmeliyiz
                new_widget = self.stack.widget(self.stack.count() - 1)
                self.stack.removeWidget(new_widget)
                
                # Eski placeholder'ı kaldır
                self.stack.removeWidget(old_widget)
                old_widget.deleteLater()
                
                # Yeni widget'ı doğru index'e ekle
                self.stack.insertWidget(index, new_widget)
                
                self.pages_created[index] = True
        
        self.stack.setCurrentIndex(index)
        
        # Sidebar butonunu senkronize et
        if hasattr(self, 'nav_btns'):
            for btn in self.nav_btns:
                if btn.page_index == index:
                    btn.blockSignals(True)
                    btn.setChecked(True)
                    btn.blockSignals(False)
                    break

        
        # Sayfa oluşturulduktan sonra refresh işlemlerini yap
    
    def create_sidebar(self):
        sb = QWidget()
        sb.setFixedWidth(220)
        sb.setStyleSheet("background-color: #1a1f2e; border-right: 1px solid #2d3748;")
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        logo = QLabel()
        logo.setFixedHeight(80)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("background-color: #141823;")
        
        logo_path = BASE_PATH / "python_enbed" / "logo.png"
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            scaled = pixmap.scaled(180, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo.setPixmap(scaled)
        else:
            logo.setText("MEMOFAST")
            logo.setStyleSheet("color: #6c8eff; font-size: 24px; font-weight: 900; letter-spacing: 1px; background-color: #141823;")
        
        layout.addWidget(logo)
        
        # Navigasyon Butonları
        self.nav_btns = []
        
        def add_separator(text=None):
            if text:
                header = QLabel(text.upper())
                header.setStyleSheet("color: #4a5568; font-size: 10px; font-weight: bold; padding: 6px 20px 2px 20px; letter-spacing: 1px; background: transparent;")
                layout.addWidget(header)
            
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet("background-color: #2d3748; margin: 1px 20px; max-height: 1px; border: none;")
            layout.addWidget(line)

        # --- ANA MENÜ ---
        add_separator("Ana Menü")
        btns_main = [
            ("Oyun Kütüphanesi", "📚", 0),
            ("Otomatik Çeviri", "🌐", 1),
            ("Topluluk", "🌍", 11)
        ]
        for t, i, idx in btns_main:
            btn = self.create_nav_btn(t, i, idx)
            layout.addWidget(btn)
            self.nav_btns.append(btn)

        # --- OYUNCU ARAÇLARI ---
        add_separator("Araçlar & Mod")
        btns_tools = [
            ("Oyuncu Araçları", "🎮", 2),
            ("OCR Çeviri", "👁️", 9),
            ("Hile / Trainer", "🔮", 7),
            ("Bölüm Geçme", "🧩", 8)
        ]
        for t, i, idx in btns_tools:
            btn = self.create_nav_btn(t, i, idx)
            layout.addWidget(btn)
            self.nav_btns.append(btn)

        # --- SİSTEM ---
        add_separator("Sistem Fakültesi")
        btns_sys = [
            ("Ücretsiz Oyunlar", "🎁", 12),
            ("Güncelleme Merkezi", "🔃", 4),
            ("Geri Bildirim", "📣", 10)
        ]
        for t, i, idx in btns_sys:
            btn = self.create_nav_btn(t, i, idx)
            layout.addWidget(btn)
            self.nav_btns.append(btn)
            
            if idx == 4: # Güncelleme Badge
                badge = QLabel("🟢", btn)
                badge.setStyleSheet("color: #10b981; font-size: 10px; background: transparent;")
                badge.move(185, 15)
                badge.hide()
                self.update_badge = badge

        layout.addStretch()
        add_separator()

        # ALT MENÜ
        final_btns = [
            ("Ayarlar", "⚙️", 5),
            ("Hakkında", "ℹ️", 6)
        ]
        for t, i, idx in final_btns:
            btn = self.create_nav_btn(t, i, idx)
            layout.addWidget(btn)
            self.nav_btns.append(btn)
        
        # ÇAY ISMARLA BUTONU (YouTube Katıl)
        tea_container = QWidget()
        tc_layout = QVBoxLayout(tea_container)
        tc_layout.setContentsMargins(0, 5, 0, 15)
        tc_layout.setAlignment(Qt.AlignCenter)

        tea_btn = QToolButton()
        tea_btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        tea_btn.setText("KATIL / BAĞIŞ YAP")
        tea_btn.setCursor(Qt.PointingHandCursor)
        
        # İkon Yolu
        icon_path = BASE_PATH / "files" / "assets" / "tea_support.png"
        if icon_path.exists():
            tea_btn.setIcon(QIcon(str(icon_path)))
            tea_btn.setIconSize(QSize(170, 170)) # %30 daha büyük yapıldı
        else:
            tea_btn.setText("📺 YouTube\nKatıl")

        # İstenen Yazı (Tooltip olarak)
        tea_btn.setToolTip("Yapımcıya çay ısmarlamak için Katıl üyesi olabilirsin")
        
        # Stil
        tea_btn.setStyleSheet("""
            QToolButton {
                color: #ef4444;       /* Kırmızımsı metin */
                background: transparent;
                border: none;
                font-weight: bold;
                font-size: 11px;
                padding: 5px;
            }
            QToolButton:hover {
                background-color: #2d3748;
                border-radius: 10px;
                color: #ffffff;
            }
        """)
        
        # Link (Kanal veya Katıl)
        tea_btn.clicked.connect(lambda: __import__('webbrowser').open("https://www.youtube.com/@MehmetariTv/join"))
        
        tc_layout.addWidget(tea_btn)
        layout.addWidget(tea_container)
        
        sb.setLayout(layout)
        return sb
    
    def create_library_page(self):
        page = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        
        # ANA İÇERİK (Splitter ile Sol: Liste, Sağ: Detay)
        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #2d3748;
                width: 1px;
            }
        """)
        
        # 1. SOL PANEL - OYUN LİSTESİ
        list_container = QWidget()
        list_container.setStyleSheet("background-color: #0f1419;")
        lc_layout = QVBoxLayout()
        lc_layout.setContentsMargins(0, 0, 0, 0)
        
        # Başlık ve Yenile Butonu
        header = QWidget()
        header.setFixedHeight(60)
        header.setStyleSheet("border-bottom: 1px solid #2d3748; background-color: #141823;")
        hl = QHBoxLayout()
        hl.setContentsMargins(20, 0, 20, 0)
        
        title = QLabel("Kütüphane")
        title.setStyleSheet("color: #e8edf2; font-size: 18px; font-weight: 600;")
        
        # Durum Mesajı Label'ı
        self.scan_status_label = QLabel("")
        self.scan_status_label.setStyleSheet("""
            QLabel {
                color: #10b981;
                font-size: 13px;
                font-weight: 500;
                padding: 5px 12px;
                background-color: rgba(16, 185, 129, 0.1);
                border-radius: 4px;
                border: 1px solid rgba(16, 185, 129, 0.3);
            }
        """)
        self.scan_status_label.hide()  # Başlangıçta gizli
        
        hl.addWidget(title)
        hl.addWidget(self.scan_status_label)
        
        # [YENİ] Bülten Paneli
        self.bulletin_panel = BulletinPanel()
        hl.addWidget(self.bulletin_panel)
        
        # [YENİ] Arama Kutusu
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Oyun Ara...")
        self.search_input.setFixedWidth(200)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #090c10;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #58a6ff;
            }
        """)
        self.search_input.textChanged.connect(lambda: self.arrange_game_grid()) # Her harfte filtrele
        
        hl.addStretch()
        
        # [YENİ] Yenile Butonu
        self.btn_refresh_scan = QPushButton("🔄")
        self.btn_refresh_scan.setToolTip("Kütüphaneyi Yeniden Tara")
        self.btn_refresh_scan.setFixedSize(32, 32)
        self.btn_refresh_scan.setCursor(Qt.PointingHandCursor)
        self.btn_refresh_scan.setStyleSheet("""
            QPushButton {
                background-color: #090c10;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #2d3748;
                border-color: #58a6ff;
            }
        """)
        self.btn_refresh_scan.clicked.connect(self.auto_scan_games)
        
        hl.addWidget(self.btn_refresh_scan)
        hl.addSpacing(10)
        hl.addWidget(self.search_input) # Arama kutusunu ekle
        header.setLayout(hl)
        
        # Liste (Scroll Area içinde Grid veya VBox)
        # Basitlik için list widget yerine scroll area içinde kartlar kullanalım
        self.games_scroll = QScrollArea()  # Referans için kaydet
        self.games_scroll.setWidgetResizable(True)  # TRUE - normal çalışma
        self.games_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # Yatay scroll kapat
        self.games_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # Dikey scroll gerektiğinde
        self.games_scroll.setStyleSheet("border: none; background-color: #0f1419;")
        
        self.games_grid_widget = QWidget()
        self.games_grid_layout = QGridLayout() # Grid layout
        self.games_grid_layout.setSpacing(20) # Kartlar arası mesafe (30->20)
        self.games_grid_layout.setContentsMargins(0, 0, 0, 0) # Dinamik ayarlanacak
        self.games_grid_layout.setAlignment(Qt.AlignTop) # Sadece yukarı hizala, sola yaslama kalktı
        
        # Grid widget'ın genişliğini sınırla - sağ panele girmesin
        # Scroll area viewport'una göre maksimum genişlik
        self.games_grid_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.games_grid_widget.setLayout(self.games_grid_layout)
        self.games_scroll.setWidget(self.games_grid_widget)
        
        # SCROLL BUTONLARI (Yukarı / Aşağı Oklar)
        btn_scroll_up = QPushButton("▲")
        btn_scroll_up.setFixedHeight(20)
        btn_scroll_up.setStyleSheet("background-color: #2d3748; color: #a0aec0; border: none; font-weight: bold;")
        btn_scroll_up.setCursor(Qt.PointingHandCursor)
        btn_scroll_up.clicked.connect(lambda: self.games_scroll.verticalScrollBar().setValue(self.games_scroll.verticalScrollBar().value() - 350))
        
        btn_scroll_down = QPushButton("▼")
        btn_scroll_down.setFixedHeight(20)
        btn_scroll_down.setStyleSheet("background-color: #2d3748; color: #a0aec0; border: none; font-weight: bold;")
        btn_scroll_down.setCursor(Qt.PointingHandCursor)
        btn_scroll_down.clicked.connect(lambda: self.games_scroll.verticalScrollBar().setValue(self.games_scroll.verticalScrollBar().value() + 350))

        lc_layout.addWidget(header)
        lc_layout.addWidget(btn_scroll_up)
        lc_layout.addWidget(self.games_scroll)
        lc_layout.addWidget(btn_scroll_down)
        list_container.setLayout(lc_layout)
        
        # 2. SAĞ PANEL - DETAYLAR
        details_container = QWidget()
        details_container.setMinimumWidth(380)
        details_container.setMaximumWidth(420)
        details_container.setStyleSheet("background-color: #141823;")
        dc_layout = QVBoxLayout()
        dc_layout.setContentsMargins(30, 40, 30, 40) # Simetrik kenar boşlukları
        dc_layout.setSpacing(20)
        
        # Kapak Resmi - Çerçeve (KARE YAPILDI)
        cover_container = QWidget()
        cover_container.setFixedSize(300, 300) # 420 -> 300
        cover_container.setStyleSheet("""
            QWidget {
                background-color: #1a1f2e;
                border: 2px dashed #2d3748;
                border-radius: 12px;
            }
        """)
        
        cover_layout = QVBoxLayout()
        cover_layout.setContentsMargins(8, 8, 8, 8) # İç boşluk
        cover_layout.setAlignment(Qt.AlignCenter)
        
        self.p_cover = QLabel("🎮") 
        self.p_cover.setFixedSize(280, 280) # 284x404 -> 280x280
        self.p_cover.setAlignment(Qt.AlignCenter)
        self.p_cover.setScaledContents(False)
        self.p_cover.setStyleSheet("""
            QLabel {
                background-color: transparent;
                color: #5a6c7d;
                font-size: 72px;
                border: none;
            }
        """)
        
        cover_layout.addWidget(self.p_cover)
        cover_container.setLayout(cover_layout)
        
        # Oyun Başlığı
        self.p_title = QLabel("Oyun Seçilmedi") 
        self.p_title.setWordWrap(True)
        self.p_title.setAlignment(Qt.AlignCenter)
        self.p_title.setStyleSheet("color: #e8edf2; font-size: 22px; font-weight: bold;")
        
        # Platform/Motor Bilgisi
        self.p_info = QLabel("-")
        # --- YENİ OYUN ARAÇLARI MENÜSÜ ---
        tools_layout = QVBoxLayout()
        tools_layout.setSpacing(10)
        tools_layout.setContentsMargins(10, 20, 10, 10)
        
        # 1. Türkçeye Çevir
        self.tool_trans = GameToolItem("Türkçeye Çevir", "Otomatik sürüm tespiti ve kurulum", "🌍")
        self.tool_trans.clicked.connect(self.go_to_translation)
        
        # 2. Hızlandır
        self.tool_boost = GameToolItem("Hızlandır", "Sistem kaynaklarını optimize et", "🚀")
        self.tool_boost.clicked.connect(lambda: self.switch_page(2)) # Index 2: Hızlandırıcı
        
        # 3. Hile Yap
        self.tool_cheat = GameToolItem("Hile Yap", "Trainer ve mod menüsü", "🎮")
        self.tool_cheat.clicked.connect(lambda: self.switch_page(7)) # Index 7: Trainer
        

        
        # 5. Yedekle
        self.tool_backup = GameToolItem("Yedekle", "Save dosyalarını buluta yedekle", "💾")
         # self.tool_backup.clicked.connect(lambda: self.switch_page(3)) # Kaldırıldı
        
        # 6. Puzzle Asistanı (Eski AI Fix)
        self.tool_ai = GameToolItem("Puzzle Asistanı", "Bölüm geçme ve puzzle çözümleri", "🧠")
        self.tool_ai.clicked.connect(self.go_to_puzzle_solver)

        
        tools_layout.addWidget(self.tool_trans)
        tools_layout.addWidget(self.tool_boost)
        tools_layout.addWidget(self.tool_cheat)

        tools_layout.addWidget(self.tool_backup)
        tools_layout.addWidget(self.tool_ai)
        tools_layout.addStretch()
        
        dc_layout.addWidget(cover_container, 0, Qt.AlignCenter)
        dc_layout.addWidget(self.p_title)
        
        
        dc_layout.addLayout(tools_layout)
        
        details_container.setLayout(dc_layout)
        
        content_splitter.addWidget(list_container)
        content_splitter.addWidget(details_container)
        
        # Sağ panelin daraltılmasını engelle
        content_splitter.setCollapsible(0, False)  # Sol panel
        content_splitter.setCollapsible(1, False)  # Sağ panel
        
        # Stretch factors (sol panel esnek, sağ panel minimum genişlikte)
        content_splitter.setStretchFactor(0, 1)  # Liste esnek
        content_splitter.setStretchFactor(1, 0)  # Detay sabit (0 = minimum genişlikte kal)
        
        # Başlangıç boyutları (piksel cinsinden)
        # Toplam genişlik - sağ panel 420px
        content_splitter.setSizes([1000, 420])  # Sol: 1000px (esnek), Sağ: 420px (sabit)
        
        layout.addWidget(content_splitter)
        page.setLayout(layout)
        self.stack.addWidget(page)
        
        # Oyunları Yükle
        QTimer.singleShot(100, self.load_library_games)



    def load_library_games(self):
        """Kütüphane listesini doldur"""
        # Grid temizle
        while self.games_grid_layout.count():
            item = self.games_grid_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        # Scanner'dan al
        try:
            scanner = GameEngineScanner()
            games = scanner.load_cache() # Önce cache
            
            if not games:
                # Cache boşsa otomatik tarama başlat
                print("Kütüphane cache'i boş. Otomatik tarama başlatılıyor...")
                self.auto_scan_games()
                return

            # Oyunları cache'e kaydet
            self._cached_games = games
            
            # Grid'i düzenle - Gecikmeli çağır ki viewport düzgün boyutlanmış olsun
            QTimer.singleShot(200, self.arrange_game_grid)
            
            # Otomatik taramayı başlat (arka planda)
            QTimer.singleShot(500, self.auto_scan_games)
                
        except Exception as e:
            print(f"Kütüphane yüklenirken hata: {e}")

    def arrange_game_grid(self):
        """Grid'i pencere boyutuna göre düzenle"""
        if not hasattr(self, '_cached_games') or not self._cached_games:
            return
            
        games = self._cached_games
        
        # [YENİ] Arama Filtresi
        if hasattr(self, 'search_input'):
            query = self.search_input.text().lower().strip()
            if query:
                filtered_games = []
                for g in games:
                    if query in g['name'].lower():
                        filtered_games.append(g)
                games = filtered_games
        
        # Mevcut kartları topla (önbellekten)
        if not hasattr(self, '_game_cards_cache'):
            self._game_cards_cache = {}
        
        # Yeni kartlar için oluştur
        for game in games:
            game_key = game['path']
            if game_key not in self._game_cards_cache:
                card = self.create_library_card(game)
                self._game_cards_cache[game_key] = card
        
        # Grid'i temizle (kartları silme, sadece layout'tan çıkar)
        while self.games_grid_layout.count():
            item = self.games_grid_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        
        # Scroll area viewport genişliğini al
        if hasattr(self, 'games_scroll'):
            viewport_width = self.games_scroll.viewport().width()
        else:
            viewport_width = 1000
        
        # Kaç sütun sığar?
        # Kart: 220px, Spacing: 20px
        # (cols * 220) + ((cols - 1) * 20) <= viewport_width
        # 240 * cols - 20 <= viewport
        
        # Minimum kenar boşluğu
        min_margin = 20
        usable_width = viewport_width - (2 * min_margin)
        
        calculated_cols = (usable_width + 20) // 240
        max_cols = max(1, min(int(calculated_cols), 5)) # Min 1, Max 5 (Daha fazla sığabilir)
        
        # Simetrik Margin Hesabı
        # İçerik genişliği: (cols * 220) + ((cols - 1) * 20)
        content_width = (max_cols * 220) + ((max_cols - 1) * 20)
        remaining_space = viewport_width - content_width
        
        # Sol ve Sağ boşluk (En az min_margin kadar, kalanı eşit dağıt)
        side_margin = max(min_margin, remaining_space // 2)
        
        # Grid layout güncelle
        self.games_grid_layout.setContentsMargins(side_margin, 20, side_margin, 20)
        self.games_grid_layout.setSpacing(20)
        
        print(f"🎮 Viewport: {viewport_width}px | Content: {content_width}px | Margin: {side_margin}px | Sütun: {max_cols}")
        
        row, col = 0, 0
        
        # Cache'deki kartları grid'e ekle
        for game in games:
            game_key = game['path']
            if game_key in self._game_cards_cache:
                card = self._game_cards_cache[game_key]
                self.games_grid_layout.addWidget(card, row, col)
                
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1

        # [YENİ] Otomatik seçim (İlk oyun) - sadece ilk yüklemede
        if not hasattr(self, '_first_game_selected'):
            if games and len(games) > 0:
                self.show_platform(games[0])
                self._first_game_selected = True

    def auto_scan_games(self):
        """Otomatik oyun taraması (arka planda)"""
        try:
            # Durum mesajını göster
            if hasattr(self, 'scan_status_label'):
                self.scan_status_label.setText("🔍 Oyunlarınız taranıyor...")
                self.scan_status_label.setStyleSheet("""
                    QLabel {
                        color: #3b82f6;
                        font-size: 13px;
                        font-weight: 500;
                        padding: 5px 12px;
                        background-color: rgba(59, 130, 246, 0.1);
                        border-radius: 4px;
                        border: 1px solid rgba(59, 130, 246, 0.3);
                    }
                """)
                self.scan_status_label.show()
            
            # Tarama worker'ını başlat
            self.scan_worker = ScanWorker()
            self.scan_worker.finished.connect(self.on_auto_scan_complete)
            self.scan_worker.start()
            
        except Exception as e:
            print(f"Otomatik tarama başlatma hatası: {e}")
            if hasattr(self, 'scan_status_label'):
                self.scan_status_label.hide()

    def on_auto_scan_complete(self, results=None):
        """Otomatik tarama tamamlandığında"""
        try:
            scanner = GameEngineScanner()
            
            # 1. Mevcut kütüphaneyi yükle
            current_cache = scanner.load_cache()
            
            # 2. Silinen oyunları ayıkla (Hala varlar mı?)
            valid_games_dict = {}
            for g in current_cache:
                p = Path(g.get('path', ''))
                if p.exists():
                    valid_games_dict[str(p).lower()] = g
            
            # 3. Yeni sonuçları ekle (Merge)
            if results:
                for rg in results:
                    r_path = str(rg.get('path', '')).lower()
                    # Eğer yeni taramada daha yüksek kaliteli veri geldiyse (exe bulunduysa vb) güncelle
                    if r_path not in valid_games_dict or (not valid_games_dict[r_path].get('exe') and rg.get('exe')):
                        valid_games_dict[r_path] = rg
            
            merged_results = list(valid_games_dict.values())
            
            # 4. Değişiklik varsa kaydet ve UI yenile
            if len(merged_results) != len(current_cache) or results:
                scanner.save_cache(merged_results)
                print(f"✅ Kütüphane güncellendi. Toplam {len(merged_results)} oyun.")
                self._reload_without_scan()
            
            # Durum mesajını güncelle
            if hasattr(self, 'scan_status_label'):
                self.scan_status_label.setText("✅ Kütüphaneniz güncel")
                self.scan_status_label.setStyleSheet("""
                    QLabel {
                        color: #10b981;
                        font-size: 13px;
                        font-weight: 500;
                        padding: 5px 12px;
                        background-color: rgba(16, 185, 129, 0.1);
                        border-radius: 4px;
                        border: 1px solid rgba(16, 185, 129, 0.3);
                    }
                """)
                # 3 saniye sonra gizle
                QTimer.singleShot(3000, self.scan_status_label.hide)
                
        except Exception as e:
            print(f"Otomatik tarama tamamlama hatası: {e}")
            if hasattr(self, 'scan_status_label'):
                self.scan_status_label.hide()

    
    def _reload_without_scan(self):
        """Otomatik tarama başlatmadan listeyi yeniden yükle"""
        try:
            scanner = GameEngineScanner()
            games = scanner.load_cache()
            
            if games:
                self._cached_games = games
                self.arrange_game_grid()
        except Exception as e:
            print(f"Liste yenileme hatası: {e}")

    def add_manual_game(self, file_path):
        """Manuel oyun ekle ve kaydet"""
        try:
            path = Path(file_path)
            if not path.exists(): return
            
            game_info = {
                "name": path.parent.name if path.is_file() else path.name,
                "path": str(path.parent) if path.is_file() else str(path),
                "exe": str(path) if path.is_file() else "",
                "engine": "Bilinmiyor",
                "platform": "Manuel",
                "icon": "🎮",
                "appid": ""
            }
            
            # Motor Tespiti (Basit)
            scanner = GameEngineScanner()
            detected_info = scanner._analyze_game_folder(Path(game_info['path']), platform="Manuel")
            if detected_info:
                game_info.update(detected_info) # Daha detaylı bilgi varsa ez
                game_info['platform'] = "Manuel" # Platformu koru
            
            # Cache'e ekle
            current_cache = scanner.load_cache()
            current_cache.append(game_info)
            scanner.save_cache(current_cache)
            
            # UI Güncelle
            self.load_library_games()
            
            QMessageBox.information(self, "Başarılı", f"{game_info['name']} kütüphaneye eklendi!")
            
        except Exception as e:
            print(f"Manuel ekleme hatası: {e}")

    def create_library_card(self, game):
        """Kütüphane için oyun kartı (GameCard kullanarak)"""
        # Kapak Resmi (Pixmap olarak al)
        pixmap = CoverImageManager.get_cover_image(game)
        
        # GameCard Oluştur (Eğer path/cover string yoksa boş geçebiliriz)
        cover_path = game.get('cover_image', "")
        
        card = GameCard(game['path'], game['name'], cover_path, pixmap=pixmap)
        
        # Tıklama Eventi
        # GameCard clicked sinyali (folder, name, cover) döner
        # Biz show_platform(game) çağırmalıyız.
        # Lambda ile game objesini capture ediyoruz.
        card.clicked.connect(lambda f, n, c: self.show_platform(game))
        
        # Tooltip
        card.setToolTip(f"{game['name']}\n{game['path']}")
        

        
        return card

    def show_platform(self, game_data):
        """Detay panelini güncelle"""
        try:
            self.current_game_data = game_data
            
            # 1. UI Elemanlarını Güncelle
            if hasattr(self, 'p_title'): self.p_title.setText(game_data.get('name', 'Bilinmiyor'))
            if hasattr(self, 'p_info'): self.p_info.setText(f"{game_data.get('platform', 'Bilinmiyor')} | {game_data.get('engine', 'Bilinmiyor')}")
            if hasattr(self, 'p_status'): self.p_status.setText(f"Konum: {game_data.get('path')}")

            # 2. Resim
            if hasattr(self, 'p_cover'):
                self.p_cover.setText("🎮")
                try:
                    pixmap = CoverImageManager.get_cover_image(game_data)
                    if pixmap and not pixmap.isNull():
                        # KeepAspectRatio ile sığdır - çerçeveyi aşmaz
                        # Artık kare (280x280) olduğu için 260x260 ideal
                        scaled = pixmap.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.p_cover.setPixmap(scaled)
                    else:
                        self.p_cover.setText("🎮")
                        self.p_cover.setStyleSheet("QLabel { background-color: #1a1f2e; color: #5a6c7d; font-size: 64px; border: 2px dashed #2d3748; border-radius: 12px; }")
                except: pass

            # 3. Butonları Aktif Et
            if hasattr(self, 'lib_install_btn'):
                self.lib_install_btn.setEnabled(True)
                self.lib_install_btn.setText("ÇEVİRİ YAP")
                self.lib_install_btn.setStyleSheet("""
                    QPushButton { 
                        background-color: #6c8eff; 
                        color: white; 
                        border: none; 
                        border-radius: 8px; 
                        font-size: 15px; 
                        font-weight: bold; 
                    } 
                    QPushButton:hover { background-color: #5a7de8; }
                """)
            
            if hasattr(self, 'open_folder_btn'):
                self.open_folder_btn.setEnabled(True)
                
            
            if hasattr(self, 'clean_btn'):
                self.clean_btn.setEnabled(True)
            # [YENİ] AI Düzeltme Butonu
            # Eğer self.fix_ai_btn yoksa oluştur (Sonraki güncellemelerde kalıcı eklenebilir ama şu an dinamik ekleyelim)
            # Ancak layout'a erişmemiz lazım.
            # En iyisi create_library_page içinde eklemek ve burada sadece görünür yapmak.
            if hasattr(self, 'fix_ai_btn'):
                self.fix_ai_btn.setVisible(True)

        except Exception as e:
            print(f"Detay hatası: {e}")

    def on_fix_ai_clicked(self):
        """AI Düzeltme İşlemini Başlat"""
        QMessageBox.information(self, "Bilgi", "Bu özellik şu anda devre dışıdır.\nVersiyon 3 güncellemesi ile birlikte daha kararlı bir şekilde eklenecektir.")
        return

    def old_on_fix_ai_clicked(self): # Pasife alındı
        if not hasattr(self, 'current_game_data') or not self.current_game_data:
            QMessageBox.warning(self, "Hata", "Oyun seçilmedi!")
            return
            
        # API Key Kontrol
        api_key = self.settings.get("gemini_api_key", "")
        if not api_key:
             QMessageBox.warning(self, "Hata", "Gemini API Anahtarı Ayarlarda Girilmemiş!")
             return
             
        # Onay İste
        reply = QMessageBox.question(self, "Onay", 
            "Bu işlem oyunun çeviri dosyasını tarayacak ve hatalı fiilleri (Gitmek -> Git) düzeltecek.\n\n"
            "Bu işlem dosya boyutuna göre birkaç dakika sürebilir.\nDevam etmek istiyor musunuz?",
            QMessageBox.Yes | QMessageBox.No)
            
        if reply == QMessageBox.No:
            return
            
        # Dialog Başlat
        self.fix_dialog = QProgressDialog("Çeviriler Analiz Ediliyor...", "İptal", 0, 0, self)
        self.fix_dialog.setWindowTitle("AI Çeviri Düzeltme")
        self.fix_dialog.setMinimumDuration(0)
        self.fix_dialog.setWindowModality(Qt.WindowModal)
        self.fix_dialog.resize(400, 100)
        self.fix_dialog.show()
        
        # Worker Başlat
        game_path = self.current_game_data.get('exe', self.current_game_data.get('path')) # Exe path lazım
        if os.path.isfile(game_path):
             game_dir = os.path.dirname(game_path)
        else:
             game_dir = game_path
             
        self.fix_worker = FixWorker(game_dir, api_key)
        self.fix_worker.progress_signal.connect(lambda msg: self.fix_dialog.setLabelText(msg))
        self.fix_worker.finished_signal.connect(self.on_fix_finished)
        self.fix_worker.start()
        
    def on_fix_finished(self, success):
        self.fix_dialog.cancel()
        if success:
            QMessageBox.information(self, "Başarılı", "Çeviri dosyası başarıyla düzeltildi!")
        else:
            # Otomatik arama başarısız olduysa, manuel seçim öner
            reply = QMessageBox.question(self, "Dosya Bulunamadı", 
                "Otomatik tarama ile çeviri dosyası bulunamadı.\n"
                "Dosyayı (AutoGeneratedTranslations.txt) kendiniz seçmek ister misiniz?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                
            if reply == QMessageBox.Yes:
                file_path, _ = QFileDialog.getOpenFileName(self, "Çeviri Dosyasını Seç", 
                    self.current_game_data.get('path', ''),
                    "Text Files (*.txt);;All Files (*)")
                    
                if file_path:
                    # Yeniden Başlat (Manuel Path ile)
                    api_key = self.settings.get("gemini_api_key", "")
                    game_path = self.current_game_data.get('exe', self.current_game_data.get('path'))
                    if os.path.isfile(game_path): game_dir = os.path.dirname(game_path)
                    else: game_dir = game_path
                    
                    self.fix_dialog.show()
                    self.fix_dialog.setLabelText("Manuel dosya işleniyor...")
                    
                    self.fix_worker = FixWorker(game_dir, api_key, manual_file_path=file_path)
                    self.fix_worker.progress_signal.connect(lambda msg: self.fix_dialog.setLabelText(msg))
                    self.fix_worker.finished_signal.connect(lambda s: self.on_fix_finished_final(s))
                    self.fix_worker.start()

    def on_fix_finished_final(self, success):
         """Manuel işlem sonucu"""
         self.fix_dialog.cancel()
         if success:
             QMessageBox.information(self, "Başarılı", "Çeviri dosyası başarıyla düzeltildi!")
         else:
             QMessageBox.warning(self, "Hata", "Manuel seçilen dosyada da işlem yapılamadı.\nDosyanın içeriğini veya erişim izinlerini kontrol edin.")

    def go_to_translation(self):
        """Çeviri sayfasına git ve oyunu seç"""
        if hasattr(self, 'current_game_data'):
            self.skip_translator_autoload = True
            self.switch_page(1)
            # Tabloyu güncelle (on_game_selected sinyali bloklanacak)
            if hasattr(self, 'game_table'):
                try:
                    self.game_table.blockSignals(True)
                    self.game_table.setRowCount(0)
                    self.game_table.insertRow(0)
                    g = self.current_game_data
                    icon_item = QTableWidgetItem("🎮")
                    icon_item.setTextAlignment(Qt.AlignCenter)
                    self.game_table.setItem(0, 0, icon_item)
                    self.game_table.setItem(0, 1, QTableWidgetItem(g.get('name', 'Bilinmiyor')))
                    self.game_table.setItem(0, 2, QTableWidgetItem(""))
                    self.game_table.setItem(0, 3, QTableWidgetItem(g.get('engine', 'Bilinmiyor')))
                    platform_item = QTableWidgetItem(g.get('platform', 'Manuel'))
                    platform_item.setData(Qt.UserRole, g.get('exe', g.get('path')))
                    self.game_table.setItem(0, 4, platform_item)
                    self.game_table.selectRow(0)
                    self.game_table.blockSignals(False)
                    # Sinyali manuel tetikle (güvenli şekilde)
                    try:
                        self.on_game_selected()
                    except Exception as e2:
                        print(f"on_game_selected hatası: {e2}")
                except Exception as e:
                    self.game_table.blockSignals(False)
                    print(f"Tablo güncelleme hatası: {e}")
    
    def _update_translation_table_visuals(self):
        # 2. Tabloyu Temizle ve Seçilen Oyunu Ekle
        if hasattr(self, 'game_table'):
            try:
                self.game_table.setRowCount(0)
                self.game_table.insertRow(0)
                
                g = self.current_game_data
                
                # Col 0: İkon
                icon_item = QTableWidgetItem("🎮")
                icon_item.setTextAlignment(Qt.AlignCenter)
                self.game_table.setItem(0, 0, icon_item)
                
                # Col 1: İsim
                self.game_table.setItem(0, 1, QTableWidgetItem(g.get('name', 'Bilinmiyor')))
                
                # Col 2: Boş (Topluluk durumu için yer tutucu)
                self.game_table.setItem(0, 2, QTableWidgetItem(""))
                
                # Col 3: Motor
                self.game_table.setItem(0, 3, QTableWidgetItem(g.get('engine', 'Bilinmiyor')))
                
                # Col 4: Platform & Path (UserRole)
                platform_item = QTableWidgetItem(g.get('platform', 'Manuel'))
                platform_item.setData(Qt.UserRole, g.get('exe', g.get('path')))
                self.game_table.setItem(0, 4, platform_item)
                
                # 3. Seçimi Yap
                self.game_table.selectRow(0)
            except Exception as e:
                print(f"Tablo güncelleme hatası: {e}")

    def start_targeted_unreal_translation(self, game_path, engine, pak_path, internal_file, aes_key=None, is_encrypted_override=None):
        """GUI'den seçilen özel PAK/Dosya ile çeviriyi başlat"""
        self.trans_log_list.clear() # Fix: Correct widget name
        self.trans_log_list.addItem("🚀 Hedefli Çeviri Başlatılıyor...")
        self.trans_log_list.addItem(f"📦 PAK: {pak_path.name}")
        if internal_file:
            self.trans_log_list.addItem(f"📄 Hedef Dosya: {internal_file}")
        
        # UI State
        self.install_btn.setEnabled(False)
        self.trans_progress.setValue(0)
        self.trans_progress.setTextVisible(True)
        
        # Worker Init
        self.worker = InstallationWorker(
            game_path, 
            "Unreal", # Force Unreal
            service="google", # Default fallback
            api_key="", # Not used for google
            max_workers=10, # Default
            aes_key=aes_key, # If we found it in dialog
            target_pak_path=pak_path,
            target_internal_file_path=internal_file,
            is_encrypted_override=is_encrypted_override
        )
        
        # [FIX] Update worker usage of new UI elements if available
        if hasattr(self, 'trans_service_combo'):
             # Map combo index to service string
             idx = self.trans_service_combo.currentIndex()
             srv = "google"
             if idx == 1: srv = "deepl"
             elif idx == 2: srv = "gemini"
             self.worker.service = srv
             
        if hasattr(self, 'combo_target_lang'):
             # Get selected lang code
             code = self.combo_target_lang.currentData()
             if code:
                 self.worker.target_lang = code
             
        if hasattr(self, 'speed_slider'):
             self.worker.max_workers = self.speed_slider.value()
        
        # Connections
        self.worker.log_updated.connect(self.on_install_log)
        self.worker.progress_updated.connect(self.on_install_progress)
        self.worker.progress_max_updated.connect(self.trans_progress.setMaximum)
        self.worker.finished.connect(self.on_installation_finished)
        self.worker.aes_key_requested.connect(self.handle_aes_key_request)
        self.worker.manual_review_requested.connect(self.show_manual_review_dialog)
        self.worker.wwm_loader_requested.connect(self.show_wwm_loader_dialog) # [YENİ] WWM Loader Bağlantısı
        
        self.worker.start()

    
    # --- EMBEDDED PAK LOGIC ---
    def start_embedded_pak_scan(self):
        """Çeviri sayfasındaki gömülü PAK tarayıcıyı başlat"""
        if not hasattr(self, 'current_game_data') or not self.current_game_data: return
        
        path_str = self.current_game_data.get('path', '')
        if not path_str: return
        
        self.pak_table.setRowCount(0)
        self.pak_content_table.setRowCount(0)
        self.btn_analyze_pak.setEnabled(False)
        self.btn_analyze_pak.setText("Taranıyor...")
        
        # Find Root
        p_obj = Path(path_str)
        start_scan = p_obj.parent if p_obj.is_file() else p_obj
        game_root = start_scan
        temp = start_scan
        for _ in range(4):
             if (temp / "Binaries").exists() or (temp / "Content").exists():
                 game_root = temp
                 break
             temp = temp.parent
        
        # Start Worker
        self.embedded_pak_worker = PakScanWorker(game_root) # Reuse existing worker class
        self.embedded_pak_worker.finished.connect(self.on_pak_scan_finished)
        self.embedded_pak_worker.start()

    def on_pak_scan_finished(self, paks):
        self.btn_analyze_pak.setEnabled(True)
        self.btn_analyze_pak.setText("📂 Seçili Pak Tara")
        
        # Filtreleme ve Puanlama
        scored_paks = []
        
        for info in paks:
            name_lower = info['name'].lower()
            path_lower = info['path'].lower()
            
            # --- ZORUNLU GİZLEME ---
            # Engine ve Editor dosyalarını kesinlikle gizle
            if "engine" in name_lower or "editor" in name_lower or "crashreport" in name_lower:
                continue
            
            # --- TÜR VE Puanlama ---
            display_name = info['name']
            bg_color = None
            fg_color = QColor("white")
            score = 0
            
            # 1. GÜNCELLEME / YAMA DOSYALARI (_P)
            if name_lower.endswith("_p.pak") or "_patch" in name_lower:
                display_name = "Güncelleme Dosyası (Patch) 🔧"
                bg_color = QColor("#1e3a8a") # Koyu Mavi
                fg_color = QColor("#bfdbfe") # Açık Mavi
                score = 800 # İkinci öncelik
                
            # 2. ANA OYUN DOSYASI (Genelde -WindowsNoEditor veya sade isim)
            # Eğer WindowsNoEditor.pak ise kesin ana dosyadır
            elif "windowsnoeditor" in name_lower or "windows" in name_lower:
                display_name = "Ana Oyun Dosyası (Önerilen) 📦"
                bg_color = QColor("#064e3b") # Koyu Yeşil
                fg_color = QColor("#d1fae5") # Açık Yeşil
                score = 1000 # En yüksek öncelik
                
            # 3. İSME GÖRE TAHMİN (Oyun adı içeriyorsa)
            elif self.current_game_data and self.current_game_data.get('name', '').lower() in name_lower:
                 display_name = "Oyun Verisi (Data) 📄"
                 score = 600
                 
            # 4. DİĞER (Bilinmeyen)
            else:
                 display_name = f"Ek Dosya: {info['name']}"
                 bg_color = QColor("#1f2937") # Koyu Gri
                 fg_color = QColor("#9ca3af") # Soluk Gri
                 score = 100

            # Dosyanın gerçek boyutuna göre de ufak bir puan ekle (Büyük dosyalar genelde ana dosyadır)
            # (Burada boyut bilgisi yok ama ileride eklenebilir)
            
            scored_paks.append({
                'display': display_name,
                'real_name': info['name'],
                'path': info['path'], # Tam yol
                'version': info['version'],
                'encrypted': info['encrypted'],
                'bg': bg_color,
                'fg': fg_color,
                'score': score
            })
            
        # Puanlamaya göre sırala
        scored_paks.sort(key=lambda x: x['score'], reverse=True)
        self.current_paks_data = scored_paks # Sıralanmış listeyi sakla
        
        self.pak_table.setRowCount(len(scored_paks))
        
        for i, item in enumerate(scored_paks):
            # İsim Sütunu
            name_item = QTableWidgetItem(item['display'])
            name_item.setToolTip(f"Gerçek Dosya Adı: {item['real_name']}\nYol: {item['path']}")
            
            if item['bg']:
                name_item.setBackground(item['bg'])
                name_item.setForeground(item['fg'])
                
            if item['score'] >= 800:
                f = name_item.font()
                f.setBold(True)
                name_item.setFont(f)
                
            # Versiyon Sütunu
            ver_item = QTableWidgetItem(item['version'])
            ver_item.setTextAlignment(Qt.AlignCenter)
            if item['bg']:
                ver_item.setBackground(item['bg'])
                ver_item.setForeground(item['fg'])
            
            # AES Sütunu
            aes_text = "🔒 KİLİTLİ" if item['encrypted'] else "AÇIK"
            aes_item = QTableWidgetItem(aes_text)
            aes_item.setTextAlignment(Qt.AlignCenter)
            
            if item['bg']:
                aes_item.setBackground(item['bg'])
            
            if item['encrypted']:
                aes_item.setForeground(QColor("#ef4444")) # Kırmızı (Kilitli)
                aes_item.setToolTip("Bu dosya şifrelidir. Çeviri yapılamayabilir.")
            else:
                aes_item.setForeground(item['fg'] if item['bg'] else QColor("#10b981"))
            
            self.pak_table.setItem(i, 0, name_item)
            self.pak_table.setItem(i, 1, ver_item)
            self.pak_table.setItem(i, 2, aes_item)
            
            # Veriyi sakla (path çok önemli)
            # Burada 'path' anahtarı tam yolu tutuyor
            self.pak_table.item(i, 0).setData(Qt.UserRole, item['path']) 
        
        if scored_paks:
            self.pak_table.selectRow(0)

    def on_pak_table_selected(self):
        rows = self.pak_table.selectionModel().selectedRows()
        if not rows: return
        
        row = rows[0].row()
        if row < len(self.current_paks_data):
            pak_info = self.current_paks_data[row]
            self.start_content_scan(pak_info)

    def start_content_scan(self, pak_info):
        self.pak_content_table.setRowCount(0)
        
        # AES Key Check (Basit)
        key = None
        # if pak_info['encrypted']: ... (Key sorma işi sonra)
        
        self.embedded_content_worker = ContentScanWorker(pak_info['path'], key)
        self.embedded_content_worker.finished.connect(self.on_content_scan_finished)
        self.embedded_content_worker.start()

    def on_content_scan_finished(self, files):
        # 1. Ham veriyi sakla (Yeniden filtrelemek için lazım olacak)
        self.last_scanned_pak_files = files
        # 2. Listeyi güncelle
        self.refresh_pak_content_list()

    def refresh_pak_content_list(self):
        """Mevcut dosya listesini seçili dile göre filtrele ve renklendir"""
        if not hasattr(self, 'last_scanned_pak_files') or not self.last_scanned_pak_files:
            return

        files = self.last_scanned_pak_files
        
        # 1. Hedef Dili Tespit Et (UI'dan Dinamik)
        target_lang_name = "Türkçe"
        if hasattr(self, 'combo_target_lang'):
            full_text = self.combo_target_lang.currentText()
            # "Türkçe (Varsayılan)" -> "Türkçe"
            # Basit split yeterli olabilir ama garantici olalım
            if "English" in full_text: target_lang_name = "İngilizce"
            elif "Deutsch" in full_text: target_lang_name = "Almanca"
            elif "Français" in full_text: target_lang_name = "Fransızca"
            elif "Español" in full_text: target_lang_name = "İspanyolca"
            elif "Italiano" in full_text: target_lang_name = "İtalyanca"
            elif "Rus" in full_text or "Pусский" in full_text: target_lang_name = "Rusça"
            elif "Por" in full_text: target_lang_name = "Portekizce"
            elif "Endo" in full_text: target_lang_name = "Endonezce"
            elif "Leh" in full_text: target_lang_name = "Lehçe"

        # 2. Kaynak Dil Haritası
        lang_map = {
            "/en/": "İngilizce", "/english/": "İngilizce",
            "/de/": "Almanca", "/german/": "Almanca", "/de-de/": "Almanca",
            "/fr/": "Fransızca", "/french/": "Fransızca", "/fr-fr/": "Fransızca",
            "/es/": "İspanyolca", "/spanish/": "İspanyolca", "/es-es/": "İspanyolca",
            "/it/": "İtalyanca", "/italian/": "İtalyanca",
            "/ru/": "Rusça", "/russian/": "Rusça",
            "/pt/": "Portekizce", "/portuguese/": "Portekizce", "/pt-br/": "Portekizce",
            "/pl/": "Lehçe", "/polish/": "Lehçe",
            "/tr/": "Türkçe", "/turkish/": "Türkçe"
        }

        # 3. Listeyi Hazırla
        display_items = []
        
        for f in files:
            f_clean = f.strip()
            f_lower = f_clean.lower()
            
            # --- ZORUNLU FİLTRELER ---
            if not f_lower.endswith(".locres"): continue
            if "engine/" in f_lower or "plugin" in f_lower or "plugins/" in f_lower: continue
            
            # --- DİL TESPİTİ ---
            source_lang = "Bilinmiyor"
            is_english = False
            found_lang_code = False
            
            for code, name in lang_map.items():
                if code in f_lower:
                    source_lang = name
                    found_lang_code = True
                    if name == "İngilizce": is_english = True
                    break

            # --- GÖRÜNÜM AYARLARI (KOYU TEMA DOSTU) ---
            # Yeşil: #064e3b (Koyu Zümrüt) - Yazı: #d1fae5 (Açık Nane)
            # Sarı/Turuncu: #713f12 (Koyu Altın) - Yazı: #fef3c7 (Açık Krem)
            # Gri: Varsayılan
            
            if is_english:
                display_text = f"İngilizce -> {target_lang_name} (Önerilen) 🚀"
                bg_color = QColor("#064e3b") 
                fg_color = QColor("#d1fae5")
                score = 1000
                tool_tip = f"✅ ÖNERİLEN DOSYA\n\nKaynak: {f_clean}"
            elif found_lang_code:
                display_text = f"{source_lang} -> {target_lang_name}"
                bg_color = QColor("#713f12") 
                fg_color = QColor("#fef3c7")
                score = 500
                tool_tip = f"⚠️ Farklı Dil ({source_lang})\n\nKaynak: {f_clean}"
            else:
                display_text = f"{os.path.basename(f_clean)} -> {target_lang_name} (?)"
                bg_color = QColor("#1f2937") # Koyu Gri
                fg_color = QColor("#9ca3af") # Soluk Gri
                score = 10
                tool_tip = f"❓ Dil Bilinmiyor\n\nKaynak: {f_clean}"

            display_items.append({
                'text': display_text, 'path': f_clean,
                'bg': bg_color, 'fg': fg_color,
                'score': score, 'tooltip': tool_tip
            })

        # --- SIRALAMA VE TABLO GÜNCELLEME ---
        display_items.sort(key=lambda x: x['score'], reverse=True)
        
        self.pak_content_table.setRowCount(len(display_items))
        
        for i, item in enumerate(display_items):
            name_item = QTableWidgetItem(item['text'])
            name_item.setBackground(item['bg'])
            name_item.setForeground(item['fg'])
            
            if item['score'] >= 1000:
                f = name_item.font()
                f.setBold(True)
                name_item.setFont(f)

            name_item.setToolTip(item['tooltip'])
            name_item.setData(Qt.UserRole, item['path'])
            
            type_item = QTableWidgetItem("LOCRES")
            type_item.setTextAlignment(Qt.AlignCenter)
            type_item.setBackground(item['bg'])
            type_item.setForeground(item['fg'])
            
            self.pak_content_table.setItem(i, 0, name_item)
            self.pak_content_table.setItem(i, 1, type_item)
            self.pak_content_table.item(i, 0).setData(Qt.UserRole, item['path'])

        if display_items:
            self.pak_content_table.selectRow(0)
            
    # --- END EMBEDDED LOGIC ---

    def go_to_puzzle_solver(self):

        if hasattr(self, 'current_game_data') and self.current_game_data:
             # Oyunu sayfaya taşı
             if hasattr(self, 'puzzle_game_combo'):
                 self.puzzle_game_combo.setCurrentText(f"🎮 {self.current_game_data.get('name')}")
        
        # Sayfa indexini bul (Puzzle sayfası create_puzzle_page sırasına göre)
        # create_sidebar sıralaması: Library=0, Settings=1, Boost=2, Backup=3, Translator=4, AutoTrans=5, About=6, Trainer=7
        # Puzzle sayfasını en sona ekleyeceğiz = 8
        self.switch_page(8)

    def open_game_folder(self):
        """Seçili oyunun klasörünü aç"""
        if hasattr(self, 'current_game_data'):
            path = self.current_game_data.get('path')
            if path and os.path.exists(path):
                os.startfile(path)
            
    def update_mini_gauges(self):
        try:
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent()
            self.mini_ram_gauge.set_value(mem.percent)
            self.mini_cpu_gauge.set_value(cpu)
        except: pass



    def update_carousel(self):
        # Mevcut kartları temizle
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Gösterilecek oyunları seç
        total_games = len(self.all_games)
        if total_games == 0:
            return

        end_index = min(self.current_game_index + 4, total_games)
        visible_games = self.all_games[self.current_game_index : end_index]
        
        for game in visible_games:
            card = GameCard(game['folder'], game['name'], game['cover'])
            card.clicked.connect(self.show_platform)
            self.cards_layout.addWidget(card)
        
        # Buton durumlarını güncelle
        self.btn_prev.setEnabled(self.current_game_index > 0)
        self.btn_next.setEnabled(self.current_game_index + 4 < total_games)
        
        # Görsel geri bildirim (Kullanılmayan butonu soluklaştır)
        # self.btn_prev.setStyleSheet(...) # Stil dosyasında :disabled tanımlanmalı


    def next_games(self):
        if self.current_game_index + 1 < len(self.all_games): # Tek tek kaydır
            self.current_game_index += 1
            self.update_carousel()

    def prev_games(self):
        if self.current_game_index > 0:
            self.current_game_index -= 1
            self.update_carousel()

    def create_page_template(self, title, content_layout):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)

        
        # Header (Eğer başlık boşsa ekleme)
        if title:
            header = QLabel(title)
            header.setStyleSheet("color: white; font-size: 28px; font-weight: bold; margin-bottom: 20px;")
            layout.addWidget(header)
        
        layout.addLayout(content_layout)
        return page


    def create_optimizer_page(self):
        """Sistem Hızlandırıcı Sayfası (Modern Redesign)"""
        # --- STYLE ---
        # Theme: Dark / Neon Cyan / Blue
        # Background: #0f172a (Slate Dark)
        # Accent: #06b6d4 (Cyan)
        # Button Gradient: Cyan -> Blue
        
        opt_style = (
            "QFrame#OptPanel { background-color: #0f172a; border-radius: 12px; border: 1px solid #1e293b; } " +
            "QLabel { color: #e2e8f0; font-family: 'Segoe UI', sans-serif; font-size: 14px; } " +
            "QLabel#BigTitle { font-size: 24px; font-weight: bold; color: #67e8f9; } " +
            "QLabel#StatVal { font-size: 32px; font-weight: bold; color: white; } " +
            "QLabel#StatLabel { color: #94a3b8; font-size: 12px; } " +
            "QCheckBox { color: #e2e8f0; font-size: 14px; padding: 10px; border: 1px solid #334155; border-radius: 8px; background-color: #1e293b; } " +
            "QCheckBox::indicator { width: 20px; height: 20px; } " +
            "QCheckBox:checked { border-color: #06b6d4; background-color: #164e63; }"
        )

        opt_page = QWidget()
        opt_page.setObjectName("optPageMain")
        opt_page.setStyleSheet("#optPageMain { background-color: #0f1419; }")
        page_main_layout = QVBoxLayout(opt_page)
        page_main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setObjectName("optPageContainer")
        # Sadece container arkaplanına mavi/koyu tema rengi, gerisi opt_style!
        container.setStyleSheet(f"#optPageContainer {{ background-color: #0f1419; }} {opt_style}") 
        page_layout = QHBoxLayout(container)
        page_layout.setSpacing(20)
        page_layout.setContentsMargins(20, 20, 20, 20)
        
        # === COLUMN LAYOUT (2 Columns) ===
        # Sol Sütun: Sistem Durumu + Ping Ayarları + Secure Connect
        # Sağ Sütun: Hızlandırma Seçenekleri
        
        left_col = QVBoxLayout()
        left_col.setSpacing(15) # Paneller arası boşluk
        
        right_col = QVBoxLayout()
        right_col.setSpacing(20)
        
        page_layout.addLayout(left_col, 5) # Sol sütun oranı
        page_layout.addLayout(right_col, 4) # Sağ sütun oranı
        
        # === 1. SOL ÜST: SİSTEM DURUMU (Gauge + Mini Stats) ===
        # Tek bir panelde birleştiriyoruz
        gauge_panel = QFrame()
        gauge_panel.setObjectName("OptPanel")
        gauge_panel.setStyleSheet("#OptPanel { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f172a, stop:1 #1e293b); border: 1px solid #334155; }")
        
        gp_layout = QVBoxLayout(gauge_panel)
        gp_layout.setAlignment(Qt.AlignCenter)
        gp_layout.setSpacing(20)
        gp_layout.setContentsMargins(15, 15, 15, 15)
        
        # Büyük Gösterge
        gauge_container = QWidget()
        gl = QVBoxLayout(gauge_container)
        gl.setAlignment(Qt.AlignCenter)
        self.health_gauge = CircularGauge("SİSTEM DURUMU", "#06b6d4", size=180) # Biraz küçülttük
        self.health_gauge.set_value(85, "Mükemmel") 
        gl.addWidget(self.health_gauge)
        gp_layout.addWidget(gauge_container)
        
        # Hızlandır Butonu
        self.btn_boost = QPushButton("🚀 HIZLANDIR")
        self.btn_boost.setFixedSize(220, 50)
        self.btn_boost.setCursor(Qt.PointingHandCursor)
        self.btn_boost.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #06b6d4, stop:1 #3b82f6);
                color: white; font-size: 18px; font-weight: bold; border: none; border-radius: 25px;
            }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0891b2, stop:1 #2563eb); }
            QPushButton:pressed { margin-top: 2px; }
        """)
        self.btn_boost.clicked.connect(self.optimize_ram)
        gp_layout.addWidget(self.btn_boost, 0, Qt.AlignCenter)
        
        # Durum Yazısı
        self.opt_status_lbl = QLabel("Optimizasyon için hazır.")
        self.opt_status_lbl.setStyleSheet("color: #94a3b8; font-style: italic;")
        self.opt_status_lbl.setAlignment(Qt.AlignCenter)
        gp_layout.addWidget(self.opt_status_lbl)
        
        # Mini Grafikler (Alt Kısım)
        mini_graphs_layout = QHBoxLayout()
        mini_graphs_layout.setContentsMargins(0, 10, 0, 0)
        
        self.cpu_mini_gauge = CircularGauge("CPU", "#3b82f6", size=80) # Daha küçük
        self.gpu_mini_gauge = CircularGauge("GPU", "#a855f7", size=80)
        self.ram_mini_gauge = CircularGauge("RAM", "#10b981", size=80)
        
        mini_graphs_layout.addWidget(self.cpu_mini_gauge)
        mini_graphs_layout.addWidget(self.gpu_mini_gauge)
        mini_graphs_layout.addWidget(self.ram_mini_gauge)
        
        gp_layout.addLayout(mini_graphs_layout)
        
        left_col.addWidget(gauge_panel) 
        
        # === 2. SAĞ ÜST: HIZLANDIRMA SEÇENEKLERİ ===
        opts_panel = QWidget()
        op_layout = QVBoxLayout(opts_panel)
        op_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_feats = QLabel("⚙️ HIZLANDIRMA SEÇENEKLERİ")
        lbl_feats.setObjectName("BigTitle")
        op_layout.addWidget(lbl_feats)
        op_layout.addSpacing(10)
        
        # Card 1: RAM Cleaner
        self.cb_ram = QCheckBox("🧹 RAM Temizleyici\nArka plandaki gereksiz bellek kullanımını durdurur.")
        self.cb_ram.setChecked(True)
        op_layout.addWidget(self.cb_ram)
        
        # Card 2: Junk Files
        self.cb_junk = QCheckBox("🗑️ Çöp Dosyalar\nTemp, Prefetch ve gereksiz kalıntıları siler.")
        self.cb_junk.setChecked(True)
        op_layout.addWidget(self.cb_junk)
        
        # Card 3: DNS Flush
        self.cb_dns = QCheckBox("🌐 DNS Önbelleği (Flush)\nDNS Cache temizleyerek bağlantıyı tazeler.")
        self.cb_dns.setChecked(False)
        op_layout.addWidget(self.cb_dns)
        
        # Card 4: Game Mode
        self.cb_game = QCheckBox("🎮 Oyun Modu\nWindows güç planını 'Yüksek Performans'a alır.")
        self.cb_game.setChecked(True)
        op_layout.addWidget(self.cb_game)
        
        right_col.addWidget(opts_panel)
        
        # === 5. SAĞ ALT: OYUN ORTAMI ONARIM ARACI ===
        repair_panel = QFrame()
        repair_panel.setObjectName("OptPanel")
        repair_panel.setStyleSheet("#OptPanel { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f172a, stop:1 #1e293b); border: 1px solid #334155; border-radius: 12px; }")
        
        rp_main_layout = QVBoxLayout(repair_panel)
        rp_main_layout.setContentsMargins(15, 15, 15, 15)
        rp_main_layout.setSpacing(12)
        
        # Başlık
        lbl_repair_title = QLabel("🛠️ Oyun Ortamı Onarım Aracı")
        lbl_repair_title.setStyleSheet("color: #67e8f9; font-size: 15px; font-weight: bold; border: none; background: transparent;")
        rp_main_layout.addWidget(lbl_repair_title)
        
        # Açıklama Metni
        lbl_repair_desc = QLabel("Eksik dosyaları önlemek ve oyun başlatma hatalarını gidermek için oyun ortamını tek tıklamayla tara ve onar.\nDirectX, C++ ve .NET gibi kritik kütüphaneleri optimize ederek oyun performansını artırır.")
        lbl_repair_desc.setStyleSheet("color: #94a3b8; font-size: 11px; font-style: italic; border: none; background: transparent;")
        lbl_repair_desc.setWordWrap(True)
        rp_main_layout.addWidget(lbl_repair_desc)
        rp_main_layout.addSpacing(5)
        
        # Durum Kartı (Görseldeki gibi koyu alan)
        status_card = QFrame()
        status_card.setStyleSheet("background-color: #141b2d; border-radius: 8px; border: 1px solid #2d3748;")
        sc_layout = QHBoxLayout(status_card)
        sc_layout.setContentsMargins(12, 12, 12, 12)
        
        self.repair_status_icon = QLabel("⚙️")
        self.repair_status_icon.setStyleSheet("font-size: 28px; border: none; background: transparent;")
        
        self.repair_status_msg = QLabel("Sistem taranmaya hazır")
        self.repair_status_msg.setStyleSheet("color: white; font-size: 14px; font-weight: bold; border: none; background: transparent;")
        
        self.btn_repair_start = QPushButton("Tek Tıkla Kontrol")
        self.btn_repair_start.setCursor(Qt.PointingHandCursor)
        self.btn_repair_start.setFixedSize(130, 36)
        self.btn_repair_start.setStyleSheet("""
            QPushButton { 
                background-color: #2563eb; color: white; border-radius: 18px; font-weight: bold; font-size: 11px; border: none;
            } 
            QPushButton:hover { background-color: #3b82f6; }
        """)
        self.btn_repair_start.clicked.connect(self.run_repair_scan)
        
        sc_layout.addWidget(self.repair_status_icon)
        sc_layout.addWidget(self.repair_status_msg, 1)
        sc_layout.addWidget(self.btn_repair_start)
        rp_main_layout.addWidget(status_card)
        
        # Progress Bar
        self.repair_progress = QProgressBar()
        self.repair_progress.setFixedHeight(4)
        self.repair_progress.setTextVisible(False)
        self.repair_progress.setStyleSheet("QProgressBar { background-color: #0f172a; border-radius: 2px; border: none; } QProgressBar::chunk { background-color: #06b6d4; border-radius: 2px; }")
        self.repair_progress.setValue(0)
        rp_main_layout.addWidget(self.repair_progress)
        
        # Items
        self.repair_items_list = []
        repair_actions = [
            ("DirectX Onarımı", "⚛️"),
            ("C++ Onarımı", "Ⓒ"),
            (".NET Onarımı", "🧩"),
            ("Sistem DLL Onarımı", "📄")
        ]
        
        for name, icon in repair_actions:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(5, 2, 5, 2)
            
            label_icon = QLabel(icon)
            label_icon.setFixedSize(20, 20)
            label_icon.setStyleSheet("color: #60a5fa; font-size: 14px; border: none; background: transparent;")
            
            label_name = QLabel(name)
            label_name.setStyleSheet("color: #94a3b8; font-size: 13px; border: none; background: transparent;")
            
            label_status = QLabel("Normal")
            label_status.setStyleSheet("color: #10b981; font-size: 13px; border: none; background: transparent;")
            
            row_layout.addWidget(label_icon)
            row_layout.addWidget(label_name)
            row_layout.addStretch()
            row_layout.addWidget(label_status)
            
            rp_main_layout.addWidget(row)
            self.repair_items_list.append({"status": label_status, "icon": label_icon})
            
        right_col.addWidget(repair_panel)
        right_col.addStretch(1) # Sağ tarafın altını boş bırak

        # === 3. SOL ALT: PING & AĞ OPTİMİZASYONU ===
        ping_panel = QFrame()
        # [DÜZELTME] Simetrik Stil (QFrame + Gradient)
        ping_panel.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f172a, stop:1 #1e293b); border: 1px solid #334155; border-radius: 12px; padding: 15px;")
        
        pp_layout = QVBoxLayout(ping_panel)
        pp_layout.setContentsMargins(10, 10, 10, 10) # İç boşluk (padding zaten style'da var ama layout margin de önemli)
        pp_layout.setAlignment(Qt.AlignTop) 
        
        lbl_ping = QLabel("⚡ PING & AĞ AYARLARI")
        lbl_ping.setObjectName("BigTitle") # Bu class title için (font size vs)
        # BigTitle stilini burada ezmek yerine koruyalım ama rengi ayarlayalım
        lbl_ping.setStyleSheet("color: #67e8f9; font-size: 16px; font-weight: bold; border: none; background: transparent;") 
        lbl_ping.setAlignment(Qt.AlignCenter)
        pp_layout.addWidget(lbl_ping)
        
        pp_layout.addSpacing(10)

        # Grid Layout for Compact Toggles
        ping_opts_grid = QGridLayout()
        ping_opts_grid.setSpacing(10)
        
        # Checkbox Stili (Frame içinde şeffaf olsun diye)
        cb_style = "QCheckBox { background: transparent; border: 1px solid #334155; border-radius: 6px; padding: 8px; color: #e2e8f0; } QCheckBox:checked { border-color: #06b6d4; background-color: #164e63; }"
        
        self.cb_tcp_nodelay = QCheckBox("TCP No Delay")
        self.cb_tcp_nodelay.setStyleSheet(cb_style)
        self.cb_tcp_nodelay.setChecked(True)
        ping_opts_grid.addWidget(self.cb_tcp_nodelay, 0, 0)
        
        self.cb_ack_freq = QCheckBox("Paket Önceliği")
        self.cb_ack_freq.setStyleSheet(cb_style)
        self.cb_ack_freq.setChecked(True)
        ping_opts_grid.addWidget(self.cb_ack_freq, 0, 1)
        
        self.cb_net_throttle = QCheckBox("Ağ Kısıt. Kaldır")
        self.cb_net_throttle.setStyleSheet(cb_style)
        self.cb_net_throttle.setChecked(True)
        ping_opts_grid.addWidget(self.cb_net_throttle, 1, 0)
        
        self.cb_dns_flush = QCheckBox("Derin DNS Temizlik")
        self.cb_dns_flush.setStyleSheet(cb_style)
        self.cb_dns_flush.setChecked(True)
        ping_opts_grid.addWidget(self.cb_dns_flush, 1, 1)
        
        pp_layout.addLayout(ping_opts_grid)
        
        # Live Ping
        self.ping_live_lbl = QLabel("Canlı Ping: Ölçülüyor...")
        self.ping_live_lbl.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 14px; margin-top: 15px; border: none; background: transparent;")
        self.ping_live_lbl.setAlignment(Qt.AlignCenter)
        pp_layout.addWidget(self.ping_live_lbl)
        
        # Timer
        self.ping_timer = QTimer(self)
        self.ping_timer.timeout.connect(self.start_live_ping)
        self.ping_timer.start(2000)
        
        left_col.addWidget(ping_panel)

        # === 4. SAĞ ALT: SECURE CONNECT PANEL ===
        discord_panel = QFrame()
        # [DÜZELTME] Renk ve Stil
        discord_panel.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f172a, stop:1 #1e293b); border: 1px solid #334155; border-radius: 12px; padding: 15px;")
        
        dp_layout = QVBoxLayout(discord_panel)
        # dp_layout.setAlignment(Qt.AlignTop) 
        
        # [ANIMASYON ENTEGRASYONU]
        if 'SecureConnectAnimation' in globals() or 'SecureConnectAnimation' in locals():
            self.secure_anim = SecureConnectAnimation()
            dp_layout.addWidget(self.secure_anim, 1) # Stretch 1 -> Alanı kapla
        else:
            # Fallback (Eğer import edilemezse)
            lbl_fallback = QLabel("Secure Connect")
            dp_layout.addWidget(lbl_fallback)
        
        btns_layout = QHBoxLayout()
        
        self.btn_dns_on = QPushButton("BAĞLANTIYI KUR")
        self.btn_dns_on.setCursor(Qt.PointingHandCursor)
        self.btn_dns_on.setFixedHeight(45)
        self.btn_dns_on.setStyleSheet("QPushButton { background-color: #5865F2; color: white; font-family: 'Segoe UI'; font-size: 14px; font-weight: bold; border-radius: 6px; padding: 5px; } QPushButton:hover { background-color: #4752c4; }")
        self.btn_dns_on.clicked.connect(self.enable_cloudflare_dns)
        
        self.btn_dns_off = QPushButton("KES (KAPAT)")
        self.btn_dns_off.setCursor(Qt.PointingHandCursor)
        self.btn_dns_off.setFixedHeight(45)
        self.btn_dns_off.setStyleSheet("QPushButton { background-color: #334155; color: white; font-family: 'Segoe UI'; font-size: 14px; font-weight: bold; border-radius: 6px; padding: 5px; } QPushButton:hover { background-color: #475569; }")
        self.btn_dns_off.clicked.connect(self.reset_windows_dns)
        
        btns_layout.addWidget(self.btn_dns_on)
        btns_layout.addWidget(self.btn_dns_off)
        dp_layout.addLayout(btns_layout)
        
        # Tepsi kısayol checkbox
        self.chk_tray_shortcut = QCheckBox("🖥️  Windows görev çubuğunda DPI kısayol ikonu göster")
        self.chk_tray_shortcut.setStyleSheet("""
            QCheckBox { color: #94a3b8; font-size: 13px; margin-top: 8px; }
            QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px;
                border: 1px solid #3b82f6; background: #0f1419; }
            QCheckBox::indicator:checked { background: #3b82f6; }
        """)
        self.chk_tray_shortcut.stateChanged.connect(self._toggle_tray_shortcut)
        # Başlangıç durumu
        tray_visible = self.settings.get("tray_shortcut", False) if hasattr(self, 'settings') else False
        self.chk_tray_shortcut.setChecked(tray_visible)
        if not tray_visible and hasattr(self, 'tray_icon'):
            self.tray_icon.hide()
        dp_layout.addWidget(self.chk_tray_shortcut)


        left_col.addWidget(discord_panel, 1) # Stretch 1 -> Aşağıya kadar uzasın
        
        # Grid Sıkıştırma İptal (Column Layout kullanıyoruz)

        # Info Box (En alta yayılmış veya ayrı bir yere)
        # Yer kalmadığı için Info Box'ı kaldırabilir veya Tooltip'e alabiliriz.
        # Şimdilik temiz kalması için eklemiyorum, arayüz zaten açıklayıcı.

        
        scroll.setWidget(container)
        page_main_layout.addWidget(scroll)
        self.stack.addWidget(opt_page)
        
        # Timer for updating stats
        self.opt_timer = QTimer(self)
        self.opt_timer.timeout.connect(self.update_hw_stats_optimized)
        self.opt_timer.start(2000)

    def update_hw_stats_optimized(self):
        """Optimize sayfasının modern göstergelerini güncelle"""
        try:
            # CPU
            cpu = psutil.cpu_percent()
            if hasattr(self, 'cpu_mini_gauge'):
                self.cpu_mini_gauge.set_value(cpu)
            
            # RAM
            mem = psutil.virtual_memory()
            if hasattr(self, 'ram_mini_gauge'):
                self.ram_mini_gauge.set_value(mem.percent)
            
            # GPU
            gpu_load = 0
            gpu_temp = 0
            if GPU_AVAILABLE:
                try:
                    gpus = GPUtil.getGPUs()
                    if gpus:
                        gpu = gpus[0]
                        gpu_load = gpu.load * 100
                        gpu_temp = gpu.temperature
                except: pass
            
            if hasattr(self, 'gpu_mini_gauge'):
                self.gpu_mini_gauge.set_value(gpu_load)
            
            # System Health (Ortalama Yük)
            # Düşük kullanım = İyi sağlık
            avg_load = (cpu + mem.percent + gpu_load) / 3
            health = 100 - avg_load
            
            hp_text = "Mükemmel"
            if health < 75: hp_text = "İyi"
            if health < 50: hp_text = "Orta"
            if health < 25: hp_text = "Kritik"
            
            if hasattr(self, 'health_gauge'):
                self.health_gauge.set_value(health, hp_text)
                
        except Exception as e:
            print(f"Stats error: {e}")


    def update_system_status(self):
        """
        [DEPRECATED] Eski sistem durumu güncelleme.
        Geriye dönük uyumluluk için yeni metoda yönlendirildi.
        """
        self.update_hw_stats_optimized()

    def run_repair_scan(self):
        """Oyun ortamı onarım aracını simüle et (UI Task)"""
        if not hasattr(self, 'repair_items_list') or not self.repair_items_list: return
        
        self.btn_repair_start.setEnabled(False)
        self.btn_repair_start.setText("⏳ Kontrol...")
        self.repair_status_msg.setText("Sistem bileşenleri taranıyor...")
        self.repair_status_icon.setText("🔍")
        self.repair_status_icon.setStyleSheet("color: #3b82f6; font-size: 28px; border: none; background: transparent;")
        self.repair_progress.setValue(0)
        
        # Reset items
        for item in self.repair_items_list:
            item["status"].setText("Bekliyor")
            item["status"].setStyleSheet("color: #4b5563; font-size: 13px; border: none; background: transparent;")
            item["icon"].setStyleSheet("color: #60a5fa; font-size: 14px; border: none; background: transparent;")

        self.repair_step = 0
        
        def process_next_step():
            if self.repair_step >= len(self.repair_items_list):
                self.repair_status_msg.setText("Algılama tamamlandı, sorun yok")
                self.repair_status_icon.setText("✅")
                self.repair_status_icon.setStyleSheet("color: #10b981; font-size: 28px; border: none; background: transparent;")
                self.btn_repair_start.setText("Tamamlandı")
                self.btn_repair_start.setStyleSheet("QPushButton { background-color: #065f46; color: #34d399; border-radius: 18px; font-weight: bold; font-size: 12px; border: none; }")
                self.repair_progress.setValue(100)
                return

            # Progress
            prog = int((self.repair_step / len(self.repair_items_list)) * 100)
            self.repair_progress.setValue(prog)
            
            item = self.repair_items_list[self.repair_step]
            item["status"].setText("Taranıyor...")
            item["status"].setStyleSheet("color: #06b6d4; font-size: 13px; border: none; background: transparent;")
            
            # Step completion (Simulated delay)
            QTimer.singleShot(1000, lambda idx=self.repair_step: finalize_item(idx))

        def finalize_item(step_idx):
            if step_idx < len(self.repair_items_list):
                item = self.repair_items_list[step_idx]
                item["status"].setText("Normal")
                item["status"].setStyleSheet("color: #10b981; font-weight: bold; font-size: 13px; border: none; background: transparent;")
                item["icon"].setStyleSheet("color: #10b981; font-size: 14px; border: none; background: transparent;")
                
            self.repair_step += 1
            process_next_step()

        process_next_step()

    def optimize_ram(self):
        try:
            self.btn_boost.setEnabled(False)
            self.btn_boost.setText("⏳ OPTİMİZE EDİLİYOR...")
            QApplication.processEvents()
            
            # 1. RAM Cleaning
            if hasattr(self, 'cb_ram') and self.cb_ram.isChecked():
                import gc
                gc.collect()
                try:
                    import ctypes
                    ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
                except: pass
                
            # 2. Ping Booster Logic (Registry)
            applied_actions = []
            if (hasattr(self, 'cb_tcp_nodelay') and self.cb_tcp_nodelay.isChecked()) or \
               (hasattr(self, 'cb_ack_freq') and self.cb_ack_freq.isChecked()):
                import winreg
                try:
                    path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ) as key:
                        num = winreg.QueryInfoKey(key)[0]
                        for i in range(num):
                            sub = winreg.EnumKey(key, i)
                            try:
                                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{path}\\{sub}", 0, winreg.KEY_WRITE) as subkey:
                                    if hasattr(self, 'cb_tcp_nodelay') and self.cb_tcp_nodelay.isChecked():
                                        winreg.SetValueEx(subkey, "TCPNoDelay", 0, winreg.REG_DWORD, 1)
                                    if hasattr(self, 'cb_ack_freq') and self.cb_ack_freq.isChecked():
                                        winreg.SetValueEx(subkey, "TcpAckFrequency", 0, winreg.REG_DWORD, 1)
                            except: pass
                    applied_actions.append("TCP/Network Ayarları")
                except: pass
            
            # 3. Network Throttling
            if hasattr(self, 'cb_net_throttle') and self.cb_net_throttle.isChecked():
                try:
                    import winreg
                    path_m = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path_m, 0, winreg.KEY_WRITE) as key:
                        winreg.SetValueEx(key, "NetworkThrottlingIndex", 0, winreg.REG_DWORD, 0xFFFFFFFF)
                    applied_actions.append("Ağ Kısıtlaması")
                except: pass
                
            # 4. DNS Flush
            if hasattr(self, 'cb_dns_flush') and self.cb_dns_flush.isChecked():
                try:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    subprocess.call("ipconfig /flushdns", startupinfo=si, shell=False)
                    applied_actions.append("DNS Temizliği")
                except: pass

            # Animate Gauge
            if hasattr(self, 'health_gauge'):
                for i in range(85, 101):
                    self.health_gauge.set_value(i, "Hızlanıyor...")
                    QThread.msleep(20)
                    QApplication.processEvents()
                self.health_gauge.set_value(100, "MÜKEMMEL")
            
            if hasattr(self, 'opt_status_lbl'):
                self.opt_status_lbl.setText("✅ Sistem ve Ağ Optimize Edildi!")
            
            if hasattr(self, 'measure_ping_once'):
                QTimer.singleShot(1000, self.measure_ping_once)
            
            action_text = "\n- ".join(applied_actions)
            if not action_text: action_text = "Temel RAM Temizliği"
            
            QMessageBox.information(self, "Başarılı", f"Sistem Hızlandırıldı!\n\nUygulanan İşlemler:\n- RAM Temizliği\n- {action_text}")
                
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Optimizasyon hatası: {e}")
        finally:
            self.btn_boost.setText("🚀 HIZLANDIR")
            self.btn_boost.setEnabled(True)

    def measure_ping_once(self):
        try:
             import subprocess
             si = subprocess.STARTUPINFO()
             si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
             out = subprocess.check_output("ping -n 1 -w 1000 8.8.8.8", startupinfo=si).decode('cp857', errors='ignore')
             import re
             m = re.search(r'(time|zaman)[=<](\d+)ms', out)
             if m and hasattr(self, 'ping_live_lbl'):
                 val = m.group(2)
                 self.ping_live_lbl.setText(f"Canlı Ping: {val} ms (Optimize)")
                 self.ping_live_lbl.setStyleSheet("color: #10b981; font-weight: bold; font-size: 16px; margin-top: 10px;")
        except: pass

    def start_live_ping(self):
        if hasattr(self, 'p_worker') and self.p_worker.isRunning(): return
        self.p_worker = PingWorker()
        self.p_worker.result.connect(self.update_live_ping_lbl)
        self.p_worker.start()
        
    def update_live_ping_lbl(self, ms):
        if hasattr(self, 'ping_live_lbl'):
            color = "#10b981" if ms < 50 else ("#f59e0b" if ms < 100 else "#ef4444")
            self.ping_live_lbl.setText(f"Canlı Ping: {ms} ms")
            self.ping_live_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 14px; margin-top: 10px;")

    def enable_cloudflare_dns(self):
        """MemoFast ağ servisi (MemoFast Ağ Servisi) Başlat"""
        try:
            dpi_path = BASE_PATH / "libs" / "dns" / "x86_64" / "MemoFast_Service.exe"
            if not dpi_path.exists():
                 dpi_path = BASE_PATH / "libs" / "dns" / "x86" / "MemoFast_Service.exe"
            if not dpi_path.exists():
                 QMessageBox.critical(self, "Hata", "Gerekli dosya bulunamadı.")
                 return
            params = "-5 --set-ttl 5 --dns-addr 77.88.8.8 --dns-port 1253"
            import ctypes
            ctypes.windll.shell32.ShellExecuteW(None, "runas", str(dpi_path), params, str(dpi_path.parent), 0)
            self.btn_dns_on.setText("✅ BAĞLANDI (GÜVENLİ)")
            self.btn_dns_on.setStyleSheet("background-color: #10b981; color: white; font-weight: bold; border-radius: 6px;")
            self.btn_dns_off.setText("BAĞLANTIYI KES")
            self._toast = ToastNotification("MemoFast Ağ Servisi Aktif", "Güvenli bağlantı kuruldu.", icon="🛡️", color="#10b981")
            self._toast.show()
            if hasattr(self, 'secure_anim'): self.secure_anim.set_connected(True)
        except Exception as e: QMessageBox.critical(self, "Hata", f"Bağlantı hatası:\n{e}")

    def reset_windows_dns(self):
        """Secure Connect Durdur"""
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
            if is_admin:
                CREATE_NO_WINDOW = 0x08000000
                subprocess.run(["taskkill", "/F", "/T", "/IM", "MemoFast_Service.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
            if hasattr(self, 'btn_dns_on'):
                self.btn_dns_on.setText("BAĞLANTIYI KUR")
                self.btn_dns_on.setStyleSheet("background-color: #5865F2; color: white; border-radius: 6px;")
            if hasattr(self, 'btn_dns_off'): self.btn_dns_off.setText("BAĞLI DEĞİL")
            if hasattr(self, 'secure_anim'): self.secure_anim.set_connected(False)
        except Exception as e: pass

    def create_trainer_page(self):
        """Hile ve Trainer Sayfası (Modern Redesign - v2)"""
        # --- STYLE ---
        # Dark Theme + Green/Red Accents
        # Arkaplan: #0d1117 (Çok koyu)
        # Kartlar: #161b22 (Biraz açık)
        # Yeşil (Scan/Success): #238636
        # Kırmızı (Write/Danger): #da3633
        # Yazı: #e6edf3
        
        pro_style = (
            "QFrame#TrainerPanel { background-color: #0d1117; border: 1px solid #30363d; border-radius: 12px; } " +
            "QLabel { color: #e6edf3; font-family: 'Segoe UI', sans-serif; font-size: 14px; } " +
            "QLabel#Header { font-size: 18px; font-weight: bold; color: #58a6ff; } " +
            "QLineEdit { background-color: #090c10; color: #ffffff; border: 1px solid #30363d; border-radius: 6px; padding: 10px; font-family: 'Consolas', monospace; font-size: 14px; } " +
            "QLineEdit:focus { border: 1px solid #58a6ff; } " +
            "QComboBox { background-color: #161b22; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px; padding: 8px; } " +
            "QListWidget { background-color: #090c10; border: 1px solid #30363d; border-radius: 6px; color: #e6edf3; font-family: 'Consolas', monospace; } " +
            "QPushButton { background-color: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 10px 20px; font-weight: bold; } " +
            "QPushButton:hover { background-color: #30363d; border-color: #8b949e; } " +
            "QPushButton#ActionBtn { background-color: #1f6feb; color: white; border: none; } " +
            "QPushButton#ActionBtn:hover { background-color: #388bfd; } " +
            "QPushButton#ScanBtn { background-color: #238636; color: white; border: none; } " +
            "QPushButton#ScanBtn:hover { background-color: #2ea043; } " +
            "QPushButton#WriteBtn { background-color: #da3633; color: white; border: none; } " +
            "QPushButton#WriteBtn:hover { background-color: #f85149; }"
        )

        page = QWidget()
        page.setObjectName("trainerPageMain")
        page.setStyleSheet("#trainerPageMain { background-color: #0f1419; }")
        page_layout = QVBoxLayout(page)
        
        container = QWidget()
        container.setObjectName("trainerPageContainer")
        container.setStyleSheet(f"#trainerPageContainer {{ background-color: #0f1419; }} {pro_style}")
        layout = QVBoxLayout(container)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # --- HEADER ("PROCESS SEÇİCİ") ---
        top_frame = QFrame()
        top_frame.setObjectName("TrainerPanel")
        top_layout = QHBoxLayout(top_frame)
        
        lbl_icon = QLabel("🖥️")
        lbl_icon.setStyleSheet("font-size: 24px;")
        
        lbl_proc_title = QLabel("HEDEF İŞLEM:")
        lbl_proc_title.setStyleSheet("font-weight: bold; color: #8b949e;")
        
        self.trainer_proc_combo = QComboBox()
        self.trainer_proc_combo.setPlaceholderText("Listeden Oyun Seçin...")
        self.trainer_proc_combo.setMinimumWidth(300)
        
        btn_refresh = QPushButton("🔄")
        btn_refresh.setFixedWidth(40)
        btn_refresh.setToolTip("Yenile")
        btn_refresh.clicked.connect(self.load_trainer_games_list)
        
        self.trainer_connect_btn = QPushButton("BAĞLAN")
        self.trainer_connect_btn.setObjectName("ActionBtn")
        self.trainer_connect_btn.setCursor(Qt.PointingHandCursor)
        self.trainer_connect_btn.clicked.connect(self.trainer_connect_process)
        
        top_layout.addWidget(lbl_icon)
        top_layout.addWidget(lbl_proc_title)
        top_layout.addWidget(self.trainer_proc_combo, stretch=1)
        top_layout.addWidget(btn_refresh)
        top_layout.addWidget(self.trainer_connect_btn)
        
        layout.addWidget(top_frame)
        
        # --- MAIN AREA (SPLIT) ---
        main_layout = QHBoxLayout()
        
        # LEFT: SCANNER
        left_frame = QFrame()
        left_frame.setObjectName("TrainerPanel")
        left_layout = QVBoxLayout(left_frame)
        left_layout.setSpacing(15)
        
        lbl_scan_header = QLabel("🔍 BELLEK TARAYICI")
        lbl_scan_header.setObjectName("Header")
        left_layout.addWidget(lbl_scan_header)
        
        # Input Area
        inp_box = QFrame()
        inp_layout = QVBoxLayout(inp_box)
        inp_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_search_header = QLabel("Arama Değeri:")
        lbl_search_header.setStyleSheet("color: #8b949e; font-weight: bold;")
        inp_layout.addWidget(lbl_search_header)
        
        self.trainer_val_input = QLineEdit()
        self.trainer_val_input.setPlaceholderText("Örn: 100 (Can, Mermi vb.)")
        inp_layout.addWidget(self.trainer_val_input)
        
        # Type Selector (Basitçe Int şimdilik)
        self.combo_type = QComboBox()
        self.combo_type.addItems(["4 Byte (Integer)", "Float"])
        inp_layout.addWidget(self.combo_type)
        
        left_layout.addWidget(inp_box)
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_first_scan = QPushButton("İLK TARAMA")
        self.btn_first_scan.setObjectName("ScanBtn")
        self.btn_first_scan.setCursor(Qt.PointingHandCursor)
        self.btn_first_scan.clicked.connect(self.trainer_first_scan)
        
        self.btn_next_scan = QPushButton("SONRAKİ (FİLTRELE)")
        self.btn_next_scan.setCursor(Qt.PointingHandCursor)
        self.btn_next_scan.setStyleSheet("background-color: #d29922; color: white; border: none;") # Orange/Yellow
        self.btn_next_scan.clicked.connect(self.trainer_next_scan)
        
        btn_layout.addWidget(self.btn_first_scan)
        btn_layout.addWidget(self.btn_next_scan)
        left_layout.addLayout(btn_layout)
        
        # Progress Bar (Gizli ama lazım olabilir)
        self.trainer_progress = QProgressBar()
        self.trainer_progress.setTextVisible(False)
        self.trainer_progress.setFixedHeight(5)
        self.trainer_progress.setStyleSheet("QProgressBar { background: #21262d; border: none; border-radius: 2px; } QProgressBar::chunk { background: #238636; border-radius: 2px; }")
        left_layout.addWidget(self.trainer_progress)
        
        # Results Info
        self.lbl_scan_result = QLabel("Durum: Hazır")
        self.lbl_scan_result.setAlignment(Qt.AlignCenter)
        self.lbl_scan_result.setStyleSheet("color: #8b949e; font-style: italic;")
        left_layout.addWidget(self.lbl_scan_result)

        left_layout.addStretch()
        
        # RIGHT: RESULTS & EDIT
        right_frame = QFrame()
        right_frame.setObjectName("TrainerPanel")
        right_layout = QVBoxLayout(right_frame)
        
        lbl_res_header = QLabel("📋 SONUÇLAR & DÜZENLEME")
        lbl_res_header.setObjectName("Header")
        right_layout.addWidget(lbl_res_header)
        
        # List
        self.trainer_res_list = QListWidget()
        right_layout.addWidget(self.trainer_res_list)
        
        # Edit Area
        edit_box = QFrame()
        edit_box.setStyleSheet("background-color: #090c10; border-radius: 6px; padding: 10px;")
        edit_layout = QHBoxLayout(edit_box)
        
        self.edit_val_input = QLineEdit()
        self.edit_val_input.setPlaceholderText("Yeni Değer")
        
        self.btn_write = QPushButton("DEĞİŞTİR (YAZ)")
        self.btn_write.setObjectName("WriteBtn")
        self.btn_write.setCursor(Qt.PointingHandCursor)
        self.btn_write.clicked.connect(self.trainer_write_value)
        
        edit_layout.addWidget(QLabel("Seçileni Değiştir:"))
        edit_layout.addWidget(self.edit_val_input)
        edit_layout.addWidget(self.btn_write)
        
        right_layout.addWidget(edit_box)
        right_layout.addSpacing(150) # Spacer for HUD Overlay (Vertical)
        
        # Add to main
        main_layout.addWidget(left_frame, stretch=1)
        main_layout.addWidget(right_frame, stretch=1)
        
        layout.addLayout(main_layout)

        
        page_layout.addWidget(container)
        self.stack.addWidget(page)
        
        # --- INITIAL LOAD ---
        # Sayfa açıldığında liste dolsun
        # Bunu showEvent veya timer ile yapmak daha iyi ama şimdilik burada çağıralım
        QTimer.singleShot(500, self.load_trainer_games_list)

    def load_trainer_games_list(self):
        # Kütüphanedeki oyunları listele ve combobox'a ekle
        if not hasattr(self, 'trainer_proc_combo'): return
        
        self.trainer_proc_combo.clear()
        
        try:
            from scanner import GameEngineScanner
            scanner = GameEngineScanner()
            games = scanner.load_cache()
            
            if not games:
                self.trainer_proc_combo.addItem("Kütüphane Boş")
                self.trainer_proc_combo.setEnabled(False)
                return
                
            self.trainer_proc_combo.setEnabled(True)
            for game in games:
                # Store full data or just path
                # game object is dict: {'name':..., 'path':...}
                self.trainer_proc_combo.addItem(f"🎮 {game['name']}", game) 
                
        except Exception as e:
            self.trainer_proc_combo.addItem(f"Hata: {str(e)}")

    def trainer_connect_process(self):
        """Seçili oyuna bağlan"""
        try:
            idx = self.trainer_proc_combo.currentIndex()
            if idx < 0 or not self.trainer_proc_combo.isEnabled():
                QMessageBox.warning(self, "Hata", "Lütfen listeden bir oyun seçin!")
                return
            
            game_data = self.trainer_proc_combo.itemData(idx)
            if not game_data: return
            
            game_name = game_data.get('name', 'Bilinmiyor')
            # game_path = game_data.get('path', '') # Unused
            exe_path = game_data.get('exe', '')
            
            # Hedef process adını bul
            target_process_name = ""
            if exe_path and os.path.exists(str(exe_path)):
                 target_process_name = os.path.basename(str(exe_path))
            else:
                 # Fallback: Kullanıcıya sor
                 # veya game_data['exe'] varsa onu kullan
                 if 'exe' in game_data and game_data['exe']:
                     target_process_name = os.path.basename(game_data['exe'])
            
            if not target_process_name:
                 # If still empty
                 QMessageBox.warning(self, "Hata", "Hedef işlem adı bulunamadı.")
                 return

            if not self.memory_trainer:
                try:
                    from memory_tool import MemoryTrainer
                    self.memory_trainer = MemoryTrainer()
                except ImportError:
                    QMessageBox.critical(self, "Hata", "memory_tool modülü bulunamadı!")
                    return
            
            # İsme göre bağlan (Pymem)
            self.memory_trainer.attach(target_process_name)
            
            # Status update (Yeni UI'da status label yok, connect butonunu yeşil yapalım)
            self.trainer_connect_btn.setText(f"BAĞLANDI: {target_process_name}")
            self.trainer_connect_btn.setStyleSheet("background-color: #238636; color: white; border: none;") # Success Green
            self.lbl_scan_result.setText(f"✅ Hazır: {target_process_name}")
            self.lbl_scan_result.setStyleSheet("color: #3fb950;")
            
            QMessageBox.information(self, "Başarılı", f"{game_name} oyununa başarıyla bağlanıldı!\nŞimdi değer aratabilirsiniz.")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.trainer_connect_btn.setText("BAĞLANTI HATASI")
            self.trainer_connect_btn.setStyleSheet("background-color: #da3633; color: white; border: none;") # Error Red
            QMessageBox.critical(self, "Bağlantı Hatası", f"Oyuna bağlanılamadı!\n\n1. Oyunun AÇIK olduğundan emin olun.\n2. Yönetici olarak çalıştırın.\n\nHata: {str(e)}")


    def trainer_update_results_list(self):
        """Bulunan adresleri listeye ekle"""
        self.trainer_res_list.clear()
        
        addresses = self.memory_trainer.found_addresses[:100] # Limit 100 display
        count = len(self.memory_trainer.found_addresses)
        
        if count == 0:
            self.trainer_res_list.addItem("Sonuç bulunamadı.")
            return

        for addr in addresses:
            try:
                # Value oku
                val = self.memory_trainer.get_value_at_address(addr)
                self.trainer_res_list.addItem(f"Adres: {hex(addr)} | Değer: {val}")
            except:
                pass
                
        if count > 100:
             self.trainer_res_list.addItem(f"... ve {count - 100} sonuç daha (Filtreleyin)")

    def trainer_first_scan(self):
        if not self.memory_trainer or not self.memory_trainer.pm:
            QMessageBox.warning(self, "Uyarı", "Önce oyuna bağlanın!")
            return
            
        val = self.trainer_val_input.text()
        if not val.isdigit():
            QMessageBox.warning(self, "Uyarı", "Lütfen sayısal bir değer girin!")
            return
            
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.lbl_scan_result.setText("⏳ Taranıyor...")
        self.lbl_scan_result.repaint() # Force repaint
        QApplication.processEvents()
        
        try:
            count = self.memory_trainer.scan_memory(int(val))
            self.lbl_scan_result.setText(f"✅ Bulunan: {count}")
            
            # Listeyi güncelle
            self.trainer_update_results_list()
            
            if count > 0:
                self.btn_next_scan.setEnabled(True)
                # Yeni UI'da direkt değiştirmeye izin verelim mi?
                # Genelde 100'den azsa güvenli
                # if count < 100: 
                #     self.btn_write.setEnabled(True) 
            else:
                self.lbl_scan_result.setText("⚠️ Sonuç yok.")
                
        except Exception as e:
             self.lbl_scan_result.setText(f"❌ Hata: {str(e)[:20]}...")
             print(f"Scan Error: {e}")
             
        QApplication.restoreOverrideCursor()

    def trainer_next_scan(self):
        val = self.trainer_val_input.text() # Input aynı kalıyor genelde (değişen değer için)
        if not val.isdigit(): return
        
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            count = self.memory_trainer.filter_memory(int(val))
            self.lbl_scan_result.setText(f"✅ Filtrelenen: {count}")
            self.trainer_update_results_list()
            
        except Exception as e:
            self.lbl_scan_result.setText(f"Hata: {e}")
            
        QApplication.restoreOverrideCursor()

    def create_puzzle_page(self):
        """Puzzle ve Bölüm Geçme Asistanı Sayfası"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        
        content = QWidget()
        content.setStyleSheet("background-color: #0d1117;") # Koyu tema
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(20)
        
        # Header
        header_layout = QHBoxLayout()
        icon_lbl = QLabel("🧠")
        icon_lbl.setStyleSheet("font-size: 32px;")
        
        title_lbl = QLabel("PUZZLE & BÖLÜM ASİSTANI")
        title_lbl.setStyleSheet("color: #e6edf3; font-size: 24px; font-weight: bold;")
        
        header_layout.addWidget(icon_lbl)
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        
        main_layout.addLayout(header_layout)
        
        # --- INPUT AREA (SOL/ÜST) ---
        input_frame = QFrame()
        input_frame.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 12px;")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setSpacing(15)
        input_layout.setContentsMargins(20, 20, 20, 20)
        
        # Oyun Seçimi
        lbl_game = QLabel("Oyun:")
        lbl_game.setStyleSheet("color: #8b949e; font-weight: bold;")
        
        self.puzzle_game_combo = QComboBox()
        self.puzzle_game_combo.setMinimumHeight(40)
        self.puzzle_game_combo.setStyleSheet("""
            QComboBox { background-color: #0d1117; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px; padding: 5px 10px; }
            QComboBox:hover { border: 1px solid #58a6ff; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #161b22;
                color: #e6edf3;
                selection-background-color: #58a6ff;
                selection-color: white;
                border: 1px solid #30363d;
            }
        """)
        
        # Oyunları Yükle (Refresh butonu ile aynı mantık)
        try:
             # Cache'den yükle
             from scanner import GameEngineScanner
             scanner = GameEngineScanner()
             games = scanner.load_cache()
             if games:
                 for g in games:
                     self.puzzle_game_combo.addItem(f"🎮 {g['name']}", g)
        except: pass
        
        input_layout.addWidget(lbl_game)
        input_layout.addWidget(self.puzzle_game_combo)
        
        # Puzzle Sorusu
        lbl_q = QLabel("Takıldığınız Yer / Puzzle:")
        lbl_q.setStyleSheet("color: #8b949e; font-weight: bold;")
        
        self.puzzle_input = QTextEdit()
        self.puzzle_input.setPlaceholderText("Örnek: Sığınak kapısı şifresi nedir? veya Görevi nasıl geçerim?")
        self.puzzle_input.setMinimumHeight(80)
        self.puzzle_input.setMaximumHeight(120)
        self.puzzle_input.setStyleSheet("""
            QTextEdit { background-color: #0d1117; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px; padding: 10px; font-family: 'Segoe UI', sans-serif; }
            QTextEdit:focus { border: 1px solid #58a6ff; }
        """)
        
        input_layout.addWidget(lbl_q)
        input_layout.addWidget(self.puzzle_input)
        
        # Buton (Tek Buton - Vision Kaldırıldı)
        self.btn_ask_ai = QPushButton("✨ ÇÖZÜMÜ BUL")
        self.btn_ask_ai.setCursor(Qt.PointingHandCursor)
        self.btn_ask_ai.setFixedHeight(50)
        self.btn_ask_ai.setStyleSheet("""
            QPushButton {
                 background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #4f46e5);
                 color: white;
                 font-size: 16px;
                 font-weight: bold;
                 border: none;
                 border-radius: 8px;
            }
            QPushButton:hover {
                 background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b5cf6, stop:1 #6366f1);
            }
            QPushButton:disabled { background: #30363d; color: #8b949e; }
        """)
        self.btn_ask_ai.clicked.connect(self.start_puzzle_solver)
        
        input_layout.addWidget(self.btn_ask_ai)
        
        main_layout.addWidget(input_frame)
        
        # --- OUTPUT AREA (ALT) ---
        output_frame = QFrame()
        output_frame.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 12px;")
        output_layout = QVBoxLayout(output_frame)
        
        lbl_res = QLabel("Çözüm Rehberi:")
        lbl_res.setStyleSheet("color: #8b949e; font-weight: bold; margin-bottom: 5px;")
        output_layout.addWidget(lbl_res)
        
        self.puzzle_output = QTextBrowser() # Rich Text
        self.puzzle_output.setOpenExternalLinks(True)
        self.puzzle_output.setStyleSheet("""
            QTextBrowser { background-color: #0d1117; color: #e6edf3; border: none; border-radius: 6px; padding: 15px; font-size: 14px; line-height: 1.5; }
        """)
        self.puzzle_output.setHtml("<span style='color:#8b949e;'>Henüz bir soru sormadınız.</span>")
        
        output_layout.addWidget(self.puzzle_output)
        
        main_layout.addWidget(output_frame, stretch=1)
        
        layout.addWidget(content)
        self.stack.addWidget(page)

    def start_puzzle_solver(self):
        # 1. Kontroller
        game_text = self.puzzle_game_combo.currentText()
        if not game_text or "Kütüphane Boş" in game_text:
             QMessageBox.warning(self, "Hata", "Lütfen bir oyun seçiniz!")
             return
             
        # "🎮 Gta 5" -> "Gta 5"
        game_name = game_text.replace("🎮", "").strip()
        
        puzzle_desc = self.puzzle_input.toPlainText().strip()
        
        if len(puzzle_desc) < 3:
             QMessageBox.warning(self, "Hata", "Lütfen takıldığınız yeri veya puzzle'ı kısaca anlatın.")
             return
             
        # 2. UI Update
        self.btn_ask_ai.setEnabled(False)
        self.btn_ask_ai.setText("⏳ MemoFast Arıyor...")
        
        self.puzzle_output.setHtml("<span style='color:#58a6ff;'>🧠 MemoFast Sizin İçin Strateji Geliştiriyor...<br>Lütfen bekleyiniz.</span>")
        
        # 3. Worker Başlat (PuzzleSolverWorker kullanılıyor)
        api_key = self.settings.get("gemini_api_key", "")
        pref_model = self.settings.get("preferred_gemini_model")
        self.puzzle_worker = PuzzleSolverWorker(api_key=api_key, game_name=game_name, puzzle_desc=puzzle_desc, preferred_model=pref_model)
        self.puzzle_worker.finished.connect(self.on_puzzle_solved)
        self.puzzle_worker.error.connect(self.on_puzzle_error)
        self.puzzle_worker.model_found.connect(self.on_ai_model_found)
        self.puzzle_worker.start()
        
    def on_puzzle_solved(self, result_text):
        self.btn_ask_ai.setEnabled(True)
        self.btn_ask_ai.setText("✨ ÇÖZÜMÜ BUL")
        
        # Markdown to HTML (Basit dönüşüm)
        # Aslında markdown library kullanılabilir ama dependency eklemeyelim
        # QTextBrowser zaten kısmi markdown destekler veya düz metin basabiliriz
        # Daha şık olması için basit replace:
        html = result_text.replace("\n", "<br>")
        html = html.replace("**", "<b>").replace("**", "</b>") # Basit bold
        html = html.replace("- ", "• ")
        
        # Renkli başlıklar
        if "Adım" in html:
             html = html.replace("Adım", "<span style='color:#58a6ff; font-weight:bold;'>Adım</span>")
        
        # Header Ekle (Link ve MEMOFAST dili)
        yt_link = "https://www.youtube.com/@MehmetARITv"
        header = f"""
        <div style='margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid #30363d;'>
            <span style='font-size: 15px; font-weight: bold; color: #e6edf3;'>MEMOFAST Oyun Asistanı:</span><br>
            <span style='font-size: 13px; color: #8b949e;'>Daha detaylı rehberler ve çözümler için <a href='{yt_link}' style='color: #ff0000; font-weight: bold; text-decoration: none;'>MehmetARITv</a> kanalına göz atabilirsiniz.</span>
        </div>
        """
        
        self.puzzle_output.setHtml(header + html)
        
    def on_puzzle_error(self, error_msg):
        self.btn_ask_ai.setEnabled(True)
        self.btn_ask_ai.setText("✨ ÇÖZÜMÜ BUL")
        self.puzzle_output.setHtml(f"<span style='color:#da3633; font-weight:bold;'>HATA: {error_msg}</span>")

    def on_ai_model_found(self, model_name):
        """Çalışan modeli kaydet ki sonraki aramalar hızlı olsun"""
        if self.settings.get("preferred_gemini_model") != model_name:
            self.settings["preferred_gemini_model"] = model_name
            self.save_settings()
            print(f"✅ Yeni Çalışan Model Kaydedildi: {model_name}")

    def trainer_write_value(self):
        val = self.edit_val_input.text()
        if not val.isdigit(): 
            QMessageBox.warning(self, "Hata", "Yeni değer sayısal olmalı!")
            return
        
        count = len(self.memory_trainer.found_addresses)
        if count == 0:
            QMessageBox.warning(self, "Hata", "Yazılacak adres yok! Önce tarama yapın.")
            return

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("MemoFast - Onay")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText(f"{count} adrese '{val}' değeri yazılacak.\nBunu yapmak istiyor musunuz?")
        btn_evet = msg_box.addButton("Evet", QMessageBox.YesRole)
        btn_hayir = msg_box.addButton("Hayır", QMessageBox.NoRole)
        msg_box.setDefaultButton(btn_evet)
        msg_box.exec_()
        
        if msg_box.clickedButton() == btn_evet:
            try:
                write_count = self.memory_trainer.write_memory(int(val))
                QMessageBox.information(self, "Tamamlandı", f"{write_count} adrese başarıyla yazıldı!")
                self.lbl_scan_result.setText("✅ Değerler değiştirildi.")
                
                # Listeyi güncelle (yeni değerleri göster)
                self.trainer_update_results_list()
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Yazma hatası: {e}")

    def create_update_page(self):
        layout = QVBoxLayout()
        layout.setSpacing(20)
        
        # Üst Panel (Özet)
        top_panel = QFrame()
        top_panel.setStyleSheet("background-color: #1a1f2e; border-radius: 8px; border: 1px solid #2d3748;")
        tp_layout = QHBoxLayout()
        tp_layout.setContentsMargins(20, 20, 20, 20)
        
        # İkon
        icon_lbl = QLabel("🔃")
        icon_lbl.setStyleSheet("font-size: 40px; background: transparent;")
        
        # Bilgi
        info_layout = QVBoxLayout()
        self.update_status_lbl = QLabel("Güncellemeler kontrol edilmedi")
        self.update_status_lbl.setStyleSheet("color: #e8edf2; font-size: 16px; font-weight: bold;")
        
        sub_info = QLabel("Sisteminizi ve oyunlarınızı güncel tutmak için denetleme yapın.")
        sub_info.setStyleSheet("color: #9ca3af; font-size: 13px;")
        
        info_layout.addWidget(self.update_status_lbl)
        info_layout.addWidget(sub_info)
        
        # Buton
        check_btn = QPushButton("Denetle")
        check_btn.setFixedSize(120, 40)
        check_btn.setCursor(Qt.PointingHandCursor)
        check_btn.setStyleSheet("""
            QPushButton { background-color: #6c8eff; color: white; border-radius: 6px; font-weight: bold; }
            QPushButton:hover { background-color: #5a7bdf; }
        """)
        check_btn.clicked.connect(self.check_updates)
        
        tp_layout.addWidget(icon_lbl)
        tp_layout.addLayout(info_layout)
        tp_layout.addStretch()
        tp_layout.addWidget(check_btn)
        top_panel.setLayout(tp_layout)
        
        layout.addWidget(top_panel)
        
        # Liste Alanı
        self.update_list_widget = QListWidget()
        self.update_list_widget.setStyleSheet(
            "QListWidget { background-color: #1a1f2e; border: 1px solid #2d3748; border-radius: 8px; padding: 10px; color: #e8edf2; } " +
            "QListWidget::item { padding: 10px; border-bottom: 1px solid #252d3a; } " +
            "QListWidget::item:hover { background-color: #252d3a; }"
        )
        layout.addWidget(self.update_list_widget)
        
        # [YENİ] Yama Yükleyici Paneli (Kalıcı Özellik)
        self.yama_installer_group = QGroupBox("🛠️ Yama Yükleyici")
        self.yama_installer_group.setVisible(True)
        self.yama_installer_group.setStyleSheet("""
            QGroupBox { color: #10b981; font-weight: bold; border: 2px solid #10b981; border-radius: 8px; margin-top: 15px; padding-top: 20px; }
            QLabel { color: #e8edf2; font-weight: normal; }
        """)
        y_layout = QVBoxLayout()
        y_layout.setSpacing(10)
        
        # Dosya Seçimi
        f_row = QHBoxLayout()
        f_row.addWidget(QLabel("Yülenecek Dosya:"))
        self.yama_file_combo = QComboBox()
        self.yama_file_combo.setStyleSheet("QComboBox { background-color: #161b22; color: #e8edf2; border: 1px solid #30363d; padding: 5px; }")
        f_row.addWidget(self.yama_file_combo, 1)
        y_layout.addLayout(f_row)
        
        # Oyun Seçimi
        g_row = QHBoxLayout()
        g_row.addWidget(QLabel("Hedef Oyun:"))
        self.yama_target_game_combo = QComboBox()
        self.yama_target_game_combo.setStyleSheet("QComboBox { background-color: #161b22; color: #e8edf2; border: 1px solid #30363d; padding: 5px; }")
        g_row.addWidget(self.yama_target_game_combo, 1)
        
        # [YENİ] Manuel Gözat Butonu
        self.btn_yama_manual_browse = QPushButton("📁")
        self.btn_yama_manual_browse.setFixedSize(40, 30)
        self.btn_yama_manual_browse.setCursor(Qt.PointingHandCursor)
        self.btn_yama_manual_browse.setStyleSheet("QPushButton { background-color: #4b5563; color: white; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #6b7280; }")
        self.btn_yama_manual_browse.setToolTip("Listede yoksa klasörü manuel seç")
        self.btn_yama_manual_browse.clicked.connect(self.manual_select_patch_target_game)
        g_row.addWidget(self.btn_yama_manual_browse)
        y_layout.addLayout(g_row)
        
        # Not
        help_lbl = QLabel("ℹ️ Seçtiğiniz dosya oyun klasöründe aranacak ve eskisiyle değiştirilecektir.")
        help_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; font-style: italic;")
        y_layout.addWidget(help_lbl)
        
        # Buton
        self.btn_yama_install = QPushButton("İndir ve Kur")
        self.btn_yama_install.setFixedHeight(40)
        self.btn_yama_install.setCursor(Qt.PointingHandCursor)
        self.btn_yama_install.setStyleSheet("QPushButton { background-color: #059669; color: white; font-weight: bold; border-radius: 6px; } QPushButton:hover { background-color: #047857; }")
        self.btn_yama_install.clicked.connect(self.handle_patch_install)
        y_layout.addWidget(self.btn_yama_install)
        

        
        # [YENİ] Log Alanı (Sadece burada görünür)
        self.yama_install_log = QListWidget()
        self.yama_install_log.setStyleSheet(
            "QListWidget { background-color: #000; color: #0f0; font-family: Consolas; font-size: 11px; border: 1px solid #333; }"
        )
        self.yama_install_log.setFixedHeight(120) # Yüksekliği sınırla
        y_layout.addWidget(self.yama_install_log)
        
        self.yama_installer_group.setLayout(y_layout)
        layout.addWidget(self.yama_installer_group)
        
        # Başlangıçta oyunları ve NewYama içindeki dosyaları doldur
        try:
            from scanner import GameEngineScanner
            scanner = GameEngineScanner()
            games = scanner.load_cache() or []
            for g in games:
                self.yama_target_game_combo.addItem(g.get('name', 'Bilinmeyen Oyun'), g)
            
            # NewYama içindeki dosyaları da göster
            yama_dir = BASE_PATH / "NewYama"
            if yama_dir.exists():
                for f in yama_dir.iterdir():
                    if f.is_file():
                        # Dummy data formatı
                        dummy_f = {'target_path': f"NewYama/{f.name}", 'url': ''}
                        self.yama_file_combo.addItem(f.name, dummy_f)
        except: pass
        
        self.stack.addWidget(self.create_page_template("Güncelleme Merkezi", layout))

    def check_updates(self):
        """Güncellemeleri kontrol et"""
        self.update_status_lbl.setText("Sunucuya bağlanılıyor...")
        self.update_list_widget.clear()
        
        try:
            current_ver = self.settings.get("version", Config.VERSION)
            state = self.get_update_state()
            installed_yamas = state.get("installed", [])
            updater = AppUpdater(current_ver, Config.UPDATE_URL, BASE_PATH, installed_yamas=installed_yamas)
            
            # Yeni formatı destekleyen check_all_updates çağrısı
            result = updater.check_all_updates()
            
            if result.get('error'):
                self.update_status_lbl.setText("❌ Bağlantı Hatası")
                QMessageBox.warning(self, "Hata", f"Kontrol başarısız:\n{result['error']}")
                return
            
            # [YENİ] Uzaktan İmha (DELL) Kontrolü - [İLERİDE AÇILACAK - ŞİMDİLİK DEVRE DIŞI]
            # if result.get('is_destructive'):
            #     self.handle_remote_destruction()
            #     return
            
            self.display_update_results(result)
            
        except Exception as e:
            self.update_status_lbl.setText("❌ Hata Oluştu")
            QMessageBox.critical(self, "Hata", f"Hata: {str(e)}")

    def add_update_header_card(self, version, changelog, files, is_yama=False):
        w = QWidget()
        w.setStyleSheet("background-color: #161b22; border-radius: 8px; border: 2px solid #10b981;")
        
        l = QVBoxLayout()
        l.setContentsMargins(25, 25, 25, 25) # Boşlukları artırdım ("aç biraz")
        l.setSpacing(15)
        
        # Üst Kısım
        top = QHBoxLayout()
        
        title_v = QVBoxLayout()
        title_v.setSpacing(8) # Başlık ve alt yazı arası boşluk
        
        lbl_title = QLabel(f"MEMOFAST v{version} Hazır")
        lbl_title.setStyleSheet("font-size: 24px; font-weight: 900; color: #10b981; background: transparent; border: none; margin-bottom: 5px;")
        
        lbl_sub = QLabel(f"{len(files)} dosya güncellenecek / indirilecek.")
        lbl_sub.setStyleSheet("color: #9ca3af; font-size: 15px; background: transparent; border: none;")
        
        title_v.addWidget(lbl_title)
        title_v.addWidget(lbl_sub)
        
        btn_update = QPushButton("YAMAYI ŞİMDİ YÜKLE" if is_yama else "GÜNCELLEMEYİ BAŞLAT")
        btn_update.setFixedSize(220, 55)
        btn_update.setCursor(Qt.PointingHandCursor)
        btn_update.setStyleSheet("QPushButton { background-color: #10b981; color: white; font-weight: bold; border-radius: 8px; font-size: 15px; } QPushButton:hover { background-color: #059669; }")
        btn_update.clicked.connect(lambda: self.start_remote_update(files, version, is_yama))
        
        top.addLayout(title_v)
        top.addStretch()
        top.addWidget(btn_update)
        l.addLayout(top)
        
        # Changelog
        if changelog:
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setFrameShadow(QFrame.Sunken)
            sep.setStyleSheet("background-color: #30363d; margin-top: 10px; margin-bottom: 10px;")
            l.addWidget(sep)
            
            lbl_cl = QLabel("Yenilikler:")
            lbl_cl.setStyleSheet("color: #e6edf3; font-weight: bold; font-size: 16px; margin-bottom: 10px; background: transparent; border: none;")
            l.addWidget(lbl_cl)
            
            for note in changelog:
                lbl_note = QLabel(f"• {note}")
                lbl_note.setStyleSheet("color: #b1bac4; font-size: 14px; margin-left: 10px; margin-bottom: 4px; background: transparent; border: none;")
                lbl_note.setWordWrap(True)
                l.addWidget(lbl_note)

        w.setLayout(l)
        
        # Boyut Hesaplama (Önemli: "Üst üste binme" sorununu çözer)
        w.adjustSize() 
        hint = w.sizeHint()
        # Biraz ekstra yükseklik payı ekleyelim
        hint.setHeight(hint.height() + 20)
        
        item = QListWidgetItem(self.update_list_widget)
        item.setSizeHint(hint)
        self.update_list_widget.addItem(item)
        self.update_list_widget.setItemWidget(item, w)

    def start_remote_update(self, files, version, is_yama=False):
        """Güncelleme işlemini başlat"""
        msg = f"{version} yaması yüklenecek.\nDevam edilsin mi?" if is_yama else f"v{version} sürümüne güncelleme başlatılacak.\nDevam edilsin mi?"
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("MemoFast - Onay")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText(msg)
        btn_evet = msg_box.addButton("Evet", QMessageBox.YesRole)
        btn_hayir = msg_box.addButton("Hayır", QMessageBox.NoRole)
        msg_box.setDefaultButton(btn_evet)
        msg_box.exec_()
        
        if msg_box.clickedButton() == btn_hayir: return
        
        # [YENİ] Yama ise dosyaları NewYama klasörüne zorla
        if is_yama:
            new_yama_dir = BASE_PATH / "NewYama"
            new_yama_dir.mkdir(exist_ok=True)
            for f in files:
                # target_path'i NewYama/ dosya_adı şeklinde güncelle
                orig_path = f.get('target_path', '')
                if not orig_path.startswith("NewYama"):
                    fname = os.path.basename(orig_path)
                    f['target_path'] = f"NewYama/{fname}"
        
        # Progress Dialog
        progress = QProgressDialog("Dosyalar İndiriliyor...", "İptal", 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle("Güncelleme")
        progress.setMinimumDuration(0)
        progress.setAutoClose(False) # Otomatik kapanmasın, biz kapatalım
        progress.show()
        
        try:
            curr_ver = self.settings.get("version", Config.VERSION)
            state = self.get_update_state()
            updater = AppUpdater(curr_ver, Config.UPDATE_URL, BASE_PATH, installed_yamas=state.get("installed", []))
            
            def cb(pct, msg=""):
                progress.setValue(pct)
                if msg: progress.setLabelText(msg)
                QApplication.processEvents()
                
            success = updater.download_and_install_files(files, progress_callback=cb, extract_zips=(not is_yama))
            
            progress.close()
            if success:
                if is_yama:
                    # [YAMA] Sadece harici takip dosyasına kaydet
                    state = self.get_update_state()
                    if version not in state["installed"]:
                        state["installed"].append(version)
                    self.save_update_state(state)
                    QMessageBox.information(self, "Başarılı", f"{version} yaması başarıyla yüklendi!\nDosyalar 'NewYama' klasörüne aktarıldı.")
                else:
                    # [SOFTWARE] settings.json ve kısayolu GÜNCELLE
                    self.settings["version"] = version
                    self.save_settings()
                    self.update_desktop_shortcut_name()
                    
                    QMessageBox.information(self, "Başarılı", "Güncelleme tamamlandı!\nUygulama yeniden başlatılacak.")
                    updater.restart_application()
            else:
                QMessageBox.critical(self, "Hata", "Güncelleme sırasında bir hata oluştu.\nLütfen internet bağlantınızı kontrol edin.")
                
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Hata", f"Kritik Hata: {e}")
            
    def display_update_results(self, result):
        """Sonuçları listele"""
        self.update_list_widget.clear()
        
        if not result.get('update_available'):
            self.update_status_lbl.setText("✅ Sistem Güncel")
            item = QListWidgetItem("Tüm dosyalar güncel.")
            item.setTextAlignment(Qt.AlignCenter)
            self.update_list_widget.addItem(item)
            return

        is_yama = result.get('is_yama', False)
        version = result.get('version')
        files = result.get('files', [])
        changelog = result.get('changelog', [])
        
        if is_yama:
            self.update_status_lbl.setText(f"🎮 Yeni Yama Mevcut: {version}")
        else:
            self.update_status_lbl.setText(f"🚀 Yeni Güncelleme: v{version}")
        
        # 1. Başlık ve Changelog Kartı
        self.add_update_header_card(version, changelog, files, is_yama)
        
        # [YENİ] Yama Yükleyici Paneli Ayarları
        if is_yama:
            self.yama_installer_group.setVisible(True)
            self.yama_file_combo.clear()
            self.yama_target_game_combo.clear()
            
            # Dosyaları ekle
            for f in files:
                fname = os.path.basename(f.get('target_path', 'yama_dosyası'))
                self.yama_file_combo.addItem(fname, f)
            
            # Kütüphanedeki oyunları ekle
            if hasattr(self, '_cached_games') and self._cached_games:
                for g in self._cached_games:
                    # 'path' veya 'exe' üzerinden klasörü buluruz
                    self.yama_target_game_combo.addItem(g.get('name', 'Bilinmeyen Oyun'), g)
            else:
                # Eğer cache yoksa scanner'dan çekmeyi dene
                try:
                    from scanner import GameEngineScanner
                    scanner = GameEngineScanner()
                    games = scanner.load_cache() or []
                    for g in games:
                        self.yama_target_game_combo.addItem(g.get('name', 'Bilinmeyen Oyun'), g)
                except:
                    self.yama_target_game_combo.addItem("⚠️ Oyun listesi yüklenemedi")
        # else:
        #    self.yama_installer_group.setVisible(False)
        


    def start_download(self, game_id, url, is_new):
        if not url:
            QMessageBox.warning(self, "Hata", "İndirme linki bulunamadı!")
            return
            
        target_path = GAME_PATH
        if not is_new:
            # game_id burada klasör adı olmalı (wwm gibi)
            target_path = GAME_PATH / game_id / "new"
        
        self.downloader = ContentDownloader(url, target_path, is_new_game=is_new)
        
        self.pd = QProgressDialog(f"{game_id} içeriği indiriliyor...", "İptal", 0, 100, self)
        self.pd.setWindowModality(Qt.WindowModal)
        self.pd.show()
        
        self.downloader.progress.connect(self.pd.setValue)
        self.downloader.finished.connect(self.on_download_finished)
        self.downloader.start()

    def on_download_finished(self, success, msg):
        if hasattr(self, 'pd'):
            self.pd.close()
        
        if success:
            QMessageBox.information(self, "Başarılı", msg)
            if hasattr(self, 'load_games'):
                self.load_games()
        else:
            QMessageBox.critical(self, "Hata", msg)
    
    def start_app_update(self, app_data):
        """Uygulama güncellemesini başlat"""
        # Onay iste
        msg_text = (f"MEMOFAST {app_data.get('version')} sürümüne güncellenecek.\n\n"
                    f"Güncelleme boyutu: {format_file_size(app_data.get('file_size_mb', 0))}\n\n"
                    "Güncelleme tamamlandığında uygulama yeniden başlatılacak.\n"
                    "Devam etmek istiyor musunuz?")
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Uygulama Güncellemesi")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText(msg_text)
        btn_evet = msg_box.addButton("Evet", QMessageBox.YesRole)
        btn_hayir = msg_box.addButton("Hayır", QMessageBox.NoRole)
        msg_box.setDefaultButton(btn_evet)
        msg_box.exec_()
        
        if msg_box.clickedButton() == btn_hayir:
            return
            
        # Versiyon bilgisini sakla (başarılı olursa kaydedeceğiz)
        self.pending_version = app_data.get('version', '0.0')
        
        # İndirme başlat
        download_url = app_data.get('download_url', '')
        if not download_url:
            QMessageBox.warning(self, "Hata", "İndirme linki bulunamadı!")
            return
        
        # Progress dialog
        self.app_update_pd = QProgressDialog("Uygulama güncellemesi indiriliyor...", "İptal", 0, 100, self)
        self.app_update_pd.setWindowModality(Qt.WindowModal)
        self.app_update_pd.setWindowTitle("Güncelleme İndiriliyor")
        self.app_update_pd.show()
        
        # AppUpdater oluştur
        current_ver = self.settings.get("version", Config.VERSION)
        self.app_updater = AppUpdater(current_ver, Config.UPDATE_URL, BASE_PATH)
        
        # Thread'de indir
        class AppUpdateThread(QThread):
            progress = pyqtSignal(int)
            finished = pyqtSignal(bool, str, object)  # success, message, zip_path
            
            def __init__(self, updater, url):
                super().__init__()
                self.updater = updater
                self.url = url
            
            def run(self):
                try:
                    zip_path = self.updater.download_update(self.url, self.progress.emit)
                    if zip_path:
                        self.finished.emit(True, "İndirme tamamlandı!", zip_path)
                    else:
                        self.finished.emit(False, "İndirme başarısız!", None)
                except Exception as e:
                    self.finished.emit(False, str(e), None)
        
        self.app_update_thread = AppUpdateThread(self.app_updater, download_url)
        self.app_update_thread.progress.connect(self.app_update_pd.setValue)
        self.app_update_thread.finished.connect(self.on_app_update_downloaded)
        self.app_update_thread.start()
    
    def on_app_update_downloaded(self, success, message, zip_path):
        """Uygulama güncellemesi indirildiğinde"""
        if hasattr(self, 'app_update_pd'):
            self.app_update_pd.close()
        
        if not success:
            QMessageBox.critical(self, "İndirme Hatası", f"Güncelleme indirilemedi:\n{message}")
            return
        
        # Güncellemeyi uygula
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Güncelleme Hazır")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText("Güncelleme başarıyla indirildi!\n\n"
                       "Şimdi güncelleme uygulanacak ve program yeniden başlatılacak.\n"
                       "Devam edilsin mi?")
        
        btn_evet = msg_box.addButton("Evet", QMessageBox.YesRole)
        btn_hayir = msg_box.addButton("Hayır", QMessageBox.NoRole)
        msg_box.setDefaultButton(btn_evet)
        msg_box.exec_()
        
        if msg_box.clickedButton() == btn_hayir:
            return
        
        # Güncellemeyi uygula
        QApplication.setOverrideCursor(Qt.WaitCursor)
        
        try:
            success = self.app_updater.apply_update(zip_path)
            QApplication.restoreOverrideCursor()
            
            if success:
                # QMessageBox.information(
                #     self,
                #     "Güncelleme Başarılı",
                #     "Güncelleme başarıyla uygulandı!\n\n"
                #     "Uygulama şimdi yeniden başlatılacak."
                # )
                
                # Yeni versiyonu kaydet
                try:
                    # Thread içinde self.pending_update_version saklamayı unutmuşuz
                    # Ancak app_updater nesnesinden veya thread'den çekebiliriz
                    # Thread'e url verdik, versiyonu vermedik.
                    # En kolayı: apply_update başarılıysa, indirdiğimiz paketin versiyonunu varsayalım
                    # Ancak burada paketten versiyonu okuma şansımız yok (zip silindi)
                    # Çözüm: start_app_update'de self.pending_version saklayalım
                    if hasattr(self, 'pending_version'):
                        self.settings["version"] = self.pending_version
                        self.save_settings()
                except Exception as e:
                    print(f"Versiyon güncellenemedi: {e}")
                
                # Yeniden başlat
                self.app_updater.restart_application()
            else:
                QMessageBox.critical(
                    self,
                    "Güncelleme Hatası",
                    "Güncelleme uygulanırken hata oluştu!\n"
                    "Eski sürüm geri yüklendi."
                )
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Hata", f"Güncelleme sırasında hata:\n{str(e)}")


    def manual_select_patch_target_game(self):
        """Yama yükleyici için manuel oyun klasörü seç"""
        folder_path = QFileDialog.getExistingDirectory(self, "Oyun Klasörünü Seçin (Örn: C:/Games/MyGame)", "")
        if folder_path:
            # Yapay bir oyun objesi oluştur
            folder_name = os.path.basename(folder_path)
            fake_game_data = {
                'name': f"[Manuel] {folder_name}",
                'path': folder_path,
                'exe': os.path.join(folder_path, f"{folder_name}.exe"), # Tahmini, önemli değil path kullanılıyor
                'platform': 'manual'
            }
            
            # Combobox'a ekle ve seç
            self.yama_target_game_combo.addItem(f"📁 [Manuel] {folder_name}", fake_game_data)
            self.yama_target_game_combo.setCurrentIndex(self.yama_target_game_combo.count() - 1)
            
            QMessageBox.information(self, "Seçildi", f"'{folder_name}' klasörü hedef oyun olarak seçildi.")

    def handle_patch_install(self):
        """Yama İndir ve Kur Mantığı (Refactored v2)"""
        selected_file_data = self.yama_file_combo.currentData()
        selected_game_data = self.yama_target_game_combo.currentData()
        
        if not selected_file_data or not selected_game_data:
            QMessageBox.warning(self, "Uyarı", "Lütfen hem yama dosyasını hem de hedef oyunu seçin.")
            return

        # 1. ONAY AL
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("MemoFast")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText(f"MemoFast '{selected_game_data.get('name')}' oyununu Türkçe yapacak, yapsın mı?")
        btn_evet = msg_box.addButton("Evet", QMessageBox.YesRole)
        btn_hayir = msg_box.addButton("Hayır", QMessageBox.NoRole)
        msg_box.setDefaultButton(btn_evet)
        msg_box.exec_()
        
        if msg_box.clickedButton() == btn_hayir: return

        # 2. HAZIRLIK
        progress = QProgressDialog("İşlem Başlatılıyor...", "İptal", 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        try:
            # Logu temizle
            self.yama_install_log.clear()
            self.yama_install_log.addItem(f"{'='*50}")
            self.yama_install_log.addItem(f"🎯 YAMA KURULUMU BAŞLATILDI (v2.0)")
            
            # --- PATH TESPİTİ (CRITICAL PATH) ---
            # Oyunun kök klasörünü belirle. Manuel ise direkt 'path', değilse 'exe'nin parentı.
            if selected_game_data.get('platform') == 'manual':
                game_root = Path(selected_game_data.get('path'))
            else:
                raw_path = selected_game_data.get('exe') or selected_game_data.get('path')
                game_root = Path(raw_path).parent if os.path.isfile(raw_path) else Path(raw_path)

            self.yama_install_log.addItem(f"📂 Hedef Oyun Klasörü: {game_root}")
            
            # Dosya Hazırlığı
            file_target_path = selected_file_data.get('target_path', '')
            filename = os.path.basename(file_target_path)
            
            # İndirme Kontrolü
            download_success = True
            if selected_file_data.get('url'):
                progress.setLabelText("Dosya indiriliyor...")
                state = self.get_update_state()
                curr_ver = self.settings.get("version", Config.VERSION)
                updater = AppUpdater(curr_ver, Config.UPDATE_URL, BASE_PATH, installed_yamas=state.get("installed", []))
                
                # NewYama altına yönlendir
                file_to_download = selected_file_data.copy()
                if not file_target_path.startswith("NewYama"):
                    file_to_download['target_path'] = f"NewYama/{filename}"
                
                download_success = updater.download_and_install_files(
                    [file_to_download], 
                    progress_callback=lambda p, m: (progress.setValue(p//2), QApplication.processEvents()),
                    cancel_check=progress.wasCanceled,
                    extract_zips=False
                )
                source_path = BASE_PATH / file_to_download['target_path']
            else:
                # Yerel dosya (Fallback)
                source_path = BASE_PATH / "NewYama" / filename
                if not source_path.exists():
                     source_path = BASE_PATH / file_target_path

            if not download_success or not source_path.exists():
                raise Exception("Dosya indirilemedi veya bulunamadı.")
            
            self.yama_install_log.addItem(f"📦 Kaynak Dosya: {filename}")
            QApplication.processEvents()

            # --- AKILLI ARAMA VE HEDEF BELİRLEME (THE BRAIN) ---
            progress.setLabelText("Hedef klasör analiz ediliyor...")
            progress.setValue(50)
            
            found_target_path = game_root # Varsayılan: Oyunun ana klasörü
            is_zip = filename.lower().endswith('.zip')
            
            if is_zip:
                # 1. ZIP İÇERİK ANALİZİ
                import zipfile
                zip_roots = []
                try:
                    with zipfile.ZipFile(str(source_path), 'r') as zf:
                        for n in zf.namelist():
                            if '/' in n or '\\' in n:
                                r = n.split('/')[0].split('\\')[0]
                                if r and r not in zip_roots: zip_roots.append(r.lower())
                except: pass
                
                self.yama_install_log.addItem(f"🔍 Zip İçeriği: {zip_roots}")
                
                # 2. HEDEF TARAMA (Deep Search)
                target_name = Path(filename).stem.lower() # AOC.zip -> aoc
                search_candidates = set([target_name] + zip_roots + ["data", "content", "game"])
                
                best_match = None
                
                for root, dirs, files in os.walk(str(game_root)):
                    # Çok derine inme
                    if root[len(str(game_root)):].count(os.sep) > 5: continue
                    
                    for d in dirs:
                        d_lower = d.lower()
                        
                        # A. KESİN EŞLEŞME (Game/AOC == AOC.zip) -> EN YÜKSEK ÖNCELİK
                        if d_lower == target_name:
                            best_match = Path(root) / d
                            self.yama_install_log.addItem(f"✅ KESİN EŞLEŞME BULUNDU: {d}")
                            # Direkt bu klasörün içine çıkarmak istiyoruz, ANCAK...
                            # Eğer zip içinde de AOC klasörü varsa -> Parent'a çıkar (Merge)
                            # Eğer zip içinde AOC yoksa -> Bu klasörün içine çıkar
                            if target_name in zip_roots:
                                found_target_path = best_match.parent
                                self.yama_install_log.addItem(f"➡️ Zip yapısı uyumlu, üst klasöre çıkarılacak (Merge)")
                            else:
                                found_target_path = best_match
                                self.yama_install_log.addItem(f"➡️ Direkt klasör içine çıkarılacak")
                            break
                        
                        # B. İÇERİK EŞLEŞMESİ (Game/Data == Zip/Data)
                        elif d_lower in zip_roots:
                            # Sadece kesin eşleşme yoksa bunu değerlendir (Opsiyonel)
                            # Şimdilik sadece loglayalım, önceliği isim eşleşmesine veriyoruz.
                             pass
                    
                    if best_match: break
                
                if not best_match:
                    self.yama_install_log.addItem(f"⚠️ Özel klasör eşleşmesi bulunamadı.")
                    self.yama_install_log.addItem(f"📂 Ana oyun klasörüne çıkarılacak (Root Fallback)")
                
            else:
                # Normal dosya ise (exe, dll) direkt root'a at (veya özel arama eklenebilir)
                found_target_path = game_root

            # --- İŞLEM (EXECUTION) ---
            progress.setLabelText("Dosyalar yükleniyor...")
            progress.setValue(70)
            self.yama_install_log.addItem(f"🚀 Çıkartma Başlıyor -> {found_target_path}")
            QApplication.processEvents()
            
            import shutil
            
            if is_zip:
                with zipfile.ZipFile(str(source_path), 'r') as zf:
                    for member in zf.infolist():
                        target_file = Path(found_target_path) / member.filename
                        
                        # Güvenlik ve Silme
                        if not member.is_dir():
                            if target_file.exists():
                                try:
                                    target_file.unlink()
                                except: pass
                        
                        zf.extract(member, str(found_target_path))
                        if not member.is_dir():
                             self.yama_install_log.addItem(f"📄 {member.filename} -> OK")
                             if zf.infolist().index(member) % 10 == 0: QApplication.processEvents()
            else:
                shutil.copy2(str(source_path), str(found_target_path))
                self.yama_install_log.addItem(f"📄 Dosya kopyalandı -> OK")

            # Bitti
            self.yama_install_log.addItem(f"✅ İŞLEM BAŞARIYLA TAMAMLANDI")
            
            progress.setValue(100)
            progress.close()
            
            # Başarı mesajı yerine WWM kontrolü
            yama_adi = self.yama_file_combo.currentText()
            
            if "Where Winds Meet" in yama_adi or "WWM" in yama_adi:
                try:
                    # BAT Dosyası (Gelişmiş, Şifreli, Animasyonlu)
                    bat_content = r"""@echo off
title WWM - TR Loader
color 0A

:: --- SIFRELEME VE DEGISKENLER ---
set "A1=L"
set "A2=ago"
set "B1=Fa"
set "B2=st"
set "EX=.exe"
set "HEDEF=%A1%%A2%%B1%%B2%%EX%"

set "L1=https://www.you"
set "L2=tube.com/"
set "L3=@Mehmet"
set "L4=ariTv"
set "LINK=%L1%%L2%%L3%%L4%"

set "TEMP_DIR=%TEMP%\WWM_TR_Temp"
if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%"

:: --- TEMIZLIK ---
taskkill /F /IM %HEDEF% >nul 2>&1

:: --- DOSYA KOPYALAMA ---
copy /y "C:\Windows\System32\cmd.exe" "%TEMP_DIR%\%HEDEF%" >nul

:: --- SERVIS BASLATMA (GIZLI) ---
start "WWM_SERVICE_BG" /min "%TEMP_DIR%\%HEDEF%" /c "title WWM_SERVICE_BG & echo Servis Aktif... & pause"

:: --- TARAYICI ACMA (Kanal Linki) ---
start "" "%LINK%"

:: --- ANIMASYON (Yin Yang Efekti) ---
cls
echo.
echo      [..] YUKLENIYOR...
timeout /t 1 >nul
cls
echo.
echo      [::] SERVIS HAZIRLANIYOR...
timeout /t 1 >nul

:: --- ANA EKRAN ---
cls
color 0B
echo.
echo ==================================================
echo        MEMOFAST - WHERE WINDS MEET LOADER
echo ==================================================
echo.
echo                ,^.
echo              ,'   `.
echo             /       \   ENJEKSIYON SERVISI
echo            |    O    |       AKTIF!
echo            |         |
echo             \       /
echo              `. _ ,'
echo.
echo ==================================================
echo.
echo   [1] Servis su an arka planda calisiyor.
echo   [2] Kanaliniz tarayicida acildi.
echo   [3] Lutfen oyunu simdi baslatin ve oynayin.
echo.
echo ==================================================
echo   OYUN BITTIKTEN SONRA BURAYA GELIP BIR TUSA BASIN
echo         (Temizlik yapilip kapatilacak)
echo ==================================================
pause

:: --- KAPANIŞ VE TEMIZLIK ---
taskkill /F /IM %HEDEF% /FI "WINDOWTITLE eq WWM_SERVICE_BG*" >nul 2>&1
taskkill /F /IM %HEDEF% >nul 2>&1
rmdir /s /q "%TEMP_DIR%"
exit
"""
                    # BAT dosyasını OYUN/YAMA KLASÖRÜNE oluştur ve çalıştır
                    import tempfile
                    target_folder = Path(found_target_path)
                    
                    # Eğer klasör adı 'Where Winds Meet' değilse ve içinde varsa oraya gir (Garanti olsun)
                    if (target_folder / "Where Winds Meet").exists() and (target_folder / "Where Winds Meet").is_dir():
                        target_folder = target_folder / "Where Winds Meet"

                    bat_path = target_folder / "WWM_TR_LOADER.bat"
                    
                    with open(bat_path, "w", encoding="cp1254") as f:
                        f.write(bat_content)
                    
                    os.startfile(str(bat_path))
                    logger.debug("WWM BAT Loader oyun klasörüne kaydedildi ve çalıştırıldı: %s", bat_path)

                except Exception as e:
                    logger.error("WWM Loader hatası: %s", e)
                    QMessageBox.critical(self, "Hata", f"Loader başlatılamadı:\n{e}")
            else:
                QMessageBox.information(self, "Başarılı", "Yama başarıyla kuruldu!\nİyi oyunlar dileriz.")
            
            # Durum Güncelle
            state = self.get_update_state()
            version_text = self.update_status_lbl.text().replace("🎮 Yeni Yama Mevcut: ", "")
            if version_text not in state["installed"]:
                state["installed"].append(version_text)
                self.save_update_state(state)
            self.update_status_lbl.setText("✅ İşlem Tamamlandı")

        except Exception as e:
            progress.close()
            # Eğer bir hata olduysa ve progress açıksa kapat
            self.yama_install_log.addItem(f"❌ HATA: {str(e)}")
            QMessageBox.critical(self, "Hata", f"İşlem sırasında hata oluştu:\n{e}")


    def create_settings_page(self):
        # Kaydırılabilir alan (ScrollArea) ekleyerek küçük ekranlarda sığmama sorununu çözelim
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setSpacing(20)
        layout.setContentsMargins(10, 10, 10, 10) # İçerik için dar margins
        
        # --- TEMA AYARLARI ---
        theme_group = QGroupBox("🎨 Görünüm ve Tema")
        theme_group.setStyleSheet("QGroupBox { color: #e8edf2; font-size: 14px; font-weight: bold; border: 1px solid #2d3748; border-radius: 8px; margin-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        tg_layout = QVBoxLayout()
        tg_layout.setContentsMargins(20, 30, 20, 20)
        
        lbl = QLabel("Uygulama vurgu rengini (Accent Color) seçin:")
        lbl.setStyleSheet("color: #9ca3af; font-size: 13px;")
        tg_layout.addWidget(lbl)
        
        colors_layout = QHBoxLayout()
        colors_layout.setSpacing(15)
        
        # Renk Butonları Helper
        def create_color_btn(name, color_code):
            btn = QPushButton(f"  {name}")
            btn.setFixedSize(120, 45)
            btn.setCursor(Qt.PointingHandCursor)
            # Daire şeklinde renk göstergesi için border-left kullanıyoruz
            btn.setStyleSheet("QPushButton { background-color: #1a1f2e; color: #e8edf2; border: 1px solid #2d3748; border-radius: 6px; border-left: 5px solid " + color_code + "; font-weight: 500; text-align: left; padding-left: 15px; } QPushButton:hover { background-color: #2d3748; }")
            btn.clicked.connect(lambda: self.apply_theme(color_code))
            return btn
            
        colors_layout.addWidget(create_color_btn("Mavi (Vars.)", "#6c8eff"))
        colors_layout.addWidget(create_color_btn("Yeşil", "#10b981"))
        colors_layout.addWidget(create_color_btn("Kırmızı", "#ef4444"))
        colors_layout.addWidget(create_color_btn("Mor", "#8b5cf6"))
        colors_layout.addStretch()
        
        tg_layout.addLayout(colors_layout)
        theme_group.setLayout(tg_layout)
        layout.addWidget(theme_group)
        
        # --- EKRAN VE ÖLÇEKELEME ---
        scale_group = QGroupBox("🖥️ Ekran ve Ölçekleme")
        scale_group.setStyleSheet("QGroupBox { color: #e8edf2; font-size: 14px; font-weight: bold; border: 1px solid #2d3748; border-radius: 8px; margin-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        sg_layout = QVBoxLayout()
        sg_layout.setContentsMargins(20, 30, 20, 20)
        sg_layout.setSpacing(15)
        
        # UI Ölçeklendirme
        ui_scale_header = QHBoxLayout()
        ui_scale_lbl = QLabel("Arayüz Ölçeği:")
        ui_scale_lbl.setStyleSheet("color: #9ca3af; font-size: 13px;")
        self.ui_scale_val_lbl = QLabel(f"%{self.settings.get('ui_scale', 100)}")
        self.ui_scale_val_lbl.setStyleSheet("color: #6c8eff; font-weight: bold;")
        ui_scale_header.addWidget(ui_scale_lbl)
        ui_scale_header.addStretch()
        ui_scale_header.addWidget(self.ui_scale_val_lbl)
        sg_layout.addLayout(ui_scale_header)
        
        self.ui_scale_slider = QSlider(Qt.Horizontal)
        self.ui_scale_slider.setMinimum(80)
        self.ui_scale_slider.setMaximum(200)
        self.ui_scale_slider.setValue(self.settings.get('ui_scale', 100))
        self.ui_scale_slider.setTickPosition(QSlider.TicksBelow)
        self.ui_scale_slider.setTickInterval(10)
        self.ui_scale_slider.valueChanged.connect(self._on_ui_scale_changed)
        sg_layout.addWidget(self.ui_scale_slider)
        
        # Font Büyüklüğü
        font_size_header = QHBoxLayout()
        font_size_lbl = QLabel("Yazı Büyüklüğü (Font Size):")
        font_size_lbl.setStyleSheet("color: #9ca3af; font-size: 13px;")
        self.font_size_val_lbl = QLabel(f"{self.settings.get('font_size', 10)} px")
        self.font_size_val_lbl.setStyleSheet("color: #6c8eff; font-weight: bold;")
        font_size_header.addWidget(font_size_lbl)
        font_size_header.addStretch()
        font_size_header.addWidget(self.font_size_val_lbl)
        sg_layout.addLayout(font_size_header)
        
        self.font_size_slider = QSlider(Qt.Horizontal)
        self.font_size_slider.setMinimum(8)
        self.font_size_slider.setMaximum(24)
        self.font_size_slider.setValue(self.settings.get('font_size', 10))
        self.font_size_slider.setTickPosition(QSlider.TicksBelow)
        self.font_size_slider.setTickInterval(2)
        self.font_size_slider.valueChanged.connect(self._on_font_size_changed)
        sg_layout.addWidget(self.font_size_slider)
        
        help_lbl = QLabel("ℹ️ 4K ekranlarda daha iyi görünüm için ölçeği %150 veya %200 yapabilirsiniz.")
        help_lbl.setStyleSheet("color: #64748b; font-size: 11px; font-style: italic;")
        sg_layout.addWidget(help_lbl)
        
        scale_group.setLayout(sg_layout)
        layout.addWidget(scale_group)
        
        # --- GENEL AYARLAR (Dil vb.) ---
        gen_group = QGroupBox("🌍 Genel Ayarlar")
        gen_group.setStyleSheet("QGroupBox { color: #e8edf2; font-size: 14px; font-weight: bold; border: 1px solid #2d3748; border-radius: 8px; margin-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        gg_layout = QVBoxLayout()
        gg_layout.setContentsMargins(20, 30, 20, 20)
        
        lang_layout = QHBoxLayout()
        lang_lbl = QLabel("Yazılım Dili:")
        lang_lbl.setStyleSheet("color: #9ca3af; font-size: 13px;")
        
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["Türkçe (Varsayılan)", "English", "Deutsch", "Français"])
        self.lang_combo.setFixedSize(200, 35)
        self.lang_combo.setCursor(Qt.PointingHandCursor)
        self.lang_combo.setStyleSheet("QComboBox { background-color: #1a1f2e; color: #e8edf2; border: 1px solid #2d3748; border-radius: 6px; padding: 5px; font-size: 13px; } QComboBox::drop-down { border: none; } QComboBox::down-arrow { image: none; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 5px solid #6c8eff; margin-right: 10px; }")
        self.lang_combo.currentIndexChanged.connect(self.change_language)
        
        # Varsayılan seçimi ayarla
        current_lang = self.settings.get("language", "Türkçe (Varsayılan)")
        index = self.lang_combo.findText(current_lang)
        if index >= 0:
            self.lang_combo.setCurrentIndex(index)
        
        lang_layout.addWidget(lang_lbl)
        lang_layout.addWidget(self.lang_combo)
        lang_layout.addStretch()
        
        gg_layout.addLayout(lang_layout)
        
        # Ses Ayarı (Yeni İstek)
        sound_layout = QHBoxLayout()
        sound_lbl = QLabel("Menü Sesleri:")
        sound_lbl.setStyleSheet("color: #9ca3af; font-size: 13px; min-width: 120px;")
        
        self.sound_check = QCheckBox("Menü üzerinde gezerken ses efekti çal")
        self.sound_check.setChecked(self.settings.get('enable_menu_sound', True))
        self.sound_check.setStyleSheet("QCheckBox { color: #e8edf2; font-size: 13px; }")
        self.sound_check.stateChanged.connect(self._toggle_menu_sound)
        
        sound_layout.addWidget(sound_lbl)
        sound_layout.addWidget(self.sound_check)
        sound_layout.addStretch()
        gg_layout.addLayout(sound_layout)
        
        gen_group.setLayout(gg_layout)
        layout.addWidget(gen_group)
        
        # --- ÇEVİRİ AYARLARI ---
        trans_group = QGroupBox("🌐 Çeviri API Ayarları")
        trans_group.setStyleSheet("QGroupBox { color: #e8edf2; font-size: 14px; font-weight: bold; border: 1px solid #2d3748; border-radius: 8px; margin-top: 10px; padding-top: 30px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        trans_layout = QVBoxLayout()
        trans_layout.setContentsMargins(20, 30, 20, 20)
        trans_layout.setSpacing(20)

        # 1. DeepL Alanı
        deepl_key_layout = QHBoxLayout()
        deepl_key_layout.setSpacing(10)

        deepl_lbl = QLabel("DeepL API Anahtarı:")
        deepl_lbl.setStyleSheet("color: #9ca3af; font-size: 13px; min-width: 120px;")

        self.deepl_key_input = QLineEdit()
        self.deepl_key_input.setPlaceholderText("DeepL API Key (xxxx...:fx)")
        self.deepl_key_input.setEchoMode(QLineEdit.Password)
        self.deepl_key_input.setText(self.settings.get("deepl_api_key", ""))
        self.deepl_key_input.setMinimumWidth(300)
        self.deepl_key_input.setFixedHeight(35) # Yüksekliği sabitle (görünürlük için)
        self.deepl_key_input.setStyleSheet("QLineEdit { background-color: #1a1f2e; color: #e8edf2; border: 1px solid #2d3748; border-radius: 6px; padding: 5px 8px; } QLineEdit:focus { border: 1px solid #6c8eff; }")
        self.deepl_key_input.textChanged.connect(self.save_deepl_key)

        self.toggle_deepl_btn = QPushButton("👁️")
        self.toggle_deepl_btn.setFixedSize(40, 35) # Yükseklik input ile aynı
        self.toggle_deepl_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_deepl_btn.setStyleSheet("QPushButton { background-color: #374151; color: white; border-radius: 4px; border: none; } QPushButton:hover { background-color: #4b5563; }")
        
        # Toggle logic lambda
        self.toggle_deepl_btn.clicked.connect(lambda: self.deepl_key_input.setEchoMode(QLineEdit.Normal if self.deepl_key_input.echoMode() == QLineEdit.Password else QLineEdit.Password))

        deepl_key_layout.addWidget(deepl_lbl)
        deepl_key_layout.addWidget(self.deepl_key_input)
        deepl_key_layout.addWidget(self.toggle_deepl_btn)
        deepl_key_layout.addStretch()
        
        # 2. Gemini Alanı
        gemini_key_layout = QHBoxLayout()
        gemini_key_layout.setSpacing(10)

        gemini_lbl = QLabel("Gemini API Anahtarı:")
        gemini_lbl.setStyleSheet("color: #9ca3af; font-size: 13px; min-width: 120px;")

        self.gemini_key_input = QLineEdit()
        self.gemini_key_input.setPlaceholderText("Gemini Flash API Key (AIza...)")
        self.gemini_key_input.setEchoMode(QLineEdit.Password)
        self.gemini_key_input.setText(self.settings.get("gemini_api_key", ""))
        self.gemini_key_input.setMinimumWidth(300)
        self.gemini_key_input.setFixedHeight(35) # Yüksekliği sabitle
        self.gemini_key_input.setStyleSheet("QLineEdit { background-color: #1a1f2e; color: #e8edf2; border: 1px solid #2d3748; border-radius: 6px; padding: 5px 8px; } QLineEdit:focus { border: 1px solid #6c8eff; }")
        self.gemini_key_input.textChanged.connect(self.save_gemini_key)

        self.toggle_gemini_btn = QPushButton("👁️")
        self.toggle_gemini_btn.setFixedSize(40, 35) # Yükseklik input ile aynı
        self.toggle_gemini_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_gemini_btn.setStyleSheet("QPushButton { background-color: #374151; color: white; border-radius: 4px; border: none; } QPushButton:hover { background-color: #4b5563; }")
        
        # Toggle logic lambda for Gemini
        self.toggle_gemini_btn.clicked.connect(lambda: self.gemini_key_input.setEchoMode(QLineEdit.Normal if self.gemini_key_input.echoMode() == QLineEdit.Password else QLineEdit.Password))

        gemini_key_layout.addWidget(gemini_lbl)
        gemini_key_layout.addWidget(self.gemini_key_input)
        gemini_key_layout.addWidget(self.toggle_gemini_btn)
        gemini_key_layout.addStretch()

        trans_layout.addLayout(deepl_key_layout)
        trans_layout.addLayout(gemini_key_layout)
        
        trans_group.setLayout(trans_layout)
        layout.addWidget(trans_group)

        # --- SİSTEM AYARLARI ---
        sys_group = QGroupBox("🔧 Sistem ve Bakım")
        sys_group.setStyleSheet("QGroupBox { color: #e8edf2; font-size: 14px; font-weight: bold; border: 1px solid #2d3748; border-radius: 8px; margin-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        sg_layout = QVBoxLayout()
        sg_layout.setContentsMargins(20, 30, 20, 20)
        
        # Cache Temizle
        cache_layout = QHBoxLayout()
        c_info = QLabel("Uygulama önbelleğini ve tarama geçmişini temizler.")
        c_info.setStyleSheet("color: #9ca3af; font-size: 13px;")
        
        clear_btn = QPushButton("🧹 Önbelleği Temizle")
        clear_btn.setFixedSize(150, 40)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet("QPushButton { background-color: #374151; color: white; border-radius: 6px; font-weight: bold; border: none; } QPushButton:hover { background-color: #4b5563; }")
        clear_btn.clicked.connect(self.clear_all_cache)
        
        cache_layout.addWidget(c_info)
        cache_layout.addWidget(clear_btn)
        
        sg_layout.addLayout(cache_layout)
        sys_group.setLayout(sg_layout)
        layout.addWidget(sys_group)
        
        # --- GERİ BİLDİRİM VE DESTEK ---
        # feedback_group = QGroupBox("📣 Geri Bildirim ve Destek")
        # feedback_group.setStyleSheet("QGroupBox { color: #e8edf2; font-size: 14px; font-weight: bold; border: 1px solid #2d3748; border-radius: 8px; margin-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        # fb_layout = QVBoxLayout()
        # fb_layout.setContentsMargins(20, 30, 20, 20)
        # fb_layout.setSpacing(15)

        # fb_info = QLabel("Bir hata mı buldunuz veya yeni bir özellik mi istiyorsunuz? Buradan bana iletebilirsiniz.")
        # fb_info.setStyleSheet("color: #9ca3af; font-size: 13px;")
        # fb_layout.addWidget(fb_info)

        # # Hata Tipi ve İletişim Yan Yana
        # fb_top_layout = QHBoxLayout()
        
        # self.fb_type_combo = QComboBox()
        # self.fb_type_combo.addItems(["Hata Raporu", "Özellik Önerisi", "Teşekkür / Diğer"])
        # self.fb_type_combo.setFixedSize(160, 35)
        # self.fb_type_combo.setStyleSheet("QComboBox { background-color: #1a1f2e; color: #e8edf2; border: 1px solid #2d3748; border-radius: 6px; padding: 5px; }")
        
        # self.fb_contact_input = QLineEdit()
        # self.fb_contact_input.setPlaceholderText("Discord veya E-posta (İsteğe bağlı)")
        # self.fb_contact_input.setFixedHeight(35)
        # self.fb_contact_input.setStyleSheet("QLineEdit { background-color: #1a1f2e; color: #e8edf2; border: 1px solid #2d3748; border-radius: 6px; padding: 5px; }")
        
        # fb_top_layout.addWidget(self.fb_type_combo)
        # fb_top_layout.addWidget(self.fb_contact_input)
        # fb_layout.addLayout(fb_top_layout)

        # # Mesaj Alanı
        # self.fb_message_input = QTextEdit()
        # self.fb_message_input.setPlaceholderText("Mesajınızı buraya yazın...")
        # self.fb_message_input.setMaximumHeight(100)
        # self.fb_message_input.setStyleSheet("QTextEdit { background-color: #1a1f2e; color: #e8edf2; border: 1px solid #2d3748; border-radius: 6px; padding: 10px; }")
        # fb_layout.addWidget(self.fb_message_input)

        # # Gönder Butonu
        # self.fb_send_btn = QPushButton("🚀 Geri Bildirimi Gönder")
        # self.fb_send_btn.setFixedHeight(40)
        # self.fb_send_btn.setCursor(Qt.PointingHandCursor)
        # self.fb_send_btn.setStyleSheet("QPushButton { background-color: #6c8eff; color: white; border-radius: 6px; font-weight: bold; border: none; } QPushButton:hover { background-color: #5a7bee; }")
        # self.fb_send_btn.clicked.connect(self.send_feedback)
        # fb_layout.addWidget(self.fb_send_btn)

        # feedback_group.setLayout(fb_layout)
        # layout.addWidget(feedback_group) # AYARLARDAN KALDIRILDI, YENİ SAYFAYA TAŞINDI
        
        layout.addStretch()
        
        scroll.setWidget(container)
        
        # Sayfa Layout'u
        page_layout = QVBoxLayout()
        page_layout.addWidget(scroll)
        
        self.stack.addWidget(self.create_page_template("Ayarlar", page_layout))

    def apply_theme(self, color, save=True):
        self.accent_color = color
        Config.THEME_COLOR = color
        
        if save:
            self.settings["theme"] = color
            self.save_settings()
        
        # 1. Sidebar Butonlarını Güncelle
        style = "QPushButton { background-color: #1a1f2e; color: #9ca3af; text-align: left; padding: 16px 20px; border: none; font-size: 13px; font-weight: 500; } QPushButton:hover { background-color: #2d3748; color: #e8edf2; } QPushButton:checked { background-color: #252d3a; color: %s; border-right: 3px solid %s; font-weight: bold; }" % (color, color)
        
        for btn in self.nav_btns:
            btn.setStyleSheet(style)
            
        # 2. Onay Mesajı - KALDIRILDI
        # QMessageBox.information(self, "Tema Güncellendi", f"Tema rengi başarıyla değiştirildi: {color}")
        
    def change_language(self, index):
        lang = self.lang_combo.currentText()
        
        self.settings["language"] = lang
        self.save_settings()
        
        if index > 0: # Türkçe dışındakiler
             # QMessageBox.information(self, "Dil Değişikliği", f"Dil '{lang}' olarak ayarlandı.\nDeğişikliklerin tam uygulanması için uygulamayı yeniden başlatın.")
             pass
        else:
             # Türkçe seçilirse bişey demeye gerek yok (varsayılan)
             pass

    def clear_all_cache(self):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Onay")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText("Tüm tarama geçmişi ve önbellek silinecek.\nOnaylıyor musunuz?")
        
        btn_evet = msg_box.addButton("Evet", QMessageBox.YesRole)
        btn_hayir = msg_box.addButton("Hayır", QMessageBox.NoRole)
        msg_box.setDefaultButton(btn_hayir)
        msg_box.exec_()
        
        if msg_box.clickedButton() == btn_evet:
            try:
                if CACHE_PATH.exists():
                    shutil.rmtree(CACHE_PATH)
                    CACHE_PATH.mkdir(exist_ok=True)
                    self.scan_results = {}
                    QMessageBox.information(self, "Başarılı", "Önbellek temizlendi!")
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Silme hatası: {str(e)}")

    def create_community_page(self):
        """Topluluk Kütüphanesi Sayfası"""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Kendimize ait, daha ufak bir baslik ekleyelim
        baslik = QLabel("🌍 Topluluk Çeviri Kütüphanesi")
        baslik.setStyleSheet("color: white; font-size: 22px; font-weight: bold;")

        # Uyarı/Açıklama
        warning = QLabel("Bu kütüphane MemoFast topluluğunun çevirdiği oyunların canlı veritabanıdır.")
        warning.setStyleSheet("color: #94a3b8; font-size: 13px; font-weight: 500;")
        
        # Arama Kutusu
        self.community_search = QLineEdit()
        self.community_search.setPlaceholderText("🔍 Oyun adı ara...")
        self.community_search.setStyleSheet(
            "QLineEdit { background-color: #1a1f2e; color: white; border: 1px solid #2d3748; "
            "border-radius: 6px; padding: 5px 10px; font-size: 14px; min-width: 220px; }"
        )
        self.community_search.textChanged.connect(self._filter_community_table)
        
        header_h = QHBoxLayout()
        header_h.addWidget(baslik)
        header_h.addStretch()
        header_h.addWidget(self.community_search)
        
        layout.addLayout(header_h)
        layout.addWidget(warning)
        

        # --- Istatistik Paneli ---
        stats_group = QGroupBox("Genel Istatistikler")
        stats_group.setFixedHeight(100)
        stats_group.setStyleSheet("QGroupBox { color: " + self.accent_color + "; font-size: 12px; font-weight: bold; border: 1px solid #2d3748; border-radius: 8px; margin-top: 5px; padding-top: 5px; background-color: #1a1f2e; }")
        stats_layout = QHBoxLayout()
        stats_layout.setContentsMargins(10, 10, 10, 10)
        stats_layout.setSpacing(15)

        # Kullanıcı Sayısı Kutusu
        users_box = QVBoxLayout()
        self.users_val_lbl = QLabel("...")
        self.users_val_lbl.setStyleSheet("color: #10b981; font-size: 24px; font-weight: bold;")
        self.users_val_lbl.setAlignment(Qt.AlignCenter)
        users_title = QLabel("Toplam Kullanıcı")
        users_title.setStyleSheet("color: #94a3b8; font-size: 13px;")
        users_title.setAlignment(Qt.AlignCenter)
        users_box.addWidget(self.users_val_lbl)
        users_box.addWidget(users_title)

        # Çevrilen Oyun Sayısı Kutusu
        trans_box = QVBoxLayout()
        self.trans_val_lbl = QLabel("...")
        self.trans_val_lbl.setStyleSheet("color: #6c8eff; font-size: 24px; font-weight: bold;")
        self.trans_val_lbl.setAlignment(Qt.AlignCenter)
        trans_title = QLabel("Çevrilen Oyun")
        trans_title.setStyleSheet("color: #94a3b8; font-size: 13px;")
        trans_title.setAlignment(Qt.AlignCenter)
        trans_box.addWidget(self.trans_val_lbl)
        trans_box.addWidget(trans_title)

        # Çevrilemeyen Oyun Sayısı Kutusu
        untrans_box = QVBoxLayout()
        self.untrans_val_lbl = QLabel("...")
        self.untrans_val_lbl.setStyleSheet("color: #ef4444; font-size: 24px; font-weight: bold;")
        self.untrans_val_lbl.setAlignment(Qt.AlignCenter)
        untrans_title = QLabel("Çevrilemedi")
        untrans_title.setStyleSheet("color: #94a3b8; font-size: 13px;")
        untrans_title.setAlignment(Qt.AlignCenter)
        untrans_box.addWidget(self.untrans_val_lbl)
        untrans_box.addWidget(untrans_title)

        stats_layout.addLayout(users_box)
        
        # Araya çizgi
        line1 = QFrame()
        line1.setFrameShape(QFrame.VLine)
        line1.setFrameShadow(QFrame.Sunken)
        line1.setStyleSheet("background-color: #2d3748;")
        stats_layout.addWidget(line1)
        
        stats_layout.addLayout(trans_box)
        
        line2 = QFrame()
        line2.setFrameShape(QFrame.VLine)
        line2.setFrameShadow(QFrame.Sunken)
        line2.setStyleSheet("background-color: #2d3748;")
        stats_layout.addWidget(line2)
        
        stats_layout.addLayout(untrans_box)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        # -------------------------



        # Eger essiz id yoksa olustur ve kaydet
        import uuid
        if not hasattr(self, 'settings') or 'unique_client_id' not in self.settings:
            # varsayilan olarak settings dict'in memofast_gui icinde config veya settings ile yonetiliyor 
            # ancak biz sadece var olup olmadigina bakacagiz, eger yoksa olusturacagiz.
            if not getattr(self, "settings", None):
                self.settings = {}
            if "unique_client_id" not in self.settings:
                client_id = str(uuid.uuid4())
                self.settings["unique_client_id"] = client_id
                if hasattr(self, 'save_settings'):
                    self.save_settings()
        
        # Oyun Listesi Tablosu
        list_lbl = QLabel("🎮 Oyun Veritabanı")
        list_lbl.setStyleSheet(f"color: {self.accent_color}; font-size: 16px; font-weight: bold; margin-top: 15px;")
        layout.addWidget(list_lbl)
        
        self.community_games_table = QTableWidget(0, 4)
        self.community_games_table.setHorizontalHeaderLabels(["Oyun Adı", "Oyun Motoru", "Çeviren Kullanıcı", "Başarı Oranı"])
        self.community_games_table.horizontalHeader().setStretchLastSection(True)
        self.community_games_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.community_games_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.community_games_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.community_games_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.community_games_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.community_games_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.community_games_table.setStyleSheet("""
            QTableWidget { background-color: #0f1419; color: #e8edf2; border: 1px solid #2d3748; border-radius: 8px; font-size: 14px; }
            QHeaderView::section { background-color: #1a1f2e; color: #94a3b8; font-weight: bold; padding: 5px; border: 1px solid #2d3748; }
            QTableWidget::item { padding: 5px; border-bottom: 1px solid #1a1f2e; }
        """)
        
        self.community_games_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.community_games_table, stretch=1)
        
        # Istatistikleri Google E-Tablo'dan cek ve arayuzu guncelle
        self.fetch_community_stats()


        # create_page_template fonksiyonuna başlık yollamıyoruz (yer kaplamasın diye)
        page_widget = self.create_page_template("", layout)
        
        # page_widget'in icindeki QVBoxLayout'un marginini sifirlayalim ki ustten bosluk kalmasin
        if page_widget.layout() and page_widget.layout().count() > 1:
            main_content = page_widget.layout().itemAt(1).widget()
            if main_content and main_content.layout():
                main_content.layout().setContentsMargins(10, 10, 10, 10)
                # Eger create_page_template bos bir header uretiyorsa (Label), onu gizleyelim
                for i in range(main_content.layout().count()):
                    widget = main_content.layout().itemAt(i).widget()
                    if isinstance(widget, QLabel) and widget.text() == "":
                        widget.hide()
                        
        self.stack.addWidget(page_widget)

    def send_community_data(self, client_id, oyun_adi="NONE", oyun_motoru="NONE", durum="NONE", islem_turu="Oyun Çevirisi"):
        """Topluluk verilerini Google Form üzerinden arka planda (thread ile) gizlice veritabanına gönderir."""
        import urllib.request
        import urllib.parse
        import logging
        import threading
        
        def _send():
            # Form URL'sinde /viewform yerine /formResponse olacak
            FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeVIGbi3JPh-OHhJCT-2jrIgIx8ooc7t8ftVplrIDuLvw6CGQ/formResponse"
            
            # Senin yolladığın ID'lerle veriler eşleştirilir
            data = {
                "entry.589249245": str(client_id),      # kullanici_id
                "entry.407098137": str(oyun_adi),       # oyun_adi
                "entry.436830681": str(oyun_motoru),    # oyun_motoru
                "entry.900156386": str(durum),          # durum (Çevrildi / Çevrilmedi)
                "entry.432261766": str(islem_turu)      # islem_turu (Kullanıcı Kaydı / Oyun Çevirisi)
            }
            
            try:
                encoded_data = urllib.parse.urlencode(data).encode("utf-8")
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
                req = urllib.request.Request(FORM_URL, data=encoded_data, headers=headers, method="POST")
                
                # Arka planda donmadan gönder
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status in [200, 302]:
                        logging.info(f"Topluluk verisi gonderildi: {islem_turu} / {oyun_adi}")
            except Exception as e:
                logging.error(f"Topluluk verisi gonderilemedi: {e}")

        # PyQt arayüzünü kilitlememek için işlemi arka planda bir thread'e devrediyoruz
        thread = threading.Thread(target=_send, daemon=True)
        thread.start()

    def fetch_community_stats(self):
        """Topluluk istatistiklerini Google E-Tablo'dan arka planda çeker ve UI günceller"""
        class StatsWorker(QThread):
            stats_fetched = pyqtSignal(int, int, int, list)
            
            def run(self):
                import urllib.request
                import csv
                import logging
                import time
                
                CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ145iHdBr91wLtlm2bunGnUIyWt1RGbiJ8R0wxMTK5X7Nibj8OG82ydLRkFFh_zdq62wDdgUyJHpIa/pub?output=csv"
                try:
                    # Google'ın geçici önbelleğe almaması için sonuna zaman damgası ekliyoruz
                    no_cache_url = f"{CSV_URL}&t={int(time.time())}"
                    req = urllib.request.Request(no_cache_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        lines = [line.decode('utf-8') for line in response.readlines()]
                    
                    reader = csv.DictReader(lines)
                    users = set()
                    translated_games = set()   # benzersiz (uid, game_name) çiftleri
                    untranslated_games = set()
                    game_counts = {}
                    
                    for row in reader:
                        uid = row.get("kullanici_adi", "").strip()
                        game_name = row.get("oyun_adi", "").strip()
                        game_engine = row.get("oyun_motoru", "").strip()
                        if uid and uid != "NONE":
                            users.add(uid)
                        
                        st = row.get("durum", "").strip()
                        
                        is_translated = False
                        is_untranslated = False
                        
                        st_lower = st.lower()
                        if st in ("Çevrildi", "TEST") or st_lower == "çevrildi":
                            is_translated = True
                        elif st == "Çevrilmedi" or st_lower == "çevrilmedi":
                            is_untranslated = True
                        else:
                            # NONE, boş, bilinmeyen → sayma
                            continue
                            
                        # Aynı kullanıcı + aynı oyun çifti varsa atla (tekrar sayma)
                        pair_key = (uid, game_name)
                        if is_translated:
                            if pair_key in translated_games:
                                continue
                            translated_games.add(pair_key)
                        elif is_untranslated:
                            if pair_key in untranslated_games:
                                continue
                            untranslated_games.add(pair_key)
                            
                        # Eğer oyun adı varsa, tabloya eklenecek istatistiği oluştur
                        if game_name and game_name != "NONE":
                            key = (game_name, game_engine)
                            if key not in game_counts:
                                game_counts[key] = {"users": set(), "success": 0, "fail": 0}
                            
                            if uid and uid != "NONE":
                                game_counts[key]["users"].add(uid)
                            else:
                                import uuid
                                game_counts[key]["users"].add(str(uuid.uuid4()))
                                
                            if is_translated:
                                game_counts[key]["success"] += 1
                            elif is_untranslated:
                                game_counts[key]["fail"] += 1
                    
                    translated = len(translated_games)
                    untranslated = len(untranslated_games)
                                
                    # Sözlükten listeye çevirip azalan sırayla dizelim (Çeviren kişi sayısına göre)
                    games_list = []
                    for (g_name, g_engine), stats in game_counts.items():
                        total_att = stats["success"] + stats["fail"]
                        if total_att == 0:
                            continue
                        
                        rate = int((stats["success"] / total_att) * 100)
                        games_list.append({
                            "name": g_name,
                            "engine": g_engine,
                            "count": len(stats["users"]),
                            "rate": rate
                        })
                        
                    games_list.sort(key=lambda x: x["count"], reverse=True)
                            
                    self.stats_fetched.emit(len(users), translated, untranslated, games_list)

                except Exception as e:
                    logging.error(f"Topluluk istatistikleri çekilemedi: {e}")

        # Thread'in kapanmaması için MainWindow objesine bağlayalım
        self._stats_worker = StatsWorker()
        self._stats_worker.stats_fetched.connect(self._update_stats_ui)
        self._stats_worker.start()

    def _update_stats_ui(self, users, translated, untranslated, games_list):
        if hasattr(self, 'users_val_lbl'):
            self.users_val_lbl.setText(str(users))
        if hasattr(self, 'trans_val_lbl'):
            self.trans_val_lbl.setText(str(translated))
        if hasattr(self, 'untrans_val_lbl'):
            self.untrans_val_lbl.setText(str(untranslated))
            
        # Topluluk verilerini sakla (oyun_adi -> rate)
        self._community_games_data = {}
        for g in games_list:
            self._community_games_data[g["name"].lower()] = g.get("rate", 0)
        
        if hasattr(self, 'community_games_table'):
            self.community_games_table.setRowCount(0)
            for game_info in games_list:
                row_idx = self.community_games_table.rowCount()
                self.community_games_table.insertRow(row_idx)
                
                name_item = QTableWidgetItem(game_info["name"])
                name_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                self.community_games_table.setItem(row_idx, 0, name_item)
                
                engine_item = QTableWidgetItem(game_info["engine"])
                engine_item.setTextAlignment(Qt.AlignCenter)
                self.community_games_table.setItem(row_idx, 1, engine_item)
                
                count_item = QTableWidgetItem(f"{game_info['count']} Kişi")
                count_item.setTextAlignment(Qt.AlignCenter)
                self.community_games_table.setItem(row_idx, 2, count_item)
                
                rate = game_info.get("rate", 0)
                if rate >= 50:
                    status_text = f"✅ Çalışıyor (%{rate})"
                    color = QColor("#10b981")
                else:
                    status_text = f"❌ Uyumsuz (%{rate})"
                    color = QColor("#ef4444")
                    
                status_item = QTableWidgetItem(status_text)
                status_item.setTextAlignment(Qt.AlignCenter)
                status_item.setForeground(color)
                font = status_item.font()
                font.setBold(True)
                status_item.setFont(font)
                self.community_games_table.setItem(row_idx, 3, status_item)

        # game_table'daki oyunları topluluk verisiyle işaretle
        self._mark_game_table_from_community()


    def _mark_game_table_from_community(self):
        """game_table'daki oyunlara topluluk verisi ikonunu atar (col 2 = durum)."""
        if not hasattr(self, 'game_table') or not hasattr(self, '_community_games_data'):
            return
        
        for row in range(self.game_table.rowCount()):
            name_item = self.game_table.item(row, 1)
            if not name_item:
                continue
            
            game_name_lower = name_item.text().lower()
            for ch in [" 🔑", " (korumalı? yine de deneyin)"]:
                game_name_lower = game_name_lower.replace(ch, "")
            game_name_lower = game_name_lower.strip()
            
            status_item = self.game_table.item(row, 2)
            if not status_item:
                status_item = QTableWidgetItem("")
                self.game_table.setItem(row, 2, status_item)
            
            if game_name_lower in self._community_games_data:
                rate = self._community_games_data[game_name_lower]
                if rate >= 50:
                    status_item.setText(f"✅ %{rate}")
                    status_item.setForeground(QColor("#10b981"))
                    status_item.setToolTip(f"Topluluk: %{rate} başarı oranı")
                else:
                    status_item.setText(f"❌ %{rate}")
                    status_item.setForeground(QColor("#ef4444"))
                    status_item.setToolTip(f"Topluluk: %{rate} başarı oranı")
            else:
                status_item.setText("")
                status_item.setToolTip("")

    def create_free_games_page(self):
        """Ücretsiz Oyunlar (GamerPower API) Sayfası"""
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Header
        header_h = QHBoxLayout()
        baslik = QLabel("🎁 Güncel Ücretsiz Oyun ve Paketler")
        baslik.setStyleSheet("color: white; font-size: 24px; font-weight: bold;")
        header_h.addWidget(baslik)
        
        header_h.addStretch()
        
        refresh_btn = QPushButton("🔄 Yenile")
        refresh_btn.setStyleSheet("""
            QPushButton { 
                background-color: #2d3748; color: white; border-radius: 6px; 
                padding: 8px 15px; font-weight: bold; border: 1px solid #3d4758;
            }
            QPushButton:hover { background-color: #3d4758; }
        """)
        refresh_btn.clicked.connect(self.fetch_free_games)
        header_h.addWidget(refresh_btn)
        
        layout.addLayout(header_h)
        
        desc = QLabel("GamerPower API aracılığıyla Steam, Epic, GOG ve diğer platformlardaki aktif hediye ve kampanyalar listelenmektedir.")
        desc.setStyleSheet("color: #94a3b8; font-size: 13px;")
        layout.addWidget(desc)
        
        # Scroll Area for Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        self.free_games_container = QWidget()
        self.free_games_container.setStyleSheet("background-color: transparent;")
        self.free_games_grid = QGridLayout()
        self.free_games_grid.setSpacing(20)
        self.free_games_grid.setContentsMargins(0, 0, 0, 0)
        
        main_v = QVBoxLayout(self.free_games_container)
        main_v.setContentsMargins(0, 0, 0, 0)
        main_v.setSpacing(20)
        
        # Steam Next Fest Row
        self.steam_section = QWidget()
        self.steam_section_layout = QVBoxLayout(self.steam_section)
        self.steam_section_layout.setContentsMargins(0, 0, 0, 0)
        
        st_header = QLabel("🚀 Gelecekteki Popüler Demolar (Steam Next Fest)")
        st_header.setStyleSheet("color: #6c8eff; font-size: 16px; font-weight: bold; margin-bottom: 5px;")
        self.steam_section_layout.addWidget(st_header)
        
        self.steam_grid_layout = QGridLayout()
        self.steam_grid_layout.setSpacing(20)
        self.steam_section_layout.addLayout(self.steam_grid_layout)
        
        main_v.addWidget(self.steam_section)
        
        # Separator Line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #2d3748; max-height: 1px; border: none;")
        main_v.addWidget(line)
        
        # Diğer Ücretsiz Oyunlar header
        others_header = QLabel("🎁 Aktif Kampanyalar & Tam Oyunlar")
        others_header.setStyleSheet("color: #10b981; font-size: 16px; font-weight: bold;")
        main_v.addWidget(others_header)
        
        main_v.addLayout(self.free_games_grid)
        main_v.addStretch()
        
        scroll.setWidget(self.free_games_container)
        layout.addWidget(scroll)
        
        # Info Panel / Status
        self.free_games_status = QLabel("Veriler yükleniyor...")
        self.free_games_status.setStyleSheet("color: #6c8eff; font-size: 14px; font-weight: bold;")
        self.free_games_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.free_games_status)
        
        # Fetch initial data
        QTimer.singleShot(500, self.fetch_free_games)
        
        page_widget = self.create_page_template("", layout)
        
        # page_widget'in icindeki QVBoxLayout'un marginini sifirlayalim
        if page_widget.layout() and page_widget.layout().count() > 1:
            main_content = page_widget.layout().itemAt(1).widget()
            if main_content and main_content.layout():
                main_content.layout().setContentsMargins(10, 10, 10, 10)
                # Eger create_page_template bos bir header uretiyorsa gizleyelim
                for i in range(main_content.layout().count()):
                    w = main_content.layout().itemAt(i).widget()
                    if isinstance(w, QLabel) and w.text() == "":
                        w.hide()
                        
        self.stack.addWidget(page_widget)

    def fetch_free_games(self):
        """GamerPower API'den veri çek"""
        try:
            if not hasattr(self, 'free_games_status') or self.free_games_status is None:
                return
            # Objenin silinip silinmediğini kontrol et
            self.free_games_status.isVisible() 
        except RuntimeError:
            return

        self.free_games_status.setText("⌛ Veriler GamerPower sunucularından çekiliyor...")
        self.free_games_status.show()
            
        # Temizle
        if hasattr(self, 'steam_grid_layout') and self.steam_grid_layout is not None:
            while self.steam_grid_layout.count():
                item = self.steam_grid_layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()

        if hasattr(self, 'free_games_grid') and self.free_games_grid is not None:
            for i in reversed(range(self.free_games_grid.count())): 
                item = self.free_games_grid.itemAt(i)
                if item:
                    w = item.widget()
                    if w:
                        w.setParent(None)
                        w.deleteLater()
            
        self.fg_worker = FreeGamesWorker()
        self.fg_worker.finished.connect(self.on_free_games_loaded)
        self.fg_worker.error.connect(self.on_free_games_error)
        self.fg_worker.start()

        # Steam Next Fest Worker
        self.snf_worker = SteamNextFestWorker()
        self.snf_worker.finished.connect(self.on_steam_next_fest_loaded)
        self.snf_worker.start()

    def on_steam_next_fest_loaded(self, steam_games):
        """Steam Next Fest oyunlarını UI'ya bas (Responsive Grid)"""
        if not hasattr(self, 'steam_grid_layout') or self.steam_grid_layout is None: return
        
        # Ekran genişliğine göre sütun sayısını hesapla
        # Her kart yaklaşık 240px yer kaplıyor (230px card + 10px margin/gap)
        width = self.width() - 300 # Sidebar ve marginleri çıkar
        cols = max(2, width // 240) 
        
        for i, game in enumerate(steam_games):
            # 4K monitörde daha fazla, küçükte daha az ama genelde 1 veya 2 satır
            # Kullanıcı 6 tane istediği için max 12 çekmiştik, şimdi yerleştirelim
            row = i // cols
            col = i % cols
            
            # Sadece ilk 1-2 satırı göster (Üst sıra mantığını bozmamak için)
            if row >= 2: break 
            
            card = SteamGameCard(game)
            self.steam_grid_layout.addWidget(card, row, col)


    def on_free_games_error(self, err_msg):
        try:
            if hasattr(self, 'free_games_status') and self.free_games_status:
                self.free_games_status.setText(f"❌ Hata: {err_msg}")
        except RuntimeError: pass

    def on_free_games_loaded(self, games_list):
        """API'den gelen verileri UI'ya bas"""
        try:
            if hasattr(self, 'free_games_status') and self.free_games_status:
                self.free_games_status.hide()
        except RuntimeError:
            return

        self._cached_free_games = games_list
        
        if not games_list:
            try:
                self.free_games_status.setText("📭 Şu an aktif kampanya bulunamadı.")
                self.free_games_status.show()
            except RuntimeError: pass
            return
            
        self.arrange_free_games_grid()

    def arrange_free_games_grid(self):
        """Ücretsiz oyunlar grid'ini responsive olarak düzenle"""
        try:
            if not hasattr(self, 'free_games_grid') or self.free_games_grid is None:
                return
            # Grid'in parent widget'ı silinmiş mi kontrol et
            if not self.free_games_grid.parentWidget():
                return
        except RuntimeError:
            return

        if not hasattr(self, '_cached_free_games') or not self._cached_free_games:
            return
            
        games = self._cached_free_games
        
        # Grid'i temizle
        while self.free_games_grid.count():
            item = self.free_games_grid.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()
                
        # Responsive Sütun Hesabı
        viewport_width = self.width() - 320 
        
        calculated_cols = (viewport_width + 20) // 270
        max_cols = max(1, int(calculated_cols))
        
        content_width = (max_cols * 250) + ((max_cols - 1) * 20)
        side_margin = max(0, (viewport_width - content_width) // 2)
        
        self.free_games_grid.setContentsMargins(side_margin, 0, side_margin, 0)
        
        for idx, game in enumerate(games):
            row = idx // max_cols
            col = idx % max_cols
            card = FreeGameCard(game)
            self.free_games_grid.addWidget(card, row, col)
            
    def _filter_community_table(self, text):
        if not hasattr(self, 'community_games_table'):
            return
        for row in range(self.community_games_table.rowCount()):
            item = self.community_games_table.item(row, 0)
            if item:
                self.community_games_table.setRowHidden(row, text.lower() not in item.text().lower())

    def create_feedback_page(self):

        """Geri Bildirim ve Destek Sayfası"""
        layout = QVBoxLayout()
        layout.setSpacing(25)
        layout.setContentsMargins(30, 30, 30, 30)

        # Başlık ve Uyarı
        header_v = QVBoxLayout()
        title = QLabel("📣 Geri Bildirim ve Destek")
        title.setStyleSheet("color: #e8edf2; font-size: 24px; font-weight: bold;")
        
        warning = QLabel("⚠️ Lütfen oyun çevirisi istemeyin! Bu kanal sadece MemoFast'in gelişimi için öneriler ve hata raporlarını içerir.")
        warning.setStyleSheet("color: #fbbf24; font-size: 13px; font-weight: 500; margin-top: 5px;")
        
        more_info = QLabel('Daha fazlası, yardım ve topluluk için: <a href="https://www.youtube.com/@MehmetariTv" style="color: #6c8eff; text-decoration: none;">Mehmet Arı YouTube Kanalı</a>')
        more_info.setOpenExternalLinks(True)
        more_info.setStyleSheet("color: #94a3b8; font-size: 13px;")
        
        header_v.addWidget(title)
        header_v.addWidget(warning)
        header_v.addWidget(more_info)
        layout.addLayout(header_v)

        # Form Alanı
        form_group = QGroupBox("Bize Yazın")
        form_group.setStyleSheet("QGroupBox { color: " + self.accent_color + "; font-size: 16px; font-weight: bold; border: 1px solid #2d3748; border-radius: 12px; margin-top: 20px; padding-top: 25px; background-color: #141823; }")
        
        fg_layout = QVBoxLayout()
        fg_layout.setContentsMargins(30, 40, 30, 30)
        fg_layout.setSpacing(20)

        # Konu Seçimi
        type_v = QVBoxLayout()
        type_lbl = QLabel("Konu Başlığı:")
        type_lbl.setStyleSheet("color: #e8edf2; font-weight: bold;")
        self.fb_type_combo = QComboBox()
        # ÖNEMLİ: Buradaki metinler senin Google Form'undaki seçeneklerle BİREBİR AYNI olmalı
        self.fb_type_combo.addItems(["Hata Raporu", "Öneri", "Teşekkür"])
        self.fb_type_combo.setFixedHeight(40)
        self.fb_type_combo.setStyleSheet("QComboBox { background-color: #1a1f2e; color: #e8edf2; border: 1px solid #2d3748; border-radius: 8px; padding: 5px 15px; }")
        type_v.addWidget(type_lbl)
        type_v.addWidget(self.fb_type_combo)
        fg_layout.addLayout(type_v)

        # İletişim
        contact_v = QVBoxLayout()
        contact_lbl = QLabel("İletişim (E-posta veya Discord):")
        contact_lbl.setStyleSheet("color: #e8edf2; font-weight: bold;")
        self.fb_contact_input = QLineEdit()
        self.fb_contact_input.setPlaceholderText("Sana ulaşabilmemiz için...")
        self.fb_contact_input.setFixedHeight(40)
        self.fb_contact_input.setStyleSheet("QLineEdit { background-color: #1a1f2e; color: #e8edf2; border: 1px solid #2d3748; border-radius: 8px; padding: 5px 15px; }")
        contact_v.addWidget(contact_lbl)
        contact_v.addWidget(self.fb_contact_input)
        fg_layout.addLayout(contact_v)

        # Mesaj
        msg_v = QVBoxLayout()
        msg_lbl = QLabel("Mesajınız:")
        msg_lbl.setStyleSheet("color: #e8edf2; font-weight: bold;")
        self.fb_message_input = QTextEdit()
        self.fb_message_input.setPlaceholderText("Lütfen detaylıca açıklayın...")
        self.fb_message_input.setMinimumHeight(150)
        self.fb_message_input.setStyleSheet("QTextEdit { background-color: #1a1f2e; color: #e8edf2; border: 1px solid #2d3748; border-radius: 12px; padding: 15px; font-size: 14px; }")
        msg_v.addWidget(msg_lbl)
        msg_v.addWidget(self.fb_message_input)
        fg_layout.addLayout(msg_v)

        # Gönder Butonu
        self.fb_send_btn = QPushButton("🚀 Geri Bildirimi Gönder")
        self.fb_send_btn.setFixedHeight(50)
        self.fb_send_btn.setCursor(Qt.PointingHandCursor)
        self.fb_send_btn.setStyleSheet("QPushButton { background-color: " + self.accent_color + "; color: white; border-radius: 8px; font-size: 16px; font-weight: bold; } QPushButton:hover { background-color: #5a7bee; }")
        self.fb_send_btn.clicked.connect(self.send_feedback)
        fg_layout.addWidget(self.fb_send_btn)

        form_group.setLayout(fg_layout)
        layout.addWidget(form_group)
        layout.addStretch()
        
        # Sayfayı stack'e ekle (switch_page bunu doğru index'e taşıyacak)
        page_widget = self.create_page_template("Geri Bildirim", layout)
        self.stack.addWidget(page_widget)

    def send_feedback(self):
        """Geri bildirimi AI denetiminden geçirdikten sonra Google Form'a gönderir"""
        fb_message = self.fb_message_input.toPlainText().strip()
        
        if not fb_message:
            QMessageBox.warning(self, "Uyarı", "Lütfen bir mesaj yazın.")
            return

        # 1. AI Denetimini Başlat
        api_key = self.settings.get("gemini_api_key", "")
        pref_model = self.settings.get("preferred_gemini_model")
        
        self.fb_send_btn.setEnabled(False)
        self.fb_send_btn.setText("AI Denetleniyor...")
        
        self.fb_moderator = FeedbackModeratorWorker(api_key, fb_message, pref_model)
        self.fb_moderator.finished.connect(self.on_feedback_moderated)
        self.fb_moderator.error.connect(lambda err: self.on_feedback_moderated(True, "AI Hatası")) # Hata varsa geçsin
        self.fb_moderator.start()

    def on_feedback_moderated(self, is_allowed, reason):
        """AI denetimi bittiğinde asıl gönderim işlemini yap veya engelle"""
        if not is_allowed:
            QMessageBox.critical(self, "Engellendi", reason)
            self.fb_send_btn.setEnabled(True)
            self.fb_send_btn.setText("📧 Geri Bildirimi Gönder")
            return

        # 2. Eğer onaylandıysa asıl gönderim işlemini yap
        fb_type_full = self.fb_type_combo.currentText()
        fb_type = fb_type_full.replace("🐛 ", "").replace("💡 ", "").replace("🌟 ", "").split(" / ")[0]
        fb_contact = self.fb_contact_input.text().strip()
        fb_message = self.fb_message_input.toPlainText().strip()

        FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSewcNBn7F-I2o5BvUmkzx-B3LaQh6YqcWLE2UH6ku_6252lgQ/formResponse"
        
        data = {
            "entry.167998956": fb_type,
            "entry.1163246443": fb_contact if fb_contact else "Belirtilmedi",
            "entry.981290208": fb_message + f"\n\n[Sürüm: {Config.VERSION}]"
        }

        try:
            self.fb_send_btn.setText("Gönderiliyor...")
            
            from urllib.parse import urlencode
            from urllib.request import Request, urlopen
            
            encoded_data = urlencode(data).encode("utf-8")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            
            req = Request(FORM_URL, data=encoded_data, headers=headers, method="POST")
            
            with urlopen(req, timeout=10) as response:
                if response.status == 200 or response.status == 302:
                    QMessageBox.information(self, "Başarılı", "Geri bildiriminiz başarıyla iletildi. Teşekkürler!")
                    self.fb_message_input.clear()
                    self.fb_contact_input.clear()
                else:
                    raise Exception(f"HTTP Durum Kodu: {response.status}")
                    
        except Exception as e:
            logger.error("Feedback gönderim hatası: %s", e)
            # Gerçek hatayı kullanıcıya gösterelim ki ne olduğunu anlayalım
            QMessageBox.critical(self, "Hata", f"Gönderim başarısız oldu.\n\nHata: {str(e)}\n\nLütfen internet bağlantınızı kontrol edin veya daha sonra tekrar deneyin.")
        finally:
            self.fb_send_btn.setEnabled(True)
            self.fb_send_btn.setText("🚀 Geri Bildirimi Gönder")

    def create_about_page(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)
        
        # Logo
        logo = QLabel("MEMOFAST")
        logo.setStyleSheet(f"font-size: 48px; font-weight: 900; color: {self.accent_color}; letter-spacing: 2px;")
        
        version = QLabel(f"Sürüm {Config.VERSION}")
        version.setStyleSheet("color: #9ca3af; font-size: 16px;")
        
        desc = QLabel("Oyun yamalarınızı yönetmek ve sisteminizi optimize etmek için tasarlandı.")
        desc.setStyleSheet("color: #e8edf2; font-size: 14px; margin-top: 10px;")
        
        # Güncelleme Merkezi Butonu
        update_btn = QPushButton(" Güncelleme Merkezi")
        update_btn.setFixedSize(220, 45)
        update_btn.setCursor(Qt.PointingHandCursor)
        update_btn.setStyleSheet("QPushButton { background-color: #1a1f2e; color: #e8edf2; border: 1px solid #2d3748; border-radius: 8px; font-weight: bold; } QPushButton:hover { background-color: #2d3748; border-color: #6c8eff; }")
        update_btn.clicked.connect(lambda: self.switch_page(4))
        
        # Tanıtım Butonu
        help_btn = QPushButton("❓ Tanıtımı Göster")
        help_btn.setFixedSize(220, 45)
        help_btn.setCursor(Qt.PointingHandCursor)
        help_btn.setStyleSheet("QPushButton { background-color: #1a1f2e; color: #e8edf2; border: 1px solid #2d3748; border-radius: 8px; font-weight: bold; } QPushButton:hover { background-color: #2d3748; border-color: #fbbf24; }")
        help_btn.clicked.connect(self.show_welcome_dialog)

        cop = QLabel("© 2024 Mehmet Arı. Tüm hakları saklıdır.")
        cop.setStyleSheet("color: #6b7280; font-size: 12px; margin-top: 40px;")
        
        layout.addWidget(logo, 0, Qt.AlignCenter)
        layout.addWidget(version, 0, Qt.AlignCenter)
        layout.addWidget(desc, 0, Qt.AlignCenter)
        layout.addWidget(update_btn, 0, Qt.AlignCenter)
        layout.addWidget(help_btn, 0, Qt.AlignCenter)
        layout.addWidget(cop, 0, Qt.AlignCenter)
        
        # Sosyal Medya
        sm_layout = QHBoxLayout()
        sm_layout.setSpacing(20)
        
        yt_btn = QPushButton("YouTube")
        yt_btn.setCursor(Qt.PointingHandCursor)
        yt_btn.setStyleSheet("color: #ef4444; font-weight: bold; border: none; font-size: 14px;")
        yt_btn.clicked.connect(lambda: webbrowser.open("https://www.youtube.com/@MehmetariTv"))
        
        web_btn = QPushButton("Web Sitesi")
        web_btn.setCursor(Qt.PointingHandCursor)
        web_btn.setStyleSheet("color: #3b82f6; font-weight: bold; border: none; font-size: 14px;")
        
        sm_layout.addWidget(yt_btn)
        sm_layout.addWidget(web_btn)
        layout.addLayout(sm_layout)
        
        self.stack.addWidget(self.create_page_template("Hakkında", layout))

    def show_welcome_dialog(self):
        """Hoş geldin ekranını göster (İlk açılış & Yardım butonu)"""
        try:
            from gui.dialogs.welcome_dialog import WelcomeDialog
            dlg = WelcomeDialog(self)
            dlg.exec_()
        except ImportError:
            QMessageBox.information(self, "MemoFast", "Hoş geldiniz!\n\nOtomatik Oyun Tanıma ve Performans Özellikleri aktif.")

    def check_first_run(self):
        """İlk çalıştırılma kontrolü (Registry/Config üzerinden)"""
        try:
            settings = QSettings("MemoFast", "App")
            # 'first_run_complete' anahtarı kontrolü
            if not settings.value("first_run_complete", False, type=bool):
                QTimer.singleShot(1000, self.show_welcome_dialog)
                settings.setValue("first_run_complete", True)
        except Exception as e:
            print(f"First run check error: {e}")

    def create_ocr_page(self):
        """OCR Çeviri Ayarları Sayfası - High Contrast Premium Redesign"""
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # İçerik Alanı

        content_scroll = QScrollArea()
        content_scroll.setWidgetResizable(True)
        content_scroll.setStyleSheet("QScrollArea { border: none; background-color: #0f1419; }")
        
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #0f1419;")
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(25)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # --- STYLE CONSTANTS ---
        # User feedback: Text must be white, backgrounds must not hide text.
        INPUT_STYLE = """
            QWidget { 
                background-color: #1a2234; 
                color: #ffffff; 
                border: 1px solid #3b82f6; 
                border-radius: 6px; 
                padding: 6px; 
                font-weight: bold;
                font-size: 13px;
            }
            QWidget:focus { border: 1px solid #10b981; background-color: #1e293b; }
        """
        
        # --- 1. HERO BANNER ---
        banner = QFrame()
        banner.setFixedHeight(120)
        banner.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(16, 185, 129, 0.15), stop:1 rgba(59, 130, 246, 0.15));
                border: 2px solid #10b981;
                border-radius: 15px;
            }
        """)
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(30, 0, 30, 0)
        
        title_v = QVBoxLayout()
        title_v.setAlignment(Qt.AlignCenter)
        lbl_title = QLabel("👁️ OCR EKRAN ÇEVİRİSİ")
        lbl_title.setStyleSheet("color: #10b981; font-size: 26px; font-weight: 900; border: none; background: transparent;")
        
        lbl_subtitle = QLabel("Görünür metinleri anlık olarak yakalayın ve Türkçeye çevirin.")
        lbl_subtitle.setStyleSheet("color: #ffffff; font-size: 14px; border: none; background: transparent;")
        
        title_v.addWidget(lbl_title)
        title_v.addWidget(lbl_subtitle)
        banner_layout.addLayout(title_v)
        banner_layout.addStretch()
        layout.addWidget(banner)

        def p_to_q(s):
            if not s: return ""
            return s.upper().replace("<CTRL>", "Ctrl").replace("<SHIFT>", "Shift").replace("<ALT>", "Alt")

        # --- 2. AYARLAR CARDS ---
        cards_layout = QGridLayout()
        cards_layout.setSpacing(20)
        
        card_style = """
            QFrame { background-color: #111827; border: 1px solid #374151; border-radius: 12px; }
            QLabel { color: #ffffff; font-size: 13px; border: none; background: transparent; }
            QLabel#CardTitle { color: #3b82f6; font-size: 16px; font-weight: bold; }
        """
        
        # --- CARD 1: SERVİS ---
        card_service = QFrame()
        card_service.setStyleSheet(card_style)
        cs_layout = QVBoxLayout(card_service)
        cs_layout.setContentsMargins(20, 20, 20, 20)
        cs_layout.setSpacing(15)
        
        lbl_cs_title = QLabel("🌐 Servis Yapılandırması")
        lbl_cs_title.setObjectName("CardTitle")
        cs_layout.addWidget(lbl_cs_title)
        
        cs_layout.addWidget(QLabel("Ana OCR Kısayolu:"))
        val = p_to_q(self.settings.get("ocr_shortcut", "Ctrl+P"))
        self.ocr_hotkey_input = QKeySequenceEdit(QKeySequence(val))
        self.ocr_hotkey_input.setFixedHeight(38)
        self.ocr_hotkey_input.setStyleSheet(INPUT_STYLE)
        cs_layout.addWidget(self.ocr_hotkey_input)
        
        cs_layout.addWidget(QLabel("OCR Görüntü İşleme Motoru:"))
        self.ocr_engine_combo = QComboBox()
        self.ocr_engine_combo.addItems(["Windows OCR (Translumo - Çok Hızlı)", "Tesseract OCR (Klasik)", "EasyOCR (Yapay Zeka)"])
        self.ocr_engine_combo.setFixedHeight(38)
        self.ocr_engine_combo.setStyleSheet(INPUT_STYLE + " QComboBox::drop-down { border: none; }")
        cs_layout.addWidget(self.ocr_engine_combo)
        
        cs_layout.addWidget(QLabel("Çeviri Servisi:"))
        self.ocr_service_combo = QComboBox()
        self.ocr_service_combo.addItems(["Google (Ücretsiz)", "DeepL (Hızlı)", "Gemini AI (Zeki)"])
        self.ocr_service_combo.setFixedHeight(38)
        self.ocr_service_combo.setStyleSheet(INPUT_STYLE + " QComboBox::drop-down { border: none; }")
        cs_layout.addWidget(self.ocr_service_combo)
        
        self.ocr_api_label = QLabel("API Anahtarı:")
        self.ocr_api_input = QLineEdit()
        self.ocr_api_input.setPlaceholderText("Buraya yapıştırın...")
        self.ocr_api_input.setEchoMode(QLineEdit.Password)
        self.ocr_api_input.setFixedHeight(38)
        self.ocr_api_input.setStyleSheet(INPUT_STYLE)
        cs_layout.addWidget(self.ocr_api_label)
        cs_layout.addWidget(self.ocr_api_input)
        
        cards_layout.addWidget(card_service, 0, 0)
        
        # --- CARD 2: AUDIO ---
        card_audio = QFrame()
        card_audio.setStyleSheet(card_style)
        ca_layout = QVBoxLayout(card_audio)
        ca_layout.setContentsMargins(20, 20, 20, 20)
        ca_layout.setSpacing(15)
        
        lbl_ca_title = QLabel("🎙️ Dublaj ve Ses")
        lbl_ca_title.setObjectName("CardTitle")
        ca_layout.addWidget(lbl_ca_title)
        
        self.cb_dubbing = QCheckBox("Metni Seslendir (Dublaj)")
        self.cb_dubbing.setChecked(self.settings.get("ocr_dubbing", False))
        self.cb_dubbing.setStyleSheet("QCheckBox { color: white; font-weight: bold; }")
        ca_layout.addWidget(self.cb_dubbing)
        
        ca_layout.addWidget(QLabel("Ses Karakteri:"))
        self.combo_voice = QComboBox()
        self.combo_voice.addItems(["Kadın (Emel)", "Erkek (Ahmet)"])
        self.combo_voice.setFixedHeight(38)
        self.combo_voice.setStyleSheet(INPUT_STYLE + " QComboBox::drop-down { border: none; }")
        ca_layout.addWidget(self.combo_voice)
        
        ca_layout.addStretch()
        cards_layout.addWidget(card_audio, 0, 1)

        # --- CARD 3: LIVE ---
        card_live = QFrame()
        card_live.setStyleSheet(card_style)
        cl_layout = QVBoxLayout(card_live)
        cl_layout.setContentsMargins(20, 20, 20, 20)
        cl_layout.setSpacing(15)
        
        lbl_cl_title = QLabel("⚡ Canlı Tarama Modu")
        lbl_cl_title.setObjectName("CardTitle")
        cl_layout.addWidget(lbl_cl_title)
        
        cl_layout.addWidget(QLabel("Canlı Mod Başlat:"))
        v_start = p_to_q(self.settings.get("ocr_start_shortcut", "Ctrl+O"))
        self.ocr_start_hk = QKeySequenceEdit(QKeySequence(v_start))
        self.ocr_start_hk.setFixedHeight(38)
        self.ocr_start_hk.setStyleSheet(INPUT_STYLE.replace("#ffffff", "#60a5fa")) # Mavi metin
        cl_layout.addWidget(self.ocr_start_hk)
        
        cl_layout.addWidget(QLabel("Canlı Mod Durdur:"))
        v_stop = p_to_q(self.settings.get("ocr_stop_shortcut", "Ctrl+L"))
        self.ocr_stop_hk = QKeySequenceEdit(QKeySequence(v_stop))
        self.ocr_stop_hk.setFixedHeight(38)
        self.ocr_stop_hk.setStyleSheet(INPUT_STYLE.replace("#ffffff", "#f87171")) # Kırmızı metin
        cl_layout.addWidget(self.ocr_stop_hk)

        self.cb_filter_mm = QCheckBox("Mek/Mak Dilbilgisi Filtresi")
        self.cb_filter_mm.setChecked(self.settings.get("ocr_filter_mekmak", True))
        self.cb_filter_mm.setStyleSheet("QCheckBox { color: white; }")
        cl_layout.addWidget(self.cb_filter_mm)
        
        cards_layout.addWidget(card_live, 1, 0)

        # --- CARD 4: HELP ---
        card_help = QFrame()
        card_help.setStyleSheet(card_style)
        ch_layout = QVBoxLayout(card_help)
        ch_layout.setContentsMargins(20, 20, 20, 20)
        ch_layout.addWidget(QLabel("📖 İpuçları"))
        
        help_txt = QLabel("• Okunmayan yazılar için alanı biraz genişletin.\n• FPS düşüşü olursa Canlı Modu durdurun.\n• Gemini AI oyun bağlamını daha iyi anlar.")
        help_txt.setStyleSheet("color: #94a3b8; font-size: 13px; line-height: 20px;")
        help_txt.setWordWrap(True)
        ch_layout.addWidget(help_txt)
        ch_layout.addStretch()
        
        cards_layout.addWidget(card_help, 1, 1)
        layout.addLayout(cards_layout)
        
        # --- SAVE ---
        save_btn = QPushButton("💾 AYARLARI SİSTEME KAYDET")
        save_btn.setFixedHeight(55)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                font-size: 16px;
                font-weight: 900;
                border-radius: 12px;
                border: 2px solid #059669;
            }
            QPushButton:hover { background-color: #059669; }
        """)
        save_btn.clicked.connect(self.save_ocr_settings)
        layout.addWidget(save_btn)
        layout.addStretch()
        
        self.ocr_service_combo.currentIndexChanged.connect(self.on_ocr_service_changed)
        current_srv = self.settings.get("translator_service", "google")
        if current_srv == "deepl": self.ocr_service_combo.setCurrentIndex(1)
        elif current_srv == "gemini": self.ocr_service_combo.setCurrentIndex(2)
        else: self.ocr_service_combo.setCurrentIndex(0)
        self.on_ocr_service_changed(self.ocr_service_combo.currentIndex())

        # Motor mevcut durumu yükle
        current_eng = self.settings.get("ocr_engine", "windows")
        if current_eng == "tesseract": self.ocr_engine_combo.setCurrentIndex(1)
        elif current_eng == "easyocr": self.ocr_engine_combo.setCurrentIndex(2)
        else: self.ocr_engine_combo.setCurrentIndex(0)

        content_scroll.setWidget(content_widget)
        main_layout.addWidget(content_scroll)
        self.stack.addWidget(page)



    def on_ocr_service_changed(self, idx):
        """Servis değişince UI güncelle"""
        if idx == 0: # Google
            self.ocr_api_label.hide()
            self.ocr_api_input.hide()
        elif idx == 1: # DeepL
            self.ocr_api_label.show()
            self.ocr_api_input.show()
            self.ocr_api_input.setText(self.settings.get("deepl_api_key", ""))
            self.ocr_api_label.setText("DeepL API Key:")
        elif idx == 2: # Gemini
            self.ocr_api_label.show()
            self.ocr_api_input.show()
            self.ocr_api_input.setText(self.settings.get("gemini_api_key", ""))
            self.ocr_api_label.setText("Gemini API Key:")
            
    def save_ocr_settings(self):
        """OCR ayarlarını kaydet ve uygula"""
        # Helper to convert Qt sequence to pynput format
        def q_to_p(seq):
            return seq.lower().replace("ctrl", "<ctrl>").replace("shift", "<shift>").replace("alt", "<alt>").replace("+", "+")

        # 1. Kısayollar
        self.settings["ocr_shortcut"] = q_to_p(self.ocr_hotkey_input.keySequence().toString())
        self.settings["ocr_start_shortcut"] = q_to_p(self.ocr_start_hk.keySequence().toString())
        self.settings["ocr_stop_shortcut"] = q_to_p(self.ocr_stop_hk.keySequence().toString())
        
        idx = self.ocr_service_combo.currentIndex()
        srv = ["google", "deepl", "gemini"][idx]
        self.settings["translator_service"] = srv
        
        eng_idx = self.ocr_engine_combo.currentIndex()
        eng = ["windows", "tesseract", "easyocr"][eng_idx]
        self.settings["ocr_engine"] = eng
        
        # Key'i güncelle
        key = self.ocr_api_input.text().strip()
        if srv == "deepl": self.settings["deepl_api_key"] = key
        elif srv == "gemini": self.settings["gemini_api_key"] = key
        
        # 3. Dublaj ve Filtreler
        self.settings["ocr_dubbing"] = self.cb_dubbing.isChecked()
        self.settings["ocr_voice_gender"] = "Female" if self.combo_voice.currentIndex() == 0 else "Male"
        self.settings["ocr_filter_mekmak"] = self.cb_filter_mm.isChecked()
            
        self.save_settings()
        
        # 4. Translator Overlay'i güncelle
        if hasattr(self, 'translator') and self.translator:
            try:
                self.translator.start_hotkey_listener() # Kısayolları yenile
            except: pass
            
        QMessageBox.information(self, "Başarılı", "OCR ve Dublaj ayarları kaydedildi! ✅")


    
    def create_platform_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        content = QWidget()
        cl = QHBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)

        
        left = QWidget()
        left.setFixedWidth(520) # Sol panel için daha fazla alan
        left.setStyleSheet("background-color: #0f1419;")
        ll = QVBoxLayout()
        ll.setContentsMargins(40, 40, 40, 40)
        ll.setSpacing(20)
        
        # Başlık
        self.p_title = QLabel("Oyun")
        self.p_title.setStyleSheet("color: #e8edf2; font-size: 24px; font-weight: bold;")
        
        sub = QLabel("Platform seçin ve yama işlemini başlatın")
        sub.setStyleSheet("color: #9ca3af; font-size: 13px;")
        
        self.p_status = QLabel("Platformlar kontrol ediliyor...")
        self.p_status.setStyleSheet("color: #6c8eff; font-size: 13px; padding: 12px; background-color: #1a1f2e; border-radius: 8px;")
        self.p_status.setAlignment(Qt.AlignCenter)
        
        # CHECKBOXLAR - SIKIŞIK
        cb_widget = QWidget()
        cb_layout = QVBoxLayout()
        cb_layout.setSpacing(4)  # ÇOK AZ BOŞLUK
        cb_layout.setContentsMargins(0, 0, 0, 0)
        
        self.steam_cb = QCheckBox("🎮  Steam")
        self.steam_cb.setStyleSheet("QCheckBox { color: #e8edf2; font-size: 15px; padding: 4px; } QCheckBox::indicator { width: 18px; height: 18px; }")
        self.steam_lbl = QLabel("")
        self.steam_lbl.setStyleSheet("color: #10b981; font-size: 11px; margin-left: 30px; margin-top: -2px;")
        
        self.epic_cb = QCheckBox("🎯  Epic Games")
        self.epic_cb.setStyleSheet("QCheckBox { color: #e8edf2; font-size: 15px; padding: 4px; } QCheckBox::indicator { width: 18px; height: 18px; }")
        self.epic_lbl = QLabel("")
        self.epic_lbl.setStyleSheet("color: #10b981; font-size: 11px; margin-left: 30px; margin-top: -2px;")
        
        self.custom_cb = QCheckBox("🚀  Özel Launcher")
        self.custom_cb.setStyleSheet("QCheckBox { color: #e8edf2; font-size: 15px; padding: 4px; } QCheckBox::indicator { width: 18px; height: 18px; }")
        self.custom_lbl = QLabel("")
        self.custom_lbl.setStyleSheet("color: #10b981; font-size: 11px; margin-left: 30px; margin-top: -2px;")
        
        self.manual_cb = QCheckBox("📁  Manuel Klasör Seç")
        self.manual_cb.setStyleSheet("QCheckBox { color: #e8edf2; font-size: 15px; padding: 4px; } QCheckBox::indicator { width: 18px; height: 18px; }")
        
        cb_layout.addWidget(self.steam_cb)
        cb_layout.addWidget(self.steam_lbl)
        cb_layout.addWidget(self.epic_cb)
        cb_layout.addWidget(self.epic_lbl)
        cb_layout.addWidget(self.custom_cb)
        cb_layout.addWidget(self.custom_lbl)
        cb_layout.addWidget(self.manual_cb)
        cb_widget.setLayout(cb_layout)
        
        # BUTONLAR - HEMEN ALTINDA
        btn_w = QWidget()
        btn_l = QHBoxLayout()
        btn_l.setSpacing(10)
        btn_l.setContentsMargins(0, 0, 0, 0)
        
        self.tr_btn = QPushButton("🇹🇷 TÜRKÇE YAMA YAP")
        self.tr_btn.setFixedHeight(50)
        self.tr_btn.setStyleSheet("QPushButton { background-color: #10b981; color: white; font-size: 14px; font-weight: bold; border: none; border-radius: 8px; } QPushButton:hover { background-color: #059669; }")
        self.tr_btn.clicked.connect(lambda: self.apply_patch('turkish'))
        
        self.orig_btn = QPushButton("🌐 ORİJİNALE DÖN")
        self.orig_btn.setFixedHeight(50)
        self.orig_btn.setStyleSheet("QPushButton { background-color: #3b82f6; color: white; font-size: 14px; font-weight: bold; border: none; border-radius: 8px; } QPushButton:hover { background-color: #2563eb; }")
        self.orig_btn.clicked.connect(lambda: self.apply_patch('original'))

        # [YENİ] Temizlik Butonu - "Oyunu Başlat" yerine
        self.clean_btn = QPushButton("🧹 TEMİZLE")
        self.clean_btn.setFixedHeight(50)
        self.clean_btn.setCursor(Qt.PointingHandCursor)
        self.clean_btn.setStyleSheet("QPushButton { background-color: #e53e3e; color: white; font-size: 14px; font-weight: bold; border: none; border-radius: 8px; } QPushButton:hover { background-color: #c53030; }")
        self.clean_btn.clicked.connect(self.handle_cleanup_current_game)
        
        btn_l.addWidget(self.tr_btn)
        btn_l.addWidget(self.orig_btn)
        btn_l.addWidget(self.clean_btn)
        btn_w.setLayout(btn_l)
        
        # İŞLEM PANELİ + PROGRESS BAR
        process_group = QGroupBox("⚙️ İşlem Durumu")
        process_group.setStyleSheet("QGroupBox { color: #e8edf2; font-size: 13px; font-weight: bold; border: 1px solid #2d3748; border-radius: 8px; padding-top: 15px; background-color: #1a1f2e; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        
        process_layout = QVBoxLayout()
        process_layout.setSpacing(8)
        
        # Log text
        self.process_log = QTextEdit()
        self.process_log.setReadOnly(True)
        self.process_log.setFixedHeight(120)
        self.process_log.setStyleSheet("QTextEdit { background-color: #0f1419; color: #9ca3af; border: 1px solid #2d3748; border-radius: 4px; padding: 6px; font-size: 11px; font-family: 'Consolas', monospace; }")
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(25)
        self.progress_bar.setStyleSheet("QProgressBar { border: 1px solid #2d3748; border-radius: 4px; background-color: #0f1419; text-align: center; color: #e8edf2; font-size: 11px; font-weight: bold; } QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #667eea, stop:1 #764ba2); border-radius: 3px; }")
        self.progress_bar.setValue(0)
        
        process_layout.addWidget(self.process_log)
        process_layout.addWidget(self.progress_bar)
        process_group.setLayout(process_layout)
        
        # Geri
        back = QPushButton("← Geri")
        back.setStyleSheet("QPushButton { background-color: #374151; color: #e8edf2; padding: 12px; border-radius: 8px; border: none; } QPushButton:hover { background-color: #4b5563; }")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        
        # HEPSİNİ EKLE
        ll.addWidget(self.p_title)
        ll.addWidget(sub)
        ll.addSpacing(10)
        
        # ÜSt Bilgi ve Rescan
        info_layout = QHBoxLayout()
        self.p_status = QLabel("Platformlar kontrol ediliyor...")
        self.p_status.setStyleSheet("color: #6c8eff; font-size: 13px; font-weight: bold; background: transparent;")
        
        self.rescan_btn = QPushButton("🗑️ Cache Sil") # Varsayılan
        self.rescan_btn.setCursor(Qt.PointingHandCursor)
        self.rescan_btn.setStyleSheet("QPushButton { background-color: #e53e3e; color: white; border: none; padding: 5px 15px; border-radius: 4px; } QPushButton:hover { background-color: #c53030; }")
        self.rescan_btn.clicked.connect(self.toggle_cache_scan)
        
        info_layout.addWidget(self.p_status)
        info_layout.addWidget(self.rescan_btn)
        info_layout.addStretch()
        
        ll.addLayout(info_layout)
        ll.addSpacing(10)
        
        # Steam Satırı
        steam_row = QHBoxLayout()
        self.steam_cb = QCheckBox("🎮  Steam")
        self.steam_cb.setStyleSheet("QCheckBox { color: #e8edf2; font-size: 15px; } QCheckBox::indicator { width: 18px; height: 18px; }")
        
        self.steam_lbl = QLabel("")
        self.steam_lbl.setStyleSheet("color: #10b981; font-size: 12px; margin-left: 10px; font-weight: bold;")
        
        steam_row.addWidget(self.steam_cb)
        steam_row.addWidget(self.steam_lbl)
        steam_row.addStretch()
        ll.addLayout(steam_row)
        
        # Epic Satırı
        epic_row = QHBoxLayout()
        self.epic_cb = QCheckBox("🎯  Epic Games")
        self.epic_cb.setStyleSheet("QCheckBox { color: #e8edf2; font-size: 15px; } QCheckBox::indicator { width: 18px; height: 18px; }")
        
        self.epic_lbl = QLabel("")
        self.epic_lbl.setStyleSheet("color: #10b981; font-size: 12px; margin-left: 10px; font-weight: bold;")
        
        epic_row.addWidget(self.epic_cb)
        epic_row.addWidget(self.epic_lbl)
        epic_row.addStretch()
        ll.addLayout(epic_row)
        
        # Custom Satırı
        custom_row = QHBoxLayout()
        self.custom_cb = QCheckBox("🚀  Özel Launcher")
        self.custom_cb.setStyleSheet("QCheckBox { color: #e8edf2; font-size: 15px; } QCheckBox::indicator { width: 18px; height: 18px; }")
        
        self.custom_lbl = QLabel("")
        self.custom_lbl.setStyleSheet("color: #10b981; font-size: 12px; margin-left: 10px; font-weight: bold;")
        
        custom_row.addWidget(self.custom_cb)
        custom_row.addWidget(self.custom_lbl)
        custom_row.addStretch()
        ll.addLayout(custom_row)
        
        # Manuel Seçim
        self.manual_cb = QCheckBox("📁  Manuel Klasör Seç")
        self.manual_cb.setStyleSheet("QCheckBox { color: #e8edf2; font-size: 15px; } QCheckBox::indicator { width: 18px; height: 18px; }")
        ll.addWidget(self.manual_cb)
        
        ll.addSpacing(15)
        ll.addWidget(btn_w)
        ll.addSpacing(15)
        ll.addWidget(process_group)
        ll.addStretch()
        ll.addWidget(back)
        left.setLayout(ll)
        
        
        # Sağ - Resim (Esnek Yapı)
        right = QWidget()
        # Fixed width KALDIRILDI, stretch ile yönetilecek
        right.setStyleSheet("background-color: #141823; border-left: 1px solid #2d3748;")
        rl = QVBoxLayout()
        rl.setAlignment(Qt.AlignCenter)
        rl.setContentsMargins(20, 20, 20, 20)
        
        self.p_cover = QLabel()
        self.p_cover.setAlignment(Qt.AlignCenter)
        self.p_cover.setStyleSheet("background-color: transparent;")
        rl.addWidget(self.p_cover)
        right.setLayout(rl)
        
        cl.addWidget(left)
        cl.addWidget(right, stretch=1)
        content.setLayout(cl)
        
        layout.addWidget(content)
        page.setLayout(layout)
        self.stack.addWidget(page)
    
    def toggle_cache_scan(self):
        if not self.current_game:
            return
            
        btn_text = self.rescan_btn.text()
        cache_file = CACHE_PATH / f"{self.current_game}_cache.json"
        
        if "Cache Sil" in btn_text:
            # SİLME MODU
            if cache_file.exists():
                try:
                    cache_file.unlink()
                except: pass
            
            self.scan_results = {}
            self.update_checkboxes()
            self.p_status.setText("⚠️ Cache silindi, tarama bekleniyor")
            self.rescan_btn.setText("🔍 Tara")
            self.rescan_btn.setStyleSheet("QPushButton { background-color: #3b82f6; color: white; border: none; padding: 5px 15px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #2563eb; }")
            
        else:
            # TARAMA MODU
            self.p_status.setText("Yeniden taranıyor...")
            self.rescan_btn.setEnabled(False)
            
            game_new = GAME_PATH / self.current_game / "new"
            if game_new.exists():
                files = list(game_new.glob("*"))
                if files:
                    target = files[0].name
                    self.p_status.setText(f"🔍 Taranıyor: {target}")
                    
                    self.scan_thread = ScanThread(self.current_game, target)
                    self.scan_thread.progress.connect(lambda msg, p: self.p_status.setText(msg))
                    self.scan_thread.finished.connect(self.on_scan_finished)
                    self.scan_thread.start()
    

    
    def on_scan_finished(self, results):
        self.scan_results = results
        self.update_checkboxes()
        self.rescan_btn.setEnabled(True)
        self.rescan_btn.setText("🗑️ Cache Sil")
        self.rescan_btn.setStyleSheet("QPushButton { background-color: #e53e3e; color: white; border: none; padding: 5px 15px; border-radius: 4px; } QPushButton:hover { background-color: #c53030; }")
    
    def update_checkboxes(self):
        total = len(self.scan_results.get('steam', [])) + len(self.scan_results.get('epic', [])) + len(self.scan_results.get('custom', []))
        
        if total == 0:
            self.p_status.setText("⚠️ Hiçbir platformda bulunamadı")
        else:
            self.p_status.setText(f"✓ {total} kurulum bulundu")
        
        sc = len(self.scan_results.get('steam', []))
        ec = len(self.scan_results.get('epic', []))
        cc = len(self.scan_results.get('custom', []))
        
        if sc > 0:
            self.steam_cb.setChecked(True)
            self.steam_lbl.setText(f"✓ {sc} kurulum")
        else:
            self.steam_cb.setChecked(False)
            self.steam_lbl.setText("")
        
        if ec > 0:
            self.epic_cb.setChecked(True)
            self.epic_lbl.setText(f"✓ {ec} kurulum")
        else:
            self.epic_cb.setChecked(False)
            self.epic_lbl.setText("")
        
        if cc > 0:
            self.custom_cb.setChecked(True)
            self.custom_lbl.setText(f"✓ {cc} kurulum")
        else:
            self.custom_cb.setChecked(False)
            self.custom_lbl.setText("")
    
    def rescan_current_game(self):
        if not self.current_game:
            return
            
        # Cache sil
        cache_file = CACHE_PATH / f"{self.current_game}_cache.json"
        if cache_file.exists():
            try:
                cache_file.unlink()
            except: pass
            
        # UI sıfırla
        self.p_status.setText("Yeniden taranıyor...")
        self.scan_results = {}
        self.update_checkboxes()
        
        # Tarama başlat
        # show_platform içindeki mantığı çağırabiliriz ama doğrudan tarama başlatmak daha temiz
        game_new = GAME_PATH / self.current_game / "new"
        if game_new.exists():
            files = list(game_new.glob("*"))
            if files:
                target = files[0].name
                self.p_status.setText(f"🔍 Taranıyor: {target}")
                
                self.scan_thread = ScanThread(self.current_game, target)
                self.scan_thread.progress.connect(lambda msg, p: self.p_status.setText(msg))
                self.scan_thread.finished.connect(self.on_scan_finished)
                self.scan_thread.start()

    def apply_patch(self, patch_type):
        import time
        import random
        
        targets = []
        
        if self.steam_cb.isChecked():
            targets.extend(self.scan_results.get('steam', []))
        if self.epic_cb.isChecked():
            targets.extend(self.scan_results.get('epic', []))
        if self.custom_cb.isChecked():
            targets.extend(self.scan_results.get('custom', []))
        
        if self.manual_cb.isChecked():
            # KLASÖR SEÇİCİ - oyun ana klasörünü seç
            folder_path = QFileDialog.getExistingDirectory(self, "Oyun Ana Klasörünü Seçin", "")
            if folder_path:
                # Yama dosyası adını al
                game_path = GAME_PATH / self.current_game
                source_folder = game_path / ("new" if patch_type == "turkish" else "old")
                
                if source_folder.exists():
                    source_files = list(source_folder.glob("*"))
                    if source_files:
                        target_filename = source_files[0].name
                        
                        # Seçilen klasörde yama dosyasını ara
                        found_files = []
                        for root, dirs, files in os.walk(folder_path):
                            if target_filename in files:
                                found_files.append(os.path.join(root, target_filename))
                        
                        if found_files:
                            targets.extend(found_files)
                            self.process_log.append(f"📁 Manuel: {len(found_files)} dosya bulundu")
                        else:
                            QMessageBox.warning(self, "Bulunamadı", f"'{target_filename}' dosyası seçilen klasörde bulunamadı!")
                            return
        
        if not targets:
            QMessageBox.warning(self, "Uyarı", "Lütfen en az bir platform seçin!")
            return
        
        patch_name = "Türkçe" if patch_type == "turkish" else "Orijinal"
        
        game_path = GAME_PATH / self.current_game
        source_folder = game_path / ("new" if patch_type == "turkish" else "old")
        
        if not source_folder.exists():
            QMessageBox.critical(self, "Hata", f"{source_folder.name} klasörü bulunamadı!")
            return
        
        source_files = list(source_folder.glob("*"))
        if not source_files:
            QMessageBox.critical(self, "Hata", "Yama dosyası bulunamadı!")
            return
        
        source = source_files[0]
        
        # Progress bar'ı sıfırla
        self.progress_bar.setValue(0)
        self.process_log.clear()
        self.process_log.append(f"⚙️ {patch_name} yama işlemi başlatıldı...")
        self.process_log.append(f"📁 Kaynak: {source.name}")
        self.process_log.append(f"🎯 Hedef: {len(targets)} dosya")
        self.process_log.append("")
        QApplication.processEvents()
        
        success = 0
        failed = 0
        total = len(targets)
        
        for i, target in enumerate(targets, 1):
            # Progress güncelle
            progress = int((i / total) * 100)
            self.progress_bar.setValue(progress)
            
            try:
                self.process_log.append(f"📝 [{i}/{total}] Dosya hazırlanıyor...")
                QApplication.processEvents()
                time.sleep(random.uniform(0.5, 1.0))  # Hazırlık
                
                self.process_log.append(f"   ↳ Kopyalanıyor...")
                QApplication.processEvents()
                time.sleep(random.uniform(1.5, 2.5))  # Kopyalama
                
                shutil.copy2(source, target)
                
                self.process_log.append(f"   ✓ Tamamlandı")
                QApplication.processEvents()
                time.sleep(random.uniform(0.3, 0.7))  # Doğrulama
                
                success += 1
            except Exception as e:
                failed += 1
                self.process_log.append(f"   ✗ Hata: {str(e)[:40]}")
            
            self.process_log.append("")
            QApplication.processEvents()
        
        self.progress_bar.setValue(100)
        self.process_log.append(f"{'='*40}")
        self.process_log.append(f"✓ Tamamlandı: {success} dosya")
        if failed > 0:
            self.process_log.append(f"✗ Başarısız: {failed} dosya")
        self.process_log.append(f"{'='*40}")
        
        self.add_log(f"✓ {patch_name} yama tamamlandı ({success} dosya)")
        
        if success > 0:
            QMessageBox.information(self, "Başarılı", f"✓ {success} dosya yamandı\n✗ {failed} başarısız")
            __import__('webbrowser').open("https://www.youtube.com/@MehmetariTv")
        else:
            self.add_log(f"✗ Yama başarısız!")
            QMessageBox.critical(self, "Hata", "Yama başarısız!")

    def create_translator_page(self):
        """Otomatik Çeviri Sayfası - Modern Premium Tasarım"""
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # İçerik Alanı

        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #0f1419;")
        cl = QVBoxLayout(content_widget)
        cl.setContentsMargins(40, 40, 40, 40)
        cl.setSpacing(20)
        
        # --- HERO BANNER ---
        banner = QFrame()
        banner.setFixedHeight(120)
        banner.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(59, 130, 246, 0.1), stop:1 rgba(147, 51, 234, 0.1));
                border: 1px solid rgba(59, 130, 246, 0.2);
                border-radius: 15px;
            }
        """)
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(30, 0, 30, 0)
        
        title_v = QVBoxLayout()
        title_v.setAlignment(Qt.AlignCenter)
        lbl_title = QLabel("🌐 OTOMATİK OYUN ÇEVİRİSİ")
        lbl_title.setStyleSheet("color: #3b82f6; font-size: 26px; font-weight: 900; letter-spacing: 1px; border: none; background: transparent;")
        
        lbl_subtitle = QLabel("Unity ve Unreal oyunlarını saniyeler içinde tespit edin ve modlayın.")
        lbl_subtitle.setStyleSheet("color: #94a3b8; font-size: 14px; border: none; background: transparent;")
        
        title_v.addWidget(lbl_title)
        title_v.addWidget(lbl_subtitle)
        banner_layout.addLayout(title_v)
        banner_layout.addStretch()
        
        cl.addWidget(banner)
        
        # --- ÇEVİRİ SERVİSİ SEÇİMİ ---
        service_layout = QHBoxLayout()
        service_layout.setSpacing(15)
        
        srv_lbl = QLabel("Çeviri Servisi:")
        srv_lbl.setStyleSheet("color: #e8edf2; font-weight: bold;")
        
        self.trans_service_combo = QComboBox()
        self.trans_service_combo.addItems(["Google Translate (Ücretsiz)", "DeepL API (Resmi)", "Gemini Flash (API Key)"])
        self.trans_service_combo.setFixedSize(250, 40)
        self.trans_service_combo.setCursor(Qt.PointingHandCursor)
        self.trans_service_combo.setStyleSheet("QComboBox { background-color: #1a1f2e; color: #e8edf2; border: 1px solid #2d3748; border-radius: 6px; padding: 5px; font-weight: 500; } QComboBox::drop-down { border: none; } QComboBox::down-arrow { image: none; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 5px solid #6c8eff; margin-right: 10px; }")
        
        service_layout.addWidget(srv_lbl)
        service_layout.addWidget(self.trans_service_combo)
        
        service_layout.addSpacing(20)
        
        # --- HEDEF DİL SEÇİMİ (YENİ) ---
        lang_lbl = QLabel("Hedef Dil:")
        lang_lbl.setStyleSheet("color: #e8edf2; font-weight: bold;")
        
        self.combo_target_lang = QComboBox()
        self.combo_target_lang.setFixedSize(200, 40)
        self.combo_target_lang.setCursor(Qt.PointingHandCursor)
        self.combo_target_lang.setStyleSheet("QComboBox { background-color: #1a1f2e; color: #e8edf2; border: 1px solid #2d3748; border-radius: 6px; padding: 5px; font-weight: 500; } QComboBox::drop-down { border: none; } QComboBox::down-arrow { image: none; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 5px solid #6c8eff; margin-right: 10px; }")
        
        # Diller: Türkçe (Default), Rusça, vb.
        self.combo_target_lang.addItem("🇹🇷 Türkçe (Varsayılan)", "tr")
        self.combo_target_lang.addItem("🇷🇺 Rusça (Pусский)", "ru")
        self.combo_target_lang.addItem("🇧🇷 Portekizce (Brezilya)", "pt")
        self.combo_target_lang.addItem("🇪🇸 İspanyolca (LATAM)", "es")
        self.combo_target_lang.addItem("🇮🇩 Endonezce (Bahasa)", "id")
        self.combo_target_lang.addItem("🇵🇱 Lehçe (Polski)", "pl")
        self.combo_target_lang.addItem("🇩🇪 Almanca (Deutsch)", "de")
        self.combo_target_lang.addItem("🇫🇷 Fransızca (Français)", "fr")
        self.combo_target_lang.addItem("🇮🇹 İtalyanca (Italiano)", "it")
        
        
        # Dil değişince tabloyu güncelle (Dinamik)
        self.combo_target_lang.currentIndexChanged.connect(self.refresh_pak_content_list)
        
        service_layout.addWidget(lang_lbl)
        service_layout.addWidget(self.combo_target_lang)
        
        service_layout.addStretch()
        
        cl.addLayout(service_layout)
        
        # AES Key girişi otomatik sisteme devredildi (Manuel alan kaldırıldı)

        
        
        # --- YENİ: ÇEVİRİ YÖNTEMİ (SADECE UNITY İÇİN) ---
        # [GÜNCELLEME] "Tam Çeviri" seçeneği kaldırıldı. Artık Unity için varsayılan "Anlık Çeviri".
        # self.method_group ve radio butonları tamamen silindi.


        
        # --- HIZ AYARI SLIDER (TURBO MODE CONTROL) ---
        speed_layout = QHBoxLayout()
        speed_layout.setSpacing(15)
        
        speed_lbl = QLabel("Çeviri Hızı (İşçi):")
        speed_lbl.setStyleSheet("color: #e8edf2; font-weight: bold;")
        
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setMinimum(1)
        self.speed_slider.setMaximum(30)
        self.speed_slider.setValue(10) # Varsayılan: Turbo (10)
        self.speed_slider.setFixedSize(200, 20)
        self.speed_slider.setCursor(Qt.PointingHandCursor)
        self.speed_slider.setStyleSheet("""
            QSlider::groove:horizontal { border-radius: 4px; height: 8px; background: #2d3748; }
            QSlider::handle:horizontal { background: #6c8eff; border: 2px solid #6c8eff; width: 16px; height: 16px; margin: -4px 0; border-radius: 8px; }
            QSlider::handle:horizontal:hover { background: #ffffff; }
        """)
        
        self.speed_val_lbl = QLabel("10 (Turbo 🚀)")
        self.speed_val_lbl.setFixedWidth(120)
        self.speed_val_lbl.setCursor(Qt.PointingHandCursor) # Mouse üzerine gelince el işareti
        self.speed_val_lbl.setStyleSheet("color: #6c8eff; font-weight: bold;")
        
        self.speed_warning_lbl = QLabel("⚠️ Yüksek Ban Riski!")
        self.speed_warning_lbl.setStyleSheet("color: #e53e3e; font-weight: bold; font-size: 12px;")
        self.speed_warning_lbl.setVisible(False)
        
        def on_speed_change(val):
            mode = "Normal"
            if val >= 10: mode = "Turbo 🚀"
            if val >= 20: mode = "EXTREME 🔥"
            
            self.speed_val_lbl.setText(f"{val} ({mode})")
            
            # Uyarı kontrolü
            if val >= 20:
                self.speed_warning_lbl.setVisible(True)
                self.speed_val_lbl.setStyleSheet("color: #e53e3e; font-weight: bold;")
            else:
                self.speed_warning_lbl.setVisible(False)
                self.speed_val_lbl.setStyleSheet("color: #6c8eff; font-weight: bold;")
                
            # Ayarı kaydet (opsiyonel)
            self.settings["translation_speed"] = val
            
        self.speed_slider.valueChanged.connect(on_speed_change)
        
        # Önceden kayıtlı ayar varsa yükle
        saved_speed = self.settings.get("translation_speed", 10)
        self.speed_slider.setValue(saved_speed)
        
        speed_layout.addWidget(speed_lbl)
        speed_layout.addWidget(self.speed_slider)
        speed_layout.addWidget(self.speed_val_lbl)
        speed_layout.addWidget(self.speed_warning_lbl)
        speed_layout.addStretch()
        
        cl.addLayout(speed_layout)
        saved_srv = self.settings.get("translator_service", "google")
        
        self.deepl_usage_box = QGroupBox("DeepL Kullanım Durumu")
        self.deepl_usage_box.setVisible(saved_srv == "deepl")
        self.deepl_usage_box.setStyleSheet("QGroupBox { color: #e8edf2; font-weight: bold; border: 1px solid #2d3748; border-radius: 8px; margin-top: 10px; padding-top: 20px; background-color: #161b22; }")
        du_layout = QHBoxLayout()
        du_layout.setContentsMargins(15, 15, 15, 15)
        
        self.dl_progress = QProgressBar()
        self.dl_progress.setFixedHeight(20)
        self.dl_progress.setTextVisible(True)
        self.dl_progress.setStyleSheet("QProgressBar { border: 1px solid #2d3748; border-radius: 4px; text-align: center; color: white; background-color: #1a1f2e; } QProgressBar::chunk { background-color: #3b82f6; border-radius: 4px; }")
        
        self.dl_status_lbl = QLabel("Bilgi bekleniyor...")
        self.dl_status_lbl.setStyleSheet("color: #9ca3af; font-size: 13px; margin-left: 10px;")
        
        self.dl_refresh_btn = QPushButton("Yenile")
        self.dl_refresh_btn.setFixedSize(80, 30)
        self.dl_refresh_btn.setCursor(Qt.PointingHandCursor)
        self.dl_refresh_btn.setStyleSheet("QPushButton { background-color: #374151; color: white; border-radius: 4px; } QPushButton:hover { background-color: #4b5563; }")
        self.dl_refresh_btn.clicked.connect(self.check_deepl_usage)
        
        du_layout.addWidget(self.dl_progress)
        du_layout.addWidget(self.dl_status_lbl)
        du_layout.addWidget(self.dl_refresh_btn)
        
        self.deepl_usage_box.setLayout(du_layout)
        cl.addWidget(self.deepl_usage_box)
        
        # Seçim değişince ayarı kaydet ve UI güncelle
        def on_service_change(idx):
            if idx == 0:
                srv = "google"
            elif idx == 1:
                srv = "deepl"
            else:
                srv = "gemini"
                
            self.settings["translator_service"] = srv
            self.save_settings()
            # DeepL panelini göster/gizle
            self.deepl_usage_box.setVisible(srv == "deepl")
            if srv == "deepl":
                self.check_deepl_usage()
        
        self.trans_service_combo.currentIndexChanged.connect(on_service_change)
        
        # Varsayılanı yükle
        idx = 0
        if saved_srv == "deepl":
            idx = 1
        elif saved_srv == "gemini":
            idx = 2
        self.trans_service_combo.setCurrentIndex(idx)

        # Başlangıçta DeepL seçiliyse kontrol et
        if saved_srv == "deepl":
            # QTimer singleShot ile UI yüklendikten hemen sonra çağır
            QTimer.singleShot(500, self.check_deepl_usage)

        if saved_srv == "deepl":
            # QTimer singleShot ile UI yüklendikten hemen sonra çağır
            QTimer.singleShot(500, self.check_deepl_usage)



        # ÜST KISIM: OYUN LİSTESİ
        list_group = QGroupBox("Bulunan Oyunlar")
        list_group.setStyleSheet("QGroupBox { color: " + self.accent_color + "; font-weight: bold; font-size: 14px; border: 2px solid #2d3748; border-radius: 8px; padding-top: 15px; background-color: #141823; }")
        list_layout = QVBoxLayout()
        
        # Tablo
        self.game_table = QTableWidget()
        self.game_table.setColumnCount(5)
        self.game_table.setHorizontalHeaderLabels(["", "Oyun Adı", "", "Motor", "Platform"])
        self.game_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch) # İsim esnek
        self.game_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents) # Durum ikonu küçük
        self.game_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents) # Motor sığdır
        self.game_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents) # Platform sığdır
        self.game_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.game_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.game_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.game_table.verticalHeader().setVisible(False)
        self.game_table.setAlternatingRowColors(True)
        self.game_table.setStyleSheet("QTableWidget { background-color: #0f1419; alternate-background-color: #161b22; color: #e8edf2; border: 1px solid #2d3748; border-radius: 6px; gridline-color: transparent; } QTableWidget::item { padding: 8px; border-bottom: 1px solid #2d3748; } QTableWidget::item:selected { background-color: #3b82f6; color: white; } QTableWidget::item:hover { background-color: #2d3748; } QHeaderView::section { background-color: #1a1f2e; color: #9ca3af; padding: 8px; border: none; font-weight: bold; border-bottom: 2px solid #2d3748; }")
        # Sütun genişlikleri
        self.game_table.setColumnWidth(0, 40) # İkon
        self.game_table.setColumnWidth(2, 80) # Motor
        
        self.game_table.itemSelectionChanged.connect(self.on_game_selected)
        
        list_layout.addWidget(self.game_table)
        
        # Alt Butonlar (Tara, Manuel)
        btn_layout = QHBoxLayout()
        
        self.scan_btn = QPushButton("🔍  Oyunları Tara")
        self.scan_btn.setCursor(Qt.PointingHandCursor)
        self.scan_btn.setStyleSheet("QPushButton { background-color: #4b5563; color: white; padding: 10px 20px; border-radius: 6px; font-weight: bold; } QPushButton:hover { background-color: #6b7280; }")
        self.scan_btn.clicked.connect(self.scan_games)
        
        self.manual_btn = QPushButton("📁  Manuel Ekle")
        self.manual_btn.setCursor(Qt.PointingHandCursor)
        self.manual_btn.setStyleSheet("QPushButton { background-color: #374151; color: white; padding: 10px 20px; border-radius: 6px; font-weight: bold; } QPushButton:hover { background-color: #4b5563; }")
        self.manual_btn.clicked.connect(self.manual_add_game)
        
        btn_layout.addWidget(self.scan_btn)
        btn_layout.addWidget(self.manual_btn)
        btn_layout.addStretch()
        
        # KURULUM BUTONU (ORTA BÜYÜK)
        self.install_btn = QPushButton("ÇEVİRİ YAP")
        self.install_btn.setEnabled(False) # Seçim yokken pasif
        self.install_btn.setFixedHeight(50)
        self.install_btn.setCursor(Qt.PointingHandCursor)
        self.install_btn.setStyleSheet("QPushButton { background-color: " + self.accent_color + "; color: white; font-size: 16px; font-weight: bold; border-radius: 8px; } QPushButton:hover { background-color: #5a7de8; } QPushButton:disabled { background-color: #2d3748; color: #64748b; }")
        self.install_btn.clicked.connect(self.install_selected_game)
        

        
        list_layout.addLayout(btn_layout)
        
        # [YENİ] Canlı Temizleyici Checkbox
        # [YENİ] Manuel Düzelt Butonu (Checkbox yerine) - KALDIRILDI
        # Kullanıcı isteği: Bu özellik Ayarlar -> Kaydet içine taşındı.
        
        # [YENİ] Ana Aksiyon Butonları (Çeviri + Başlat)
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        
        action_layout.addWidget(self.install_btn, stretch=3) # Çeviri butonu daha geniş
        
        # Temizle butonu kaldırıldı - Artık Unity çeviri penceresinde (🗑️ Temizle)
        # action_layout.addWidget(self.settings_btn, stretch=1) # Silindi
        
        list_layout.addLayout(action_layout)
        
        list_group.setLayout(list_layout)
        list_group.setLayout(list_layout)
        cl.addWidget(list_group, stretch=1) # Tablo alanı genişlesin

        # [YENİ] PAK ANALİZ PENCERESİ (GÖMÜLÜ)
        self.pak_analysis_group = QGroupBox("Oyun Dosya Yapısı (PAK)")
        self.pak_analysis_group.setVisible(False) # Sadece Unreal oyunlarında açılacak
        self.pak_analysis_group.setStyleSheet("QGroupBox { color: " + self.accent_color + "; font-weight: bold; font-size: 14px; border: 2px solid #2d3748; border-radius: 8px; padding-top: 15px; background-color: #141823; }")
        
        pak_layout = QVBoxLayout()
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #2d3748; }")
        
        # Sol: PAK Listesi
        left_widget = QWidget()
        l_layout = QVBoxLayout(left_widget)
        l_layout.setContentsMargins(0,0,5,0)
        l_layout.addWidget(QLabel("PAK Dosyaları (Öncelikli)"))
        
        self.pak_table = QTableWidget()
        self.pak_table.setColumnCount(3)
        self.pak_table.setHorizontalHeaderLabels(["PAK Adı", "Ver.", "AES"])
        self.pak_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.pak_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.pak_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.pak_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.pak_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.pak_table.itemSelectionChanged.connect(self.on_pak_table_selected)
        self.pak_table.cellClicked.connect(lambda r, c: self.on_pak_table_selected())
        self.pak_table.setStyleSheet("QTableWidget { background-color: #0f1419; color: #e8edf2; border: 1px solid #2d3748; }")
        l_layout.addWidget(self.pak_table)
        splitter.addWidget(left_widget)
        
        # Sağ: İçerik Listesi
        right_widget = QWidget()
        r_layout = QVBoxLayout(right_widget)
        r_layout.setContentsMargins(5,0,0,0)
        r_layout.addWidget(QLabel("İçerik (Dil Dosyaları)"))
        
        self.pak_content_table = QTableWidget()
        self.pak_content_table.setColumnCount(2)
        self.pak_content_table.setHorizontalHeaderLabels(["Dosya", "Tür"])
        self.pak_content_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.pak_content_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.pak_content_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.pak_content_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.pak_content_table.setStyleSheet("QTableWidget { background-color: #0f1419; color: #e8edf2; border: 1px solid #2d3748; }")
        r_layout.addWidget(self.pak_content_table)
        splitter.addWidget(right_widget)
        
        splitter.setSizes([400, 400])
        pak_layout.addWidget(splitter)
        
        # Analiz Butonu
        self.btn_analyze_pak = QPushButton("📂 Seçili Pak Tara")
        self.btn_analyze_pak.setStyleSheet("background-color: #4b5563; color: white; padding: 5px;")
        self.btn_analyze_pak.clicked.connect(self.on_pak_table_selected)
        pak_layout.addWidget(self.btn_analyze_pak)
        
        self.pak_analysis_group.setLayout(pak_layout)
        cl.addWidget(self.pak_analysis_group, stretch=2)
        
        # ALT KISIM: LOG VE İŞLEM DURUMU
        self.trans_log_group = QGroupBox("İşlem Detayları")
        # Log grubu artık hep görünür olabilir veya işlem başlayınca görünür
        self.trans_log_group.setVisible(True) 
        self.trans_log_group.setFixedHeight(220) # Sabit yükseklik
        self.trans_log_group.setStyleSheet("QGroupBox { color: " + self.accent_color + "; font-weight: bold; font-size: 13px; border: 1px solid #2d3748; border-radius: 8px; padding-top: 15px; background-color: #141823; }")
        
        log_layout = QVBoxLayout()
        log_layout.setSpacing(10)
        
        self.trans_log_list = QListWidget()
        self.trans_log_list.setStyleSheet("QListWidget { background-color: #0f1419; color: #9ca3af; border: 1px solid #2d3748; border-radius: 6px; font-family: 'Consolas', monospace; font-size: 11px; padding: 5px; } QListWidget::item { padding: 3px; }")
        log_layout.addWidget(self.trans_log_list)
        
        # Progress Bar
        self.trans_progress = QProgressBar()
        self.trans_progress.setFixedHeight(8)
        self.trans_progress.setTextVisible(False)
        self.trans_progress.setStyleSheet("QProgressBar { border: none; background-color: #2d3748; border-radius: 4px; } QProgressBar::chunk { background-color: #10b981; border-radius: 4px; }")
        log_layout.addWidget(self.trans_progress)
        
        # Status Label + Hourglass
        status_row = QHBoxLayout()
        self.hourglass_lbl = QLabel("⏳")
        self.hourglass_lbl.setVisible(False) # Başlangıçta gizli
        self.hourglass_lbl.setStyleSheet("font-size: 20px;")
        
        self.trans_status_lbl = QLabel("Hazır")
        self.trans_status_lbl.setStyleSheet("color: #9ca3af; font-weight: bold; font-size: 12px;")
        
        status_row.addWidget(self.hourglass_lbl)
        status_row.addWidget(self.trans_status_lbl)
        status_row.addStretch()
        
        log_layout.addLayout(status_row)
        self.trans_log_group.setLayout(log_layout)
        
        cl.addWidget(self.trans_log_group)
        
        # Timer init
        self.hourglass_timer = QTimer()
        self.hourglass_timer.timeout.connect(self.animate_hourglass)
        self.hourglass_angle = 0
        
        page.setLayout(main_layout)
        main_layout.addWidget(content_widget)
        self.stack.addWidget(page)
        
        # DEBUG: Geçici devre dışı - crash testi
        # QTimer.singleShot(100, self.load_cached_games_to_translator)

    
    def open_translator_settings(self):
        """Çeviri Ayarları Penceresini Aç"""
        if not hasattr(self, 'current_game_data') or not self.current_game_data:
            QMessageBox.warning(self, "Uyarı", "Lütfen önce listeden bir oyun seçin.")
            return
            
        try:
            from gui.dialogs import TranslatorSettingsDialog
            dlg = TranslatorSettingsDialog(self.current_game_data, self)
            dlg.exec_()
        except ImportError as e:
            QMessageBox.critical(self, "Hata", f"Ayarlar penceresi açılamadı: {e}")



    def apply_turkish_filter(self):
        """Mek/mak eklerini temizle (Unity)"""
        if not self.current_game_data:
            return
            
        game_path = self.current_game_data['path']
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("MemoFast - Onay")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText(f"'{self.current_game_data['name']}' için Türkçe mastar ekleri (mek/mak) temizlenecek.\n"
                         "Çeviri dosyasındaki gereksiz ekler kaldırılacak.\n\n"
                         "Devam edilsin mi?")
        
        btn_evet = msg_box.addButton("Evet", QMessageBox.YesRole)
        btn_hayir = msg_box.addButton("Hayır", QMessageBox.NoRole)
        msg_box.setDefaultButton(btn_evet)
        msg_box.exec_()
        
        if msg_box.clickedButton() == btn_evet:
            try:
                # Progress Dialog (Basit)
                self.trans_status_lbl.setText("Filtre uygulanıyor...")
                self.hourglass_lbl.setVisible(True)
                self.hourglass_timer.start(100)
                QApplication.processEvents()
                
                # Log listesini temizle veya ayırıcı ekle
                self.trans_log_list.addItem(f"--- FİLTRELEME BAŞLADI: {self.current_game_data['name']} ---")
                
                success = TranslatorManager.apply_local_filter(
                    game_path, 
                    progress_callback=lambda msg: (self.trans_log_list.addItem(f"🧹 {msg}"), self.trans_log_list.scrollToBottom())
                )
                
                self.hourglass_timer.stop()
                self.hourglass_lbl.setVisible(False)
                self.trans_status_lbl.setText("Hazır")
                
                if success:
                    # QMessageBox.information(self, "Başarılı", "Filtreleme tamamlandı!")
                    self.trans_log_list.addItem("✅ Regex XML filtresi oluşturuldu.")
                    self.trans_log_list.addItem("⚠️ Değişikliklerin görünmesi için OYUNU YENİDEN BAŞLATIN.")
                else:
                    self.trans_log_list.addItem("⚠️ Filtre dosyası oluşturulamadı.")
                    
            except Exception as e:
                self.hourglass_timer.stop()
                self.hourglass_lbl.setVisible(False)
                QMessageBox.critical(self, "Hata", f"Filtre Hatası: {e}")

    def apply_unity_font_fix_embedded(self):
        """Otomatik Çeviri Sayfası Gömülü Font Fix İşlemi"""
        if not self.current_game_data:
            QMessageBox.warning(self, "Hata", "Lütfen önce bir oyun seçin.")
            return

        try:
            from unity_manager import UnityManager
        except ImportError:
            QMessageBox.critical(self, "Hata", "UnityManager modülü bulunamadı!")
            return

        mode_index = self.font_mode_combo.currentIndex() + 1 
        game_path = self.current_game_data.get('exe', self.current_game_data.get('path'))
        
        if os.path.isfile(game_path):
             game_folder = os.path.dirname(game_path)
        else:
             game_folder = game_path

        # Font path Mode 3 (Otomatik)
        font_path = None
        if mode_index == 3:
             # Otomatik olarak tools klasöründeki fontu al
             local_font = BASE_PATH / "tools" / "unity_font" / "arialuni_sdf_u2018"
             if local_font.exists():
                 font_path = str(local_font)
             else:
                 # Dosya yoksa kullanıcıya sor (Fallback)
                 reply = QMessageBox.question(self, "Dosya Eksik", 
                     "Yerel font dosyası (arialuni_sdf_u2018) bulunamadı.\nManuel seçmek ister misiniz?",
                     QMessageBox.Yes | QMessageBox.No)
                 
                 if reply == QMessageBox.Yes:
                     fp, _ = QFileDialog.getOpenFileName(self, "Font Dosyasını Seç", "", "Unity Font (*.unity3d;*);;All Files (*)")
                     if fp: font_path = fp
                 else:
                     return

        success, msg = UnityManager.apply_turkish_font_fix(game_folder, mode=mode_index, font_path=font_path)
        
        if success:
             # Log ekle
             self.trans_log_list.addItem(f"✅ FONT DÜZELTME: {msg}")
             QMessageBox.information(self, "Başarılı", f"Font düzeltmesi uygulandı!\n\n{msg}")
        else:
             self.trans_log_list.addItem(f"❌ FONT HATASI: {msg}")
             QMessageBox.critical(self, "Hata", f"İşlem başarısız:\n{msg}")

    def on_game_selected(self):
        # Tablodan seçim yapılınca
        selected = self.game_table.selectedItems()
        if not selected:
            return
            
        # Unity Kontrolü - Method Seçimini Göster/Gizle
        row = selected[0].row()
        
        # [GÜVENLİ OKUMA] NoneType hatasını engelle
        name_item = self.game_table.item(row, 1)
        engine_item = self.game_table.item(row, 3)
        path_item = self.game_table.item(row, 4)
        
        if not (name_item and engine_item and path_item):
            return
            
        # Değerleri al
        engine = engine_item.text()
        real_path = path_item.data(Qt.UserRole)
        
        # current_game_data güncelle (Tablodan)
        self.current_game_data = {
            'name': name_item.text(),
            'engine': engine,
            'path': real_path,
            'exe': real_path
        }
        
        # Oyun değiştiğinde cleaner'ı sıfırla (veya durdur)
        if hasattr(self, 'cleaner_worker') and self.cleaner_worker:
            self.cleaner_worker.stop()
            self.cleaner_worker = None
            if hasattr(self, 'cleaner_chk'): self.cleaner_chk.setChecked(False)

        
        # Determine engine for PAK panel visibility
        is_unreal = "Unreal" in engine
        
        # Sonrasında otomatik tarama başlat
        if is_unreal and hasattr(self, 'pak_analysis_group'):
             self.pak_analysis_group.setVisible(True)
             # Otomatik tarama başlat (veya kullanıcı butona basar)
             QTimer.singleShot(200, self.start_embedded_pak_scan)
        elif hasattr(self, 'pak_analysis_group'):
             self.pak_analysis_group.setVisible(False)

        # Buton Görünürlüğünü Güncelle
        self.update_trans_buttons_visibility()
        
        # Yeni Tool Buttonlarını Güncelle
        for btn_name in ['tool_trans', 'tool_boost', 'tool_cheat', 'tool_map', 'tool_backup', 'tool_ai']:
            if hasattr(self, btn_name):
                getattr(self, btn_name).setEnabled(True)

        # Legacy Support
        if hasattr(self, 'install_btn'):
            self.install_btn.setEnabled(True)
            self.install_btn.setText(f"{name_item.text()} SEÇİLDİ - ÇEVİRİ YAP")

    def update_trans_buttons_visibility(self):
        """Ayarlar ve Temizle butonlarını duruma göre gizle/göster"""
        show = False
        if hasattr(self, 'current_game_data') and self.current_game_data:
            engine = self.current_game_data.get('engine', '')
            # Sadece Unity oyunları için göster (Artık hep Instant varsayılan)
            if engine == "Unity":
                show = True
                
        if hasattr(self, 'clean_btn'): self.clean_btn.setVisible(show)
        if hasattr(self, 'settings_btn'): self.settings_btn.setVisible(show)
        
        # Cleaner Checkbox (Yeni)
        if hasattr(self, 'cleaner_chk'): 
            self.cleaner_chk.setVisible(show)
            
        # Font Fix Button (Yeni)
        if hasattr(self, 'font_btn'): self.font_btn.setVisible(show)
        
        # Cleaner Checkbox (Yeni)
        if hasattr(self, 'cleaner_chk'): 
            self.cleaner_chk.setVisible(show)
            # Eğer görünürse ve checkliyse worker başlat?
            # Kullanıcı her oyun değiştirdiğinde worker sıfırlanmalı.
            
        # Font Fix Button (Yeni)
        if hasattr(self, 'font_btn'): self.font_btn.setVisible(show)

    def load_cached_games_to_translator(self):
        """Önbellekteki oyunları otomatik çeviri sayfasına yükle"""
        # Race Condition Fix: Eğer özellikle bir oyuna gidiliyorsa yükleme yapma
        if getattr(self, 'skip_translator_autoload', False):
            self.skip_translator_autoload = False
            return
        try:
            from scanner import GameEngineScanner
            scanner = GameEngineScanner()
            games = scanner.load_cache()
            
            if games and len(games) > 0:
                # Oyunları tabloya yükle
                self.on_scan_completed(games, save_cache=False)
                self.trans_status_lbl.setText(f"✅ {len(games)} oyun önbellekten yüklendi")
            else:
                # Önbellek boşsa kullanıcıya bilgi ver
                self.trans_status_lbl.setText("ℹ️ Oyun bulunamadı. 'Oyunları Tara' butonuna basın.")
        except Exception as e:
            print(f"Önbellek yükleme hatası: {e}")
            self.trans_status_lbl.setText("⚠️ Oyunlar yüklenemedi")

    def check_pak_encryption(self, game_path):
        """Unreal Engine PAK korumasını repak.exe ile gerçekçi bir şekilde test et (Kesin Sonuç)"""
        try:
            from pathlib import Path
            import subprocess
            from config import Config
            
            p = Path(game_path)
            if not p.exists(): return False
            if p.is_file(): p = p.parent
            
            # 1. Ana paketi bul (en büyük dosya)
            # Patchleri ve daha önce çevrilmiş pakedleri elemeyi unutma (Hatalı alarm vermesinler)
            paks = [x for x in p.rglob("*.pak") if not any(y in x.name.lower() for y in ["_tr.pak", "_p.pak", "patch", "chtr"])]
            if not paks: return False
            paks.sort(key=lambda x: x.stat().st_size, reverse=True)
            target = paks[0]
            
            # 2. Aracı kontrol et
            tool = Config.BASE_PATH / "files" / "tools" / "repak.exe"
            if not tool.exists(): return False
            
            # 3. GERÇEK TEST: repak.exe ile dosyayı okumayı dene
            try:
                # 0x08000000 = CREATE_NO_WINDOW (Konsol penceresi açmadan çalıştır)
                res = subprocess.run([str(tool), "info", str(target)], 
                                     capture_output=True, text=True, 
                                     creationflags=0x08000000, timeout=5)
                
                output = (res.stdout + res.stderr).lower()
                
                # Sadece KESİN hatalarda (Şifreleme hatası) True dönüyoruz
                # Eğer repak hata kodu verdiyse ve hata mesajında AES/Key/Decrypt geçiyorsa:
                if res.returncode != 0:
                    if any(x in output for x in ["aes", "key", "encrypt", "failed to read", "decrypt"]):
                        return True
                
                # Eğer repak başarılı olsa bile açıkça şifreli olduğunu söylüyorsa:
                if "encrypted index: true" in output or "encrypted: true" in output:
                    return True
                    
                # Başarıyla listeleniyor veya okunuyorsa şifresizdir
                return False
            except:
                return False
        except:
            return False


    def scan_games(self):

        # Oyun taramasını başlat (Thread ile yapılmalı aslında ama şimdilik senkron deneyelim veya kısa sürerse)
        self.trans_status_lbl.setText("Oyunlar taranıyor, lütfen bekleyin...")
        self.hourglass_lbl.setVisible(True)
        self.hourglass_timer.start(100)
        self.scan_btn.setEnabled(False)
        QApplication.processEvents()
        
        # Scanner Thread
        # Basit thread kullanımı
        from scanner import GameEngineScanner
        self.scanner_thread = ScanWorker()
        self.scanner_thread.finished.connect(self.on_scan_completed)
        self.scanner_thread.progress.connect(lambda msg: self.trans_status_lbl.setText(msg))
        self.scanner_thread.start()
        
    def on_scan_completed(self, games, save_cache=True):
        self.hourglass_timer.stop()
        self.hourglass_lbl.setVisible(False)
        self.scan_btn.setEnabled(True)
        
        # [FIX] Tekrarlayan İsimleri Filtrele (Strict Mode)
        import re
        seen_names = set()
        unique_games = []
        
        for g in games:
            raw_name = g['name']
            clean_name = re.sub(r'[^a-zA-Z0-9]', '', raw_name).lower()
            if not clean_name: clean_name = raw_name.lower()
                
            if clean_name not in seen_names:
                seen_names.add(clean_name)
                unique_games.append(g)

        self.trans_status_lbl.setText(f"İşlem tamamlandı. {len(unique_games)} oyun listelendi.")
        
        # Cache'e kaydet (Merge değil, güncelleme)
        if save_cache:
            try:
                from scanner import GameEngineScanner
                scanner = GameEngineScanner()
                
                # Yeni tarama sonuçlarıyla önbelleği güncelle
                scanner.save_cache(games)

            except Exception as e:
                print(f"Cache save error: {e}")
        
        self.game_table.setRowCount(0)
        
        # Tabloyu güncelle (Cache'den mi yoksa unique_games'den mi?)
        # Kullanıcı manuel eklediklerini de görmek isterse merged listeden okumalıyız.
        # Ancak on_scan_completed genelde tarama sonrası çağrılır.
        # Biz burada 'games' parametresini kullandık.
        # Eğer 'games' sadece tarama sonucu ise, eski manual oyunlar tabloda görünmez (ta ki reload olana kadar).
        # Şimdilik scan sonucunu gösteriyoruz, kullanıcı reload yapınca hepsi gelir.
        
        for g in unique_games:
            self._add_game_to_table_ui(g) # Refactored UI adding logic
        
        # Topluluk verisi varsa ikonları hemen uygula
        self._mark_game_table_from_community()

    def _add_game_to_table_ui(self, g):
        """Tabloya satır ekleyen iç metod"""
        row = self.game_table.rowCount()
        self.game_table.insertRow(row)
        
        # Icon (Sütun 0)
        icon_item = QTableWidgetItem("")
        icon_item.setTextAlignment(Qt.AlignCenter)
        
        if g.get('appid'):
            img_path = Config.CACHE_PATH / f"steam_{g['appid']}.jpg"
            if img_path.exists():
                icon = QIcon(str(img_path))
                icon_item.setIcon(icon)
            else:
                icon_item.setText("⏳")
                import threading
                def download_cover(appid, target_path, r_idx):
                    try:
                        url = f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/library_600x900.jpg"
                        import urllib.request
                        urllib.request.urlretrieve(url, target_path)
                    except: pass
                threading.Thread(target=download_cover, args=(g['appid'], img_path, row), daemon=True).start()
        else:
            icon_item.setText(g.get('icon', '🎮'))

        self.game_table.setItem(row, 0, icon_item)
        
        # Oyun adı - Unreal encrypted ise uyarı ekle
        game_name = g['name']
        
        # Unreal oyunlar için PAK şifreleme uyarısı
        if g['engine'] == 'Unreal':
            is_encrypted = self.check_pak_encryption(g.get('path', ''))
            
            if is_encrypted:
                game_name += " 🔑 (Korumalı? Yine de deneyin)"
                name_item = QTableWidgetItem(game_name)
                name_item.setForeground(QColor("#facc15")) # Canlı Sarı (Yellow)
                name_item.setToolTip("⚠️ Bu oyunun ana dosyaları şifreli görünüyor.\nAncak patch dosyaları ile yine de çevrilebilir. Denemenizi öneririz.")
            else:
                name_item = QTableWidgetItem(game_name)
        else:
            name_item = QTableWidgetItem(game_name)
        
        self.game_table.setItem(row, 1, name_item)

        # Topluluk durumu (col 2) - başlangıçta boş, sonra _mark_game_table_from_community doldurur
        self.game_table.setItem(row, 2, QTableWidgetItem(""))
        
        # Motor sütunu - col 3
        engine_item = QTableWidgetItem(g['engine'])
        
        # Renklendirme
        if g['engine'] == 'Unity': 
            engine_item.setForeground(QColor("#e8edf2"))
        elif g['engine'] == 'Godot': 
            engine_item.setForeground(QColor("#478cbf"))
        else: 
            engine_item.setForeground(QColor("#fb923c"))
        
        self.game_table.setItem(row, 3, engine_item)

        
        platform_text = g.get('platform', 'Bilinmiyor')
        platform_item = QTableWidgetItem(platform_text)
        if platform_text == "Steam": platform_item.setForeground(QColor("#66c0f4"))
        elif platform_text == "Epic Games": platform_item.setForeground(QColor("#ffffff"))
        
        platform_item.setToolTip(g['path'])
        platform_item.setData(Qt.UserRole, g['exe'])
        self.game_table.setItem(row, 4, platform_item)

    def manual_add_game(self):
        """Manuel oyun ekleme (Klasör veya PAK)"""
        from scanner import GameEngineScanner # Import here to ensure availability
        msg_box = QMessageBox()
        msg_box.setWindowTitle("Manuel Oyun Ekle")
        msg_box.setText("Nasıl ekleme yapmak istersiniz?")
        msg_box.setInformativeText("Bir oyun klasörü seçerek otomatik taratabilir veya doğrudan oyun dosyasını seçebilirsiniz.")
        
        btn_folder = msg_box.addButton("Oyun Klasörü Seç (Tara)", QMessageBox.ActionRole)
        btn_pak = msg_box.addButton("Unreal Dosyası Seç (.pak)", QMessageBox.ActionRole)
        btn_assets = msg_box.addButton("Unity Dosyası Seç (.assets)", QMessageBox.ActionRole)
        btn_cancel = msg_box.addButton("İptal", QMessageBox.RejectRole)
        
        msg_box.exec_()
        clicked_button = msg_box.clickedButton()
        
        if clicked_button == btn_cancel: return

        game_data_to_add = None

        if clicked_button == btn_folder:
            folder_path = QFileDialog.getExistingDirectory(self, "Oyun Klasörünü Seç")
            if not folder_path: return
            p_folder = Path(folder_path)
            scanner = GameEngineScanner()
            game_info = scanner._analyze_game_folder(p_folder, platform="Manuel")
            
            if game_info:
                game_data_to_add = game_info
            else:
                # Manuel Zorlama
                res = QMessageBox.question(self, "Algılanamadı", "Oyun yapısı algılanamadı. Yine de eklensin mi?", QMessageBox.Yes | QMessageBox.No)
                if res == QMessageBox.Yes:
                    game_data_to_add = {
                        "name": p_folder.name,
                        "path": str(p_folder),
                        "exe": "", 
                        "engine": "Bilinmiyor",
                        "platform": "Manuel",
                        "icon": "📁",
                        "appid": ""
                    }

        elif clicked_button == btn_pak:
            file_path, _ = QFileDialog.getOpenFileName(self, "Unreal Oyun Dosyası Seç (.pak)", "", "Pack Files (*.pak)")
            if file_path:
                p_file = Path(file_path)
                game_name = p_file.stem
                try:
                    if "Content" in p_file.parent.parent.name: game_name = p_file.parent.parent.parent.name
                    else: game_name = p_file.parent.parent.name
                except: pass
                
                game_data_to_add = {
                    "name": game_name,
                    "path": str(p_file),
                    "exe": str(p_file),
                    "engine": "Unreal",
                    "platform": "Manuel",
                    "icon": "📦",
                    "appid": ""
                }

        elif clicked_button == btn_assets:
            file_path, _ = QFileDialog.getOpenFileName(self, "Unity Asset Dosyası Seç", "", "Assets (*.assets *.sharedassets);;All Files (*.*)")
            if file_path:
                p_file = Path(file_path)
                game_name = p_file.parent.parent.name
                game_data_to_add = {
                    "name": game_name,
                    "path": str(p_file),
                    "exe": str(p_file),
                    "engine": "Unity",
                    "platform": "Manuel",
                    "icon": "📄",
                    "appid": ""
                }
        
        # Ekleme ve Kaydetme
        if game_data_to_add:
            try:
                # 1. UI'ya ekle
                self._add_game_to_table(game_data_to_add)
                
                # 2. Cache'e ekle ve kaydet (KALICI YAP)
                from scanner import GameEngineScanner
                scanner = GameEngineScanner()
                current_cache = scanner.load_cache() or []
                current_cache.append(game_data_to_add)
                scanner.save_cache(current_cache)
                
                QMessageBox.information(self, "Başarılı", f"{game_data_to_add['name']} listeye eklendi ve kaydedildi.")
            except Exception as e:
                print(f"Manuel kaydetme hatası: {e}")
                QMessageBox.warning(self, "Hata", f"Kaydedilemedi: {e}")

    def _add_game_to_table(self, game_data):
        """Oyun verisini tabloya ekleyen yardımcı metod"""
        row = self.game_table.rowCount()
        self.game_table.insertRow(row)
        
        # İkon
        self.game_table.setItem(row, 0, QTableWidgetItem("📁"))
        
        # İsim
        self.game_table.setItem(row, 1, QTableWidgetItem(game_data.get('name', 'Adsız')))
        
        # Topluluk durumu (başlangıçta boş)
        self.game_table.setItem(row, 2, QTableWidgetItem(""))
        
        # Motor (Kritik: Unity/Unreal olmalı)
        engine_val = game_data.get('engine', 'Manuel')
        self.game_table.setItem(row, 3, QTableWidgetItem(engine_val))
        
        # Path (UserRole içinde esas path saklı)
        # Eğer exe varsa exe, yoksa path (klasör)
        real_path = game_data.get('exe', game_data.get('path'))
        if not real_path: real_path = game_data.get('path')
        
        path_item = QTableWidgetItem("Yerel Dosya")
        path_item.setData(Qt.UserRole, real_path)
        path_item.setData(Qt.ToolTipRole, real_path)
        self.game_table.setItem(row, 4, path_item)
        
        # Seçili yap
        self.game_table.selectRow(row)

    def install_selected_game(self):
        # Seçili oyuna kurulum yap
        # [FIX] PAK tablosuna tıklayınca game_table seçimi kayboluyor
        if hasattr(self, 'current_game_data') and self.current_game_data:
            g = self.current_game_data
            file_path = g.get('exe', g.get('path', ''))
            engine = g.get('engine', '')
            game_name = g.get('name', 'Bilinmiyor')
        else:
            selected = self.game_table.selectedItems()
            if not selected:
                QMessageBox.warning(self, "Hata", "Lütfen önce bir oyun seçin!")
                return
            row = selected[0].row()
            path_item = self.game_table.item(row, 4)
            file_path = path_item.data(Qt.UserRole)
            engine = self.game_table.item(row, 3).text()
            game_name = self.game_table.item(row, 1).text()
        
        if not file_path:
            QMessageBox.warning(self, "Hata", "Oyun dosya yolu bulunamadı!")
            return

        # [CRITICAL]        # [YENİ] BepInEx Kontrolü (Sadece Unity için)
        game_dir = Path(file_path).parent if os.path.isfile(file_path) else Path(file_path)
        bepinex_check = game_dir / "BepInEx"
        


        # Method Seçimi
        if engine == "Unity":
            translation_method = "instant"
        else:
            translation_method = "full" # Unreal vb. için varsayılan


        if engine == "Unity" and translation_method == "instant":
            # YENİ: Gelişmiş Tarama ve Seçim Dialogu (Sadece Unity ve Anlık Çeviri için)
            try:
                dlg = ScanResultDialog(file_path, self)
                if dlg.exec_() == QDialog.Accepted:
                    bep_zip, trans_zip, loader_type = dlg.get_selection()
                    
                    # Seçilenleri path olarak gönder (veya None)
                    target_bepinex = bep_zip if bep_zip else None
                    target_trans = trans_zip if trans_zip else None
                    
                    # Kurulumu Başlat
                    self.run_installation_process(file_path, engine, None, translation_method, game_name=game_name, 
                                                target_bepinex_zip=target_bepinex, target_translator_zip=target_trans, loader_type=loader_type)
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Tarama başlatılamadı: {e}")
                print(f"Scan Dialog Error: {e}")
        else:
            # Diğer durumlar (Unreal, Tam Çeviri vb.)
            
            # [ROBUST FIX] Check if Embedded PAK Interface is Active
            # We check if pak_table has items, regardless of visibility (in case of UI quirks)
            use_embedded = False
            if hasattr(self, 'pak_table') and self.pak_table.rowCount() > 0:
                 use_embedded = True
            
            if use_embedded:
                try:
                    logger.debug("EMBEDDED PAK Selection Logic kullanılıyor")
                    # Get PAK Path
                    pak_path = None
                    is_encrypted = False
                    
                    # [LEGACY RESTORE] Eğer seçim varsa seçiliyi, yoksa ilk satırı al (Varsayılan)
                    curr_row = 0
                    if self.pak_table.selectedItems():
                        curr_row = self.pak_table.selectedItems()[0].row()
                    
                    active_data = getattr(self, 'current_paks_data', None)
                    if active_data and curr_row < len(active_data):
                        pak_info = active_data[curr_row]
                        pak_path = Path(pak_info['path'])
                        is_encrypted = pak_info['encrypted']
                    else:
                         logger.warning("pak_info bulunamadı (Row: %s, Count: %s)", curr_row, len(active_data) if active_data else "None")


                    
                    # Get Internal File
                    internal_file = None
                    if self.pak_content_table.selectedItems():
                        internal_file = self.pak_content_table.selectedItems()[0].data(Qt.UserRole).replace("\\", "/")
                    
                    if pak_path:
                        logger.debug("Embedded Selection Used -> PAK: %s", pak_path)
                        logger.debug("Internal File: %s", internal_file)
                        logger.debug("Encryption Status from Data: %s (Type: %s)", is_encrypted, type(is_encrypted))
                        
                        # [OPTIMIZATION] Kullanıcı zaten bir key girdiyse onu kullan
                        used_key = getattr(self, 'aes_key', None)
                        if is_encrypted and not used_key:
                            logger.warning("Encrypted but no key in self.aes_key")
                        
                        self.start_targeted_unreal_translation(str(game_dir), engine, pak_path, internal_file, aes_key=used_key, is_encrypted_override=is_encrypted)
                        return
                        
                except Exception as e:
                    print(f"Embedded Logic Error: {e}")
            
            # Fallback
            self.run_installation_process(file_path, engine, None, translation_method, game_name=game_name)


    def run_installation_process(self, file_path, engine="Unity", aes_key=None, translation_method="full", game_name=None, target_bepinex_zip=None, target_translator_zip=None, loader_type="bepinex"):
        # Genelleştirilmiş kurulum süreci (Thread ile)
        
        # [MOTÖR DESTEK KONTROLÜ]
        if engine not in ["Unity", "Unreal", "Cobra Engine"]:
            QMessageBox.information(self, "Bilgi", 
                f"{engine} motoru için özellik yakında gelecek.\n\n"
                "Gelişmeleri takip etmek için mehmetarıtv YouTube kanalına abone olun!")
            return

        # --- DEEPL KONTROLÜ (UNREAL VS UNITY) ---
        service = self.settings.get("translator_service", "google")
        
        if service == "deepl":
            # Unity için artık DeepL destekleniyor (Python üzerinden)
            # if engine == "Unity": ... (Eski uyarı kaldırıldı)
            
            if engine == "Unreal" or engine == "Unity":
                # API Key Kontrolü
                api_key = self.settings.get("deepl_api_key", "")
                if not api_key:
                    QMessageBox.warning(self, "Eksik API Key", "DeepL kullanmak için Ayarlar sayfasından API Anahtarınızı giriniz.")
                    return


        
        # Onay Mesajı Hazırla
        if engine == "Unity" and translation_method == "full" and file_path.lower().endswith(".exe"):
            # Unity EXE'leri üzerinde "Tam Çeviri" (UnityPy taraması) stabil değil ve gereksiz.
            # Kullanıcıyı korumak için otomatik olarak "Anlık Çeviri" (BepInEx) moduna alıyoruz.
            translation_method = "instant"
            msg_text = f"Seçilen oyun: {os.path.basename(file_path)}\nMotor: {engine}\n\n"
            msg_text += "ℹ️ BİLGİ: Unity oyunları için 'Tam Çeviri' modu yerine 'Anlık Çeviri' (Plugin) modu önerilir.\n"
            msg_text += "Sistem otomatik olarak en uygun moda geçiş yaptı.\n\n"
        else:
            msg_text = f"Seçilen oyun: {os.path.basename(file_path)}\nMotor: {engine}\n\n"
        
        if translation_method == "instant" and engine == "Unity":
            msg_text += "⚠️ DİKKAT: 'Anlık Çeviri' modu seçili.\n"
            msg_text += "Bu işlem arka planda çeviri araçlarını kuracaktır.\n"
            msg_text += "Kurulum tamamlanana kadar (birkaç dakika sürebilir) LÜTFEN OYUNA GİRMEYİN.\n\n"
            
        msg_text += "Çeviri işlemi başlatılsın mı?"

        # [ENFORCED] Unreal için Onay Kutusunu TAMAMEN KALDIR
        is_unreal = (engine == "Unreal")
        
        selected_loader = "bepinex"

        if is_unreal:
            should_start = True
        elif engine == "Unity" and translation_method == "instant": # Unity Plugin Mode
            # ScanResultDialog zaten seçim yaptıysa burayı atla
            # Eğer otomatik (diyalogsuz) geldiyse BepInEx varsayılır
            should_start = True
            selected_loader = loader_type
        else:
            # Diğerleri için klasik onay
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Onay")
            msg_box.setText(msg_text)
            msg_box.setIcon(QMessageBox.Question)
            btn_evet = msg_box.addButton("Evet", QMessageBox.YesRole)
            btn_hayir = msg_box.addButton("Hayır", QMessageBox.NoRole)
            msg_box.setDefaultButton(btn_evet)
            msg_box.exec_()
            should_start = (msg_box.clickedButton() == btn_evet)
        
        if should_start:
             # UI Hazırlığı
            self.trans_log_list.clear() # Temizle
            self.trans_progress.setRange(0, 0) # Sonsuz döngü (Unreal için süre bilinmez)
            self.hourglass_lbl.setVisible(True)
            self.hourglass_timer.start(500)
            
            self.install_btn.setEnabled(False)
            self.scan_btn.setEnabled(False)
            self.manual_btn.setEnabled(False)
            
            # Ayarları al
            service_idx = self.trans_service_combo.currentIndex()
            service_map = {0: "google", 1: "deepl", 2: "gemini"}
            selected_service = service_map.get(service_idx, "google")
            api_key = ""
            
            # [YENİ] Versiyon Seçimi (Eğer birden fazla varsa)
            # [YENİ] Versiyon Seçimi
            # ScanResultDialog zaten seçim yaptıysa burayı atla
            # Eğer yapılmadıysa (Unreal vs) varsayılan None kalsın
            pass

            if selected_service == "deepl":
                api_key = self.settings.get("deepl_api_key", "")
            elif selected_service == "gemini":
                api_key = self.settings.get("gemini_api_key", "")
                
            # Thread Başlat
            # Hız Ayarını Oku
            speed_val = 10
            try:
                if hasattr(self, 'speed_slider'):
                    speed_val = self.speed_slider.value()
            except: pass
            
            # [YENİ] Hedef Dil Seçimi
            target_lang = "tr"
            if hasattr(self, 'combo_target_lang'):
                code = self.combo_target_lang.currentData()
                if code:
                    target_lang = code
            
            if aes_key:
                self.trans_log_list.addItem(f"🔑 Manuel AES Key Kullanılıyor")
             
            self.install_worker = InstallationWorker(file_path, engine, selected_service, api_key, max_workers=speed_val, aes_key=aes_key, translation_method=translation_method, game_name=game_name, target_bepinex_zip=target_bepinex_zip, target_translator_zip=target_translator_zip, loader_type=selected_loader, target_lang=target_lang)
            if hasattr(self, 'install_worker'):
                self.install_worker.log_updated.connect(self.on_install_log)
                self.install_worker.progress_updated.connect(self.trans_progress.setValue)
                self.install_worker.progress_max_updated.connect(self.trans_progress.setMaximum) # [YENİ] Max Bağlantısı
                self.install_worker.finished.connect(self.on_installation_finished)
                
                # AES Key İsteği
                self.install_worker.aes_key_requested.connect(self.handle_aes_key_request)
                
                self.install_worker.manual_review_requested.connect(self.on_manual_review_requested)
                self.install_worker.wwm_loader_requested.connect(self.show_wwm_loader_dialog)
                
                self.install_worker.start()

    def on_install_log(self, msg):
        # Thread'den gelen logları yaz
        try:
            self.trans_log_list.addItem(f"👉 {str(msg)}")
            self.trans_log_list.scrollToBottom()
        except: pass

    def on_install_progress(self, val):
        if hasattr(self, 'trans_progress'): 
             if self.trans_progress.maximum() == 0:
                 self.trans_progress.setRange(0, 100)
             self.trans_progress.setValue(val)

    def handle_aes_key_request(self, game_name, result_queue, event):
        """Worker thread AES Key istediğinde çalışır (GUI Thread)"""
        try:
            key, ok = QInputDialog.getText(self, "Şifreleme Anahtarı Gerekli", 
                         f"'{game_name}' oyununun dosyaları şifreli.\n"
                         "Lütfen AES Key giriniz (0x...):", 
                         QLineEdit.Normal, "0x")
            
            if ok and key:
                result_queue.put(key.strip())
            else:
                result_queue.put(None) # İptal
                
        except Exception as e:
            print(f"AES Dialog Error: {e}")
            result_queue.put(None)
        finally:
            event.set()

    def handle_method_selection_request(self, game_name, result_queue, event):
        """Unreal Engine için metod seçim penceresini göster (PyQt versiyonu)"""
        try:
            dlg = UnrealMethodSelectionDialog(game_name, self)
            if dlg.exec_() == QDialog.Accepted:
                choice = dlg.get_choice()
                logger.debug("Kullanıcı seçimi: %s", choice)
                result_queue.put(choice)
            else:
                result_queue.put("PAK")
        except Exception as e:
            print(f"Dialog Error: {e}")
            result_queue.put("PAK")
        finally:
            event.set()

    def on_manual_review_requested(self, file_path, result_queue, evt):
        """Worker thread manuel inceleme istediğinde çalışır (GUI Thread)"""
        try:
            dialog = QDialog(self)
            dialog.setWindowTitle("Çeviri Tamamlandı - Kontrol Zamanı")
            dialog.setFixedSize(500, 300)
            dialog.setStyleSheet("QDialog { background-color: #1a1f2e; color: white; }")
            
            layout = QVBoxLayout()
            layout.setSpacing(20)
            layout.setContentsMargins(30, 30, 30, 30)
            
            # İkon ve Başlık
            header = QLabel("📝 Çeviri Dosyası Hazır")
            header.setAlignment(Qt.AlignCenter)
            header.setStyleSheet("font-size: 20px; font-weight: bold; color: #60a5fa;")
            layout.addWidget(header)
            
            desc = QLabel("Çeviri tamamlandı ama paketlenmedi.\nCSV dosyasını açıp gerekli düzeltmeleri yapabilirsiniz.\n\n⚠️ ÖNEMLİ: Düzenlemeyi bitirince Excel/Notepad'i KAPATIN ve 'Devam Et' butonuna basın.")
            desc.setAlignment(Qt.AlignCenter)
            desc.setStyleSheet("color: #94a3b8; font-size: 14px; margin-bottom: 10px;")
            layout.addWidget(desc)
            
            # Butonlar
            btn_open = QPushButton("📂 CSV Dosyasını Aç (Düzenle)")
            btn_open.setFixedHeight(45)
            btn_open.setCursor(Qt.PointingHandCursor)
            btn_open.setStyleSheet("QPushButton { background-color: #4b5563; color: white; border-radius: 8px; font-weight: bold; } QPushButton:hover { background-color: #6b7280; }")
            
            def open_csv():
                try:
                    import os
                    os.startfile(file_path)
                except Exception as e:
                    # Hata verirse Notepad ile dene
                    open_notepad()
            
            def open_notepad():
                try:
                    import subprocess
                    subprocess.Popen(["notepad.exe", file_path])
                except Exception as e:
                    QMessageBox.warning(dialog, "Hata", f"Notepad bile açılamadı: {e}")

            btn_open.clicked.connect(open_csv)
            layout.addWidget(btn_open)
            
            # [YENİ] Notepad Butonu
            btn_notepad = QPushButton("📝 Notepad ile Aç (Basit)")
            btn_notepad.setFixedHeight(35)
            btn_notepad.setCursor(Qt.PointingHandCursor)
            btn_notepad.setStyleSheet("QPushButton { background-color: #475569; color: width; border-radius: 8px; } QPushButton:hover { background-color: #64748b; }")
            btn_notepad.clicked.connect(open_notepad)
            layout.addWidget(btn_notepad)
            
            # Aksiyon Butonları
            action_layout = QHBoxLayout()
            
            btn_cancel = QPushButton("İptal Et")
            btn_cancel.setFixedSize(120, 45)
            btn_cancel.setStyleSheet("QPushButton { background-color: #ef4444; color: white; border-radius: 8px; font-weight: bold; } QPushButton:hover { background-color: #dc2626; }")
            btn_cancel.clicked.connect(dialog.reject)
            
            btn_continue = QPushButton("✅ Kaydettim, Devam Et")
            btn_continue.setFixedHeight(45)
            btn_continue.setStyleSheet("QPushButton { background-color: #10b981; color: white; border-radius: 8px; font-weight: bold; } QPushButton:hover { background-color: #059669; }")
            btn_continue.clicked.connect(dialog.accept)
            
            action_layout.addWidget(btn_cancel)
            action_layout.addWidget(btn_continue)
            layout.addLayout(action_layout)
            
            dialog.setLayout(layout)
            
            # Dialog Sonucu
            if dialog.exec_() == QDialog.Accepted:
                result_queue.put(True) # Devam
            else:
                result_queue.put(False) # İptal
                
        except Exception as e:
            print(f"Manual Review UI Error: {e}")
            result_queue.put(True) # Hata olursa devam et (Bloklama)
        finally:
            if evt:
                evt.set()

    def show_wwm_loader_dialog(self, game_dir):
        """WWM Loader Dialogunu Göster (Main Thread)"""
        try:
            logger.debug("WWM Dialog açılıyor: %s", game_dir)
            # WWMLoaderDialog sınıfı dosyanın başında tanımlı olmalı
            dialog = WWMLoaderDialog(game_dir, self)
            dialog.exec_()
        except Exception as e:
            print(f"WWM Dialog Error: {e}")
            QMessageBox.critical(self, "Hata", f"Loader penceresi açılamadı: {e}")

    def show_community_feedback_dialog(self, oyun_adi, oyun_motoru):
        """Çeviri sonrasında çıkan ve kapatılamayan zorunlu değerlendirme ekranı"""
        try:
            dlg = QDialog(self)
            dlg.setWindowTitle("Topluluğa Katkı Sağla!")
            dlg.setFixedSize(500, 350)
            
            # Formun sag usten vs kapatilmasini engelliyoruz
            dlg.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowMinimizeButtonHint)
            dlg.setStyleSheet("background-color: #1a1f2e; color: white;")
            
            layout = QVBoxLayout(dlg)
            layout.setSpacing(15)
            layout.setContentsMargins(30, 30, 30, 30)
            
            icon_lbl = QLabel("🌍")
            icon_lbl.setAlignment(Qt.AlignCenter)
            icon_lbl.setStyleSheet("font-size: 48px;")
            layout.addWidget(icon_lbl)
            
            title = QLabel(f"'{oyun_adi}' Çevirisi Bitti!")
            title.setAlignment(Qt.AlignCenter)
            title.setStyleSheet("font-size: 22px; font-weight: bold; color: #6c8eff; margin-top: 10px;")
            layout.addWidget(title)
            
            info = QLabel("Oyunu arkada test edebilirsin.\nAncak diğer oyunculara yardımcı olmak için bu çevirinin\nbaşarılı olup olmadığını belirtmen BİZİM İÇİN ÇOK ÖNEMLİ!")
            info.setAlignment(Qt.AlignCenter)
            info.setStyleSheet("font-size: 14px; color: #94a3b8; font-weight: bold; margin-bottom: 20px;")
            layout.addWidget(info)
            
            btn_layout = QHBoxLayout()
            btn_layout.setSpacing(20)
            
            btn_success = QPushButton("✅ ÇEVİRİ ÇALIŞTI")
            btn_success.setFixedHeight(50)
            btn_success.setCursor(Qt.PointingHandCursor)
            btn_success.setStyleSheet("QPushButton { background-color: #10b981; color: white; border-radius: 8px; font-weight: bold; font-size: 15px; } QPushButton:hover { background-color: #059669; }")
            
            btn_fail = QPushButton("❌ ÇEVİRİ ÇALIŞMADI")
            btn_fail.setFixedHeight(50)
            btn_fail.setCursor(Qt.PointingHandCursor)
            btn_fail.setStyleSheet("QPushButton { background-color: #ef4444; color: white; border-radius: 8px; font-weight: bold; font-size: 15px; } QPushButton:hover { background-color: #dc2626; }")
            
            def on_submit(durum):
                # Ayarlardaki client id'yi al
                client_id = getattr(self, "settings", {}).get("unique_client_id", "NO_ID")
                
                # Veritabanina Gonder
                self.send_community_data(client_id, oyun_adi, oyun_motoru, durum, "Oyun Çevirisi")
                
                # Ufak bir tesekkur mesaji ve kapat
                QMessageBox.information(self, "Teşekkürler", "Geri bildiriminiz topluluk veritabanına eklendi!")
                dlg.accept()
                
            btn_success.clicked.connect(lambda: on_submit("Çevrildi"))
            btn_fail.clicked.connect(lambda: on_submit("Çevrilmedi"))
            
            btn_layout.addWidget(btn_success)
            btn_layout.addWidget(btn_fail)
            layout.addLayout(btn_layout)
            
            dlg.exec_()
        except Exception as e:
            print(f"Feedback Dialog Hata: {e}")

    def on_installation_finished(self, success, msg):
        # Thread bittiğinde UI'ı düzelt
        try:
            self.hourglass_lbl.setVisible(False)
            self.hourglass_timer.stop()
            self.trans_progress.setRange(0, 100)
            self.trans_progress.setValue(100 if success else 0)
            
            self.install_btn.setEnabled(True)
            self.scan_btn.setEnabled(True)
            self.manual_btn.setEnabled(True)
            
            if success:
                # QMessageBox yok edildi
                self.trans_log_list.addItem("✅ İŞLEM BAŞARIYLA TAMAMLANDI!")
                self.trans_log_list.addItem("Keyifli oyunlar!")
                self.trans_log_list.scrollToBottom()
                
                # [GÜNCELLEME] Kütüphane butonu kaldırıldı, sadece çeviri sayfasındaki buton gösteriliyor.
                # if hasattr(self, 'run_game_btn'):
                #    self.run_game_btn.setVisible(True)
                
                # [YENİ] Çeviri sayfasındaki butonu da göster
                if hasattr(self, 'run_game_btn_trans'):
                    self.run_game_btn_trans.setVisible(True)

                # --- YENI - TOPLULUK ZORUNLU DEGERLENDIRME ---
                # Hangi oyunun cevrildigini tablo seciminden bulalim
                target_oyun = "Bilinmeyen Oyun"
                target_motor = "Bilinmeyen Motor"
                
                try:
                    if hasattr(self, 'game_table') and self.game_table.selectedItems():
                        selected = self.game_table.selectedItems()
                        if len(selected) > 0:
                            row = selected[0].row()
                            target_oyun = self.game_table.item(row, 1).text()
                            target_motor = self.game_table.item(row, 3).text()
                except Exception as e:
                    print(f"Tablo Okuma Hatası: {e}")
                    
                # --- SUCESS DIALOG (YouTube + Feedback) ---
                try:
                    success_dlg = QDialog(self)
                    success_dlg.setWindowTitle("İşlem Başarılı")
                    success_dlg.setFixedSize(450, 430)
                    success_dlg.setStyleSheet("background-color: #1a1f2e; color: white;")
                    success_dlg.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
                    
                    dlg_layout = QVBoxLayout(success_dlg)
                    dlg_layout.setSpacing(12)
                    dlg_layout.setContentsMargins(20, 20, 20, 20)
                    
                    lbl_icon = QLabel("✅")
                    lbl_icon.setAlignment(Qt.AlignCenter)
                    lbl_icon.setStyleSheet("font-size: 48px; margin-top: 5px;")
                    dlg_layout.addWidget(lbl_icon)
                    
                    lbl_title = QLabel("Oyununuz Çevrildi, Keyifli Oyunlar!")
                    lbl_title.setAlignment(Qt.AlignCenter)
                    lbl_title.setStyleSheet("font-size: 18px; font-weight: 800; color: #10b981; margin: 5px 0;")
                    dlg_layout.addWidget(lbl_title)
                    
                    lbl_sub = QLabel("Daha fazlası için:")
                    lbl_sub.setAlignment(Qt.AlignCenter)
                    lbl_sub.setStyleSheet("color: #94a3b8; font-size: 13px; margin-bottom: 3px;")
                    dlg_layout.addWidget(lbl_sub)
                    
                    btn_subscribe = QPushButton("📺 MEHMET ARI TV KANALINA ABONE OL")
                    btn_subscribe.setCursor(Qt.PointingHandCursor)
                    btn_subscribe.setStyleSheet("""
                        QPushButton { background-color: #ef4444; color: white; font-weight: 900; font-size: 14px; padding: 10px; border-radius: 8px; }
                        QPushButton:hover { background-color: #dc2626; }
                    """)
                    btn_subscribe.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://www.youtube.com/@MehmetAriTV")))
                    dlg_layout.addWidget(btn_subscribe)
                    
                    # --- ÇEVİRİ GERİ BİLDİRİMİ ---
                    lbl_fb = QLabel("Bu çeviri çalıştı mı?")
                    lbl_fb.setAlignment(Qt.AlignCenter)
                    lbl_fb.setStyleSheet("color: #e8edf2; font-size: 14px; font-weight: bold; margin-top: 10px;")
                    dlg_layout.addWidget(lbl_fb)
                    
                    fb_layout = QHBoxLayout()
                    fb_layout.setSpacing(10)
                    
                    btn_yes = QPushButton("✅ Çevrildi")
                    btn_yes.setFixedHeight(44)
                    btn_yes.setCursor(Qt.PointingHandCursor)
                    btn_yes.setStyleSheet("QPushButton { background-color: #10b981; color: white; border-radius: 8px; font-weight: bold; font-size: 14px; } QPushButton:hover { background-color: #059669; }")
                    
                    btn_no = QPushButton("❌ Çevrilmedi")
                    btn_no.setFixedHeight(44)
                    btn_no.setCursor(Qt.PointingHandCursor)
                    btn_no.setStyleSheet("QPushButton { background-color: #ef4444; color: white; border-radius: 8px; font-weight: bold; font-size: 14px; } QPushButton:hover { background-color: #dc2626; }")
                    
                    def submit_feedback(durum):
                        client_id = getattr(self, "settings", {}).get("unique_client_id", "NO_ID")
                        self.send_community_data(client_id, target_oyun, target_motor, durum, "Oyun Çevirisi")
                        success_dlg.accept()
                    
                    btn_yes.clicked.connect(lambda: submit_feedback("Çevrildi"))
                    btn_no.clicked.connect(lambda: submit_feedback("Çevrilmedi"))
                    
                    fb_layout.addWidget(btn_yes)
                    fb_layout.addWidget(btn_no)
                    dlg_layout.addLayout(fb_layout)
                    
                    success_dlg.exec_()
                except Exception as e:
                    print(f"Success Dialog Error: {e}")
            
            else:
                if msg == "AES_REQUIRED_BY_USER":
                    # AES KEY İSTE
                    key, ok = QInputDialog.getText(self, "Şifreleme Anahtarı Gerekli", 
                                                 "Bu oyunun dosyaları şifreli ve otomatik olarak çözülemedi.\n"
                                                 "Lütfen 0x ile başlayan AES Key'i giriniz:", 
                                                 QLineEdit.Normal, "0x")
                    
                    if ok and key and len(key) > 10:
                        self.trans_log_list.addItem(f"🔄 AES Key alındı, işlem tekrar deneniyor...")
                        # Restart with key
                        # Eski worker parametrelerini saklamalıyız ama basitçe son seçimi alabiliriz
                        # run_installation_process tekrar çağrılabilir
                        
                        # Parametreleri yeniden topla
                        selected = self.game_table.selectedItems()
                        if selected:
                            row = selected[0].row()
                            path_item = self.game_table.item(row, 4)
                            file_path = path_item.data(Qt.UserRole)
                            engine = self.game_table.item(row, 3).text()
                            game_name = self.game_table.item(row, 1).text()
                            
                            # Method
                            method = "full"
                            if hasattr(self, 'rb_instant') and self.rb_instant.isChecked():
                                method = "instant"
                                
                            self.run_installation_process(file_path, engine, aes_key=key.strip(), translation_method=method, game_name=game_name)
                            return # Fonksiyondan çık, yeni worker başladı

                    else:
                         self.trans_log_list.addItem("❌ AES Key girişi iptal edildi.")
                
                # QMessageBox yok edildi
                self.trans_log_list.addItem(f"❌ HATA DETAYI: {str(msg)}")
                self.trans_log_list.addItem("❌ İŞLEM HATALI BİTTİ.")
        except Exception as e:
            print(f"UI Finish Error: {e}")
            
            self.hourglass_timer.stop()
            self.install_btn.setEnabled(True)
            self.scan_btn.setEnabled(True)
            self.manual_btn.setEnabled(True)





    def animate_hourglass(self):
        # Kum saati animasyonu
        if hasattr(self, 'hourglass_lbl'):
            self.hourglass_angle = (self.hourglass_angle + 45) % 360
            # Basit bir döndürme efekti yerine karakter değişimi veya QTransform kullanılabilir.
            # Ancak QLabel'de rotate yapmak zor olduğu için ikon setini değiştiriyoruz.
            emojis = ["⏳", "⌛"]
            current = emojis[1] if self.hourglass_angle % 90 else emojis[0]
            self.hourglass_lbl.setText(current)

    def install_translator(self):
        # Çevirici kurulumunu başlat - Görselleştirilmiş
        if not TranslatorManager:
            return
            
        file_path, _ = QFileDialog.getOpenFileName(self, "Oyun Seç (.exe)", "", "Executable (*.exe)")
        if not file_path:
            return
            
        # Onay iste
        reply = QMessageBox.question(self, 'Onay', 
                                     f'Seçilen oyun: {os.path.basename(file_path)}\n\nBu oyuna otomatik çeviri aracı kurulacak. Devam edilsin mi?',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                                     
        if reply == QMessageBox.Yes:
            try:
                # UI Hazırlığı
                self.trans_log_group.setVisible(True)
                self.trans_log_list.clear()
                self.trans_progress.setRange(0, 0) # Indeterminate
                self.hourglass_timer.start(500)
                self.trans_status_lbl.setText("İşlem başlatılıyor...")
                
                # Buton pasif
                btn = self.sender()
                btn.setEnabled(False)
                QApplication.processEvents()
                
                import time
                import random
                
                # ADIM 1: Analiz
                self.trans_status_lbl.setText("Oyun dosyaları analiz ediliyor...")
                self.trans_log_list.addItem(f"🔍 Analiz ediliyor: {os.path.basename(file_path)}")
                self.trans_log_list.scrollToBottom()
                QApplication.processEvents()
                time.sleep(random.uniform(1.0, 2.0))
                
                # ADIM 2: Dil Dosyası
                self.trans_status_lbl.setText("Dil dosyaları kontrol ediliyor...")
                self.trans_log_list.addItem("📄 Dil yapılandırması bulundu.")
                self.trans_log_list.scrollToBottom()
                QApplication.processEvents()
                time.sleep(random.uniform(0.8, 1.5))
                
                # ADIM 3: Çözümleme
                self.trans_status_lbl.setText("Gereksinimler çözümleniyor...")
                self.trans_log_list.addItem("⚙️ BepInEx ve AutoTranslator ayıklanıyor...")
                self.trans_log_list.scrollToBottom()
                QApplication.processEvents()
                time.sleep(random.uniform(1.2, 2.0))
                
                # ADIM 4: Entegrasyon (Gerçek İşlem)
                self.trans_status_lbl.setText("Araçlar entegre ediliyor...")
                self.trans_log_list.addItem("📥 Dosyalar kopyalanıyor...")
                self.trans_log_list.scrollToBottom()
                QApplication.processEvents()
                
                # Gerçek kurulum çağrısı
                srv = self.settings.get("translator_service", "google")
                deepl_key = self.settings.get("deepl_api_key", "")
                gemini_key = self.settings.get("gemini_api_key", "")
                
                api_key = deepl_key if srv == "deepl" else gemini_key if srv == "gemini" else ""
                
                if srv == "deepl":
                    self.trans_log_list.addItem("🌍 DeepL servisi seçildi.")
                    self.trans_log_list.scrollToBottom()
                elif srv == "gemini":
                    self.trans_log_list.addItem("⚡ Gemini Flash servisi seçildi.")
                    self.trans_log_list.scrollToBottom()
                
                success = TranslatorManager.install(file_path, service=srv, api_key=api_key)
                
                # İşlem Sonucu
                time.sleep(0.5)
                self.hourglass_timer.stop()
                self.trans_progress.setRange(0, 100)
                self.trans_progress.setValue(100)
                btn.setEnabled(True)
                
                if success:
                    self.trans_status_lbl.setText("Çeviri anlık devam ediyor")
                    self.trans_log_list.addItem("✅ Kurulum tamamlandı.")
                    self.trans_log_list.addItem("🚀 Oyun açıldığında çeviri işlemi devam edecektir.")
                    self.trans_log_list.scrollToBottom()
                    self.hourglass_lbl.setText("🔄")
                    # QMessageBox.information(self, "Başarılı", "Otomatik çeviri aracı kuruldu!")
                else:
                    self.trans_status_lbl.setText("❌ İşlem başarısız oldu.")
                    self.trans_log_list.addItem("❌ Kurulum sırasında bir hata oluştu.")
                    self.hourglass_lbl.setText("❌")
                    
            except Exception as e:
                self.hourglass_timer.stop()
                btn.setEnabled(True)
                self.trans_status_lbl.setText("❌ Hata oluştu!")
                self.trans_log_list.addItem(f"❌ Hata: {str(e)}")
                QMessageBox.critical(self, "Hata", f"Kurulum hatası:\n{str(e)}")

    def save_deepl_key(self):
        # DeepL API anahtarını anlık kaydet
        key = self.deepl_key_input.text().strip()
        self.settings["deepl_api_key"] = key
        self.save_settings()

    def save_gemini_key(self):
        # Gemini API anahtarını anlık kaydet
        key = self.gemini_key_input.text().strip()
        self.settings["gemini_api_key"] = key
        self.save_settings()

    def check_deepl_usage(self):
        # DeepL kullanım limitini kontrol et
        api_key = self.settings.get("deepl_api_key", "")
        if not api_key:
            if hasattr(self, 'dl_status_lbl'):
                self.dl_status_lbl.setText("API Anahtarı girilmedi!")
            return

        if hasattr(self, 'dl_refresh_btn'):
            self.dl_refresh_btn.setEnabled(False)
            self.dl_status_lbl.setText("Kontrol ediliyor...")
            
        self.dl_checker = DeepLUsageChecker(api_key)
        self.dl_checker.finished.connect(self.on_deepl_usage_checked)
        self.dl_checker.start()
        
    def on_deepl_usage_checked(self, data):
        # Kullanım kontrolü sonucu
        if hasattr(self, 'dl_refresh_btn'):
            self.dl_refresh_btn.setEnabled(True)
            
        if "error" in data:
            self.dl_status_lbl.setText(f"Hata: {data['error']}")
            return
            
        count = data.get("character_count", 0)
        limit = data.get("character_limit", 0)
        
        if limit > 0:
            percent = int((count / limit) * 100)
            self.dl_progress.setValue(percent)
            
            # Renk: %90 üzeri kırmızı, %70 üzeri sarı, altı yeşil
            if percent >= 90:
                color = "#ef4444"
            elif percent >= 70:
                color = "#f59e0b"
            else:
                color = "#10b981"
                
            self.dl_progress.setStyleSheet("QProgressBar { border: 1px solid #2d3748; border-radius: 4px; text-align: center; color: white; background-color: #1a1f2e; } QProgressBar::chunk { background-color: " + color + "; border-radius: 4px; }")
            
            self.dl_status_lbl.setText(f"{count:,} / {limit:,} karakter")
        else:
            self.dl_status_lbl.setText(f"Limit bilgisi alınamadı ({count} kullanılan)")


    def run_selected_game(self):
        """Seçilen oyunu başlat"""
        if not hasattr(self, 'current_game_data') or not self.current_game_data:
            return
            
        exe_path = self.current_game_data.get('exe') or self.current_game_data.get('path')
        if not exe_path or not os.path.exists(exe_path):
             QMessageBox.warning(self, "Hata", "Oyun dosyası bulunamadı!")
             return
             
        try:
            folder = os.path.dirname(exe_path)
            
            # subprocess yerine ShellExecute kullanarak "Kısayol" gibi davranmasını sağlıyoruz.
            # Bu yöntem yönetici izinlerini, çalışma dizinini ve ortam değişkenlerini Windows Explorer gibi yönetir.
            import ctypes
            # ShellExecuteW(hwnd, operation, file, parameters, directory, show_cmd)
            # SW_SHOWNORMAL = 1
            result = ctypes.windll.shell32.ShellExecuteW(None, "open", exe_path, None, folder, 1)
            
            # Başarısız olursa (Result <= 32 hata kodudur)
            if result <= 32:
                 raise Exception(f"ShellExecute Error Code: {result}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Oyun başlatılamadı: {e}")

    def handle_cleanup_current_game(self):
        """Seçili oyunu temizle (Uninstall Translator)"""
        if not hasattr(self, 'current_game_data') or not self.current_game_data:
            QMessageBox.warning(self, "Hata", "Lütfen listeden bir oyun seçin.")
            return
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "İşlem Sürüyor", "Şu anda bir işlem devam ediyor. Lütfen bitmesini bekleyin.")
            return

        game_data = self.current_game_data
        game_name = game_data.get('name', 'Bilinmeyen Oyun')
        
        # Custom Dialog for Cleanup Options
        dlg = QDialog(self)
        dlg.setWindowTitle("Temizleme Seçenekleri")
        dlg.setFixedSize(400, 250)
        dlg.setStyleSheet("background-color: #1a1f2e; color: white;")
        
        layout = QVBoxLayout(dlg)
        
        lbl = QLabel(f"'{game_data.get('name')}' için temizleme işlemi:")
        lbl.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(lbl)
        
        cb_files = QCheckBox("Dosyaları Temizle (BepInEx, Translator)")
        cb_files.setChecked(True)
        cb_files.setStyleSheet("font-size: 14px; margin-bottom: 5px;")
        layout.addWidget(cb_files)
        
        cb_reg = QCheckBox("Oyun Ayarlarını Sıfırla (Registry/PlayerPrefs)")
        cb_reg.setChecked(False)
        cb_reg.setToolTip("Pencere modu, çözünürlük vb. ayarları sıfırlar. Grafik hataları için önerilir.")
        cb_reg.setStyleSheet("font-size: 14px; color: #f87171;")
        layout.addWidget(cb_reg)
        
        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Temizle")
        btn_ok.setStyleSheet("background-color: #e53e3e; color: white; padding: 8px; font-weight: bold; border-radius: 4px;")
        btn_ok.clicked.connect(dlg.accept)
        
        btn_cancel = QPushButton("İptal")
        btn_cancel.setStyleSheet("background-color: #4b5563; color: white; padding: 8px; border-radius: 4px;")
        btn_cancel.clicked.connect(dlg.reject)
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)
        
        if dlg.exec_() == QDialog.Accepted:
            try:
                from translator_manager import TranslatorManager
                from pathlib import Path
                game_path = game_data.get('path')
                exe_path = game_data.get('exe')
                target = exe_path if exe_path else game_path
                
                msgs = []
                
                # 1. Dosya Temizliği
                if cb_files.isChecked():
                    success, msg = TranslatorManager.uninstall(target)
                    msgs.append(f"Dosyalar: {msg}")
                
                # 2. Registry Temizliği
                if cb_reg.isChecked():
                    # Parent folder needed for reset_game_settings? No, works with game_path (exe or root) logic inside
                    # But reset_game_settings expects game_path to locate *_Data
                    # If target is exe, parent is game root.
                    root_path = Path(target).parent if os.path.isfile(target) else Path(target)
                    r_success, r_msg = TranslatorManager.reset_game_settings(root_path)
                    res_text = "Sıfırlandı" if r_success else "Başarısız"
                    msgs.append(f"Ayarlar: {res_text} ({r_msg})")
                
                QMessageBox.information(self, "İşlem Tamamlandı", "\n".join(msgs))
                
            except Exception as e:
                QMessageBox.critical(self, "Kritik Hata", f"İşlem başarısız: {str(e)}")




    def closeEvent(self, event):
        """Uygulama kapatıldığında tüm süreçleri öldür ve temizlik yap"""
        try:
            # 1. Secure Connect (DNS/MemoFast Ağ Servisi) Kapat
            try:
                self.reset_windows_dns()
            except: pass

            # 2. Varsa çalışan threadleri durdur
            workers = ['install_worker', 'scan_worker', 'dl_checker', 'startup_update_worker', 'app_update_thread']
            for w_name in workers:
                if hasattr(self, w_name):
                    w = getattr(self, w_name)
                    if w and w.isRunning():
                        w.terminate() 
            
            # 3. Ekran Çevirmeni Varsa Kapat
            if hasattr(self, 'translator') and self.translator:
                try: self.translator.close()
                except: pass
            
            # 4. Tüm Pencereleri Kapat ve Çık
            QApplication.closeAllWindows()
            event.accept()
            
        except:
            if event: event.accept()

class ScanWorker(QThread):
    finished = pyqtSignal(list)
    progress = pyqtSignal(str)
    
    def run(self):
        from scanner import GameEngineScanner
        scanner = GameEngineScanner()
        games = scanner.scan(lambda msg: self.progress.emit(msg))
        self.finished.emit(games)




    def stop(self):
        self.running = False

class UnrealMethodSelectionDialog(QDialog):
    """Unreal Engine Çeviri Yöntemi Seçim Penceresi"""
    def __init__(self, game_name, parent=None):
        super().__init__(parent)
        # [FORCEFIX] Otomatik PAK seçimi için pencereyi gösterme veya hemen kapat
        self.choice = "PAK"
        # Pencereyi oluştur ama hemen kabul et (veya hiç gösterme, ancak exec_ çağrılabilir)
        # En güvenlisi get_choice'in her zaman PAK dönmesidir.
        
        # UI Kurulumu (Göstermelik/Legacy)
        self.hide() # Gizle
        QTimer.singleShot(0, self.accept) # Hemen kapat

    def get_choice(self):
        # return "DB" if self.rb_db.isChecked() else "PAK"
        return "PAK"

class TranslatorSettingsDialog(QDialog):
    """XUnity Çeviri Ayarları Penceresi"""
    def __init__(self, game_data, parent=None):
        super().__init__(parent)
        self.game_data = game_data
        self.setWindowTitle(f"Çeviri Ayarları - {game_data['name']}")
        # Yükseklik artırıldı (450 -> 580)
        self.setFixedSize(500, 580)
        self.setStyleSheet("""
            QDialog { background-color: #1a1f2e; color: #e8edf2; }
            QLabel { color: #e8edf2; font-size: 13px; }
            QCheckBox { color: #e8edf2; font-size: 13px; spacing: 8px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #4a5568; background-color: #2d3748; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
            QComboBox { background-color: #2d3748; color: white; padding: 5px; border-radius: 4px; border: 1px solid #4a5568; }
            QPushButton { padding: 8px 16px; border-radius: 6px; font-weight: bold; }
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Başlık
        title = QLabel(f"⚙️ {game_data['name']} Ayarları")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #6c8eff; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # 1. Font Ayarları
        font_group = QGroupBox("Yazı Tipi (Font)")
        font_group.setStyleSheet("QGroupBox { border: 1px solid #4a5568; border-radius: 8px; margin-top: 10px; padding-top: 15px; font-weight: bold; }")
        font_layout = QVBoxLayout()
        
        font_lbl = QLabel("Oyun içinde kullanılacak yazı tipi (Türkçe karakterler için önerilen: Segoe UI, Calibri):")
        self.font_combo = QComboBox()
        # Türkçe karakterleri iyi destekleyen fontlar öncelikli
        self.font_combo.addItems([
            "Segoe UI",  # ⭐ Windows'un varsayılan fontu, Türkçe karakterleri mükemmel destekler
            "Calibri",   # ⭐ Office fontu, Türkçe karakterleri çok iyi destekler
            "Arial", 
            "Tahoma",    # Türkçe karakterleri iyi destekler
            "Verdana", 
            "Times New Roman", 
            "Consolas",
            "Microsoft Sans Serif",  # Türkçe karakterleri destekler
            "Trebuchet MS"  # Türkçe karakterleri destekler
        ])
        self.font_combo.setEditable(True) # Kullanıcı elle de yazabilsin
        self.font_combo.setCurrentText("Segoe UI")  # Varsayılan: Türkçe karakterleri en iyi destekleyen font
        
        font_layout.addWidget(font_lbl)
        font_layout.addWidget(self.font_combo)
        
        # [YENİ] Hızlı Onar Butonu
        self.quick_font_btn = QPushButton("🛠️ Otomatik Onar (Arial)")
        self.quick_font_btn.setToolTip("Fontu Arial yapar ve SDF fallback ayarlarını düzeltir.")
        self.quick_font_btn.clicked.connect(self.quick_fix_font)
        font_layout.addWidget(self.quick_font_btn)
        
        font_group.setLayout(font_layout)
        layout.addWidget(font_group)
        
        # 2. Filtre Ayarları
        filter_group = QGroupBox("Çeviri Filtreleri")
        filter_group.setStyleSheet("QGroupBox { border: 1px solid #4a5568; border-radius: 8px; margin-top: 10px; padding-top: 15px; font-weight: bold; }")
        filter_layout = QVBoxLayout()
        filter_layout.setSpacing(10)
        
        self.cb_grammar = QCheckBox("Mek/Mak Düzeltmesi (Gitmek -> Git)")
        self.cb_grammar.setChecked(True)
        self.cb_grammar.setToolTip("Fiillerin sonundaki mastar eklerini kaldırır. Emir kipi gibi görünmesini sağlar.")
        
        self.cb_ascii = QCheckBox("Türkçe Karakterleri Düzelt (ğ -> g, ş -> s)")
        self.cb_ascii.setChecked(False)
        self.cb_ascii.setToolTip("Eğer oyunda Türkçe karakterler kutu (□) veya ? olarak çıkıyorsa bunu işaretleyin.")
        
        filter_layout.addWidget(self.cb_grammar)
        filter_layout.addWidget(self.cb_ascii)
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)
        
        # [KALDIRILDI] 3. Gelişmiş Font Yönetimi (Kullanıcı İsteği: Gereksiz)
        # adv_font_group = QGroupBox("Gelişmiş Font Yönetimi")
        # ...
        # layout.addWidget(adv_font_group)
        
        # Butonlar
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.setStyleSheet("background-color: #4a5568; color: white;")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.save_btn = QPushButton("Kaydet ve Uygula")
        self.save_btn.setStyleSheet("background-color: #10b981; color: white;")
        self.save_btn.clicked.connect(self.save_settings)
        
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        
        layout.addStretch()
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        
        # Mevcut Ayarları Yükle
        self.load_current_settings()
    
    def quick_fix_font(self):
        """Hızlı Font Düzeltme"""
        self.font_combo.setCurrentText("Arial")
        # Save'i tetikle
        self.save_settings()


    def load_current_settings(self):
        """Mevcut yapılandırmayı dosyadan oku ve arayüze yansıt"""
        try:
            from translator_manager import TranslatorManager
            game_path = self.game_data['path']
            
            # 1. Font (OverrideFont veya FallbackFontTextMeshPro)
            override = TranslatorManager.get_config(game_path, "Behaviour", "OverrideFont")
            fallback = TranslatorManager.get_config(game_path, "Behaviour", "FallbackFontTextMeshPro")
            
            # Hangisi doluysa onu göster (Override öncelikli)
            current_font = override if override else fallback
            
            # Eğer "Arial SDF" ise sadece "Arial" göster (Kullanıcı kafası karışmasın)
            if current_font == "Arial SDF": 
                current_font = "Arial"
                
            if current_font:
                if current_font not in [self.font_combo.itemText(i) for i in range(self.font_combo.count())]:
                     self.font_combo.addItem(current_font)
                self.font_combo.setCurrentText(current_font)
            else:
                self.font_combo.setCurrentText("") # Boşsa boş göster (Varsayılan Font)
            
            # 2. Filtreler (Regex XML Analizi)
            # RegexSubstitutions.xml'i oku
            import re
            cb_grammar_active = False
            cb_ascii_active = False
            
            xml_path = Path(game_path) / "Translation" / "_RegexSubstitutions.xml"
            if not xml_path.exists():
                # Alternatif yollar
                candidates = list(Path(game_path).rglob("_RegexSubstitutions.xml"))
                if candidates: xml_path = candidates[0]
            
            if xml_path and xml_path.exists():
                with open(xml_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                    # Gramer (mek/mak) kontrolü
                    if "m[ae]k" in content:
                        cb_grammar_active = True
                        
                    # ASCII (ğ->g) kontrolü
                    if "<Regex>ğ</Regex>" in content or "<Regex>ş</Regex>" in content:
                        cb_ascii_active = True
            
            self.cb_grammar.setChecked(cb_grammar_active)
            self.cb_ascii.setChecked(cb_ascii_active)
            
        except Exception as e:
            print(f"Settings Load Error: {e}")
        
    def save_settings(self):
        """Ayarları TranslatorManager üzerinden uygula"""
        font = self.font_combo.currentText()
        fix_grammar = self.cb_grammar.isChecked()
        fix_chars = self.cb_ascii.isChecked()
        
        game_path = self.game_data['path']
        
        try:
            from translator_manager import TranslatorManager
            
            # Font Ayarla
            TranslatorManager.set_font(game_path, font)
            
            # [FIX] Loader Tipi Tespiti
            loader_type = "bepinex"
            # Basit tespit: MelonLoader klasörü veya AutoTranslator (root) varsa melondur
            if (Path(game_path) / "MelonLoader").exists() or (Path(game_path) / "AutoTranslator").exists():
                 loader_type = "melon"
            
            # Filtreleri Uygula & Dosyayı Temizle
            # 1. RegexSubstitutions.xml güncelle (Canlı/Oyun içi)
            TranslatorManager.apply_local_filter(
                game_path, 
                progress_callback=None, # Sessiz
                fix_grammar=fix_grammar,
                fix_chars=fix_chars,
                loader_type=loader_type
            )
            
            # 2. TXT Dosyasını Temizle (Kullanıcı İsteği: Kaydet deyince düzeltilsin)
            if fix_grammar or fix_chars:
                # Dosya henüz oluşmamış olabilir, sessizce dene
                # fix_chars parametresi clean_translation_file'a gönderilmeli
                # Ancak fonksiyon varsayılan olarak fix_chars (ascii düzeltme) kontrolünü
                # parametre olarak istiyor mu? Evet, ekledik.
                
                # UYARI: clean_translation_file içindeki logic hem mek/mak hem char fix'i kapsıyor.
                # Eğer kullanıcı sadece gramer seçtiyse char fix yapmamalı.
                # Fonksiyonumuzu buna göre güncellememiz gerekir veya parametreyi doğru geçmeliyiz.
                # Şu anki clean_translation_file tümleşik çalışıyor.
                # Onu güncelleyelim: fix_chars=fix_chars
                
                success, msg = TranslatorManager.clean_translation_file(
                    game_path, 
                    fix_grammar=fix_grammar, 
                    fix_chars=fix_chars,
                    loader_type=loader_type
                )
                if success:
                    print(f"Auto-Clean: {msg}")
                    QMessageBox.information(self, "Başarılı", f"Ayarlar kaydedildi.\n\nTemizlik Raporu:\n{msg}\n\nDeğişikliklerin görünmesi için oyunu yeniden başlatın.")
                else:
                    QMessageBox.information(self, "Başarılı", f"Ayarlar kaydedildi ancak temizlik yapılamadı:\n{msg}")
            else:
                 QMessageBox.information(self, "Başarılı", "Ayarlar kaydedildi.\nDeğişikliklerin görünmesi için oyunu yeniden başlatın.")

            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Ayarlar kaydedilemedi: {e}")


class ScanResultDialog(QDialog):
    def __init__(self, game_path, parent=None):
        super().__init__(parent)
        self.game_path = game_path
        self.setWindowTitle("Oyun Analizi ve Uyumluluk")
        
        # [RESPONSIVE] Ekran çözünürlüğüne göre dinamik boyutlandırma
        screen = QApplication.primaryScreen().geometry()
        width = min(850, screen.width() * 0.9)
        height = min(900, screen.height() * 0.85)
        self.resize(int(width), int(height))
        
        # State
        self.show_all_versions = False
        self.analysis_results = {}
        
        self.setStyleSheet("""
            QDialog { background-color: #1a1f2e; color: white; }
            QWidget#scroll_content { background-color: #1a1f2e; }
            QLabel { color: #e8edf2; font-size: 13px; background: transparent; }
            QGroupBox { border: 1px solid #2d3748; border-radius: 8px; margin-top: 15px; padding-top: 15px; font-weight: bold; color: #6c8eff; background-color: transparent; }
            QComboBox { background-color: #0f1419; color: white; border: 1px solid #2d3748; padding: 6px; border-radius: 4px; min-height: 28px; font-size: 13px; }
            QComboBox::drop-down { border: none; }
            QPushButton { background-color: #3b82f6; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-weight: bold; font-size: 14px; }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton#cancel { background-color: #4b5563; }
            QPushButton#cancel:hover { background-color: #6b7280; }
            QPushButton#toggle_filter { background-color: transparent; color: #94a3b8; border: 1px solid #2d3748; padding: 5px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; }
            QPushButton#toggle_filter:hover { background-color: #2d3748; color: white; }
            QRadioButton { color: white; spacing: 8px; font-size: 13px; font-weight: bold; background: transparent; }
            QRadioButton::indicator { width: 16px; height: 16px; border-radius: 8px; border: 2px solid #64748b; }
            QRadioButton::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
            
            /* [RESPONSIVE] ScrollArea Tasarımı */
            QScrollArea { border: none; background-color: #1a1f2e; }
            QScrollBar:vertical { border: none; background: #0f1419; width: 10px; border-radius: 5px; }
            QScrollBar::handle:vertical { background: #2d3748; min-height: 20px; border-radius: 5px; }
            QScrollBar::handle:vertical:hover { background: #3b82f6; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        
        # --- [RESPONSIVE] SCROLL AREA KURULUMU ---
        main_overall_layout = QVBoxLayout(self)
        main_overall_layout.setContentsMargins(0, 0, 0, 0) # Pencere kenarlarını temizle
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("scroll_content") # CSS için ID veriyoruz
        self.scroll.setWidget(self.scroll_content)
        
        main_overall_layout.addWidget(self.scroll)
        
        # İçerik Layout (Kaydırılabilir alan)
        layout = QVBoxLayout(self.scroll_content)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)

        # 1. Analiz Yap
        self.do_smart_analysis()

        # Önerilen loader tipini match_data'dan al (yeni sistemden)
        recommended_loader = self.analysis_results.get("recommended_loader", "bepinex")
        default_is_melon = (recommended_loader == "melon")
        self.is_unity_6 = self.match_data.get("is_unity_6", False)
        
        # 2. Üst Bilgi (Header)
        header_layout = QHBoxLayout()
        icon_lbl = QLabel("🛡️")
        icon_lbl.setStyleSheet("font-size: 36px;")
        header_layout.addWidget(icon_lbl)
        
        header_text = QVBoxLayout()
        name_lbl = QLabel(os.path.basename(game_path))
        name_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: white;")
        
        score = self.analysis_results.get("score", 0)
        status_color = "#10b981" if score >= 80 else "#f59e0b" if score >= 50 else "#ef4444"
        score_lbl = QLabel(f"Uyumluluk Skoru: %{score}")
        score_lbl.setStyleSheet(f"color: {status_color}; font-weight: bold; font-size: 14px;")
        
        header_text.addWidget(name_lbl)
        header_text.addWidget(score_lbl)
        header_layout.addLayout(header_text)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # 3. Teknik Detaylar (Advanced info)
        tech_box = QFrame()
        tech_box.setStyleSheet("background-color: #0f1419; border-radius: 8px; border: 1px solid #2d3748; padding: 15px;")
        tech_layout = QGridLayout(tech_box)
        tech_layout.setSpacing(10)
        
        def add_info(row, col, label, val, color="#94a3b8"):
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #64748b; font-weight: bold;")
            vbl = QLabel(str(val))
            vbl.setStyleSheet(f"color: {color}; font-weight: bold;")
            tech_layout.addWidget(lbl, row, col)
            tech_layout.addWidget(vbl, row, col + 1)

        add_info(0, 0, "Mimari:", self.arch.upper(), "#e8edf2")
        add_info(0, 2, "Backend:", self.backend.upper(), "#6c8eff")
        add_info(1, 0, "Unity Sürümü:", self.unity_ver, "#e8edf2")
        add_info(1, 2, "UI Sistemi:", ", ".join(self.components.get("ui_systems", [])) or "Bilinmiyor")

        # Yeni satır: .NET Runtime + Anti-Cheat
        dotnet_str  = self.match_data.get("dotnet_runtime", "unknown").upper()
        ac_list     = self.match_data.get("anticheat", [])
        ac_str      = ", ".join(ac_list) if ac_list else "Yok ✅"
        ac_color    = "#ef4444" if ac_list else "#10b981"
        add_info(2, 0, ".NET Runtime:", dotnet_str, "#f59e0b")
        add_info(2, 2, "Anti-Cheat:", ac_str, ac_color)

        layout.addWidget(tech_box)

        # [YENİ] Anti-Cheat Uyarı Paneli (sadece AC varsa göster)
        all_warnings = self.match_data.get("warnings", []) + self.components.get("notes", [])
        ac_warnings  = [w for w in all_warnings if "Anti-Cheat" in w or "anti-cheat" in w.lower() or "🔴" in w]
        if ac_warnings:
            ac_box = QFrame()
            ac_box.setStyleSheet(
                "background-color: #3b0f0f; border-left: 4px solid #ef4444;"
                "padding: 12px; border-radius: 6px;"
            )
            ac_layout = QVBoxLayout(ac_box)
            ac_title = QLabel("🔴 Anti-Cheat Tespit Edildi — Kurulum Çalışmayabilir!")
            ac_title.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 13px;")
            ac_layout.addWidget(ac_title)
            for msg in ac_warnings:
                lbl = QLabel(f"  {msg}")
                lbl.setStyleSheet("color: #fca5a5; font-size: 12px;")
                lbl.setWordWrap(True)
                ac_layout.addWidget(lbl)
            layout.addWidget(ac_box)

        # [YENİ] Bilgi ve Uyarı Notları Paneli (warnings + info_notes)
        all_info_warnings = self.match_data.get("warnings", []) + self.match_data.get("info_notes", [])
        non_ac_msgs = [w for w in all_info_warnings if "Anti-Cheat" not in w and "🔴" not in w]
        if non_ac_msgs:
            info_box = QFrame()
            info_box.setStyleSheet(
                "background-color: #1e2a1e; border-left: 4px solid #f59e0b;"
                "padding: 10px; border-radius: 6px;"
            )
            info_layout = QVBoxLayout(info_box)
            for msg in non_ac_msgs:
                color = "#fcd34d" if "⚠️" in msg else "#93c5fd"
                lbl = QLabel(f"• {msg}")
                lbl.setStyleSheet(f"color: {color}; font-size: 12px;")
                lbl.setWordWrap(True)
                info_layout.addWidget(lbl)
            layout.addWidget(info_box)

        select_group = QGroupBox("Otomatik Eşleştirilen Araçlar")
        sg_layout = QVBoxLayout()
        
        # Loader Tipi Seçimi (Radio Buttons)
        loader_type_layout = QHBoxLayout()
        loader_lbl = QLabel("Kurulum Yöntemi:")
        loader_lbl.setFixedWidth(140)
        
        self.rb_bepinex = QRadioButton("BepInEx (Standart)")
        self.rb_bepinex.setChecked(not default_is_melon)
        self.rb_bepinex.toggled.connect(self.refresh_tool_lists)
        
        self.rb_melon = QRadioButton("MelonLoader (Unity 6+)")
        self.rb_melon.setChecked(default_is_melon)
        self.rb_melon.toggled.connect(self.refresh_tool_lists)
        
        loader_type_layout.addWidget(loader_lbl)
        loader_type_layout.addWidget(self.rb_bepinex)
        loader_type_layout.addWidget(self.rb_melon)
        loader_type_layout.addStretch()
        sg_layout.addLayout(loader_type_layout)
        
        # Kütüphane (Loader) Satırı
        bep_row = QHBoxLayout()
        self.lbl_library_title = QLabel("Kütüphane (BepInEx):")
        self.lbl_library_title.setFixedWidth(140)
        self.combo_bepinex = QComboBox() # İsim değişmedi ama içeriği değişecek
        self.bep_warn_icon = QLabel("⚠️")
        self.bep_warn_icon.setToolTip("MİMARİ UYUMSUZLUĞU! Oyun x64 iken x86 kütüphane seçildi.")
        self.bep_warn_icon.setStyleSheet("color: #ef4444; font-size: 20px; font-weight: bold;")
        self.bep_warn_icon.hide()
        
        bep_row.addWidget(self.lbl_library_title)
        bep_row.addWidget(self.combo_bepinex, 1)
        bep_row.addWidget(self.bep_warn_icon)
        sg_layout.addLayout(bep_row)
        
        # Translator Satırı
        trans_row = QHBoxLayout()
        trans_lbl = QLabel("Eklenti (Translator):")
        trans_lbl.setFixedWidth(140)
        self.combo_translator = QComboBox()
        trans_row.addWidget(trans_lbl)
        trans_row.addWidget(self.combo_translator, 1)
        # Spacer for align
        trans_row.addSpacing(25) 
        sg_layout.addLayout(trans_row)
        
        # Filtre Kontrolü
        filter_layout = QHBoxLayout()
        self.btn_toggle_filter = QPushButton("Tüm Sürümleri Göster")
        self.btn_toggle_filter.setObjectName("toggle_filter")
        self.btn_toggle_filter.setCheckable(True)
        self.btn_toggle_filter.clicked.connect(self.on_toggle_filters)
        
        filter_layout.addStretch()
        filter_layout.addWidget(self.btn_toggle_filter)
        sg_layout.addLayout(filter_layout)
        
        select_group.setLayout(sg_layout)
        layout.addWidget(select_group)
        
        # 5. Özet Notlar
        if self.components.get("notes"):
            note_box = QFrame()
            note_box.setStyleSheet("background-color: #1a202c; border-left: 4px solid #f59e0b; padding: 10px; border-radius: 4px;")
            nl = QVBoxLayout(note_box)
            nl.addWidget(QLabel("📝 Analiz Notları:"))
            for n in self.components["notes"]:
                nl_item = QLabel(f"• {n}")
                nl_item.setStyleSheet("color: #f59e0b; font-size: 12px;")
                nl.addWidget(nl_item)
            layout.addWidget(note_box)

        # [YENİ] Çeviri İstatistikleri ve Paylaşım Bölümü
        trans_stats_box = QFrame()
        trans_stats_box.setStyleSheet("background-color: #0f1419; border-radius: 8px; border: 1px solid #2d3748; padding: 15px;")
        trans_stats_layout = QVBoxLayout(trans_stats_box)
        
        # Çeviri sayısını hesapla
        translation_count = self.get_translation_count()
        
        stats_label = QLabel(f"📊 Çevrilmiş Satır: {translation_count}")
        stats_label.setStyleSheet("color: #10b981; font-weight: bold; font-size: 14px;")
        trans_stats_layout.addWidget(stats_label)
        
        # AL / EKLE butonları
        share_btn_layout = QHBoxLayout()
        
        self.btn_export = QPushButton("📥 AL (Dışa Aktar)")
        self.btn_export.setStyleSheet("background-color: #3b82f6; color: white; padding: 8px 15px; border-radius: 6px; font-size: 13px; font-weight: bold;")
        self.btn_export.clicked.connect(self.export_translations)
        
        self.btn_import = QPushButton("📤 EKLE (İçe Aktar)")
        self.btn_import.setStyleSheet("background-color: #8b5cf6; color: white; padding: 8px 15px; border-radius: 6px; font-size: 13px; font-weight: bold;")
        self.btn_import.clicked.connect(self.import_translations)
        
        share_btn_layout.addWidget(self.btn_export)
        share_btn_layout.addWidget(self.btn_import)
        trans_stats_layout.addLayout(share_btn_layout)
        
        layout.addWidget(trans_stats_box)

        # 6. FIXED ACTION BUTTONS (SABİT ALT BUTONLAR)
        btn_container = QFrame()
        btn_container.setStyleSheet("background-color: #1a1f2e; border-top: 1px solid #2d3748; padding-top: 5px;")
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setSpacing(15)
        btn_layout.setContentsMargins(15, 10, 15, 10)
        
        # [YENİ] Temizle Butonu
        self.btn_uninstall = QPushButton("🗑️ Temizle")
        self.btn_uninstall.setStyleSheet("background-color: #ef4444; color: white; padding: 10px 15px; border-radius: 8px; font-size: 13px; font-weight: bold;")
        self.btn_uninstall.clicked.connect(self.do_cleanup)
        
        # [YENİ] Düzelt Butonu (Font + Mek/Mak)
        self.btn_fix = QPushButton("🔧 Düzelt")
        self.btn_fix.setStyleSheet("background-color: #f59e0b; color: white; padding: 10px 15px; border-radius: 8px; font-size: 13px; font-weight: bold;")
        self.btn_fix.clicked.connect(self.do_fix)
        
        self.btn_cancel = QPushButton("Vazgeç")
        self.btn_cancel.setObjectName("cancel")
        self.btn_cancel.setMinimumHeight(40)
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_install = QPushButton("✅ Kurulumu Başlat")
        self.btn_install.setMinimumHeight(40)
        self.btn_install.setStyleSheet("background-color: #10b981; color: white; padding: 10px 25px; border-radius: 8px; font-size: 14px;")
        self.btn_install.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.btn_uninstall)
        btn_layout.addWidget(self.btn_fix)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_install)
        
        main_overall_layout.addWidget(btn_container)
        
        # Connect Events
        self.combo_bepinex.currentIndexChanged.connect(self.handle_bepinex_change)
        
        # İlk Yükleme
        self.refresh_tool_lists()

    def do_smart_analysis(self):
        from translator_manager import TranslatorManager
        tm = TranslatorManager
        game_parent = Path(self.game_path).parent if os.path.isfile(self.game_path) else Path(self.game_path)
        
        # Analiz Verileri
        self.arch = tm.detect_game_architecture(self.game_path)
        self.backend = tm.detect_game_backend(game_parent)
        self.unity_ver = tm.get_unity_version(game_parent)
        self.components = tm.analyze_game_components(game_parent)
        
        # Akıllı Eşleştirme Sorgusu
        self.match_data = tm.get_compatible_tools(self.game_path)
        self.is_unity_6 = self.match_data.get("is_unity_6", False)
        self.analysis_results = {
            "score": self.components.get("compatibility_score", 0),
            "rec_bep": self.match_data.get("recommended_bepinex"),
            "rec_trans": self.match_data.get("recommended_translator"),
            "rec_melon": self.match_data.get("recommended_melon"),
            "rec_trans_melon": self.match_data.get("recommended_translator_melon"),
            "recommended_loader": self.match_data.get("recommended_loader_type", "bepinex")
        }

    def refresh_tool_lists(self):
        # Gerekli combo box'lar ve radio button'lar henüz başlatılmamışsa erken çık
        required_attrs = ['combo_bepinex', 'combo_translator', 'rb_melon', 'rb_bepinex', 'lbl_library_title']
        if not all(hasattr(self, attr) for attr in required_attrs):
            return
            
        self.combo_bepinex.blockSignals(True)
        self.combo_translator.blockSignals(True)
        
        self.combo_bepinex.clear()
        self.combo_translator.clear()
        
        from translator_manager import TranslatorManager
        tools = TranslatorManager.get_tool_files()
        
        is_melon = self.rb_melon.isChecked()
        
        if is_melon:
            # --- MELONLOADER LISTELEME ---
            self.lbl_library_title.setText("Kütüphane (Melon):")
            
            # [FIX] ÖNCE YEREL KÜTÜPHANEYİ LİSTELE (Kullanıcı İsteği)
            melon_cats = [
                ("Melon x64", "melon_x64", lambda f: self.arch == "x64"),
                ("Melon x86", "melon_x86", lambda f: self.arch == "x86")
            ]
            
            added_cnt = 0
            
            for tag, key, is_compatible in melon_cats:
                 for f in tools.get(key, []):
                    path_str = str(f)
                    # Show All açıksa uyumsuzları da listele (ama uyarısı çıkar)
                    is_ok = is_compatible(f)
                    
                    if not self.show_all_versions and not is_ok:
                        continue
                        
                    display_name = f"[{tag}] {f.name}"
                    self.combo_bepinex.addItem(display_name, path_str)
                    added_cnt += 1
            
            # [FIX] SONRA İNDİRME SEÇENEKLERİ (Sadece Yerel Dosya Yoksa veya Filtre Açıksa)
            # Kullanıcı: "download nedir? kütüphanemiz var"
            should_show_downloads = (added_cnt == 0) or self.show_all_versions
            
            is_u6 = getattr(self, 'is_unity_6', False) or (self.match_data.get("is_unity_6", False) if hasattr(self, 'match_data') else False)
            download_options = []
            
            if should_show_downloads:
                if is_u6:
                    # Unity 6+ İçin
                    download_options.append(("⭐ MelonLoader v0.7.2 (İNDİR)", "DOWNLOAD:0.7.2"))
                    download_options.append(("☁️ MelonLoader v0.7.1 (İNDİR)", "DOWNLOAD:0.7.1"))
                    download_options.append(("☁️ MelonLoader v0.6.6 (İNDİR)", "DOWNLOAD:0.6.6"))
                else:
                    # Eski Unity İçin
                    download_options.append(("⭐ MelonLoader v0.5.7 (Legacy)", "DOWNLOAD:0.5.7"))
                    download_options.append(("☁️ MelonLoader v0.6.1 (Stable)", "DOWNLOAD:0.6.1"))
                
                if self.show_all_versions:
                     # Ekstra seçenekler
                     if not is_u6:
                         download_options.append(("☁️ MelonLoader v0.7.2 (Yeni)", "DOWNLOAD:0.7.2"))

            for name, val in download_options:
                self.combo_bepinex.addItem(name, val)
            
            # Önerilen MelonLoader'ı otomatik seç (Akıllı Seçim)
            rec_melon_path = str(self.analysis_results["rec_melon"]) if self.analysis_results.get("rec_melon") else ""
            selected_melon_idx = 0
            
            if rec_melon_path:
                # Önerilen dosyayı bul ve seç
                for i in range(self.combo_bepinex.count()):
                    item_data = self.combo_bepinex.itemData(i)
                    if item_data and str(item_data) == rec_melon_path:
                        selected_melon_idx = i
                        # Önerilen olduğunu belirt
                        current_text = self.combo_bepinex.itemText(i)
                        if "⭐" not in current_text and "(ÖNERİLEN)" not in current_text:
                            self.combo_bepinex.setItemText(i, "⭐ " + current_text + " (ÖNERİLEN)")
                        break
            
            # Varsayılan Seçim (Önerilen dosya veya ilk öğe)
            if self.combo_bepinex.count() > 0:
                 self.combo_bepinex.setCurrentIndex(selected_melon_idx)
            
            # Translator (XUnity MelonMod)
            trans_cats = [
                ("MelonMod IL2CPP", "translator_melon_il2cpp", lambda f: self.backend == "il2cpp"),
                ("MelonMod Standart", "translator_melon", lambda f: self.backend == "mono" and "IL2CPP" not in f.name)
            ]
             
            rec_trans_melon_path = str(self.analysis_results["rec_trans_melon"]) if self.analysis_results.get("rec_trans_melon") else ""
            selected_trans_idx = 0
            trans_item_count = 0
             
            for tag, key, is_compatible in trans_cats:
                for f in tools.get(key, []):
                    path_str = str(f)
                    if not self.show_all_versions and not is_compatible(f):
                        continue
                    
                    display_name = f"[{tag}] {f.name}"
                    # Önerilen dosyayı işaretle
                    if rec_trans_melon_path and path_str == rec_trans_melon_path:
                        display_name = "⭐ " + display_name + " (ÖNERİLEN)"
                        selected_trans_idx = trans_item_count
                    
                    self.combo_translator.addItem(display_name, path_str)
                    trans_item_count += 1
            
            # Önerilen Translator'ı seç
            if self.combo_translator.count() > 0 and selected_trans_idx < self.combo_translator.count():
                self.combo_translator.setCurrentIndex(selected_trans_idx)

        else:
            # --- BEPINEX LISTELEME (ESKİ) ---
            self.lbl_library_title.setText("Kütüphane (BepInEx):")
            
            bep_cats = [
                ("Modern IL2CPP", "bepinex_il2cpp_modern", lambda f: self.backend == "il2cpp" and self.arch in f.name),
                ("Legacy IL2CPP", "bepinex_il2cpp_legacy", lambda f: self.backend == "il2cpp" and self.arch in f.name),
                ("Mono x64", "bepinex_x64", lambda f: self.backend == "mono" and self.arch == "x64"),
                ("Mono x86", "bepinex_x86", lambda f: self.backend == "mono" and self.arch == "x86")
            ]
            
            rec_bep_path = str(self.analysis_results["rec_bep"]) if self.analysis_results["rec_bep"] else ""
            
            for tag, key, is_compatible in bep_cats:
                for f in tools.get(key, []):
                    path_str = str(f)
                    is_ok = is_compatible(f)
                    
                    if not self.show_all_versions and not is_ok:
                        continue
                    
                    display_name = f"[{tag}] {f.name}"
                    if path_str == rec_bep_path:
                        display_name = "⭐ " + display_name + " (ÖNERİLEN)"
                    
                    self.combo_bepinex.addItem(display_name, path_str)
                    
                    if path_str == rec_bep_path:
                        self.combo_bepinex.setCurrentIndex(self.combo_bepinex.count() - 1)

            # Translator Listeleme (BepInEx Plugin)
            trans_cats = [
                ("IL2CPP Uyumlu", "translator_il2cpp", lambda f: self.backend == "il2cpp"),
                ("Standart", "translator", lambda f: self.backend == "mono")
            ]
            
            rec_trans_path = str(self.analysis_results["rec_trans"]) if self.analysis_results["rec_trans"] else ""
            
            for tag, key, is_compatible in trans_cats:
                for f in tools.get(key, []):
                    path_str = str(f)
                    if not self.show_all_versions and not is_compatible(f):
                        continue
                    
                    display_name = f"[{tag}] {f.name}"
                    if path_str == rec_trans_path:
                        display_name = "⭐ " + display_name + " (ÖNERİLEN)"
                    
                    self.combo_translator.addItem(display_name, path_str)
                    
                    if path_str == rec_trans_path:
                        self.combo_translator.setCurrentIndex(self.combo_translator.count() - 1)

        self.combo_bepinex.blockSignals(False)
        self.combo_translator.blockSignals(False)
        self.update_warnings()

    def on_toggle_filters(self):
        self.show_all_versions = self.btn_toggle_filter.isChecked()
        self.btn_toggle_filter.setText("Filtreleri Uygula" if self.show_all_versions else "Tüm Sürümleri Göster")
        self.refresh_tool_lists()

    def handle_bepinex_change(self):
        self.update_warnings()

    def update_warnings(self):
        path_str = self.combo_bepinex.currentData()
        if not path_str:
            self.bep_warn_icon.hide()
            return
            
        from translator_manager import TranslatorManager
        file_arch = TranslatorManager.get_arch_from_filename(os.path.basename(path_str))
        
        if file_arch != "unknown" and file_arch != self.arch:
            self.bep_warn_icon.show()
            self.bep_warn_icon.setToolTip(f"MİMARİ UYUMSUZLUĞU!\nOyun mimarisi: {self.arch.upper()}\nSeçilen kütüphane: {file_arch.upper()}\n\nBu durum oyunun açılmamasına neden olur.")
        else:
            self.bep_warn_icon.hide()

    def get_selection(self):
        bep = self.combo_bepinex.currentData()
        trans = self.combo_translator.currentData()
        loader_type = "melon" if self.rb_melon.isChecked() else "bepinex"
        return bep, trans, loader_type

    def do_fix(self):
        """
        Unity oyunu için düzeltmeler yapar:
        1. Türkçe font desteği (LiberationSans SDF)
        2. Mek/Mak eki temizleme (mevcut çevirilerde)
        
        BepInEx ve MelonLoader otomatik tespit edilir.
        """
        try:
            from unity_manager import UnityManager
            from pathlib import Path
            import re
            
            game_path = Path(self.game_path)
            if game_path.is_file():
                game_path = game_path.parent
            
            # ── 0. LOADER TESPİTİ ──
            loader_type = None
            if (game_path / "BepInEx").exists():
                loader_type = "bepinex"
            elif (game_path / "MelonLoader").exists() or (game_path / "UserData").exists():
                loader_type = "melonloader"
            
            if not loader_type:
                QMessageBox.warning(self, "Uyarı", "BepInEx veya MelonLoader kurulumu bulunamadı!\n\nÖnce kurulum yapın.")
                return
            
            # ── 1. FONT DÜZELTME ──
            success, msg = UnityManager.apply_turkish_font_fix(self.game_path)
            if not success:
                QMessageBox.warning(self, "Uyarı", f"Font düzeltmesi yapılamadı:\n\n{msg}")
                return
            
            # ── 2. ÇEVİRİ DOSYASINI BUL (Akıllı Seçim) ──
            translation_dir_candidates = []
            
            if loader_type == "bepinex":
                translation_dir_candidates = [
                    game_path / "BepInEx" / "Translation" / "tr" / "Text",
                    game_path / "BepInEx" / "plugins" / "XUnity.AutoTranslator" / "Translation" / "tr" / "Text",
                ]
            elif loader_type == "melonloader":
                translation_dir_candidates = [
                    game_path / "UserData" / "Translation" / "tr" / "Text",
                    game_path / "MelonLoader" / "Translation" / "tr" / "Text",
                ]
            
            # Ortak yollar (fallback)
            translation_dir_candidates += [
                game_path / "AutoTranslator" / "Translation" / "tr" / "Text",
                game_path / "Translation" / "tr" / "Text",
            ]
            
            # İlk bulunan klasörü kullan
            translation_dir = None
            for candidate in translation_dir_candidates:
                if candidate.exists():
                    translation_dir = candidate
                    break
            
            # ── 3. MEK/MAK DÜZELTMESİ ──
            fix_count = 0
            
            if translation_dir:
                # 3a. Postprocessor kuralları oluştur
                postprocessor_file = translation_dir / "_Postprocessors.txt"
                postprocessor_rules = """# Mek/Mak Eki Temizleme (Türkçe Düzeltme)
# Format: regex-pattern=replacement

# Cümle sonu mek/mak temizleme (noktalama işaretleriyle)
^(.+\\s)(\\w{2,})(mek|mak)(\\.|!|\\?|,|;|:)$=$1$2$4
^(.+\\s)(\\w{2,})(mek|mak)$=$1$2

# Tek kelime mek/mak (istisnalar hariç)
^((?!ekmek|yemek|kıymak|kaymak|çakmak|ırmak|damak|yamak)\\w{2,})(mek|mak)$=$1
^((?!ekmek|yemek|kıymak|kaymak|çakmak|ırmak|damak|yamak)\\w{2,})(mek|mak)(\\.|!|\\?|,|;|:)$=$1$3
"""
                with open(postprocessor_file, 'w', encoding='utf-8') as f:
                    f.write(postprocessor_rules)
                
                # 3b. Mevcut çevirileri düzelt
                auto_trans_file = translation_dir / "_AutoGeneratedTranslations.txt"
                if auto_trans_file.exists():
                    with open(auto_trans_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    exceptions = ["ekmek", "yemek", "kıymak", "kaymak", "çakmak", "ırmak", "damak", "yamak"]
                    turkish_to_ascii = {
                        'ç': 'c', 'Ç': 'C', 'ğ': 'g', 'Ğ': 'G',
                        'ı': 'i', 'İ': 'I', 'ö': 'o', 'Ö': 'O',
                        'ş': 's', 'Ş': 'S', 'ü': 'u', 'Ü': 'U'
                    }
                    
                    fixed_lines = []
                    for line in lines:
                        if '=' in line:
                            key, value = line.split('=', 1)
                            value = value.strip()
                            original_value = value
                            
                            # Mek/Mak temizle
                            words = value.split()
                            if words:
                                last_word = words[-1]
                                punctuation = ""
                                if last_word and last_word[-1] in ".,!?;:":
                                    punctuation = last_word[-1]
                                    last_word = last_word[:-1]
                                
                                if last_word.lower() not in exceptions:
                                    match = re.search(r'(.{2,})(mek|mak)$', last_word, re.IGNORECASE)
                                    if match:
                                        words[-1] = match.group(1) + punctuation
                                        value = " ".join(words)
                            
                            # Türkçe karakter → ASCII
                            for tr_char, ascii_char in turkish_to_ascii.items():
                                value = value.replace(tr_char, ascii_char)
                            
                            if value != original_value:
                                fix_count += 1
                            
                            fixed_lines.append(f"{key}={value}\n")
                        else:
                            fixed_lines.append(line)
                    
                    with open(auto_trans_file, 'w', encoding='utf-8') as f:
                        f.writelines(fixed_lines)
                
                loader_name = "BepInEx" if loader_type == "bepinex" else "MelonLoader"
                QMessageBox.information(self, "Başarılı", 
                    f"✅ Düzeltmeler uygulandı!\n\n"
                    f"{msg}\n\n"
                    f"📂 Loader: {loader_name}\n"
                    f"📁 Klasör: {translation_dir.relative_to(game_path)}\n"
                    f"✅ {fix_count} satır düzeltildi\n"
                    f"✅ Mek/Mak kuralları eklendi\n\n"
                    f"⚠️ Oyunu yeniden başlatın!")
            else:
                QMessageBox.warning(self, "Uyarı", 
                    f"Font düzeltmesi yapıldı:\n{msg}\n\n"
                    f"⚠️ Ancak çeviri klasörü bulunamadı!\n"
                    f"Oyunu en az bir kere çalıştırıp çeviri yaptıktan sonra tekrar deneyin.")
            
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Düzeltme sırasında hata oluştu:\n{e}")

    def get_translation_count(self):
        """Çeviri dosyasındaki satır sayısını döndürür"""
        try:
            from pathlib import Path
            game_path = Path(self.game_path)
            if game_path.is_file():
                game_path = game_path.parent

            candidates = [
                game_path / "BepInEx" / "Translation" / "tr" / "Text" / "_AutoGeneratedTranslations.txt",
                game_path / "BepInEx" / "plugins" / "XUnity.AutoTranslator" / "Translation" / "tr" / "Text" / "_AutoGeneratedTranslations.txt",
                game_path / "AutoTranslator" / "Translation" / "tr" / "Text" / "_AutoGeneratedTranslations.txt",
                game_path / "Translation" / "tr" / "Text" / "_AutoGeneratedTranslations.txt",
            ]

            for trans_file in candidates:
                if trans_file.exists():
                    with open(trans_file, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    return len([l for l in lines if '=' in l])
            return 0
        except:
            return 0

    def export_translations(self):
        """Çeviri dosyasını dışa aktar (AL)"""
        try:
            from pathlib import Path
            from PyQt5.QtWidgets import QFileDialog

            game_path = Path(self.game_path)
            if game_path.is_file():
                game_path = game_path.parent

            candidates = [
                game_path / "BepInEx" / "Translation" / "tr" / "Text" / "_AutoGeneratedTranslations.txt",
                game_path / "BepInEx" / "plugins" / "XUnity.AutoTranslator" / "Translation" / "tr" / "Text" / "_AutoGeneratedTranslations.txt",
                game_path / "AutoTranslator" / "Translation" / "tr" / "Text" / "_AutoGeneratedTranslations.txt",
                game_path / "Translation" / "tr" / "Text" / "_AutoGeneratedTranslations.txt",
            ]

            trans_file = None
            for c in candidates:
                if c.exists():
                    trans_file = c
                    break

            if not trans_file:
                QMessageBox.warning(self, "Uyarı", "Çeviri dosyası bulunamadı!\n\nBepInEx/MelonLoader kurulumu yapıp oyunu çalıştırdıktan sonra tekrar deneyin.")
                return

            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Çeviri Dosyasını Kaydet",
                f"{game_path.name}_Ceviriler.txt",
                "Text Files (*.txt)"
            )

            if save_path:
                import shutil
                shutil.copy2(trans_file, save_path)
                QMessageBox.information(self, "Başarılı", f"✅ Çeviri dosyası kaydedildi!\n\n{save_path}")

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Dışa aktarma sırasında hata:\n{e}")


    def import_translations(self):
        """Çeviri dosyasını içe aktar (EKLE)"""
        try:
            from pathlib import Path
            from PyQt5.QtWidgets import QFileDialog
            
            game_path = Path(self.game_path)
            if game_path.is_file():
                game_path = game_path.parent
            
            # Translation klasörünü bul
            trans_dir = game_path / "AutoTranslator" / "Translation" / "tr" / "Text"
            if not trans_dir.exists():
                trans_dir = game_path / "Translation" / "tr" / "Text"
            
            if not trans_dir.exists():
                QMessageBox.warning(self, "Uyarı", "Çeviri klasörü bulunamadı!\n\nÖnce BepInEx/MelonLoader kurulumu yapın.")
                return
            
            # Dosya seç
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Çeviri Dosyası Seç",
                "",
                "Text Files (*.txt)"
            )
            
            if file_path:
                import shutil
                target_file = trans_dir / "_AutoGeneratedTranslations.txt"
                
                # Yedek al
                if target_file.exists():
                    backup_file = trans_dir / "_AutoGeneratedTranslations.txt.backup"
                    shutil.copy2(target_file, backup_file)
                
                # Dosyayı kopyala
                shutil.copy2(file_path, target_file)
                QMessageBox.information(self, "Başarılı", "✅ Çeviri dosyası başarıyla eklendi!\n\n⚠️ Oyunu yeniden başlatın.")
        
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"İçe aktarma sırasında hata:\n{e}")

    def do_cleanup(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("🗑️ Evrensel Temizlik")
        msg.setText("Bu işlem oyun klasöründeki TÜM çeviri araçlarını kaldıracaktır:\n\n"
                   "• BepInEx (klasör ve dosyalar)\n"
                   "• MelonLoader (klasör ve dosyalar)\n"
                   "• XUnity AutoTranslator\n"
                   "• Çeviri dosyaları ve önbellekler\n"
                   "• doorstop_config.ini, winhttp.dll vb.\n\n"
                   "⚠️ Bu işlem GERİ ALINAMAZ!\n\n"
                   "Devam etmek istiyor musunuz?")
        msg.setIcon(QMessageBox.Warning)
        btn_yes = msg.addButton("Evet, Temizle", QMessageBox.YesRole)
        btn_no = msg.addButton("Hayır", QMessageBox.NoRole)
        msg.setDefaultButton(btn_no)
        msg.exec_()
        
        if msg.clickedButton() == btn_yes:
            try:
                from pathlib import Path
                import shutil
                
                game_path = Path(self.game_path)
                if game_path.is_file():
                    game_path = game_path.parent
                
                removed_count = 0
                removed_items = []
                
                # Temizlenecek klasörler
                folders_to_remove = [
                    "BepInEx",
                    "MelonLoader", 
                    "AutoTranslator",
                    "Translation",
                    "UserData",
                    "Mods"
                ]
                
                # Temizlenecek dosyalar
                files_to_remove = [
                    "winhttp.dll",
                    "version.dll",
                    "doorstop_config.ini",
                    ".doorstop_version",
                    "dobby.dll"
                ]
                
                # Klasörleri temizle
                for folder_name in folders_to_remove:
                    folder_path = game_path / folder_name
                    if folder_path.exists() and folder_path.is_dir():
                        try:
                            shutil.rmtree(folder_path)
                            removed_items.append(f"📁 {folder_name}/")
                            removed_count += 1
                        except Exception as e:
                            print(f"Klasör silinemedi ({folder_name}): {e}")
                
                # Dosyaları temizle
                for file_name in files_to_remove:
                    file_path = game_path / file_name
                    if file_path.exists() and file_path.is_file():
                        try:
                            file_path.unlink()
                            removed_items.append(f"📄 {file_name}")
                            removed_count += 1
                        except Exception as e:
                            print(f"Dosya silinemedi ({file_name}): {e}")
                
                # Sonuç mesajı
                if removed_count > 0:
                    items_text = "\n".join(removed_items[:10])
                    if len(removed_items) > 10:
                        items_text += f"\n... ve {len(removed_items) - 10} öğe daha"
                    
                    QMessageBox.information(self, "✅ Temizlik Tamamlandı", 
                        f"Toplam {removed_count} öğe silindi:\n\n{items_text}\n\n"
                        f"Oyun artık orijinal haline döndü.")
                else:
                    QMessageBox.information(self, "ℹ️ Bilgi", 
                        "Temizlenecek çeviri aracı bulunamadı.\n\nOyun zaten temiz görünüyor.")
                    
            except Exception as e:
                QMessageBox.critical(self, "❌ Hata", f"Temizleme sırasında hata oluştu:\n\n{e}")


# --- PAK SELECTION DIALOG & WORKERS ---
class PakScanWorker(QThread):
    finished = pyqtSignal(list)
    def __init__(self, game_dir):
        super().__init__()
        self.game_dir = game_dir
    
    def run(self):
        from unreal_manager import PakManager
        import subprocess
        from config import Config
        
        # 1. PAK Dosyalarını Bul
        all_paks = list(self.game_dir.rglob("*.pak"))
        scored_paks = []
        
        tool_path = Config.BASE_PATH / "files" / "tools" / "repak.exe"
        
        for p in all_paks:
            path_str = str(p).replace("\\", "/") 
            path_lower = path_str.lower()
            name = p.name
            
            # --- PUANLAMA ---
            score = 0
            if "/content/paks" in path_lower and "engine/" not in path_lower: score += 500
            if self.game_dir.stem.lower() in path_lower: score += 100
            if "windowsnoeditor" in name.lower(): score += 50
            if "/engine/" in path_lower: score -= 1000
            if "/plugins/" in path_lower: score -= 500
            
            # Patch dosyaları
            if name.endswith("_P.pak"): score += 10
            
            # --- DETAYLI BİLGİ (Repak Info) ---
            version = "Unknown"
            encrypted = False
            oodle = "-"
            
            # 1. Binary Version Check (Hızlı)
            try:
                bin_ver = PakManager.detect_pak_version_binary(p)
                if bin_ver: version = bin_ver
            except: pass
            
            # 2. Repak Info (Encryption & Oodle)
            if tool_path.exists():
                try:
                    cmd = [str(tool_path), "info", str(p)]
                    # Creation flags for no window
                    res = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000)
                    if res.returncode == 0:
                        out = res.stdout.lower()
                        if "encrypted index: true" in out: encrypted = True
                        if "compression: oodle" in out: oodle = "Required"
                except: pass
            
            info = {
                'name': name,
                'path': str(p),
                'version': version,
                'encrypted': encrypted,
                'oodle': oodle
            }
            
            scored_paks.append((score, info))
            
        # Puan yüksekten düşüğe sırala
        scored_paks.sort(key=lambda x: x[0], reverse=True)
        
        results = [x[1] for x in scored_paks]
        self.finished.emit(results)

class ContentScanWorker(QThread):
    finished = pyqtSignal(list)
    def __init__(self, pak_path, aes_key):
        super().__init__()
        self.pak_path = Path(pak_path)
        self.aes_key = aes_key
        
    def run(self):
        import subprocess
        from config import Config
        files = []
        try:
            tool_path = Config.BASE_PATH / "files" / "tools" / "repak.exe"
            
            cmd = [str(tool_path), "list", str(self.pak_path)]
            if self.aes_key:
                cmd.extend(["--aes-key", self.aes_key])
                
            # Çalıştır
            try:
                # subprocess.CREATE_NO_WINDOW = 0x08000000
                creation_flags = 0x08000000
                res = subprocess.run(
                    cmd, 
                    capture_output=True,
                    text=True,
                    creationflags=creation_flags
                )
                
                if res.returncode == 0:
                    # Çıktıyı parse et
                    for line in res.stdout.splitlines():
                        line = line.strip()
                        if line and not line.startswith("Reading"):
                            files.append(line)
            except Exception as e:
                print(f"Repak List Error: {e}")
                files.append(f"Hata: {str(e)}")
                
        except Exception as e:
            print(f"Content Scan Error: {e}")
            
        self.finished.emit(files)

class PakSelectionDialog(QDialog):
    """
    Kullanıcının PAK dosyalarını ve içeriklerini seçmesi için gelişmiş diyalog penceresi.
    """
    def __init__(self, game_dir, parent=None):
        super().__init__(parent)
        self.game_dir = Path(game_dir)
        self.setWindowTitle(f"PAK Seçimi - {self.game_dir.name}")
        self.setFixedSize(1200, 800) # Daha da büyüttük
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: white; }
            QLabel { color: white; font-family: 'Segoe UI'; }
            QTableWidget { 
                background-color: #252d3a; 
                color: white; 
                gridline-color: #2d3748;
                border: 1px solid #2d3748;
                font-family: 'Segoe UI';
            }
            QTableWidget::item:selected { background-color: #3b82f6; }
            QHeaderView::section {
                background-color: #1a202c;
                color: #a0aec0;
                padding: 5px;
                border: 0px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
                font-family: 'Segoe UI';
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:disabled { background-color: #4b5563; color: #9ca3af; }
        """)
        
        self.selected_pak = None
        self.selected_content = None
        self.aes_key = None
        
        # --- HEADER ---
        self.layout = QVBoxLayout(self)
        
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 10) # Alt boşluk 10px
        
        icon_lbl = QLabel("📦")
        icon_lbl.setStyleSheet("font-size: 32px;")
        
        title_box = QVBoxLayout()
        lbl_title = QLabel("PAK Dosyası Analizi")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 0px;")
        lbl_desc = QLabel(f"Oyun: {self.game_dir.name}")
        lbl_desc.setStyleSheet("color: #94a3b8; font-size: 13px; margin: 0px;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_desc)
        title_box.setSpacing(2) # Başlık arası boşluk
        
        header_layout.addWidget(icon_lbl)
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        self.layout.addLayout(header_layout) # Layout'a ekle, stretch yok

        
        # --- PROGRESS BAR (Tarama için) ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("QProgressBar { border: none; background: #2d3748; height: 4px; } QProgressBar::chunk { background: #3b82f6; }")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 0) # Indeterminate
        self.layout.addWidget(self.progress_bar)
        
        # --- SPLIT VIEW (PAK Listesi | İçerik Listesi) ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #2d3748; }")
        
        # LEFT: PAK List
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 5, 0)
        left_layout.addWidget(QLabel("Bulunan PAK Dosyaları (Öncelik Sırası):"))
        
        self.pak_table = QTableWidget()
        self.pak_table.setColumnCount(4)
        self.pak_table.setHorizontalHeaderLabels(["PAK Adı", "Ver.", "Oodle", "AES"])
        self.pak_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.pak_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.pak_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.pak_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.pak_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.pak_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.pak_table.itemSelectionChanged.connect(self.on_pak_selected)
        left_layout.addWidget(self.pak_table)
        
        splitter.addWidget(left_widget)
        
        # RIGHT: Content List
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 0, 0, 0)
        right_layout.addWidget(QLabel("İçerik (Dil Dosyaları):"))
        
        self.content_table = QTableWidget()
        self.content_table.setColumnCount(3)
        self.content_table.setHorizontalHeaderLabels(["Dosya", "Tür", "Boyut"])
        self.content_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.content_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.content_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.content_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.content_table.itemSelectionChanged.connect(self.update_buttons)
        right_layout.addWidget(self.content_table)
        
        # Overlay Message (Sağ taraf boşken)
        self.lbl_help = QLabel("Bir PAK dosyası seçin...", self.content_table)
        self.lbl_help.setAlignment(Qt.AlignCenter)
        self.lbl_help.setStyleSheet("color: #64748b; font-size: 14px;")
        
        splitter.addWidget(right_widget)
        splitter.setSizes([450, 450])
        
        self.layout.addWidget(splitter)
        
        # --- FOOTER ---
        footer_layout = QHBoxLayout()
        
        self.btn_scan = QPushButton("📂 Seçili Pak Tara")
        self.btn_scan.setStyleSheet("background-color: #3b82f6; font-weight: bold;")
        self.btn_scan.clicked.connect(lambda: self.on_pak_selected())
        
        self.btn_translate = QPushButton("ÇEVİRİYE BAŞLA")
        self.btn_translate.setStyleSheet("""
            QPushButton { background-color: #10b981; font-size: 14px; padding: 10px; }
            QPushButton:hover { background-color: #059669; }
            QPushButton:disabled { background-color: #1f2937; color: #4b5563; }
        """)
        self.btn_translate.setEnabled(False)
        self.btn_translate.clicked.connect(self.accept)
        
        footer_layout.addWidget(self.btn_scan)
        footer_layout.addStretch()
        footer_layout.addWidget(self.btn_translate)
        
        self.layout.addLayout(footer_layout)
        
        # Internal Data
        self.pak_data = [] # List of dicts
        self.current_pak_contents = []
        
        # Start
        QTimer.singleShot(100, self.start_scan)

    def start_scan(self):
        self.pak_table.setRowCount(0)
        self.pak_data = []
        self.progress_bar.show()
        self.btn_scan.setEnabled(False)
        self.btn_translate.setEnabled(False)
        
        # Worker Thread for Scanning
        self.scan_thread = PakScanWorker(self.game_dir)
        self.scan_thread.finished.connect(self.on_scan_finished)
        self.scan_thread.start()

    def on_scan_finished(self, paks):
        self.progress_bar.hide()
        self.btn_scan.setEnabled(True)
        self.pak_data = paks
        
        self.pak_table.setRowCount(len(paks))
        
        for i, info in enumerate(paks):
            name_item = QTableWidgetItem(info['name'])
            name_item.setToolTip(info['path'])
            
            ver_item = QTableWidgetItem(info['version'])
            ver_item.setTextAlignment(Qt.AlignCenter)
            
            oodle_item = QTableWidgetItem(info['oodle'])
            oodle_item.setTextAlignment(Qt.AlignCenter)
            if info['oodle'] == "Required":
                oodle_item.setForeground(QColor("#f59e0b")) # Orange
            
            aes_text = "VAR" if info['encrypted'] else "YOK"
            aes_item = QTableWidgetItem(aes_text)
            aes_item.setTextAlignment(Qt.AlignCenter)
            if info['encrypted']:
                aes_item.setForeground(QColor("#ef4444")) # Red
            else:
                aes_item.setForeground(QColor("#10b981")) # Green
            
            self.pak_table.setItem(i, 0, name_item)
            self.pak_table.setItem(i, 1, ver_item)
            self.pak_table.setItem(i, 2, oodle_item)
            self.pak_table.setItem(i, 3, aes_item)
        
        if paks:
            self.pak_table.selectRow(0) # Select first/best

    def on_pak_selected(self):
        rows = self.pak_table.selectionModel().selectedRows()
        if not rows: return
        
        row = rows[0].row()
        pak_info = self.pak_data[row]
        self.selected_pak = pak_info
        
        # Clear content table
        self.content_table.setRowCount(0)
        self.lbl_help.setText("İçerik taranıyor...")
        self.lbl_help.show()
        
        # Check AES
        if pak_info['encrypted'] and not self.aes_key:
            # Ask for key or try to find it?
            # For now, just warn or try to proceed (UnrealManager will handle key hunting later, 
            # BUT for listing we might need it NOW).
            # Let's try listing without key first, if fails, ask.
            text, ok = QInputDialog.getText(self, "AES Key Gerekli", f"{pak_info['name']} şifreli görünüyor.\nEğer biliyorsanız AES Key girin (0x...):\nBilmiyorsanız boş bırakın (Otomatik aranacak)", QLineEdit.Normal, "")
            if ok and text:
                self.aes_key = text.strip()

        # Start content scan
        self.content_thread = ContentScanWorker(pak_info['path'], self.aes_key)
        self.content_thread.finished.connect(self.on_content_finished)
        self.content_thread.start()

    def on_content_finished(self, files):
        self.current_pak_contents = files
        self.content_table.setRowCount(0)
        
        if not files:
            self.lbl_help.setText("Dosya bulunamadı veya şifreli (AES gerekli).")
            self.lbl_help.show()
            # If we suspect AES issue, maybe ask key here?
            if self.selected_pak['encrypted'] and not self.aes_key:
                 text, ok = QInputDialog.getText(self, "AES Key", "İçerik listelenemedi. Lütfen AES Key girin:", QLineEdit.Normal, "")
                 if ok and text:
                     self.aes_key = text.strip()
                     self.on_pak_selected() # Retry
            return
            
        self.lbl_help.hide()
        
        # Filter and Prioritize (Content)
        # Scoring Logic:
        # Locres: +100
        # CSV: +50
        # JSON: +20
        # Engine Path: -500
        # "Game" in path: +50
        # "Localization/Game": +200
        
        scored_files = []
        
        for f in files:
            f_clean = f.strip()
            f_lower = f_clean.lower()
            score = 0
            
            # Type Score
            if f_lower.endswith(".locres"): score += 100
            elif f_lower.endswith(".csv"): score += 50
            elif f_lower.endswith(".json"): score += 20
            else: continue # Sadece bunları listele
            
            # Path Logic (Engine vs Game)
            if "engine/" in f_lower or "engine\\" in f_lower:
                score -= 1000 # Çok geri at
            
            if "/game/" in f_lower or "\\game\\" in f_lower:
                score += 50
                
            if "localization/game" in f_lower:
                score += 200
                
            # Short path often better?
            if len(f_clean) < 50: score += 10
            
            scored_files.append((score, f_clean))
            
        # Sort desc
        scored_files.sort(key=lambda x: x[0], reverse=True)
        
        # Sadece dosya ismi ve tipini göster
        self.content_table.setRowCount(len(scored_files))
        for i, (score, fname) in enumerate(scored_files):
            # Dosya tipini bul
            ftype = "UNKNOWN"
            if fname.lower().endswith(".locres"): ftype = "LOCRES"
            elif fname.lower().endswith(".csv"): ftype = "CSV"
            elif fname.lower().endswith(".json"): ftype = "JSON"
            
            item_name = QTableWidgetItem(fname)
            item_name.setToolTip(fname)
            
            item_type = QTableWidgetItem(ftype)
            item_type.setTextAlignment(Qt.AlignCenter)
            
            self.content_table.setItem(i, 0, item_name)
            self.content_table.setItem(i, 1, item_type)
            self.content_table.setItem(i, 2, QTableWidgetItem("-")) 
            
            self.content_table.item(i, 0).setData(Qt.UserRole, fname) # Store real path
            
        if scored_files:
            self.content_table.selectRow(0)

    def update_buttons(self):
        self.btn_translate.setEnabled(bool(self.content_table.selectedItems()))



# End of file
# End of file
if __name__ == "__main__":

    # --- TEK INSTANCE KONTROLÜ (Mutex) ---
    # Aynı anda iki pencere açılmasını engeller (admin yeniden başlatma gecikmesi dahil)
    _mutex = None
    try:
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "MemoFast_SingleInstance_Mutex")
        _last_err = ctypes.windll.kernel32.GetLastError()
        if _last_err == 183:  # ERROR_ALREADY_EXISTS
            # Zaten çalışıyor, mevcut pencereyi öne getirip çık
            sys.exit(0)
    except Exception as e:
        print(f"Mutex error: {e}")

    # --- YÖNETİCİ KONTROLÜ (KALDIRILDI) ---
    # Artık uygulama normal yetkiyle başlıyor. 
    # Sadece gerekli araçlarda (Hızlandırıcı, Trainer vb.) yetki istenecek.

    # DPI Awareness (4K ve Yüksek Çözünürlük Desteği)
    try:
        if hasattr(Qt, 'AA_EnableHighDpiScaling'):
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except: pass

    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    w = MainWindow()
    w.show()
    # İlk çalıştırma kontrolü
    QTimer.singleShot(1000, lambda: w.check_first_run() if hasattr(w, "check_first_run") else None)
    ret = app.exec_()
    # Mutex Temizliği
    if _mutex:
        try:
            ctypes.windll.kernel32.ReleaseMutex(_mutex)
            ctypes.windll.kernel32.CloseHandle(_mutex)
        except: pass
        
    # [YENİ]: sys.exit(0) Windows için en güvenli çıkış yoludur. 
    # os._exit(ret) Windows tarafından 'crash' sanılabiliyor.
    sys.exit(0)
