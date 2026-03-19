"""
AES Key Dialog
Request and validate AES keys from user
"""

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt
from logger import setup_logger

logger = setup_logger(__name__)


class AESKeyDialog(QDialog):
    """
    AES Key Request Dialog
    
    Used when:
    - Game memory needs AES key for decryption
    - Multiple keys available for selection
    """
    
    def __init__(self, game_name, parent=None):
        """
        Initialize AES key dialog
        
        Args:
            game_name: Name of the game requiring key
            parent: Parent widget
        """
        super().__init__(parent)
        logger.info(f"AES Key Dialog opened for {game_name}")
        
        self.setWindowTitle(f"AES Key - {game_name}")
        self.setGeometry(100, 100, 400, 150)
        
        layout = QVBoxLayout()
        
        label = QLabel(f"AES Key girin ({game_name}):")
        layout.addWidget(label)
        
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("64 hex characters...")
        layout.addWidget(self.key_input)
        
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("Tamam")
        cancel_btn = QPushButton("İptal")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
    
    def get_key(self):
        """Get entered AES key"""
        return self.key_input.text()
