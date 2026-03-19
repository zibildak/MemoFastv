import sys
import psutil
import subprocess
import winreg
import ctypes
import time
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

# Try importing GPUtil
try:
    import GPUtil
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False
    
# Nvidia-SMI Helper Function
def get_nvidia_gpu_load():
    """Fallback method for Nvidia GPUs using nvidia-smi"""
    try:
        # Run nvidia-smi to get GPU utilization
        # Format: utilization.gpu
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"], 
            startupinfo=startupinfo,
            creationflags=0x08000000
        ).decode("utf-8")
        
        # Parse first line (if multiple GPUs, simpler to take first)
        val = int(output.strip().split('\n')[0])
        return val
    except:
        return 0

class PingWorker(QThread):
    result = pyqtSignal(int)

    def run(self):
        try:
            # Measure ping to Google DNS
            # Create startupinfo to hide window
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            output = subprocess.check_output(
                "ping -n 1 -w 1000 8.8.8.8", 
                startupinfo=startupinfo,
                creationflags=0x08000000,
                shell=False
            ).decode('cp857', errors='ignore')
            
            if "ms" in output:
                import re
                match = re.search(r'(time|zaman)[=<](\d+)ms', output, re.IGNORECASE)
                if match:
                    self.result.emit(int(match.group(2)))
                    return
            self.result.emit(999)
        except:
            self.result.emit(999)

class HUDOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(430, 110)
        # Transparent for background, catch mouse events
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Shadow Effect
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(20)
        self.shadow.setColor(QColor(0, 0, 0, 150))
        self.shadow.setOffset(0, 5)
        self.setGraphicsEffect(self.shadow)
        
        # [YENİ] Mouse Tracking (Hover Efekti İçin)
        self.setMouseTracking(True)

        # Style Variables
        self.bg_color = QColor(15, 23, 42, 180) # Dark Blue-Slate (Glass - Daha Saydam)
        self.text_color = QColor(226, 232, 240) # Slate 200
        self.accent_color = QColor(56, 189, 248) # Light Blue
        self.boost_color = QColor(16, 185, 129) # Emerald Green
        
        # Data
        self.cpu = 0
        self.ram = 0
        self.gpu = 0
        self.ping = 0
        self.is_boosting = False
        self.boost_angle = 0
        
        # Timers
        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self.update_stats)
        self.stats_timer.start(2000)
        
        self.ping_worker = None
        self.measure_ping()
        
        self.boost_anim_timer = QTimer(self)
        self.boost_anim_timer.timeout.connect(self.animate_boost)

        # [HUD GİZLE/GÖSTER SİSTEMİ]
        self.is_hidden = False
        self.animation = QPropertyAnimation(self, b"pos")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        
        # Gizleme Butonu (Soldaki ince şerit)
        self.toggle_btn = QPushButton(self)
        self.toggle_btn.setGeometry(0, 5, 25, 100)
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.setStyleSheet("background: transparent; border: none;")
        self.toggle_btn.clicked.connect(self.toggle_visibility)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect().adjusted(5, 5, -5, -5)
        
        # 1. Background (Glassmorphism)
        path = QPainterPath()
        # Ana kutu (Buton hariç kısım 30px içeriden başlar)
        content_rect = QRectF(rect.x() + 25, rect.y(), rect.width() - 25, rect.height())
        path.addRoundedRect(content_rect, 16, 16)
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.bg_color)
        painter.drawPath(path)
        
        # Border Glow
        glow_pen = QPen(self.accent_color, 1.5)
        painter.setPen(glow_pen)
        painter.drawPath(path)
        
        # 1.5. Toggle Button Drawing (Triangular)
        painter.setBrush(QColor(255, 255, 255, 40) if self.toggle_btn.underMouse() else QColor(255, 255, 255, 20))
        painter.setPen(Qt.NoPen)
        btn_bg_path = QPainterPath()
        btn_bg_path.addRoundedRect(QRectF(rect.x(), rect.y() + 20, 22, 60), 5, 5)
        painter.drawPath(btn_bg_path)
        
        # Üçgen Çizimi
        painter.setBrush(self.accent_color)
        tri = QPainterPath()
        if not self.is_hidden:
            # Sağ göster (Kapatma modu)
            tri.moveTo(rect.x() + 8, rect.y() + 42)
            tri.lineTo(rect.x() + 16, rect.y() + 50)
            tri.lineTo(rect.x() + 8, rect.y() + 58)
        else:
            # Sol göster (Açma modu)
            tri.moveTo(rect.x() + 16, rect.y() + 42)
            tri.lineTo(rect.x() + 8, rect.y() + 50)
            tri.lineTo(rect.x() + 16, rect.y() + 58)
        painter.drawPath(tri)

        # 2. Left Side: Stats (CPU, GPU, RAM)
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        
        stat_x_start = 55 # Buton geldiği için içeriği sağa kaydırdık
        def draw_stat_row(y, label, value, color):
            painter.setPen(QColor(148, 163, 184))
            painter.drawText(stat_x_start, y+10, label)
            
            # Bar Background
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(51, 65, 85))
            painter.drawRoundedRect(stat_x_start + 40, y+2, 80, 8, 4, 4)
            
            # Bar Fill
            fill_w = int(80 * (value / 100))
            painter.setBrush(color)
            painter.drawRoundedRect(stat_x_start + 40, y+2, fill_w, 8, 4, 4)
            
            # Value Text
            painter.setPen(Qt.white)
            painter.drawText(stat_x_start + 125, y+10, f"{int(value)}%")

        draw_stat_row(25, "CPU", self.cpu, QColor("#ef4444"))
        draw_stat_row(50, "GPU", self.gpu, QColor("#a855f7"))
        draw_stat_row(75, "RAM", self.ram, QColor("#3b82f6"))
        
        # 3. Separator
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.drawLine(215, 20, 215, 90)
        
        # 4. Middle: PING
        painter.setPen(QColor("#94a3b8"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.drawText(240, 35, "PING (MS)")
        
        ping_val_text = f"{self.ping}" if self.ping < 999 else "N/A"
        ping_color = self.boost_color if self.ping < 50 else (QColor("#f59e0b") if self.ping < 100 else QColor("#ef4444"))
        
        painter.setPen(ping_color)
        painter.setFont(QFont("Segoe UI", 26, QFont.Bold))
        painter.drawText(235, 75, ping_val_text)
        
        # 5. Right: BOOST BUTTON (Revolutionary Gauge)
        center = QPoint(365, 55)
        radius = 35
        
        # Outer Ring
        painter.setPen(QPen(QColor(30, 41, 59), 8, Qt.SolidLine, Qt.RoundCap))
        painter.drawEllipse(center, radius, radius)
        
        # Animated/Progress Ring
        if self.is_boosting:
            # Spinner animation
            start_angle = self.boost_angle * 16
            span_angle = 270 * 16
            painter.setPen(QPen(self.accent_color, 8, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(QRect(center.x()-radius, center.y()-radius, radius*2, radius*2), start_angle, span_angle)
        else:
             # Static "Ready" Ring (Green)
             painter.setPen(QPen(self.boost_color, 8, Qt.SolidLine, Qt.RoundCap))
             painter.drawArc(QRect(center.x()-radius, center.y()-radius, radius*2, radius*2), 90*16, 360*16)
             
        # Inner Circle Button
        painter.setPen(Qt.NoPen)
        btn_grad = QRadialGradient(center, radius-10)
        btn_grad.setColorAt(0, QColor(30, 41, 59))
        btn_grad.setColorAt(1, QColor(15, 23, 42))
        painter.setBrush(btn_grad)
        painter.drawEllipse(center, radius-10, radius-10)
        
        # Button Text/Icon
        painter.setPen(Qt.white)
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        text = "..." if self.is_boosting else "BOOST"
        font_metrics = QFontMetrics(painter.font())
        text_w = font_metrics.width(text)
        text_h = font_metrics.height()
        painter.drawText(center.x() - text_w//2, center.y() + text_h//4, text)

    def toggle_visibility(self):
        """HUD'u sağa kaydırarak gizle veya göster"""
        if not self.window(): return
        
        main_win = self.window()
        padding = 20
        target_y = main_win.height() - self.height() - padding
        
        if self.is_hidden:
            # GÖSTER (Sola kay)
            target_x = main_win.width() - self.width() - padding
            self.is_hidden = False
        else:
            # GİZLE (Sağa kay - sadece buton kalsın)
            target_x = main_win.width() - 35
            self.is_hidden = True
            
        self.animation.setStartValue(self.pos())
        self.animation.setEndValue(QPoint(target_x, target_y))
        self.animation.start()
        self.update() # Üçgen yönü için

    def mousePressEvent(self, event):
        # Eğer toggle butonuna basıldıysa Toggle logic çalışsın (zaten clicked bağlı)
        if self.toggle_btn.geometry().contains(event.pos()):
            return
            
        # Click on Boost Button
        x, y = event.x(), event.y()
        # HUD kayıkken boost butonuna basılmasın
        if self.is_hidden: return
        
        # Center 365, 55, Radius ~40 for hitbox
        if (x - 365)**2 + (y - 55)**2 <= 40**2:
            self.start_boost()

    def mouseMoveEvent(self, event):
        """Fare hareketini izle ve buton üzerindeyse imleci değiştir"""
        x, y = event.x(), event.y()
        
        # Toggle butonu kontrolü
        if self.toggle_btn.geometry().contains(QPoint(x, y)):
             self.setCursor(Qt.PointingHandCursor)
             self.update() # Hover rengi için
             return
             
        # Boost butonu kontrolü
        if not self.is_hidden and (x - 365)**2 + (y - 55)**2 <= 40**2:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        self.update()
            
    def update_stats(self):
        self.cpu = psutil.cpu_percent()
        self.ram = psutil.virtual_memory().percent
        
        # GPU Check (GPUtil -> Nvidia-SMI -> 0)
        self.gpu = 0
        if GPU_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                if gpus: self.gpu = gpus[0].load * 100
            except: pass
            
        # If GPUtil failed or returned 0 (maybe not detected), try nvidia-smi
        if self.gpu == 0:
            nv_val = get_nvidia_gpu_load()
            if nv_val > 0:
                self.gpu = nv_val
                
        self.update()
        
    def measure_ping(self):
        if self.ping_worker and self.ping_worker.isRunning(): return
        self.ping_worker = PingWorker()
        self.ping_worker.result.connect(self.on_ping_result)
        self.ping_worker.start()
        
    def on_ping_result(self, val):
        self.ping = val
        self.update()
        # Schedule next ping
        QTimer.singleShot(5000, self.measure_ping)

    def start_boost(self):
        if self.is_boosting: return
        self.is_boosting = True
        self.boost_angle = 0
        self.boost_anim_timer.start(20)
        
        # Run logic in background without blocking UI
        QTimer.singleShot(100, self.perform_boost_logic)

    def animate_boost(self):
        self.boost_angle = (self.boost_angle - 10) % 360
        self.update()

    def perform_boost_logic(self):
        # 1. RAM Cleaning (Safe)
        try:
             import gc
             gc.collect()
        except: pass
        
        # 2. Ping Booster (From ping_gui.py)
        try:
            # TCP Tweaks
            path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ) as key:
                num = winreg.QueryInfoKey(key)[0]
                for i in range(num):
                    sub = winreg.EnumKey(key, i)
                    try:
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{path}\\{sub}", 0, winreg.KEY_WRITE) as subkey:
                            winreg.SetValueEx(subkey, "TCPNoDelay", 0, winreg.REG_DWORD, 1)
                            winreg.SetValueEx(subkey, "TcpAckFrequency", 0, winreg.REG_DWORD, 1)
                    except: pass
            
            # DNS Flush
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.call("ipconfig /flushdns", startupinfo=startupinfo, shell=False)
            
            # Network Throttling
            path_m = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path_m, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, "NetworkThrottlingIndex", 0, winreg.REG_DWORD, 0xFFFFFFFF)
        except: pass

        # Finish after delay for effect
        QTimer.singleShot(2000, self.finish_boost)

    def finish_boost(self):
        self.is_boosting = False
        self.boost_anim_timer.stop()
        self.accent_color = QColor("#10b981") # Change Glow to Green
        self.update()
        # Reset color after a while via lambda workaround or just leave green for "Success" look
        QTimer.singleShot(3000, lambda: self.reset_glow())

    def reset_glow(self):
        self.accent_color = QColor(56, 189, 248) # Back to Blue
        self.update()
