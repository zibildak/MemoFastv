import sys
import json
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QTextEdit, QPushButton, QFileDialog, 
                             QMessageBox, QFrame, QScrollArea, QListWidget, QListWidgetItem,
                             QComboBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon

class UpdateBuilder(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MemoFast - Update JSON Builder")
        self.setMinimumSize(800, 700)
        self.setStyleSheet("""
            QMainWindow { background-color: #0f172a; }
            QWidget { background-color: #0f172a; color: #e2e8f0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
            QLabel { font-weight: bold; color: #94a3b8; }
            QLineEdit, QTextEdit, QComboBox { 
                background-color: #1e293b; 
                border: 1px solid #334155; 
                border-radius: 6px; 
                padding: 8px; 
                color: white;
            }
            QLineEdit:focus, QTextEdit:focus { border-color: #3b82f6; }
            QPushButton { 
                background-color: #3b82f6; 
                color: white; 
                border-radius: 6px; 
                padding: 10px; 
                font-weight: bold; 
                border: none;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton#addBtn { background-color: #10b981; }
            QPushButton#removeBtn { background-color: #ef4444; }
            QPushButton#loadBtn { background-color: #6366f1; }
            QFrame#card { background-color: #1e293b; border-radius: 12px; border: 1px solid #334155; }
        """)

        # Data
        self.files = []
        self.current_file_path = None

        container = QWidget()
        self.setCentralWidget(container)
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(20)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("🚀 Update Builder")
        title.setStyleSheet("font-size: 24px; color: #f8fafc; font-weight: 800;")
        header_layout.addWidget(title)
        
        load_btn = QPushButton("📂 Eski JSON Seç")
        load_btn.setObjectName("loadBtn")
        load_btn.setFixedWidth(150)
        load_btn.clicked.connect(self.load_json)
        header_layout.addWidget(load_btn)
        main_layout.addLayout(header_layout)

        # Scroll Area for Form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        form_content = QWidget()
        form_layout = QVBoxLayout(form_content)
        form_layout.setSpacing(15)

        # 1. Version & Force Update
        v_layout = QHBoxLayout()
        v_vlayout = QVBoxLayout()
        v_vlayout.addWidget(QLabel("Versiyon (Örn: 1.1.8)"))
        self.version_input = QLineEdit()
        v_vlayout.addWidget(self.version_input)
        v_layout.addLayout(v_vlayout)

        f_vlayout = QVBoxLayout()
        f_vlayout.addWidget(QLabel("Zorunlu Güncelleme?"))
        self.force_combo = QComboBox()
        self.force_combo.addItems(["Hayır", "Evet"])
        f_vlayout.addWidget(self.force_combo)
        v_layout.addLayout(f_vlayout)
        form_layout.addLayout(v_layout)

        # 2. Bulletin Settings
        b_card = QFrame()
        b_card.setObjectName("card")
        b_layout = QVBoxLayout(b_card)
        b_layout.addWidget(QLabel("📢 Bülten / Duyuru Metni"))
        self.bulletin_input = QLineEdit()
        self.bulletin_input.setPlaceholderText("Uygulama kütüphanesinde görünecek mesaj...")
        b_layout.addWidget(self.bulletin_input)

        t_layout = QHBoxLayout()
        t_layout.addWidget(QLabel("Duyuru Tipi:"))
        self.bulletin_type = QComboBox()
        self.bulletin_type.addItems(["info", "success", "warning"])
        t_layout.addWidget(self.bulletin_type)
        t_layout.addStretch()
        b_layout.addLayout(t_layout)
        form_layout.addWidget(b_card)

        # 3. Changelog
        form_layout.addWidget(QLabel("📝 Değişiklik Listesi (Satır satır yazın)"))
        self.changelog_input = QTextEdit()
        self.changelog_input.setPlaceholderText("- Hata düzeltildi\n- Yeni özellik eklendi...")
        self.changelog_input.setFixedHeight(120)
        form_layout.addWidget(self.changelog_input)

        # 4. Files List
        form_layout.addWidget(QLabel("📦 Dosyalar (İndirilecek Linkler)"))
        self.files_list = QListWidget()
        self.files_list.setFixedHeight(150)
        form_layout.addWidget(self.files_list)

        file_tools = QHBoxLayout()
        self.file_url = QLineEdit()
        self.file_url.setPlaceholderText("İndirme URL'si (ZIP/EXE)")
        self.file_target = QLineEdit()
        self.file_target.setText(".")
        self.file_target.setPlaceholderText("Hedef Yol ( . = Ana Dizin)")
        self.file_target.setFixedWidth(120)
        
        add_file_btn = QPushButton("➕ Ekle")
        add_file_btn.setObjectName("addBtn")
        add_file_btn.clicked.connect(self.add_file_item)
        
        rem_file_btn = QPushButton("🗑️ Sil")
        rem_file_btn.setObjectName("removeBtn")
        rem_file_btn.clicked.connect(self.remove_file_item)
        
        file_tools.addWidget(self.file_url)
        file_tools.addWidget(self.file_target)
        file_tools.addWidget(add_file_btn)
        file_tools.addWidget(rem_file_btn)
        form_layout.addLayout(file_tools)

        scroll.setWidget(form_content)
        main_layout.addWidget(scroll)

        # Save Actions
        actions = QHBoxLayout()
        save_as_btn = QPushButton("💾 Farklı Kaydet")
        save_as_btn.clicked.connect(lambda: self.save_json(True))
        
        self.save_quick_btn = QPushButton("✅ JSON OLUŞTUR / GÜNCELLE")
        self.save_quick_btn.setStyleSheet("height: 50px; background-color: #10b981; font-size: 16px;")
        self.save_quick_btn.clicked.connect(lambda: self.save_json(False))
        
        actions.addWidget(save_as_btn)
        actions.addWidget(self.save_quick_btn)
        main_layout.addLayout(actions)

    def add_file_item(self):
        url = self.file_url.text().strip()
        target = self.file_target.text().strip()
        if url:
            item_text = f"{url}  ->  [{target}]"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, {"url": url, "target_path": target})
            self.files_list.addItem(item)
            self.file_url.clear()

    def remove_file_item(self):
        current_item = self.files_list.currentItem()
        if current_item:
            self.files_list.takeItem(self.files_list.row(current_item))

    def load_json(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "updates.json Seç", "", "JSON Files (*.json)")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.current_file_path = file_path
                self.version_input.setText(data.get("version", ""))
                self.force_combo.setCurrentIndex(1 if data.get("force_update") else 0)
                self.bulletin_input.setText(data.get("bulletin", ""))
                
                b_type = data.get("bulletin_type", "info")
                idx = self.bulletin_type.findText(b_type)
                if idx >= 0: self.bulletin_type.setCurrentIndex(idx)
                
                changelog = data.get("changelog", [])
                self.changelog_input.setText("\n".join(changelog))
                
                self.files_list.clear()
                for f in data.get("files", []):
                    item_text = f"{f.get('url')}  ->  [{f.get('target_path')}]"
                    item = QListWidgetItem(item_text)
                    item.setData(Qt.UserRole, f)
                    self.files_list.addItem(item)
                
                QMessageBox.information(self, "Başarılı", "JSON başarıyla yüklendi!")
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Yükleme hatası: {e}")

    def save_json(self, save_as=False):
        data = {
            "version": self.version_input.text().strip(),
            "bulletin": self.bulletin_input.text().strip(),
            "bulletin_type": self.bulletin_type.currentText(),
            "force_update": self.force_combo.currentIndex() == 1,
            "changelog": [line.strip() for line in self.changelog_input.toPlainText().split('\n') if line.strip()],
            "files": []
        }

        for i in range(self.files_list.count()):
            data["files"].append(self.files_list.item(i).data(Qt.UserRole))

        if save_as or not self.current_file_path:
            file_path, _ = QFileDialog.getSaveFileName(self, "JSON Kaydet", "updates.json", "JSON Files (*.json)")
            if file_path:
                self.current_file_path = file_path
            else:
                return

        try:
            with open(self.current_file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            QMessageBox.information(self, "Başarılı", f"Dosya kaydedildi:\n{self.current_file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kaydetme hatası: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = UpdateBuilder()
    window.show()
    sys.exit(app.exec_())
