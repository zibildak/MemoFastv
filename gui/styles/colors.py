"""
MemoFast Styling & Color Palette
Dark theme and color definitions
"""

# Color Palette (Dark Theme)
COLORS = {
    # Primary
    "primary": "#2563eb",
    "primary_hover": "#1d4ed8",
    "primary_light": "#3b82f6",
    
    # Background
    "bg_main": "#0f1419",
    "bg_secondary": "#1a1f2e",
    "bg_tertiary": "#2d3748",
    
    # Text
    "text_primary": "#ffffff",
    "text_secondary": "#94a3b8",
    "text_muted": "#64748b",
    
    # Accent
    "accent_success": "#10b981",
    "accent_warning": "#f59e0b",
    "accent_danger": "#ef4444",
    "accent_info": "#3b82f6",
    
    # Borders
    "border": "#334155",
    "border_light": "#475569",
}

DARK_THEME_STYLESHEET = """
QMainWindow, QDialog, QWidget {
    background-color: #0f1419;
    color: #ffffff;
}

QTabWidget::pane {
    border: 1px solid #334155;
}

QTabBar::tab {
    background-color: #1a1f2e;
    color: #94a3b8;
    padding: 8px 20px;
    border: 1px solid #334155;
    border-bottom: 2px solid transparent;
}

QTabBar::tab:selected {
    background-color: #2d3748;
    color: #ffffff;
    border-bottom: 2px solid #2563eb;
}

QTabBar::tab:hover {
    background-color: #2d3748;
}

QPushButton {
    background-color: #2563eb;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #1d4ed8;
}

QPushButton:pressed {
    background-color: #1e40af;
}

QLineEdit, QTextEdit, QComboBox {
    background-color: #1a1f2e;
    color: #ffffff;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 6px;
    selection-background-color: #2563eb;
}

QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 2px solid #2563eb;
}

QListWidget, QTableWidget {
    background-color: #1a1f2e;
    color: #ffffff;
    border: 1px solid #334155;
    gridline-color: #2d3748;
}

QListWidget::item:selected, QTableWidget::item:selected {
    background-color: #2563eb;
}

QHeaderView::section {
    background-color: #2d3748;
    color: #ffffff;
    padding: 5px;
    border: 1px solid #334155;
}

QLabel {
    color: #ffffff;
}

QProgressBar {
    background-color: #2d3748;
    border: 1px solid #334155;
    border-radius: 4px;
    height: 24px;
}

QProgressBar::chunk {
    background-color: #10b981;
    border-radius: 4px;
}

QScrollBar:vertical {
    background-color: #1a1f2e;
    width: 12px;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #475569;
    border-radius: 6px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #64748b;
}

QMessageBox QLabel {
    color: #ffffff;
}

QMessageBox QPushButton {
    min-width: 60px;
}
"""
