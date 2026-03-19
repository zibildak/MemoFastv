"""
Log Widget
Custom log display widget
"""

from PyQt5.QtWidgets import QListWidget, QListWidgetItem
from PyQt5.QtCore import Qt
from logger import setup_logger

logger = setup_logger(__name__)


class LogWidget(QListWidget):
    """
    Custom Log Display Widget
    
    Features:
    - Color-coded log levels
    - Auto-scroll to bottom
    - Clear functionality
    """
    
    def __init__(self):
        """Initialize log widget"""
        super().__init__()
        logger.info("Log Widget initialized")
        self.setStyleSheet("""
            QListWidget {
                background-color: #1a1f2e;
                color: #ffffff;
                border: 1px solid #334155;
            }
        """)
    
    def add_log(self, message, level="INFO"):
        """
        Add log message
        
        Args:
            message: Log message text
            level: Log level (INFO, WARNING, ERROR, SUCCESS)
        """
        item = QListWidgetItem(message)
        
        # Color coding by level
        if level == "ERROR":
            item.setForeground(Qt.red)
        elif level == "WARNING":
            item.setForeground(Qt.yellow)
        elif level == "SUCCESS":
            item.setForeground(Qt.green)
        else:
            item.setForeground(Qt.white)
        
        self.addItem(item)
        self.scrollToBottom()
    
    def clear_logs(self):
        """Clear all logs"""
        self.clear()
        logger.info("Logs cleared")
