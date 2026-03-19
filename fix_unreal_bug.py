
import os

target_file = r"c:\Users\Mehmet\Desktop\MemoFast 1.1.2\unreal_manager.py"

with open(target_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    new_lines.append(line)
    if "bin_ver = PakManager.detect_pak_version_binary(target_pak)" in line:
        indent = line[:line.find("bin_ver")]
        fix_code = [
            "\n",
            f"{indent}# [FIX] Repak V12 Limitation\n",
            f"{indent}if bin_ver and (bin_ver == 'V12' or (len(bin_ver)>1 and bin_ver[1:].isdigit() and int(bin_ver[1:]) > 11)):\n",
            f"{indent}     bin_ver = 'V11'\n",
            "\n"
        ]
        new_lines.extend(fix_code)
        print("Fix applied!")

with open(target_file, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Done.")
