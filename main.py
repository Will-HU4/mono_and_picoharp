# from plot_data import PlotData
import sys
import os
import pyvisa

paths = [
    r'C:\Program Files\IVI Foundation\VISA\Win64\ktvisa\ktbin',
    r'C:\Program Files\IVI Foundation\VISA\Win64\ktbin',
    r'C:\Windows\System32'
]

for path in paths:
    if os.path.exists(path):
        os.add_dll_directory(path)
        print(f"Added to DLL search path: {path}")

try:
    rm = pyvisa.ResourceManager()
    print("--- Success! ---")
    print(f"VISA Implementation: {rm.visalib}")
    print(f"Resources found: {rm.list_resources()}")
except Exception as e:
    print(f"--- Still failing ---")
    print(f"Error detail: {e}")
    
from PyQt6.QtWidgets import QApplication
from main_window_function import MainWindow

if __name__ == "__main__":
    # 1. Setup environment
    # setup_visa_paths()

    # 2. Initialize Application
    app = QApplication(sys.argv)
    
    # 3. SET DARK MODE DEFAULT
    # Fusion style is required for custom palettes to work properly on Windows
    app.setStyle("Fusion") 
    
    # Use the static method from your MainWindow class
    from main_window_function import get_dark_palette
    app.setPalette(get_dark_palette())
    
    # 4. Launch Window
    main_window = MainWindow()
    main_window.show()
    
    sys.exit(app.exec())
