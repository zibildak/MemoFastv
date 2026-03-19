"""
Translator List Widget
Display available translators
"""

from PyQt5.QtWidgets import QListWidget, QListWidgetItem
from PyQt5.QtCore import Qt, pyqtSignal
from logger import setup_logger

logger = setup_logger(__name__)


class TranslatorListWidget(QListWidget):
    """
    Translator List Widget
    
    Features:
    - Display available translators
    - Type indicators (BepInEx, MelonLoader, etc.)
    - Architecture support info
    """
    
    translator_selected = pyqtSignal(str)  # Emits selected translator name
    
    def __init__(self):
        """Initialize translator list widget"""
        super().__init__()
        logger.info("Translator List Widget initialized")
        
        self.setStyleSheet("""
            QListWidget {
                background-color: #1a1f2e;
                color: #ffffff;
                border: 1px solid #334155;
            }
            QListWidget::item:selected {
                background-color: #2563eb;
            }
        """)
        
        self.itemClicked.connect(self.on_translator_selected)
    
    def add_translator(self, translator_info):
        """
        Add translator to list
        
        Args:
            translator_info: Dictionary with translator details
                {
                    'name': 'BepInEx',
                    'type': 'Framework',
                    'architecture': 'x64, x86',
                    'supported_games': ['Game1', 'Game2']
                }
        """
        item = QListWidgetItem()
        name = translator_info.get('name', 'Unknown')
        type_ = translator_info.get('type', '')
        arch = translator_info.get('architecture', '')
        
        display_text = f"📦 {name}"
        if type_:
            display_text += f" ({type_})"
        if arch:
            display_text += f" [{arch}]"
        
        item.setText(display_text)
        item.setData(Qt.UserRole, translator_info)
        self.addItem(item)
        logger.info(f"Translator added: {name}")
    
    def on_translator_selected(self, item):
        """Handle translator selection"""
        translator_data = item.data(Qt.UserRole)
        self.translator_selected.emit(translator_data.get('name', ''))
        logger.info(f"Translator selected: {translator_data.get('name')}")
