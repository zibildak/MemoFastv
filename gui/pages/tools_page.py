from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QRadioButton, 
    QPushButton, QFileDialog, QHBoxLayout, QLineEdit, QMessageBox, QTextEdit
)
from PyQt5.QtCore import Qt
import os

# UnityManager Opsiyonel Import
try:
    from unity_manager import UnityManager
except ImportError:
    UnityManager = None
    print("ToolsPage: UnityManager import edilemedi.")

from logger import setup_logger

logger = setup_logger(__name__)

class ToolsPage(QWidget):
    """
    Tools Tab Page
    Araçlar ve Ekstra Düzeltme İşlemleri
    """
    
    def __init__(self):
        """Initialize tools page"""
        super().__init__()
        logger.info("Tools Page başlatılıyor")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # Başlık eklenebilir ama GroupBox zaten açıklayıcı
        
        # --- Group Box: Türkçe Karakter Düzeltici ---
        font_group = QGroupBox("Türkçe Karakter ve Font Düzeltici (Unity/XUnity)")
        font_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #555; margin-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }")
        
        font_layout = QVBoxLayout()
        font_layout.setSpacing(10)
        
        # 1. Oyun Seçimi
        lbl_game = QLabel("Hedef Oyun:")
        game_sel_layout = QHBoxLayout()
        self.game_path_edit = QLineEdit()
        self.game_path_edit.setPlaceholderText("Oyun klasörünü veya EXE dosyasını seçin...")
        btn_select_game = QPushButton("Oyun Seç")
        btn_select_game.clicked.connect(self.select_game)
        game_sel_layout.addWidget(self.game_path_edit)
        game_sel_layout.addWidget(btn_select_game)
        
        font_layout.addWidget(lbl_game)
        font_layout.addLayout(game_sel_layout)
        
        # 2. Mod Seçenekleri
        lbl_mode = QLabel("Düzeltme Yöntemi:")
        font_layout.addWidget(lbl_mode)
        
        self.radio_mode1 = QRadioButton("Yöntem 1: Config Düzenle (Dynamic Mode + Fallback Fonts)")
        self.radio_mode1.setToolTip("OverrideFontMode=Dynamic yapar ve yaygın fontları ekler. (Önerilen İlk Adım)")
        self.radio_mode1.setChecked(True)
        
        self.radio_mode2 = QRadioButton("Yöntem 2: TextMeshPro (TMP) Fix")
        self.radio_mode2.setToolTip("Modern oyunlar için TMP Isolator açar ve Arial fontunu zorlar. (Yöntem 1 işe yaramazsa)")
        
        self.radio_mode3 = QRadioButton("Yöntem 3: Font Dosyası Ekle (arialuni.unity3d)")
        self.radio_mode3.setToolTip("Kesin Çözüm: Font dosyasını oyun klasörüne kopyalar ve zorlar.")
        self.radio_mode3.toggled.connect(self.on_mode_changed)
        
        font_layout.addWidget(self.radio_mode1)
        font_layout.addWidget(self.radio_mode2)
        font_layout.addWidget(self.radio_mode3)
        
        # 3. Font Dosyası Seçimi (Sadece Mod 3 için)
        self.font_file_widget = QWidget()
        font_file_layout = QHBoxLayout()
        font_file_layout.setContentsMargins(0,0,0,0)
        self.font_path_edit = QLineEdit()
        self.font_path_edit.setPlaceholderText("arialuni.unity3d dosyasını seçin...")
        
        # Otomatik tanımlama: Eğer files/libs/arialuni.unity3d varsa varsayılan yap
        default_font = os.path.join(os.getcwd(), "files", "libs", "arialuni.unity3d")
        if os.path.exists(default_font):
            self.font_path_edit.setText(default_font)

        btn_select_font = QPushButton("Font Dosyası Seç")
        btn_select_font.clicked.connect(self.select_font_file)
        font_file_layout.addWidget(self.font_path_edit)
        font_file_layout.addWidget(btn_select_font)
        self.font_file_widget.setLayout(font_file_layout)
        self.font_file_widget.setVisible(False) # Başlangıçta gizli
        
        font_layout.addWidget(self.font_file_widget)
        
        # 4. Uygula Butonu
        btn_apply = QPushButton("Düzeltmeyi Uygula")
        btn_apply.setStyleSheet("QPushButton { background-color: #27ae60; color: white; font-weight: bold; padding: 8px; border-radius: 4px; } QPushButton:hover { background-color: #2ecc71; }")
        btn_apply.clicked.connect(self.apply_fix)
        font_layout.addWidget(btn_apply)
        
        font_group.setLayout(font_layout)
        layout.addWidget(font_group)
        
        # Status Log
        lbl_log = QLabel("İşlem Kaydı:")
        layout.addWidget(lbl_log)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(150)
        self.log_area.setPlaceholderText("İşlem sonuçları burada görünecek...")
        layout.addWidget(self.log_area)
        
        layout.addStretch()
        self.setLayout(layout)

    def select_game(self):
        path, _ = QFileDialog.getOpenFileName(self, "Oyun Seç", "", "Executable (*.exe);;All Files (*)")
        if path:
            self.game_path_edit.setText(path)
            
    def select_font_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Font Dosyası Seç", "", "Unity3D Files (*.unity3d);;All Files (*)")
        if path:
            self.font_path_edit.setText(path)
            
    def on_mode_changed(self):
        self.font_file_widget.setVisible(self.radio_mode3.isChecked())

    def log(self, msg):
        self.log_area.append(f" >> {msg}")
        # Scroll to bottom
        sb = self.log_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def apply_fix(self):
        game_path = self.game_path_edit.text()
        if not game_path:
            QMessageBox.warning(self, "Hata", "Lütfen bir oyun seçin.")
            return
            
        if not UnityManager:
            self.log("HATA: UnityManager modülü yüklenemediği için işlem yapılamıyor.")
            QMessageBox.critical(self, "Hata", "UnityManager modülü eksik.")
            return

        mode = 1
        font_path = None
        
        if self.radio_mode2.isChecked(): mode = 2
        elif self.radio_mode3.isChecked(): 
            mode = 3
            font_path = self.font_path_edit.text()
            if not font_path:
                QMessageBox.warning(self, "Hata", "Mod 3 için font dosyasını seçmeniz gerekmektedir.")
                return

        self.log(f"İşlem başlatılıyor... Yöntem: {mode}")
        if mode == 3: self.log(f"Font Kaynağı: {font_path}")
        
        result, msg = UnityManager.apply_turkish_font_fix(game_path, mode, font_path)
        
        if result:
            self.log(f"✅ BAŞARILI: {msg}")
            QMessageBox.information(self, "Tamamlandı", msg)
        else:
            self.log(f"❌ HATA: {msg}")
            QMessageBox.critical(self, "Hata", msg)
