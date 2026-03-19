
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt

class WelcomeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MemoFast'e Hoş Geldiniz! 🚀")
        self.setFixedSize(600, 500)
        self.setStyleSheet("""
            QDialog { background-color: #1a1f2e; color: white; border: 1px solid #2d3748; }
            QLabel { color: #e8edf2; font-size: 14px; }
            QPushButton { background-color: #3b82f6; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-weight: bold; }
            QPushButton:hover { background-color: #2563eb; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Logo / Başlık
        title = QLabel("MEMOFAST\nOyun Çeviri ve Asistanı")
        title.setAlignment(Qt.AlignCenter)
        # title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title.setStyleSheet("font-size: 28px; font-weight: 900; color: #3b82f6; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # İçerik
        content_text = """
        <p style='font-size: 16px; margin-bottom: 15px;'>Merhaba! MemoFast ile oyun deneyiminizi bir üst seviyeye taşıyın.</p>
        
        <ul style='font-size: 14px; line-height: 1.6;'>
            <li>🎮 <b>Oyunlarınızı Otomatik Tanır:</b> Steam, Epic Games ve diğer platformlardaki oyunlarınızı otomatik bulur.</li>
            <li>🌍 <b>Tek Tıkla Türkçe Yama:</b> Unity ve Unreal Engine oyunlarını saniyeler içinde Türkçeye çevirir.</li>
            <li>⚡ <b>Performans Odaklı:</b> Oyunlarınızı optimize eder ve daha akıcı çalışmasını sağlar.</li>
            <li>🛡️ <b>Güvenli ve Pratik:</b> Oyun dosyalarınızı bozmadan, güvenli yöntemlerle yama yapar.</li>
        </ul>
        
        <p style='font-size: 13px; color: #ef4444; font-weight: bold; margin-top: 8px; border: 1px solid #ef4444; padding: 8px; border-radius: 6px; background-color: #2b1d1d;'>
            ⚠️ DİKKAT: AES Key şifrelemesi ile korunan bazı Unreal Engine oyunları bu sürümde çevrilememektedir.
        </p>
        
        <p style='font-size: 13px; color: #fbbf24; margin-top: 10px; font-weight: bold;'>
            📢 YENİLİKLER YOLDA: Godot ve diğer oyun motorları için destek çok yakında! 
            <br>Tüm güncellemelerden haberdar olmak ve destek için <span style='color: #ef4444;'>Mehmet Arı</span> kanalına abone olmayı unutmayın!
        </p>
        
        <p style='font-size: 14px; color: #9ca3af; margin-top: 15px;'>Başlamak için "Oyunları Tara" butonuna tıklayın veya listeden bir oyun seçip "Çevir" diyin.</p>
        """
        
        content = QLabel(content_text)
        content.setWordWrap(True)
        content.setTextFormat(Qt.RichText)
        content.setStyleSheet("color: #e8edf2;")
        layout.addWidget(content)
        
        layout.addStretch()
        
        # Butonlar
        h_layout = QHBoxLayout()
        h_layout.setSpacing(15)
        
        yt_btn = QPushButton("📺 Mehmet Arı Youtube")
        yt_btn.setFixedSize(180, 45)
        yt_btn.setCursor(Qt.PointingHandCursor)
        yt_btn.setStyleSheet("""
            QPushButton { background-color: #991b1b; color: white; border: 1px solid #ef4444; border-radius: 6px; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background-color: #dc2626; }
        """)
        import webbrowser
        yt_btn.clicked.connect(lambda: webbrowser.open("https://www.youtube.com/@MehmetariTv"))
        
        btn = QPushButton("Hadi Başlayalım! 🚀")
        btn.setFixedSize(180, 45)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.accept)
        
        h_layout.addStretch()
        h_layout.addWidget(yt_btn)
        h_layout.addWidget(btn)
        h_layout.addStretch()
        
        layout.addLayout(h_layout)

