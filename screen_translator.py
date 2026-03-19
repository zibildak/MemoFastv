import sys
import os
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import pytesseract
from PIL import ImageGrab
from deep_translator import GoogleTranslator
from pynput import keyboard
import threading
try:
    import easyocr
except ImportError:
    pass
try:
    import numpy as np
    import cv2
except ImportError:
    pass
import re
import asyncio
import io
import edge_tts

# WinRT Windows OCR (Translumo Engine)
try:
    from winrt.windows.storage.streams import InMemoryRandomAccessStream, DataWriter
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.globalization import Language
    winrt_available = True
except ImportError:
    winrt_available = False
import pygame
import tempfile
import time
import ctypes
from difflib import SequenceMatcher

# Varsayılan İstisnalar (Dosya okunamazsa)
DEFAULT_EXCEPTIONS = {
    "ekmek", "yemek", "parmak", "çakmak", "kaymak", 
    "damak", "ırmak", "yamak", "kıymak", "yumak"
}

# Tesseract yolu
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSSIBLE_TESSERACT_PATHS = [
    os.path.join(BASE_DIR, "tesseract", "tesseract.exe"),
    os.path.join(os.getcwd(), "tesseract", "tesseract.exe"),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    os.path.join(os.getenv("LOCALAPPDATA", ""), "Tesseract-OCR", "tesseract.exe")
]

tesseract_cmd = None
for path in POSSIBLE_TESSERACT_PATHS:
    if os.path.exists(path):
        tesseract_cmd = path
        break

if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    tessdata_path = os.path.join(os.path.dirname(tesseract_cmd), "tessdata")
    if os.path.exists(tessdata_path):
        os.environ["TESSDATA_PREFIX"] = tessdata_path



class TranslationResultWindow(QWidget):
    """Premium, modern ve animasyonlu çeviri sonuç penceresi"""
    def __init__(self, text, bbox=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.bbox_pos = bbox # Expected format: (x, y, w, h)
        
        self.setup_ui(text)
        
        # Win32 TopMost forcing
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 3)
        except: pass
        
    def setup_ui(self, text):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        self.container = QFrame()
        self.container.setObjectName("ResultContainer")
        self.container.setStyleSheet("""
            #ResultContainer {
                background-color: rgba(26, 31, 46, 245);
                border: 1px solid rgba(16, 185, 129, 150);
                border-radius: 15px;
            }
        """)
        
        inner_layout = QVBoxLayout(self.container)
        inner_layout.setContentsMargins(15, 10, 15, 15)
        
        # Header (Close Button Only)
        header = QHBoxLayout()
        header.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet("""
            QPushButton { 
                background: transparent; 
                color: #94a3b8; 
                font-weight: bold; 
                font-size: 14px; 
                border-radius: 12px;
            } 
            QPushButton:hover { background-color: rgba(239, 68, 68, 40); color: #ef4444; }
        """)
        header.addWidget(close_btn)
        inner_layout.addLayout(header)
        
        # Content
        self.text_lbl = QLabel(text)
        self.text_lbl.setWordWrap(True)
        self.text_lbl.setAlignment(Qt.AlignCenter)
        self.text_lbl.setStyleSheet("""
            color: #e2e8f0; 
            font-size: 16px; 
            font-weight: 500; 
            line-height: 1.4;
            background: transparent;
        """)
        inner_layout.addWidget(self.text_lbl)
        
        layout.addWidget(self.container)
        
        # Position
        screen = QApplication.primaryScreen().geometry()
        self.adjustSize()
        
        if self.bbox_pos:
            bx, by, bw, bh = self.bbox_pos
            # Align center with the box center
            target_x = bx + (bw // 2) - (self.width() // 2)
            target_y = by + bh + 15  # 15px below the box
            
            # Keep within screen bounds
            if target_x < 0: target_x = 10
            if target_x + self.width() > screen.width(): target_x = screen.width() - self.width() - 10
            
            if target_y + self.height() > screen.height():
                target_y = by - self.height() - 15 # Place above if no space below
                if target_y < 0: target_y = 10
                
            self.move(target_x, target_y)
        else:
            self.setFixedWidth(int(screen.width() * 0.4))
            self.adjustSize()
            self.move(screen.center().x() - self.width()//2, screen.height() - self.height() - 120)
        
    def mousePressEvent(self, event):
        self.close()

class ScreenTranslatorOverlay(QWidget):
    """MemoFast Snipping OCR Overlay - Translumo/Modern Style"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MemoFast Snipping OCR")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)

        # Merged screen coverage
        screen_rect = QRect()
        for screen in QApplication.screens():
            screen_rect = screen_rect.united(screen.geometry())
        self.setGeometry(screen_rect)
        
        # State variables
        self.origin = QPoint()
        self.current_rect = QRect()
        self.is_selecting = False
        self.last_bbox = None

        # Win32 TopMost forcing
        try:
            hwnd = int(self.winId())
            style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongPtrW(hwnd, -20, style | 0x8 | 0x80 | 0x08000000)
            self.force_topmost()
        except: pass

        self.init_resources()
        self.init_signals_and_timers()

    def init_resources(self):
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
        except: pass
        
        self.audio_lock = threading.Lock()
        self.current_audio_file = None
        self.last_text = ""
        self.is_running = False
        self.loop_thread = None
        self.result_window = None
        self.exceptions = set(DEFAULT_EXCEPTIONS)
        self.load_exceptions()
        
        self.reader = None
        threading.Thread(target=self.init_easyocr, daemon=True).start()

    def init_easyocr(self):
        try:
            self.reader = easyocr.Reader(['en', 'tr'])
        except Exception as e: pass

    def init_signals_and_timers(self):
        self.topmost_timer = QTimer(self)
        self.topmost_timer.timeout.connect(self.force_topmost)
        self.topmost_timer.start(500)
        self.start_hotkey_listener()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150)) # Ekranı Karart
        
        if not self.current_rect.isNull():
            # Seçili alanın içini şeffaf yap
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(self.current_rect, Qt.transparent)
            
            # Seçili alana yeşil bir çerçeve çiz
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(16, 185, 129), 2))
            painter.drawRect(self.current_rect)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_selecting = True
            self.origin = event.pos()
            self.current_rect = QRect(self.origin, self.origin)
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.current_rect = QRect(self.origin, event.pos()).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.is_selecting = False
            r = self.current_rect
            self.current_rect = QRect()
            self.update()
            
            if r.width() > 10 and r.height() > 10:
                self.hide()
                QApplication.processEvents()
                time.sleep(0.12) # Ekran karanlığının geçmesini bekle
                
                global_pos = self.mapToGlobal(r.topLeft())
                
                # PyQt's mapping might need Device Pixel Ratio for correct bbox on high DPI screens
                ratio = self.devicePixelRatio()
                
                bx1 = int(global_pos.x() * ratio)
                by1 = int(global_pos.y() * ratio)
                bx2 = int((global_pos.x() + r.width()) * ratio)
                by2 = int((global_pos.y() + r.height()) * ratio)
                
                self.last_bbox = (bx1, by1, bx2, by2)
                
                # Sadece sonucu gösterirken normal Qt koordinatları kullanıyoruz (ekranın kendisine çizeceğimiz için)
                qt_bbox = (global_pos.x(), global_pos.y(), r.width(), r.height())
                self.perform_translation(self.last_bbox, qt_bbox, is_auto=False)
            else:
                self.hide()

    def force_topmost(self):
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 1107)
            if self.result_window and self.result_window.isVisible():
                p_hwnd = int(self.result_window.winId())
                ctypes.windll.user32.SetWindowPos(p_hwnd, -1, 0, 0, 0, 0, 1107)
        except: pass

    def start_hotkey_listener(self):
        try:
            s = self.load_settings()
            def run_listener():
                def show(): 
                    print(f"[DEBUG] Hotkey trigger: show selection")
                    try:
                        import winsound
                        winsound.Beep(1000, 100)
                    except: pass
                    self.toggle_visibility()
                def start(): 
                    print("[DEBUG] Hotkey trigger: start loop")
                    if self.isVisible(): self.toggle_visibility()
                    self.start_loop()
                def stop(): 
                    print("[DEBUG] Hotkey trigger: stop loop")
                    self.stop_loop()
                
                hotkey_map = {
                    s.get("ocr_shortcut", "<ctrl>+p").lower(): show,
                    s.get("ocr_start_shortcut", "<ctrl>+o").lower(): start,
                    s.get("ocr_stop_shortcut", "<ctrl>+l").lower(): stop
                }
                print(f"[OCR] Kısayollar kaydediliyor: {list(hotkey_map.keys())}")
                
                try:
                    self.listener = keyboard.GlobalHotKeys(hotkey_map)
                    with self.listener as h: 
                        print("[OCR] Hotkey Listener çalışıyor.")
                        h.join()
                except Exception as ex:
                    print(f"[OCR] Hotkey listener hatası (Kritik): {ex}")
                    
            threading.Thread(target=run_listener, daemon=True).start()
        except Exception as e: 
            print(f"Hotkey listener başlatılırken hata oluştu: {e}")

    def toggle_visibility(self):
        QMetaObject.invokeMethod(self, "_safe_toggle", Qt.QueuedConnection)

    @pyqtSlot()
    def _safe_toggle(self):
        if self.isVisible(): 
            self.hide()
        else:
            self.current_rect = QRect()
            self.show()
            self.raise_()
            self.activateWindow()
            self.force_topmost()

    def toggle_loop(self):
        if self.is_running: self.stop_loop()
        else: self.start_loop()

    def start_loop(self):
        if not self.last_bbox: return
        self.is_running = True
        if not self.loop_thread or not self.loop_thread.is_alive():
            self.loop_thread = threading.Thread(target=self.translation_loop, daemon=True)
            self.loop_thread.start()

    def stop_loop(self):
        self.is_running = False
        try: pygame.mixer.music.stop()
        except: pass

    def translation_loop(self):
        while self.is_running:
            try:
                if self.last_bbox and hasattr(self, 'last_qt_bbox'):
                    self.perform_translation(self.last_bbox, self.last_qt_bbox, is_auto=True)
            except: pass
            time.sleep(1.0)

    def is_similar(self, a, b, threshold=0.92):
        if not a or not b: return False
        a_n, b_n = re.sub(r'\s+', ' ', f"{a}").strip().lower(), re.sub(r'\s+', ' ', f"{b}").strip().lower()
        if a_n == b_n: return True
        return SequenceMatcher(None, a_n, b_n).ratio() > threshold

    def run_windows_ocr_sync(self, img):
        if not winrt_available: return ""
        async def _ocr():
            try:
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                data = img_byte_arr.getvalue()
                
                stream = InMemoryRandomAccessStream()
                writer = DataWriter(stream)
                writer.write_bytes(data)
                await writer.store_async()
                await writer.flush_async()
                stream.seek(0)
                
                decoder = await BitmapDecoder.create_async(stream)
                bitmap = await decoder.get_software_bitmap_async()
                
                lang = Language("en-US")
                if OcrEngine.is_language_supported(lang):
                    engine = OcrEngine.try_create_from_language(lang)
                    result = await engine.recognize_async(bitmap)
                    return result.text
                return ""
            except: return ""
                
        loop = asyncio.new_event_loop()
        ans = loop.run_until_complete(_ocr())
        loop.close()
        return ans

    def perform_translation(self, bbox, qt_bbox=None, is_auto=False):
        try:
            self.last_qt_bbox = qt_bbox
            img = ImageGrab.grab(bbox=bbox)
            
            s = self.load_settings()
            ocr_engine = s.get("ocr_engine", "windows")
            text = ""
            
            if ocr_engine == "windows" and winrt_available:
                img = img.resize((img.width * 2, img.height * 2), 3)
                text = self.run_windows_ocr_sync(img).strip()
                print(f"[OCR] Windows OCR Sonucu: {text}")
                
            elif ocr_engine == "easyocr" and getattr(self, "reader", None):
                img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                results = self.reader.readtext(img_cv, detail=0)
                text = " ".join(results).strip()
                print(f"[OCR] EasyOCR Sonucu: {text}")
                
            else:
                img = img.convert('L')
                img = img.resize((img.width * 2, img.height * 2), 3)
                config = '--psm 6 --oem 3'
                text = pytesseract.image_to_string(img, lang='eng', config=config).strip()
                print(f"[OCR] Tesseract Sonucu: {text}")
            
            if not text:
                return
            
            # Canlı modda (is_auto=True) aynı metni tekrar çevirme, ama elle seçimde her zaman çevir
            if is_auto and self.is_similar(text, self.last_text):
                return
            
            self.last_text = text
            service = s.get("translator_service", "google")
            
            try:
                if service=="deepl" and s.get("deepl_api_key"): 
                    translated = self.translate_with_deepl(text, s["deepl_api_key"])
                elif service=="gemini" and s.get("gemini_api_key"): 
                    translated = self.translate_with_gemini(text, s["gemini_api_key"])
                else: translated = GoogleTranslator(target='tr').translate(text)
            except: translated = GoogleTranslator(target='tr').translate(text)
            
            if s.get("ocr_filter_mekmak", True): 
                translated = self.apply_turkish_correction(translated)
            
            display_bbox = qt_bbox if qt_bbox else bbox
            
            if not is_auto:
                QMetaObject.invokeMethod(self, "show_custom_popup", Qt.QueuedConnection, Q_ARG(str, translated), Q_ARG(tuple, display_bbox))
            else:
                if self.result_window:
                    QMetaObject.invokeMethod(self.result_window.text_lbl, "setText", Qt.QueuedConnection, Q_ARG(str, translated))
            
            if s.get("ocr_dubbing", False):
                threading.Thread(target=self.speak_text, args=(translated, s.get("ocr_voice_gender", "Male")), daemon=True).start()
                
            print(f"[TRANSLATE] Çeviri Sonucu: {translated}")
                
        except Exception as e:
            print(f"[HATA] perform_translation'da hata: {e}")
            import traceback
            traceback.print_exc()
            display_bbox = qt_bbox if qt_bbox else bbox
            if not is_auto:
                QMetaObject.invokeMethod(self, "show_custom_popup", Qt.QueuedConnection, Q_ARG(str, f"Error: {e}"), Q_ARG(tuple, display_bbox))

    def speak_text(self, text, gender):
        with self.audio_lock:
            voice = "tr-TR-EmelNeural" if gender.lower() == "female" else "tr-TR-AhmetNeural"
            try:
                if not pygame.mixer.get_init(): pygame.mixer.init()
                pygame.mixer.music.unload()
            except: pass
            if self.current_audio_file and os.path.exists(self.current_audio_file):
                try: os.remove(self.current_audio_file)
                except: pass
            tfile = os.path.join(tempfile.gettempdir(), f"mf_tts_{int(time.time())}.mp3")
            async def _save(): await edge_tts.Communicate(text, voice).save(tfile)
            try:
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                loop.run_until_complete(_save()); loop.close()
                if os.path.exists(tfile):
                    self.current_audio_file = tfile
                    pygame.mixer.music.load(tfile); pygame.mixer.music.play()
            except: pass

    @pyqtSlot(str, tuple)
    def show_custom_popup(self, text, bbox):
        if getattr(self, 'result_window', None): self.result_window.close()
        self.result_window = TranslationResultWindow(text, bbox)
        self.result_window.show()

    def translate_with_gemini(self, text, key):
        import requests
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
        data = {"contents": [{"parts": [{"text": f"Translate to Turkish (Game Context): {text}"}]}]}
        try:
            res = requests.post(url, json=data, timeout=5).json()
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
        except: return GoogleTranslator(target='tr').translate(text)

    def translate_with_deepl(self, text, key):
        import requests
        url = "https://api-free.deepl.com/v2/translate" if key.endswith(":fx") else "https://api.deepl.com/v2/translate"
        try:
            res = requests.post(url, data={"auth_key": key, "text": text, "target_lang": "TR"}, timeout=5).json()
            return res['translations'][0]['text']
        except: return GoogleTranslator(target='tr').translate(text)

    def load_settings(self):
        import json
        p = os.path.join(os.path.dirname(__file__), "settings.json")
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f: return json.load(f)
        return {}

    def load_exceptions(self):
        p = os.path.join(os.path.dirname(__file__), "files", "exceptions_tr.txt")
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                for l in f:
                    if l.strip() and not l.startswith("#"): self.exceptions.add(l.strip().lower())

    def apply_turkish_correction(self, text):
        if not text: return text
        words = text.split()
        if not words: return text
        match = re.search(r'^(.+?)(m[ae]k)(\W*)$', words[-1], re.IGNORECASE)
        if match and (match.group(1)+match.group(2)).lower() not in self.exceptions:
            words[-1] = match.group(1) + match.group(3)
            return " ".join(words)
        return text

    def closeEvent(self, event):
        self.stop_loop(); 
        try: self.listener.stop()
        except: pass
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ScreenTranslatorOverlay()
    window.show()
    sys.exit(app.exec_())

