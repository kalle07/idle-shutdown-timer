import os
import shutil
import subprocess
import sys

APP_NAME = "shutdown-timer"
ENTRY_SCRIPT = "shutdown-timer_04_tray.py"  # Change to your actual filename

# Clean previous builds
for folder in ("build", "dist"):
    if os.path.exists(folder):
        shutil.rmtree(folder)

spec_file = f"{APP_NAME}.spec"
if os.path.exists(spec_file):
    os.remove(spec_file)

cmd = [
    sys.executable,
    "-m",
    "PyInstaller",
    #"--noconsole",
    '--console',
    "--onefile",
    #"--onedir",
    "--windowed",              # No console window
    "--clean",
    "--noconfirm",

    "--name",
    APP_NAME,

    # Hidden imports
    "--hidden-import=psutil",
    "--hidden-import=ctypes",
    "--hidden-import=collections",
    "--hidden-import=typing",
    "--hidden-import=pystray",
    "--hidden-import=PIL",
    "--hidden-import=subprocess",
    "--hidden-import=tkinter",

    ENTRY_SCRIPT,
]

print("Running:")
print(" ".join(cmd))
print()

subprocess.run(cmd, check=True)

print()
print("Build complete.")
print(f"Executable: dist\\{APP_NAME}.exe")