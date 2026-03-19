"""
Translator Settings Dialog
Settings for Translation Module
"""

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QGroupBox, QFormLayout, QLineEdit, QComboBox, QCheckBox, QPushButton, QHBoxLayout, QMessageBox, QTabWidget, QWidget
from PyQt5.QtCore import Qt
import os
import shutil

class TranslatorSettingsDialog(QDialog):
    def __init__(self, game_data, parent=None):
        super().__init__(parent)
        self.game_data = game_data
        self.parent = parent
        self.setWindowTitle(f"Çeviri Ayarları: {game_data.get('name')}")
        self.resize(500, 600)
        self.setStyleSheet("background-color: #1a1f2e; color: #e8edf2;")
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Sekmeli Yapı
        tabs = QTabWidget()
        tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #2d3748; } QTabBar::tab { background: #2d3748; color: #e8edf2; padding: 8px 12px; } QTabBar::tab:selected { background: #4a5568; font-weight: bold; }")
        
        # 1. Genel Ayarlar Tab'ı
        general_tab = QWidget()
        g_layout = QVBoxLayout(general_tab)
        
        # Font Ayarları Grubu (Unity için)
        if "Unity" in self.game_data.get('engine', ''):
            font_group = QGroupBox("🔤 Unity Font ve Karakter Düzeltme")
            font_group.setStyleSheet("QGroupBox { border: 1px solid #2d3748; border-radius: 6px; margin-top: 10px; padding-top: 15px; font-weight: bold; }")
            f_layout = QVBoxLayout()
            
            # Açıklama
            info = QLabel("Türkçe karakterlerin (ğ, ş, ı, ö, ü, ç) oyunda düzgün görünmesi için yapılandırma.")
            info.setWordWrap(True)
            info.setStyleSheet("color: #9ca3af; font-size: 11px; margin-bottom: 10px;")
            f_layout.addWidget(info)
            
            # Yöntem Seçimi
            self.font_mode_combo = QComboBox()
            self.font_mode_combo.addItems([
                "Dinamik Yapılandırma (Önerilen)",
                "TextMeshPro İzolatörü (Alternatif)",
                "Özel Font Dosyası (arialuni.unity3d)"
            ])
            self.font_mode_combo.setStyleSheet("padding: 5px; background-color: #0f1419; border: 1px solid #2d3748; border-radius: 4px;")
            f_layout.addWidget(QLabel("Düzeltme Yöntemi:"))
            f_layout.addWidget(self.font_mode_combo)
            
            # Uygula Butonu
            apply_font_btn = QPushButton("Uygula")
            apply_font_btn.setStyleSheet("background-color: #3b82f6; color: white; padding: 6px; border-radius: 4px; font-weight: bold;")
            apply_font_btn.setCursor(Qt.PointingHandCursor)
            apply_font_btn.clicked.connect(self.apply_unity_font_fix)
            f_layout.addWidget(apply_font_btn)
            
            font_group.setLayout(f_layout)
            g_layout.addWidget(font_group)

            # Temizlik Grubu (Unity)
            clean_group = QGroupBox("🧹 Temizlik ve Onarım")
            clean_group.setStyleSheet("QGroupBox { border: 1px solid #2d3748; border-radius: 6px; margin-top: 10px; padding-top: 15px; font-weight: bold; }")
            c_layout = QVBoxLayout()
            
            clean_btn = QPushButton("Oyunun Çeviri Araçlarını Temizle")
            clean_btn.setStyleSheet("background-color: #ef4444; color: white; padding: 8px; border-radius: 4px; font-weight: bold;")
            clean_btn.setCursor(Qt.PointingHandCursor)
            clean_btn.clicked.connect(self.clean_unity_tools)
            
            help_lbl = QLabel("Eğer oyun açılmıyorsa veya siyah ekranda kalıyorsa bu seçeneği kullanın.")
            help_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; font-style: italic;")
            
            c_layout.addWidget(clean_btn)
            c_layout.addWidget(help_lbl)
            clean_group.setLayout(c_layout)
            g_layout.addWidget(clean_group)
        else:
             g_layout.addWidget(QLabel("Bu oyun için özel ayar bulunmuyor."))
             
        g_layout.addStretch()
        tabs.addTab(general_tab, "Genel")
        
        # 2. Gelişmiş Tab (Placeholder)
        adv_tab = QWidget()
        a_layout = QVBoxLayout(adv_tab)
        a_layout.addWidget(QLabel("Gelişmiş ayarlar yakında..."))
        a_layout.addStretch()
        tabs.addTab(adv_tab, "Gelişmiş")

        layout.addWidget(tabs)

        # Kapat Butonu
        close_btn = QPushButton("Kapat")
        close_btn.setStyleSheet("background-color: #4b5563; color: white; padding: 8px; border-radius: 4px;")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)

    def apply_unity_font_fix(self):
        try:
            from unity_manager import UnityManager
        except ImportError:
            QMessageBox.critical(self, "Hata", "UnityManager modülü bulunamadı!")
            return

        mode_index = self.font_mode_combo.currentIndex() + 1 # 0->1, 1->2, 2->3
        game_path = self.game_data.get('exe', self.game_data.get('path')) # Exe or Folder
        
        if os.path.isfile(game_path):
             game_folder = os.path.dirname(game_path)
        else:
             game_folder = game_path

        # Mode 3 için font path (Opsiyonel - şimdilik otomatik indiriyor varsayalım veya kullanıcı manuel ekleyecek)
        font_path = None 
        if mode_index == 3:
             # Dosya seçtirilebilir veya varsayılan kullanılabilir
             # Şimdilik None geçiyoruz, UnityManager'da logic var mı bakalım
             pass

        success, msg = UnityManager.apply_turkish_font_fix(game_folder, mode=mode_index, font_path=font_path)
        
        if success:
            QMessageBox.information(self, "Başarılı", f"Font düzeltmesi uygulandı!\n\n{msg}")
        else:
            QMessageBox.critical(self, "Hata", f"İşlem başarısız:\n{msg}")

    def clean_unity_tools(self):
        # Temizleme işlemi (MemoFast GUI'deki mantığı çağıralım veya buraya taşıyalım)
        game_path = self.game_data.get('exe', self.game_data.get('path'))
        
        reply = QMessageBox.question(self, "Onay", 
            f"Bu işlem '{self.game_data.get('name')}' klasöründeki tüm çeviri araçlarını (BepInEx, AutoTranslator vb.) SİLECEKTİR.\n\nDevam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No)
            
        if reply == QMessageBox.Yes:
            try:
                from translator_manager import TranslatorManager
                success, msg = TranslatorManager.uninstall(game_path)
                if success:
                    QMessageBox.information(self, "Başarılı", "Temizlik tamamlandı!")
                else:
                    QMessageBox.warning(self, "Hata", f"Temizlik sırasında hata: {msg}")
            except Exception as e:
                QMessageBox.critical(self, "Hata", str(e))
