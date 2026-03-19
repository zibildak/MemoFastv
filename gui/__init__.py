"""
MemoFast GUI Module
Modularized PyQt5 interface components
"""

from .main_window import MemoFastMainWindow
from .pages import ScannerPage, TranslatorPage, SettingsPage, ToolsPage
from .dialogs import AESKeyDialog, ManualReviewDialog, WWMLoaderDialog
from .widgets import LogWidget, GameListWidget, TranslatorListWidget
from .styles import COLORS, DARK_THEME_STYLESHEET

__all__ = [
    'MemoFastMainWindow',
    'ScannerPage',
    'TranslatorPage',
    'SettingsPage',
    'ToolsPage',
    'AESKeyDialog',
    'ManualReviewDialog',
    'WWMLoaderDialog',
    'LogWidget',
    'GameListWidget',
    'TranslatorListWidget',
    'COLORS',
    'DARK_THEME_STYLESHEET',
]
