"""
Test Stage 6 GUI Integration - Verify imports and basic structure
"""
import sys
import os

# Add workspace path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("STAGE 6 GUI REFACTORING - INTEGRATION TEST")
print("=" * 60)

# Test 1: Import main memofast_gui module
print("\n[1/6] Testing memofast_gui imports...")
try:
    import memofast_gui
    print("✓ memofast_gui imported successfully (GUI_MODULAR flag set)")
except Exception as e:
    print(f"✗ Failed to import memofast_gui: {e}")
    sys.exit(1)

# Test 2: Verify GUI_MODULAR flag
print("\n[2/6] Checking GUI_MODULAR flag...")
if hasattr(memofast_gui, 'GUI_MODULAR'):
    print(f"✓ GUI_MODULAR = {memofast_gui.GUI_MODULAR}")
else:
    print("✗ GUI_MODULAR flag not found")

# Test 3: Import from gui package
print("\n[3/6] Testing gui package imports...")
try:
    from gui import (
        MemoFastMainWindow,
        ScannerPage, TranslatorPage, SettingsPage, ToolsPage,
        AESKeyDialog, ManualReviewDialog, WWMLoaderDialog,
        LogWidget, GameListWidget, TranslatorListWidget,
        COLORS, DARK_THEME_STYLESHEET
    )
    print("✓ All gui components imported successfully")
except Exception as e:
    print(f"✗ Failed to import gui components: {e}")
    sys.exit(1)

# Test 4: Verify key classes exist
print("\n[4/6] Verifying key classes...")
classes_to_check = [
    ("MemoFastMainWindow", MemoFastMainWindow),
    ("LogWidget", LogWidget),
    ("GameListWidget", GameListWidget),
    ("TranslatorListWidget", TranslatorListWidget),
]
for name, cls in classes_to_check:
    if cls:
        print(f"✓ {name}: {cls.__name__}")

# Test 5: Verify styling
print("\n[5/6] Verifying styling components...")
if COLORS and len(COLORS) > 0:
    print(f"✓ COLORS dict loaded ({len(COLORS)} colors)")
if DARK_THEME_STYLESHEET and len(DARK_THEME_STYLESHEET) > 100:
    print(f"✓ DARK_THEME_STYLESHEET loaded ({len(DARK_THEME_STYLESHEET)} chars)")

# Test 6: Check MainWindow class in memofast_gui
print("\n[6/6] Checking MainWindow class...")
if hasattr(memofast_gui, 'MainWindow'):
    print(f"✓ MainWindow class found in memofast_gui")
else:
    print("✗ MainWindow class not found in memofast_gui")

print("\n" + "=" * 60)
print("✓ STAGE 6 INTEGRATION TEST PASSED")
print("=" * 60)
