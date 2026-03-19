"""
MemoFast DPI Tray Agent
MemoFast kapalı olsa bile arka planda çalışır.
MemoFast Ağ Servisini sistem tepsisinden başlatıp durdurur.
"""
import sys
import os
import subprocess
import ctypes
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction, QMessageBox
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt, QSize

BASE_PATH = Path(__file__).parent

CREATE_NO_WINDOW = 0x08000000

# --- Tek Instance Kontrolü (Windows Mutex) ---
_MUTEX_NAME = "MemoFastTrayAgentMutex_v1"
_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    sys.exit(0)  # Zaten çalışıyor, sessizce çık

dpi_process = None


def get_dpi_path():
    p64 = BASE_PATH / "libs" / "dns" / "x86_64" / "MemoFast_Service.exe"
    p86 = BASE_PATH / "libs" / "dns" / "x86" / "MemoFast_Service.exe"
    if p64.exists():
        return p64
    if p86.exists():
        return p86
    return None


def make_tray_icon():
    """Basit renkli ikon oluştur"""
    pix = QPixmap(32, 32)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#3b82f6"))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, 28, 28)
    painter.setPen(QColor("white"))
    font = QFont("Segoe UI", 14, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignCenter, "M")
    painter.end()
    return QIcon(pix)


def start_dpi():
    global dpi_process
    path = get_dpi_path()
    if not path:
        QMessageBox.critical(None, "Hata", "MemoFast_Service.exe bulunamadı!\nlibs/dns klasörünü kontrol edin.")
        return

    params = "-5 --set-ttl 5 --dns-addr 77.88.8.8 --dns-port 1253 --dnsv6-addr 2a02:6b8::feed:0ff --dnsv6-port 1253"
    ctypes.windll.shell32.ShellExecuteW(None, "runas", str(path), params, str(path.parent), 0)


def stop_dpi():
    subprocess.run(
        ["taskkill", "/F", "/T", "/IM", "MemoFast_Service.exe"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW
    )


def main():
    import time
    # Windows başladığında görev çubuğunun (explorer.exe) tam yüklenmesini beklemek için gecikme ekliyoruz.
    time.sleep(5)
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    tray = QSystemTrayIcon()
    tray.setIcon(make_tray_icon())
    tray.setToolTip("MemoFast Ağ Servisi")

    menu = QMenu()
    menu.setStyleSheet("""
        QMenu {
            background-color: #1a1f2e;
            color: white;
            border: 1px solid #3b82f6;
            font-size: 14px;
            padding: 4px;
        }
        QMenu::item:selected { background-color: #3b82f6; border-radius: 4px; }
    """)

    act_start = QAction("🛡️  MemoFast Bağlantı Kur")
    act_start.triggered.connect(start_dpi)
    menu.addAction(act_start)

    act_stop = QAction("🛑  MemoFast Bağlantı Kes")
    act_stop.triggered.connect(stop_dpi)
    menu.addAction(act_stop)

    menu.addSeparator()

    act_quit = QAction("❌  Çıkış")
    act_quit.triggered.connect(lambda: (stop_dpi(), app.quit()))
    menu.addAction(act_quit)

    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: tray.showMessage(
        "MemoFast Ağ Servisi", "Sağ tık ile bağlantı kurabilirsiniz.", QSystemTrayIcon.Information, 2000
    ) if reason == QSystemTrayIcon.Trigger else None)

    tray.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
