"""
Scanner Page
Game discovery and scanning interface
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from logger import setup_logger

logger = setup_logger(__name__)


class ScannerPage(QWidget):
    """
    Scanner Tab Page
    
    Features:
    - Game discovery
    - Multi-platform scanning
    - Progress display
    """
    
    def __init__(self):
        """Initialize scanner page"""
        super().__init__()
        logger.info("Scanner Page başlatılıyor")
        
        layout = QVBoxLayout()
        label = QLabel("Scanner Page")
        layout.addWidget(label)
        
        self.setLayout(layout)
