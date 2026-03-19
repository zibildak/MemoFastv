from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt5.QtGui import QPainter, QColor, QPen, QPainterPath, QLinearGradient, QBrush, QFont
import math

class SecureConnectAnimation(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150) # Animasyon için yeterli alan
        
        # Durumlar
        self.is_connected = False
        self.is_animating = True
        
        # Animasyon Değişkenleri
        self.packet_offset = 0
        self.packet_speed = 2 # Piksel/frame
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(30) # ~30 FPS
        
        # Renkler
        self.color_bg = QColor("#0f172a") # Panel arka planıyla aynı veya transparan
        self.color_blocked = QColor("#ef4444") # Kırmızı (Engelli)
        self.color_active = QColor("#06b6d4") # Cyan (Aktif)
        self.color_path = QColor("#334155") # Gri (Yol)
        
    def set_connected(self, connected):
        self.is_connected = connected
        self.update()
        
    def update_animation(self):
        self.packet_offset += self.packet_speed
        if self.packet_offset > 100: # 100 birimlik döngü
            self.packet_offset = 0
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Koordinatlar
        w = self.width()
        h = self.height()
        
        # Dikey Merkez (Biraz yukarı alalım ki alt yazılar sığsın)
        cy = h / 2 - 10 
        
        # 1. İkonların Konumları
        icon_size = 40
        
        # Gamer (Sol)
        gamer_rect = QRectF(30, cy - icon_size/2, icon_size, icon_size)
        
        # Server (Sağ)
        server_rect = QRectF(w - 70, cy - icon_size/2, icon_size, icon_size)
        
        # Engel (Orta)
        obstacle_rect = QRectF(w/2 - 20, cy - 20, 40, 40)
        
        # 2. ÇİZİM: İkonlar
        
        # --- Gamer İkonu (Monitör + Kullanıcı Silüeti) ---
        painter.setPen(QPen(QColor("#94a3b8"), 2))
        painter.setBrush(Qt.NoBrush)
        
        # Monitör Çerçevesi
        painter.drawRoundedRect(gamer_rect, 5, 5)
        
        # Monitör Ayağı
        painter.drawLine(QPointF(gamer_rect.center().x(), gamer_rect.bottom()), QPointF(gamer_rect.center().x(), gamer_rect.bottom() + 5))
        painter.drawLine(QPointF(gamer_rect.center().x()-10, gamer_rect.bottom() + 5), QPointF(gamer_rect.center().x()+10, gamer_rect.bottom() + 5))

        # Kullanıcı Silüeti (İçeride)
        painter.setBrush(QColor("#3b82f6")) # Mavi dolgu
        painter.setPen(Qt.NoPen)
        
        # Kafa
        head_radius = 6
        head_center = QPointF(gamer_rect.center().x(), gamer_rect.center().y() - 5)
        painter.drawEllipse(head_center, head_radius, head_radius)
        
        # Omuzlar (Yay)
        path_shoulder = QPainterPath()
        path_shoulder.moveTo(gamer_rect.left() + 8, gamer_rect.bottom() - 5)
        path_shoulder.quadTo(gamer_rect.center().x(), gamer_rect.center().y() + 5, gamer_rect.right() - 8, gamer_rect.bottom() - 5)
        painter.drawPath(path_shoulder)
        
        
        # --- Server İkonu (Stack) ---
        painter.setPen(QPen(QColor("#94a3b8"), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(server_rect)
        painter.drawLine(QPointF(server_rect.left(), server_rect.top()+13), QPointF(server_rect.right(), server_rect.top()+13))
        painter.drawLine(QPointF(server_rect.left(), server_rect.top()+26), QPointF(server_rect.right(), server_rect.top()+26))
        
        # Sunucu Durum Işığı
        if self.is_connected:
            painter.setBrush(QColor("#22c55e")) # Yeşil ışık
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(server_rect.right()-8, server_rect.bottom()-8), 3, 3)
            painter.drawEllipse(QPointF(server_rect.right()-8, server_rect.top()+8), 3, 3)
        
        # 3. YOLLAR VE AKIŞ
        
        path = QPainterPath()
        path.moveTo(gamer_rect.right() + 5, cy)
        
        if not self.is_connected:
            # --- DURUM: ENGELLİ ---
            # Düz çizgi engele kadar
            path.lineTo(obstacle_rect.left() - 5, cy)
            
            # Yolu Çiz (Gri - Kesik Çizgi)
            painter.setPen(QPen(self.color_path, 2, Qt.DotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
            
            # Akan Paketler (Kırmızıya dönen)
            packet_color = self.color_blocked
            self.draw_packets(painter, path, packet_color, stop_at_end=True)
            
            # Engel Çiz (Kırmızı X)
            painter.setPen(QPen(self.color_blocked, 4))
            # X Şekli
            painter.drawLine(obstacle_rect.topLeft(), obstacle_rect.bottomRight())
            painter.drawLine(obstacle_rect.bottomLeft(), obstacle_rect.topRight())
            
            # Engel Yazısı (Geniş Alan)
            painter.setPen(QColor("#ef4444"))
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            # Alanı genişlet: x - 60, width + 120
            text_rect = obstacle_rect.adjusted(-60, 45, 60, 75) 
            painter.drawText(text_rect, Qt.AlignCenter, "ERİŞİM ENGELİ")

        else:
            # --- DURUM: TÜNELLEME (BYPASS) ---
            
            # Bezier Curve ile engelin üzerinden atla
            start_pt = QPointF(gamer_rect.right() + 5, cy)
            end_pt = QPointF(server_rect.left() - 5, cy)
            
            # Kavis yüksekliği ayarı: cy - 60 (Daha yumuşak kavis, kesilmez)
            ctrl1 = QPointF(w/2 - 40, cy - 80) 
            ctrl2 = QPointF(w/2 + 40, cy - 80)
            
            path.cubicTo(ctrl1, ctrl2, end_pt)
            
            # Yolu Çiz (Cyan - Glow Efektli)
            painter.setBrush(Qt.NoBrush)
            # Glow
            painter.setPen(QPen(QColor(6, 182, 212, 50), 8)) 
            painter.drawPath(path)
            # Ana Çizgi
            painter.setPen(QPen(self.color_active, 3))
            painter.drawPath(path)
            
            # Akan Paketler
            self.draw_packets(painter, path, QColor("#ffffff"), stop_at_end=False)
            
            # Engel (Pasif - Gri)
            painter.setPen(QPen(QColor("#334155"), 2))
            painter.drawLine(obstacle_rect.topLeft(), obstacle_rect.bottomRight())
            painter.drawLine(obstacle_rect.bottomLeft(), obstacle_rect.topRight())
            
            # Tünel Yazısı
            painter.setPen(self.color_active)
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            text_rect = QRectF(w/2 - 100, cy - 50, 200, 30) # Yazı 1 tık yukarı (cy - 50)
            painter.drawText(text_rect, Qt.AlignCenter, "GÜVENLİ TÜNEL")

    def draw_packets(self, painter, path, color, stop_at_end=False):
        # Yol üzerindeki belirli noktalara daireler çiz
        path_len = path.length()
        if path_len == 0: return

        # Kaç paket olacak?
        num_packets = 5
        spacing = 100 / num_packets # Yüzde olarak aralık
        
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        
        for i in range(num_packets):
            # Pozisyon hesapla (offset ile kaydır)
            pos_percent = (self.packet_offset + (i * spacing)) % 100
            
            # Eğer stop_at_end ise ve %90'ı geçtiyse çizme (Engele çarpıp yok oluyor)
            if stop_at_end and pos_percent > 90:
                continue
                
            # Path üzerinde yüzdeye denk gelen noktayı bul
            point = path.pointAtPercent(pos_percent / 100.0)
            
            # Çiz
            painter.drawEllipse(point, 4, 4)

def try_get_center(x, y):
    return QPointF(x, y)
