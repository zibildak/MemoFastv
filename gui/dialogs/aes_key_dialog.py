"""
AES Key Dialog - Hack Tool Edition
Animasyonlu bruteforce görünümü ile AES key arama
"""

import os
import json
import random
import string
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QFrame, QProgressBar, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor, QPalette, QFontDatabase

from logger import setup_logger

logger = setup_logger(__name__)

# ─── Renk Paleti ────────────────────────────────────────────────────────────
BG        = "#0a0e17"
BG2       = "#0f1623"
BORDER    = "#1a2744"
GREEN     = "#00ff88"
GREEN_DIM = "#00663a"
CYAN      = "#00d4ff"
RED       = "#ff3366"
YELLOW    = "#ffcc00"
GRAY      = "#3a4a6b"
GRAY_LT   = "#8899bb"
WHITE     = "#e8f0ff"

BASE_STYLE = f"""
    QDialog {{
        background-color: {BG};
        border: 1px solid {BORDER};
    }}
    QLabel {{
        color: {GREEN};
        background: transparent;
    }}
    QLineEdit {{
        background-color: {BG2};
        color: {GREEN};
        border: 1px solid {GREEN_DIM};
        border-radius: 4px;
        padding: 8px 12px;
        font-family: 'Consolas', monospace;
        font-size: 12px;
        selection-background-color: {GREEN_DIM};
    }}
    QLineEdit:focus {{
        border: 1px solid {GREEN};
    }}
    QTextEdit {{
        background-color: {BG2};
        color: {GREEN};
        border: 1px solid {BORDER};
        border-radius: 4px;
        font-family: 'Consolas', monospace;
        font-size: 11px;
        padding: 6px;
    }}
    QProgressBar {{
        background-color: {BG2};
        border: 1px solid {BORDER};
        border-radius: 3px;
        height: 6px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 {GREEN_DIM}, stop:1 {GREEN});
        border-radius: 3px;
    }}
    QPushButton {{
        background-color: {BG2};
        color: {GREEN};
        border: 1px solid {GREEN_DIM};
        border-radius: 4px;
        padding: 8px 20px;
        font-family: 'Consolas', monospace;
        font-size: 11px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: {GREEN_DIM};
        border: 1px solid {GREEN};
        color: {WHITE};
    }}
    QPushButton:disabled {{
        color: {GRAY};
        border-color: {GRAY};
        background-color: {BG};
    }}
    QPushButton#btn_cancel {{
        color: {RED};
        border-color: #661a2a;
    }}
    QPushButton#btn_cancel:hover {{
        background-color: #330d15;
        border-color: {RED};
    }}
    QPushButton#btn_manual {{
        color: {CYAN};
        border-color: #005566;
    }}
    QPushButton#btn_manual:hover {{
        background-color: #002233;
        border-color: {CYAN};
    }}
"""


# ─── Arama Worker ───────────────────────────────────────────────────────────
class AesSearchWorker(QThread):
    log_signal   = pyqtSignal(str)
    found_signal = pyqtSignal(str)   # key bulununca
    done_signal  = pyqtSignal(bool)  # True=bulundu, False=bulunamadı

    def __init__(self, game_name: str, json_path: str):
        super().__init__()
        self.game_name = game_name
        self.json_path = json_path

    def run(self):
        import time, re

        def log(msg, color=None):
            if color:
                self.log_signal.emit(f'<span style="color:{color}">{msg}</span>')
            else:
                self.log_signal.emit(msg)

        log(f'<span style="color:{CYAN}">[ MemoFast AES Avcısı v2.0 ]</span>')
        log(f'<span style="color:{GRAY_LT}">Hedef Oyun   : </span>'
            f'<span style="color:{YELLOW}">{self.game_name}</span>')
        log(f'<span style="color:{GRAY_LT}">Veritabanı   : aes_keys.json</span>')
        log(f'<span style="color:{GRAY_LT}">Mod          : GLOBAL KEY TARAMA</span>')
        log("─" * 52, GRAY)
        time.sleep(0.4)

        # JSON yükle
        log("[ YÜKLENİYOR ] AES veritabanı açılıyor...", CYAN)
        time.sleep(0.3)
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            log(f"[ TAMAM ] {len(data)} kayıt yüklendi", GREEN)
        except Exception as e:
            log(f"[ HATA ] Veritabanı yüklenemedi: {e}", RED)
            self.done_signal.emit(False)
            return

        time.sleep(0.2)
        log("─" * 52, GRAY)
        log("[ BAŞLAT ] Şifre kırma sekansı başlatılıyor...", CYAN)
        time.sleep(0.3)

        # Sahte bruteforce stream
        fake_keys = [
            "0x" + "".join(random.choices("0123456789ABCDEF", k=64))
            for _ in range(18)
        ]
        for i, fk in enumerate(fake_keys):
            progress_pct = int((i / len(fake_keys)) * 60)
            self.log_signal.emit(
                f'<span style="color:{GRAY}">[{progress_pct:02d}%] DENİYOR → </span>'
                f'<span style="color:{GREEN_DIM}">{fk[:20]}...{fk[-8:]}</span>'
                f'<span style="color:{RED}"> ✗ BAŞARISIZ</span>'
            )
            time.sleep(random.uniform(0.06, 0.14))

        log("─" * 52, GRAY)
        log("[ GEÇİŞ ] İmza veritabanına geçiliyor...", CYAN)
        time.sleep(0.4)

        # Gerçek arama
        norm_target = re.sub(r'[^a-z0-9]', '', self.game_name.lower())

        candidates = []
        for entry in data:
            gname = entry.get("game", "")
            gkey  = entry.get("key", "")
            if not gname or not gkey:
                continue
            norm_db = re.sub(r'[^a-z0-9]', '', gname.lower())

            # Eşleşme skoru
            score = 0
            if norm_target == norm_db:
                score = 100
            elif norm_target in norm_db or norm_db in norm_target:
                score = 80
            else:
                # Kelime bazlı eşleşme
                words_t = set(norm_target.split())
                words_d = set(norm_db.split())
                common  = words_t & words_d
                if common:
                    score = int(60 * len(common) / max(len(words_t), len(words_d)))

            if score > 40:
                candidates.append((score, gname, gkey))

        candidates.sort(reverse=True)

        if not candidates:
            # Aramayı göster
            for entry in random.sample(data, min(8, len(data))):
                gname = entry.get("game", "")
                self.log_signal.emit(
                    f'<span style="color:{GRAY}">[~~] KONTROL: </span>'
                    f'<span style="color:{GRAY_LT}">{gname[:40]}</span>'
                    f'<span style="color:{RED}"> ✗</span>'
                )
                time.sleep(0.08)

            log("─" * 52, GRAY)
            log("[ UYARI ] Veritabanında eşleşen key bulunamadı", YELLOW)
            log("[ BİLGİ ] Manuel key girişi gerekli", GRAY_LT)
            self.done_signal.emit(False)
            return

        # Adayları göster (yavaş)
        log(f"[ EŞLEŞME ] {len(candidates)} aday bulundu. Doğrulanıyor...", YELLOW)
        time.sleep(0.3)

        for idx, (score, gname, gkey) in enumerate(candidates[:5]):
            self.log_signal.emit(
                f'<span style="color:{GRAY}">[{60 + idx*7:02d}%] DOĞRULANIYOOR: </span>'
                f'<span style="color:{YELLOW}">{gname[:36]}</span>'
            )
            time.sleep(0.25)
            self.log_signal.emit(
                f'<span style="color:{GRAY}">       KEY → </span>'
                f'<span style="color:{GREEN}">{gkey[:24]}...{gkey[-8:]}</span>'
            )
            time.sleep(0.2)

            if score >= 80:
                log("─" * 52, GRAY)
                time.sleep(0.2)
                log("[ BAŞARILI ] GLOBAL KEY KIRILDI!", GREEN)
                log(f'<span style="color:{GRAY_LT}">Oyun Eşleşmesi : </span>'
                    f'<span style="color:{YELLOW}">{gname}</span>')
                log(f'<span style="color:{GRAY_LT}">AES-256 Key    : </span>'
                    f'<span style="color:{GREEN}"><b>{gkey}</b></span>')
                log("─" * 52, GRAY)
                log("[ HAZIR ] Key enjeksiyona hazır.", CYAN)
                self.found_signal.emit(gkey)
                self.done_signal.emit(True)
                return
            time.sleep(0.15)

        # En iyi adayı kullan
        best_score, best_name, best_key = candidates[0]
        log("─" * 52, GRAY)
        log("[ BAŞARILI ] GLOBAL KEY KIRILDI!", GREEN)
        log(f'<span style="color:{GRAY_LT}">Oyun Eşleşmesi : </span>'
            f'<span style="color:{YELLOW}">{best_name}</span>')
        log(f'<span style="color:{GRAY_LT}">AES-256 Key    : </span>'
            f'<span style="color:{GREEN}"><b>{best_key}</b></span>')
        log("─" * 52, GRAY)
        log("[ HAZIR ] Key enjeksiyona hazır.", CYAN)
        self.found_signal.emit(best_key)
        self.done_signal.emit(True)


# ─── Ana Dialog ─────────────────────────────────────────────────────────────
class AESKeyDialog(QDialog):

    def __init__(self, game_name: str, parent=None):
        super().__init__(parent)
        logger.info(f"AES Key Dialog opened for {game_name}")
        self.game_name   = game_name
        self._found_key  = ""
        self._searching  = False

        self.setWindowTitle(f"AES Key Hunter — {game_name}")
        self.setFixedSize(720, 540)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setStyleSheet(BASE_STYLE)

        self._build_ui()
        self._setup_cursor_blink()

        # Otomatik başlat
        QTimer.singleShot(300, self._start_search)

    # ── UI ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Başlık Çubuğu ──
        title_bar = QFrame()
        title_bar.setFixedHeight(38)
        title_bar.setStyleSheet(f"background:{BG2}; border-bottom:1px solid {BORDER};")
        tb_lay = QHBoxLayout(title_bar)
        tb_lay.setContentsMargins(14, 0, 10, 0)

        ico = QLabel("⚡")
        ico.setStyleSheet(f"color:{GREEN}; font-size:16px;")

        title_lbl = QLabel(f"MemoFast  //  AES KEY HUNTER  //  {self.game_name.upper()}")
        title_lbl.setStyleSheet(
            f"color:{GREEN}; font-family:'Consolas',monospace; font-size:11px; font-weight:bold;"
        )

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{GRAY_LT};border:none;font-size:14px;}}"
            f"QPushButton:hover{{color:{RED};}}"
        )
        close_btn.clicked.connect(self.reject)

        tb_lay.addWidget(ico)
        tb_lay.addSpacing(8)
        tb_lay.addWidget(title_lbl)
        tb_lay.addStretch()
        tb_lay.addWidget(close_btn)
        root.addWidget(title_bar)

        # ── İçerik ──
        content = QFrame()
        content.setStyleSheet(f"background:{BG}; padding:0px;")
        c_lay = QVBoxLayout(content)
        c_lay.setContentsMargins(16, 14, 16, 14)
        c_lay.setSpacing(10)

        # Status satırı
        status_row = QHBoxLayout()
        self.lbl_status = QLabel("► BAŞLATILIYOR...")
        self.lbl_status.setStyleSheet(
            f"color:{CYAN}; font-family:'Consolas',monospace; font-size:11px; font-weight:bold;"
        )
        self.lbl_cursor = QLabel("█")
        self.lbl_cursor.setStyleSheet(f"color:{GREEN}; font-size:14px;")
        status_row.addWidget(self.lbl_status)
        status_row.addWidget(self.lbl_cursor)
        status_row.addStretch()
        c_lay.addLayout(status_row)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminate
        self.progress.setFixedHeight(5)
        self.progress.setTextVisible(False)
        c_lay.addWidget(self.progress)

        # Terminal log
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMinimumHeight(280)
        self.log_area.document().setDefaultStyleSheet(
            f"body{{color:{GREEN}; font-family:'Consolas',monospace; font-size:11px;}}"
        )
        c_lay.addWidget(self.log_area)

        # Bulunan key gösterimi
        self.lbl_key_title = QLabel("AES-256 KEY:")
        self.lbl_key_title.setStyleSheet(
            f"color:{GRAY_LT}; font-family:'Consolas',monospace; font-size:10px;"
        )
        self.lbl_key_title.setVisible(False)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("0x... (Manuel giriş veya otomatik bulunacak)")
        self.key_input.setVisible(True)
        self.key_input.setFixedHeight(36)

        c_lay.addWidget(self.lbl_key_title)
        c_lay.addWidget(self.key_input)

        # Alt butonlar
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_inject = QPushButton("▶  KEY'İ KULLAN")
        self.btn_inject.setFixedHeight(38)
        self.btn_inject.setEnabled(False)
        self.btn_inject.clicked.connect(self._on_use_key)

        self.btn_manual = QPushButton("✎  MANUEL GİR")
        self.btn_manual.setObjectName("btn_manual")
        self.btn_manual.setFixedHeight(38)
        self.btn_manual.clicked.connect(self._on_manual_mode)

        self.btn_cancel = QPushButton("✕  İPTAL")
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setFixedHeight(38)
        self.btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(self.btn_inject, 2)
        btn_row.addWidget(self.btn_manual, 1)
        btn_row.addWidget(self.btn_cancel, 1)
        c_lay.addLayout(btn_row)

        root.addWidget(content)

    # ── Cursor blink ────────────────────────────────────────────────────────
    def _setup_cursor_blink(self):
        self._cursor_visible = True
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink_cursor)
        self._blink_timer.start(500)

    def _blink_cursor(self):
        self._cursor_visible = not self._cursor_visible
        color = GREEN if self._cursor_visible else BG
        self.lbl_cursor.setStyleSheet(f"color:{color}; font-size:14px;")

    # ── Arama ───────────────────────────────────────────────────────────────
    def _start_search(self):
        json_path = str(Path(__file__).parent.parent.parent / "aes_keys.json")
        if not Path(json_path).exists():
            self._log_html(f'<span style="color:{RED}">[ HATA ] aes_keys.json bulunamadı!</span>')
            self.lbl_status.setText("► MANUEL GİRİŞ GEREKLİ")
            return

        self._searching = True
        self.lbl_status.setText("► KIRILMA İŞLEMİ SÜRÜYOR...")
        self.btn_inject.setEnabled(False)

        self._worker = AesSearchWorker(self.game_name, json_path)
        self._worker.log_signal.connect(self._log_html)
        self._worker.found_signal.connect(self._on_key_found)
        self._worker.done_signal.connect(self._on_search_done)
        self._worker.start()

    def _log_html(self, html: str):
        self.log_area.append(html)
        self.log_area.verticalScrollBar().setValue(
            self.log_area.verticalScrollBar().maximum()
        )

    def _on_key_found(self, key: str):
        self._found_key = key
        self.key_input.setText(key)
        self.key_input.setStyleSheet(
            f"background:{BG2}; color:{GREEN}; border:1px solid {GREEN};"
            f"border-radius:4px; padding:8px 12px;"
            f"font-family:'Consolas',monospace; font-size:12px; font-weight:bold;"
        )
        self.lbl_key_title.setVisible(True)

    def _on_search_done(self, found: bool):
        self._searching = False
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if found else 0)

        if found:
            self.lbl_status.setText("► KEY KIRILDI — HAZIR")
            self.lbl_status.setStyleSheet(
                f"color:{GREEN}; font-family:'Consolas',monospace; font-size:11px; font-weight:bold;"
            )
            self.btn_inject.setEnabled(True)
            self.btn_inject.setStyleSheet(
                f"background:{GREEN_DIM}; color:{WHITE}; border:1px solid {GREEN};"
                f"border-radius:4px; padding:8px 20px;"
                f"font-family:'Consolas',monospace; font-size:11px; font-weight:bold;"
            )
        else:
            self.lbl_status.setText("► BULUNAMADI — MANUEL GİRİŞ")
            self.lbl_status.setStyleSheet(
                f"color:{YELLOW}; font-family:'Consolas',monospace; font-size:11px; font-weight:bold;"
            )
            self.btn_manual.setStyleSheet(
                f"background:#002233; color:{CYAN}; border:1px solid {CYAN};"
                f"border-radius:4px; padding:8px 20px;"
                f"font-family:'Consolas',monospace; font-size:11px; font-weight:bold;"
            )

    def _on_use_key(self):
        key = self.key_input.text().strip()
        if key:
            self._found_key = key
            self.accept()

    def _on_manual_mode(self):
        """Kullanıcı manuel key girebilsin"""
        self.key_input.setReadOnly(False)
        self.key_input.setFocus()
        self.key_input.selectAll()
        self.btn_inject.setEnabled(True)
        self.lbl_status.setText("► MANUEL KEY GİRİŞ MODU")
        self._log_html(
            f'<span style="color:{CYAN}">[ GİRİŞ ] Manuel key giriş modu aktif.</span>'
        )

    # ── API ─────────────────────────────────────────────────────────────────
    def get_key(self) -> str:
        return self.key_input.text().strip()

    # ── Pencere sürükleme ───────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag_pos'):
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def closeEvent(self, event):
        if hasattr(self, '_worker') and self._worker.isRunning():
            self._worker.terminate()
        event.accept()
