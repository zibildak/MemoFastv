import sys
import os

file_path = r'c:\Users\Mehmet\Desktop\MemoFast 1.1.2\memofast_gui.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Line numbers from view_file are 1-indexed.
# We want to keep lines 1 to 1429 (indices 0 to 1428).
# We want to remove lines 1430 to 1526 (indices 1429 to 1525).
# Actually, let's check what's at 1526.
# 1526: self.error.emit(f"Genel Hata: {str(e)}")
# 1527: 
# 1528: class MainWindow...

new_lines = lines[:1429] + lines[1527:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Done")
