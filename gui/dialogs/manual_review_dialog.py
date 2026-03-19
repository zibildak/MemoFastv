"""
Manual Review Dialog
Allow user to review and edit translation files
"""

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from logger import setup_logger

logger = setup_logger(__name__)


class ManualReviewDialog(QDialog):
    """
    Manual Review Dialog
    
    Used when:
    - Translation completed but not packaged
    - User needs to review/edit CSV
    """
    
    def __init__(self, file_path, parent=None):
        """
        Initialize manual review dialog
        
        Args:
            file_path: Path to translation CSV file
            parent: Parent widget
        """
        super().__init__(parent)
        logger.info(f"Manual Review Dialog opened for {file_path}")
        
        self.file_path = file_path
        self.setWindowTitle("Çeviri Dosyası Hazır")
        self.setGeometry(100, 100, 500, 300)
        
        layout = QVBoxLayout()
        
        label = QLabel("Çeviri tamamlandı. CSV dosyasını düzenleyebilirsiniz.")
        layout.addWidget(label)
        
        btn_layout = QHBoxLayout()
        open_btn = QPushButton("📂 CSV Dosyasını Aç")
        continue_btn = QPushButton("Devam Et")
        open_btn.clicked.connect(self.open_file)
        continue_btn.clicked.connect(self.accept)
        btn_layout.addWidget(open_btn)
        btn_layout.addWidget(continue_btn)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
    
    def open_file(self):
        """Open CSV file in text editor"""
        import subprocess
        try:
            subprocess.Popen(["notepad.exe", self.file_path])
        except Exception as e:
            logger.error(f"Cannot open file: {e}")
