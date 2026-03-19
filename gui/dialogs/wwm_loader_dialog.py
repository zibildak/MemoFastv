"""
WWM Loader Dialog
Load WWM translation mods
"""

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
from logger import setup_logger

logger = setup_logger(__name__)


class WWMLoaderDialog(QDialog):
    """
    WWM Loader Dialog
    
    Used when:
    - Loading WWM (What's Wrong Mod) translations
    - Displaying loader status
    """
    
    def __init__(self, game_path, parent=None):
        """
        Initialize WWM loader dialog
        
        Args:
            game_path: Path to game directory
            parent: Parent widget
        """
        super().__init__(parent)
        logger.info(f"WWM Loader Dialog opened for {game_path}")
        
        self.game_path = game_path
        self.setWindowTitle("WWM Loader")
        self.setGeometry(100, 100, 400, 200)
        
        layout = QVBoxLayout()
        
        label = QLabel(f"WWM Loading...\n{game_path}")
        layout.addWidget(label)
        
        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
