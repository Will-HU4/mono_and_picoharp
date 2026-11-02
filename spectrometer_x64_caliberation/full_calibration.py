# run_full_calibration.py
import os
import sys
import time
import datetime
import json
import glob
import ctypes
from ctypes import c_uint64, c_float, byref
import pyvisa
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

# ---------------------------------------------------------
# 1. CONFIGURATION & PATHS (Portable / Relative Paths)
# ---------------------------------------------------------
VISA_PATHS = [
    r'C:\Program Files\IVI Foundation\VISA\Win64\ktvisa\ktbin',
    r'C:\Windows\System32'
]

# Get the absolute folder path where this current script is saved
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Create a local 'data sets' folder inside your project directory
BASE_DATA_DIR = os.path.join(SCRIPT_DIR, "data sets")

# Create a unique, timestamped subfolder for this specific run
timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
DATA_DIR = os.path.join(BASE_DATA_DIR, f"calibration_{timestamp}")

# Output paths inside the new unique folder
OUTPUT_JSON = os.path.join(DATA_DIR, "mapping_sine.json")

# OTO Spectrometer Constants
SPEC_VID = 1592
SPEC_PID = 2732
DLL_PATH = os.path.join(SCRIPT_DIR, "UserApplication.dll")
# ---------------------------------------------------------
# 2. SPECTROMETER & ADAPTIVE ACQUISITION HELPERS
# ---------------------------------------------------------

# Fixed acquisition settings for all steps
FIXED_INTEGRATION_TIME_MS = 50.0  # ms
FIXED_AVG_COUNT = 5               # scans

def connect_spectrometer(dll_path=DLL_PATH):
    try:
        oto_dll = ctypes.cdll.LoadLibrary(dll_path)
    except Exception as e:
        print(f"Failed to load spectrometer DLL: {e}")
        return None, None, None, None

    device_amount = c_uint64(0)
    oto_dll.UAI_SpectrometerGetDeviceAmount.restype = ctypes.c_uint64
    oto_dll.UAI_SpectrometerGetDeviceAmount(SPEC_VID, SPEC_PID, byref(device_amount))

    if device_amount.value < 1:
        print("No OTO spectrometer device found.")
        return None, None, None, None

    device_handle = c_uint64(0)
    oto_dll.UAI_SpectrometerOpen.restype = ctypes.c_uint64
    oto_dll.UAI_SpectrometerOpen(0, byref(device_handle), SPEC_VID, SPEC_PID)

    framesize = c_uint64(0)
    oto_dll.UAI_SpectromoduleGetFrameSize.restype = ctypes.c_uint64
    oto_dll.UAI_SpectromoduleGetFrameSize(device_handle, byref(framesize))

    temp_lambda = (c_float * framesize.value)()
    oto_dll.UAI_SpectrometerWavelengthAcquire(device_handle, byref(temp_lambda))
    wavelengths = [temp_lambda[i] for i in range(framesize.value)]

    print(f"Spectrometer connected successfully. Handle: {device_handle.value}")
    return oto_dll, device_handle, framesize, wavelengths

def acquire_spectrum(oto_dll, device_handle, framesize, wavelengths, integration_time_ms, avg_count):
    temp_intensity = (c_float * framesize.value)()
    integrating_time_us = int(integration_time_ms * 1000)

    # Hardware averaging via DLL
    oto_dll.UAI_SpectrometerDataOneshot(
        device_handle, integrating_time_us, byref(temp_intensity), avg_count
    )
    oto_dll.UAI_BackgroundRemove(device_handle, integrating_time_us, byref(temp_intensity))
    oto_dll.UAI_LinearityCorrection(device_handle, framesize, byref(temp_intensity))

    return [temp_intensity[i] for i in range(framesize.value)]

# ---------------------------------------------------------
# 3. SINE GRATING MODEL DEFINITION
# ---------------------------------------------------------
def sine_grating_model(S, C1, C2, C3):
    return C1 * np.sin(C2 * S + C3)

# ---------------------------------------------------------
# 4. MAIN EXECUTION PIPELINE
# ---------------------------------------------------------
if __name__ == "__main__":
    # Setup VISA DLL search directories
    for path in VISA_PATHS:
        if os.path.exists(path):
            os.add_dll_directory(path)
            print(f"Added VISA DLL path: {path}")

    # Ensure metadata output directory exists
    os.makedirs(DATA_DIR, exist_ok=True)

    try:
        # Initialize VISA ResourceManager
        rm = pyvisa.ResourceManager()
        print(f"VISA Implementation: {rm.visalib}")

        import triax_320

        # Connect Monochromator
        mono = triax_320.Triax320(resource_manager=rm, GPIB_address="GPIB0::1::INSTR")
        mono.connect_device()

        print("\n--- Initializing Monochromator Motor & Slits ---")
        mono.init_motor()
        time.sleep(2)
        mono.slit_control(slit_num=0, width=500)
        time.sleep(2)
        mono.slit_control(slit_num=3, width=500)
        time.sleep(2)

        # Connect Spectrometer
        oto_dll, device_handle, framesize, wavelengths = connect_spectrometer()
        if not oto_dll:
            raise RuntimeError("Aborting: Spectrometer initialization failed.")

        # Define scan sequence (e.g., 0 to 550000 in steps of 5000)
        # Make sure to change this according to monochromater
        scan_steps = list(range(0, 25000, 100))

        print(f"\n--- Starting Automated Calibration Scan ({len(scan_steps)} steps) ---")
        print(f"Saving individual step CSVs to: '{DATA_DIR}'\n")

        for step in scan_steps:
            current_pos = mono.get_motor_position()
            move_amount = step - current_pos
            mono.move_motor_relative(move_amount)

            # Wait for motor to idle
            for _ in range(20):
                if mono.get_motor_status() == 'idle':
                    break
                time.sleep(0.5)
            time.sleep(0.3)

            # Use fixed parameters instead of adaptive lookup
            int_time_ms = FIXED_INTEGRATION_TIME_MS
            num_avg = FIXED_AVG_COUNT

            # Acquire spectrum
            intensity_data = acquire_spectrum(
                oto_dll, device_handle, framesize, wavelengths, 
                integration_time_ms=int_time_ms, 
                avg_count=num_avg
            )

            if intensity_data:
                step_file_path = os.path.join(DATA_DIR, f"{step}.csv")
                with open(step_file_path, "w", newline="") as f:
                    import csv
                    writer = csv.writer(f)
                    writer.writerow(["Wavelength (nm)", "Intensity"])
                    for wl, intensity in zip(wavelengths, intensity_data):
                        writer.writerow([f"{wl:.4f}", f"{intensity:.2f}"])

                max_intensity = max(intensity_data)
                print(f"Step {step:6d} -> Saved | Int Time: {int_time_ms}ms | Avg: {num_avg}x | Max Intensity: {max_intensity:.1f}") | Avg: {num_avg}x | Max Intensity: {max_intensity:.1f}")

    except KeyboardInterrupt:
        print("\nScan interrupted manually by user.")
    except Exception as e:
        print(f"Execution Error during scan: {e}")
        sys.exit(1)
    finally:
        if 'mono' in locals() and mono.device_connected:
            mono.close_device()
            print("Monochromator connection closed.")

    # ---------------------------------------------------------
    # 5. AUTOMATED POST-PROCESSING & SINE MODEL FITTING
    # ---------------------------------------------------------
    print("\n" + "=" * 60)
    print("       STARTING AUTOMATED SINE MODEL FITTING")
    print("=" * 60)

    csv_pattern = os.path.join(DATA_DIR, "*.csv")
    csv_files = glob.glob(csv_pattern)

    steps_m1 = []
    wl_m1 = []

    for f in sorted(csv_files):
        name, _ = os.path.splitext(os.path.basename(f))
        if name.isdigit():
            s = int(name)
            if 11000 >= s >= 5500:  # Primary diffraction order filter
                df = pd.read_csv(f)
                max_idx = df['Intensity'].idxmax()
                
                # 11-point local window for sub-pixel centroid peak fitting
                window = df.iloc[max(0, max_idx - 5):min(len(df), max_idx + 6)]
                w_arr = window['Wavelength (nm)'].values
                i_arr = window['Intensity'].values - window['Intensity'].min()
                
                peak_subpixel = np.sum(w_arr * i_arr) / np.sum(i_arr) if np.sum(i_arr) > 0 else df.loc[max_idx, 'Wavelength (nm)']
                steps_m1.append(s)
                wl_m1.append(peak_subpixel)

    steps_m1 = np.array(steps_m1)
    wl_m1 = np.array(wl_m1)

    if len(steps_m1) < 5:
        print(f"Error: Not enough valid peak data points found (got {len(steps_m1)}).")
        sys.exit(1)

    # Perform non-linear curve fitting for Sine grating equation
    p0 = [1662.46, 1.3634e-6, -0.00465]
    popt, _ = curve_fit(sine_grating_model, steps_m1, wl_m1, p0=p0, maxfev=10000)
    C1, C2, C3 = popt

    residuals = wl_m1 - sine_grating_model(steps_m1, *popt)
    rmsd = np.sqrt(np.mean(residuals**2))
    r2_score = 1.0 - (np.sum(residuals**2) / np.sum((wl_m1 - np.mean(wl_m1))**2))

    print(f"Fitted Equation : λ(S) = {C1:.4f} * sin({C2:.8e} * S + {C3:.6f})")
    print(f"R² Score        : {r2_score:.6f}")
    print(f"RMSD            : {rmsd:.4f} nm")

    # Save mapping JSON
    mapping_data = {
        "model": "sine",
        "C1": float(C1),
        "C2": float(C2),
        "C3": float(C3),
        "score": float(r2_score)
    }

    with open(OUTPUT_JSON, "w") as f:
        json.dump(mapping_data, f, indent=4)
    print(f"Sine mapping successfully saved to:\n  {OUTPUT_JSON}")

    # Generate and save overlay/residual diagnostic plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
    s_fine = np.linspace(min(steps_m1) - 5000, max(steps_m1) + 5000, 200)

    ax1.plot(steps_m1, wl_m1, 'ko', label='Extracted Centroid Peaks', markersize=6)
    ax1.plot(s_fine, sine_grating_model(s_fine, *popt), 'b-', label=f'Sine Fit: λ = {C1:.2f}·sin({C2:.4e}·S + {C3:.4f})')
    ax1.set_ylabel('Peak Wavelength (nm)', fontsize=11)
    ax1.set_title('Automated Monochromator Sine Calibration', fontsize=12, fontweight='bold')
    ax1.legend(loc='upper left', fontsize=10)
    ax1.grid(True, linestyle='--', alpha=0.5)

    ax2.plot(steps_m1, residuals, 'b:d', label='Residuals')
    ax2.axhline(0, color='black', linestyle='-', alpha=0.3)
    ax2.set_xlabel('Motor Steps (S)', fontsize=11)
    ax2.set_ylabel('Residuals (nm)', fontsize=11)
    ax2.legend(loc='upper right', fontsize=10)
    ax2.grid(True, linestyle='--', alpha=0.5)

    plt.tight_layout()
    plot_path = os.path.join(DATA_DIR, "sine_fit_result.png")
    plt.savefig(plot_path, dpi=300)
    print(f"Diagnostic plot saved to:\n  {plot_path}")
    plt.show()