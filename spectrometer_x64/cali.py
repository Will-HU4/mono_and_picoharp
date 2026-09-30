import os
import sys
import pyvisa

# 1. Initialize VISA Search Paths
paths = [
    r'C:\Program Files\IVI Foundation\VISA\Win64\ktvisa\ktbin',
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

    import triax_320
    from spectrometer_function import generate_step_to_wavelength_mapping
    import time

    # 2. Connect Monochromator
    mono = triax_320.Triax320(resource_manager=rm, GPIB_address="GPIB0::1::INSTR")
    mono.connect_device()

    # CRITICAL FIX: Monochromator motor must be explicitly initialized
    print("\n--- Initializing Monochromator Motor ---")
    mono.init_motor()
    time.sleep(2)
    mono.slit_control(slit_num=0, width=500)
    time.sleep(2)
    mono.slit_control(slit_num=3, width=500)
    time.sleep(2)

    # 3. Define sequence of motor steps to scan
    scan_steps = list(range(0, 550000, 5000))

    # 4. Execute calibration & generate mapping.json
    print("\n--- Starting Calibration Scan ---")
    generate_step_to_wavelength_mapping(mono_instance=mono, steps_to_scan=scan_steps)

except Exception as e:
    print(f"Execution Error: {e}")

finally:
    if 'mono' in locals() and mono.device_connected:
        mono.close_device()
        print("Monochromator connection closed.")