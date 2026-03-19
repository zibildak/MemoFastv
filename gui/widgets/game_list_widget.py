"""
Game List Widget
Reusable game list display
"""

from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QMenu
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from logger import setup_logger

logger = setup_logger(__name__)


class GameListWidget(QListWidget):
    """
    Custom Game List Widget
    
    Features:
    - Display discovered games
    - Platform icons
    - Context menu support
    - Selection handling
    """
    
    game_selected = pyqtSignal(dict)  # Emits selected game data
    
    def __init__(self):
        """Initialize game list widget"""
        super().__init__()
        logger.info("Game List Widget initialized")
        
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
        
        self.itemClicked.connect(self.on_game_selected)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
    
    def add_game(self, game_data):
        """
        Add game to list
        
        Args:
            game_data: Dictionary with game info
                {
                    'name': 'Game Name',
                    'path': '/path/to/game',
                    'platform': 'Steam',
                    'type': 'Unity'
                }
        """
        item = QListWidgetItem()
        item.setText(f"🎮 {game_data.get('name', 'Unknown')} ({game_data.get('platform', 'Custom')})")
        item.setData(Qt.UserRole, game_data)
        self.addItem(item)
        logger.info(f"Game added: {game_data.get('name')}")
    
    def on_game_selected(self, item):
        """Handle game selection"""
        game_data = item.data(Qt.UserRole)
        self.game_selected.emit(game_data)
        logger.info(f"Game selected: {game_data.get('name')}")
    
    def show_context_menu(self, position):
        """Show context menu"""
        menu = QMenu()
        menu.addAction("Sil", self.delete_selected)
        menu.exec_(self.mapToGlobal(position))
    
    def delete_selected(self):
        """Delete selected game"""
        item = self.currentItem()
        if item:
            self.takeItem(self.row(item))
            logger.info("Game removed from list")
