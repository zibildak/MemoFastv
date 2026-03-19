"""
MemoFast Main Window Adapter
Bridges the modular gui/ structure with the legacy memofast_gui.py MainWindow
"""

import sys
import os
from pathlib import Path
from PyQt5.QtWidgets import QMainWindow, QApplication, QMessageBox
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QIcon, QFont

from config import Config, Constants
from logger import setup_logger

logger = setup_logger(__name__)


class MemoFastMainWindow(QMainWindow):
    """
    MemoFast Main Application Window Adapter
    
    This is a placeholder/adapter class that allows the modular gui/ package
    to coexist with the legacy memofast_gui.py implementation.
    
    The actual MainWindow class is defined in memofast_gui.py as "MainWindow"
    and will be imported and re-exported here for compatibility.
    """
    
    def __init__(self):
        """Initialize main window adapter"""
        super().__init__()
        logger.info("MemoFast Main Window Adapter başlatılıyor")
        
        self.setWindowTitle("MemoFast 1.1.2")
        self.setGeometry(100, 100, 1600, 950)
        
        # Placeholder - actual implementation in memofast_gui.py
        self.settings = {}
        self.current_game = None
        self.scan_results = {}
        
        # Theme apply
        self.apply_dark_theme()
        
    def apply_dark_theme(self):
        """Apply dark theme styling"""
        from gui.styles.colors import DARK_THEME_STYLESHEET
        self.setStyleSheet(DARK_THEME_STYLESHEET)
        logger.debug("Dark theme applied")
        
    def closeEvent(self, event):
        """Handle window close event"""
        logger.info("MemoFast kapatılıyor")
        event.accept()
