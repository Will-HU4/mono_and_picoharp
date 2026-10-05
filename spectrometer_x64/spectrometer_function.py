import tkinter as tk
import ctypes
from ctypes import c_uint64, c_float, byref
import json
import time
import numpy as np
import csv
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import filedialog, messagebox
import shutil  # saving file module
import os


#OTO USB2.0 spectrameter's VID & PID
# Constant DO NOT MODIFY---------------------------------
VID = 1592
PID = 2732
OTOdll = ctypes.cdll.LoadLibrary("./UserApplication.dll")
# -------------------------------------------------------
# keep track of how many row of data saved:
SPEC_VID = 1592
SPEC_PID = 2732

row_count = 0
cache_location = './spectrometer_data_cache.csv'
integration_time = 100
update_active = False
data_count = 10
def print_data(textbox: tk.Text, content: str):
    textbox.insert(tk.END, content)


def getDeviceHandle(textBox: tk.Text):
    DeviceHandle = c_uint64(0)
    OTOdll.UAI_SpectrometerOpen.restype = ctypes.c_uint64
    OTOdll.UAI_SpectrometerOpen(0,byref(DeviceHandle),VID,PID)
    #display value:
    # device_info_box.insert(tk.END, f"Device handle:{DeviceHandle.value}\n")
    print_data(textBox, f"Device handle:{DeviceHandle.value}\n")
    return DeviceHandle


# Framesize is to get the data points of wavelength we obtained
def getDeviceFramesize(DeviceHandle, textBox: tk.Text):
    intFramesize = c_uint64(0)
    OTOdll.UAI_SpectromoduleGetFrameSize.restype = ctypes.c_uint64
    OTOdll.UAI_SpectromoduleGetFrameSize(DeviceHandle,byref(intFramesize))
    print_data(textBox, f"Device framesize:{intFramesize.value}\n")

    return intFramesize


def initilizingCache(waveLengthList):
    # Open a new CSV file for writing
    with open('./spectrometer_data_cache.csv', 'w', newline='') as file:
        writer = csv.writer(file)
        waveLengthList = ["wavelength"]+waveLengthList
        # Writing the header (optional)
        writer.writerow(waveLengthList)


def getWavelength(device_handle, device_framesize, waveLengthArray: list):
    TempLambda = (c_float*device_framesize.value)()
    #Get wavelength
    OTOdll.UAI_SpectrometerWavelengthAcquire(device_handle,byref(TempLambda))
    for i in range(0, device_framesize.value):
        waveLengthArray.append(TempLambda[i])

    # initilizingCache(waveLengthList=waveLengthArray)


def getDevice(textBox: tk.Text, waveLengthArray):
    #Check how many device is connected with PC.
    intDeviceamout = c_uint64(0)
    OTOdll.UAI_SpectrometerGetDeviceAmount.restype = ctypes.c_uint64
    OTOdll.UAI_SpectrometerGetDeviceAmount(VID,PID,byref(intDeviceamout))
    print_data(textBox, f"Device amount:{intDeviceamout.value}\n")

    device_handle = getDeviceHandle(textBox)
    device_framesize = getDeviceFramesize(device_handle, textBox)

    if intDeviceamout.value < 1:
        print_data(textBox, f"NO device connecting.\nPlease connect device and rerun the program.\n")
        return 0, 0
    else:
        getWavelength(device_handle, device_framesize, waveLengthArray)
    return device_handle, device_framesize


def appendRow(filename, new_row):
    # Open the file in append mode and write the new row
    global row_count
    row_count += 1
    new_row = [f"Spectrum_{row_count}, int_time= {integration_time}"]+new_row
    with open(filename, 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(new_row)


def getIntensity(device_handle, device_framesize, intensityArray: list):
    TempIntensity = (c_float*device_framesize.value)()
    global integration_time
    # for i in range(1, 100, +1):
    if len(intensityArray) > 0:
        intensityArray.clear()
    # integrating time in millisecond
    integratingTime = integration_time*1000  # (ms)
    #Get Intensity
    #Parameters:
    # api_handle: The spectrometer handle.
    # integration_time_us: The integration time in microseconds (us).
    # buffer: A pointer to a 1D array buffer where the data (in counts) will be stored.
    # average: The number of times the data acquisition is averaged.
    OTOdll.UAI_SpectrometerDataOneshot(device_handle,integratingTime,byref(TempIntensity),1)
    #Do Background
    OTOdll.UAI_BackgroundRemove(device_handle,integratingTime,byref(TempIntensity))
    #Do Linearity
    OTOdll.UAI_LinearityCorrection(device_handle,device_framesize,byref(TempIntensity))
    for element in range(0,device_framesize.value):
        intensityArray.append(TempIntensity[element])


def updating_plot(waveLength: list, ref_intensity: list, cur_intensity: list,
                  fig, canvas: FigureCanvasTkAgg, root: tk.Tk,
                  device_handle, device_framesize):
    # renew current intensity:
    global integration_time, update_active
    getIntensity(device_handle, device_framesize, intensityArray=cur_intensity)
    if update_active:
        # Clear the current plot
        fig.clear()
        # Plot the data on a new subplot
        ax = fig.add_subplot(111)
        ax.plot(waveLength, ref_intensity, label="Reference", color="red", linestyle="-")
        ax.plot(waveLength, cur_intensity, label="Current", color="blue", linestyle="-")

        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Intensity")

        # Redraw the canvas
        canvas.draw_idle()
        root.after(50, updating_plot, waveLength, ref_intensity, cur_intensity, fig, canvas, root, device_handle, device_framesize)


def startPlotting(waveLength: list, ref_intensity: list, cur_intensity: list,
                  fig, canvas: FigureCanvasTkAgg, root: tk.Tk, device_handle, device_framesize):
    global update_active
    update_active = ~update_active
    updating_plot(waveLength=waveLength, ref_intensity=ref_intensity, cur_intensity=cur_intensity, fig=fig,
                  canvas=canvas, root=root, device_handle=device_handle, device_framesize=device_framesize)


def create_blank_plot(window, row, column, horizontalSpan):
    # Create a blank figure with white background
    fig = Figure(figsize=(6,5), dpi=100, facecolor='white')
    # Create a subplot (this will also be blank)
    fig.add_subplot(111)
    # Create the Matplotlib canvas and embed it in the Tkinter window
    canvas = FigureCanvasTkAgg(fig, master=window)
    canvas_widget = canvas.get_tk_widget()
    canvas_widget.grid(row=row, column=column, columnspan=horizontalSpan)
    canvas.draw()
    return fig, canvas


def export_csv(existing_file_path):
    # Ask the user for the new save location
    new_file_path = filedialog.asksaveasfilename(defaultextension=".csv",
                                                 filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
    if new_file_path:  # Check if a file path was selected
        shutil.copy(existing_file_path, new_file_path)


def export_data(device_handle, device_framesize, waveLength: list):
    global integration_time, data_count
    initilizingCache(waveLengthList=waveLength)
    intensity_list = []
    for time in range(0, data_count):
        getIntensity(device_handle=device_handle, device_framesize=device_framesize,
                     intensityArray=intensity_list)
        appendRow(cache_location, intensity_list)
    export_csv(cache_location)

def on_closing(window: tk.Tk):
    if messagebox.askokcancel("Quit", "Have you saved all the needed data?"):
        window.destroy()


#end
def retrieve_input(input_entry):
    global integration_time
    # confirmation = messagebox.askyesno("Confirm", "Are you sure?", parent=root)
    # Get the current text in input_entry
    input_text = input_entry.get()
    # Now input_text holds the text entered by the user
    if 900 >= int(input_text) >= 1:
        integration_time = int(input_text)
        print(f"User input:{integration_time}")  # You can process the text as needed
    else:
        messagebox.showwarning("Invalid input", "Integration time out of bound!\n"
                                                "Between 1 and 900.")
        print(f"User input:{integration_time}")


def retrieve_count(count_entry):
    global data_count
    count_text = count_entry.get()

    if int(count_text) >= 50:
        messagebox.showwarning("warning", "Large counts will cause dalay.")
        response = messagebox.askyesno("Permission", "Do you want to proceed?")
        if response:  # If the user clicked 'Yes'
            data_count = int(count_text)
        else:
            messagebox.showwarning("Prompt", "Default data count is 10.")
            pass
    else:
        data_count = int(count_text)
# ---------------------------------------------------------------------------

def connect_spectrometer(dll_path="./UserApplication.dll"):
    try:
        oto_dll = ctypes.cdll.LoadLibrary(dll_path)
    except Exception as e:
        print(f"Failed to load DLL: {e}")
        return None, None, None, None

    device_amount = c_uint64(0)
    oto_dll.UAI_SpectrometerGetDeviceAmount.restype = ctypes.c_uint64
    oto_dll.UAI_SpectrometerGetDeviceAmount(SPEC_VID, SPEC_PID, byref(device_amount))

    if device_amount.value < 1:
        print("No spectrometer device found.")
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


def acquire_full_spectrum(oto_dll, device_handle, framesize, wavelengths, integration_time_ms=10):
    """Acquires current intensity spectrum across all wavelengths."""
    temp_intensity = (c_float * framesize.value)()
    integrating_time_us = int(integration_time_ms * 1000)

    oto_dll.UAI_SpectrometerDataOneshot(
        device_handle, integrating_time_us, byref(temp_intensity), 1
    )
    oto_dll.UAI_BackgroundRemove(device_handle, integrating_time_us, byref(temp_intensity))
    oto_dll.UAI_LinearityCorrection(device_handle, framesize, byref(temp_intensity))

    intensity_data = [temp_intensity[i] for i in range(framesize.value)]
    return intensity_data


def generate_step_to_wavelength_mapping_peak(mono_instance, steps_to_scan, output_json="mapping_new.json", min_intensity_threshold=100.0):
    oto_dll, device_handle, framesize, wavelengths = connect_spectrometer()
    if not oto_dll:
        print("Aborting: Spectrometer initialization failed.")
        return

    collected_steps = []
    collected_peak_wavelengths = []
    collected_peak_intensities = []
    last_full_spectrum = []

    print("\n--- Starting Step-to-Wavelength Calibration Scan ---")

    try:
        for step in steps_to_scan:
            current_pos = mono_instance.get_motor_position()
            move_amount = step - current_pos
            mono_instance.move_motor_relative(move_amount)

            for _ in range(20):
                if mono_instance.get_motor_status() == 'idle':
                    break
                time.sleep(0.5)

            time.sleep(0.5)

            # Read full intensity spectrum
            intensity_data = acquire_full_spectrum(
                oto_dll, device_handle, framesize, wavelengths
            )

            if intensity_data:
                max_intensity = max(intensity_data)
                
                # Check if peak intensity meets the threshold
                if max_intensity >= min_intensity_threshold:
                    peak_index = intensity_data.index(max_intensity)
                    peak_wl = wavelengths[peak_index]

                    collected_steps.append(step)
                    collected_peak_wavelengths.append(peak_wl)
                    collected_peak_intensities.append(max_intensity)
                    last_full_spectrum = intensity_data

                    print(f"Step {step:6d} -> Peak Wavelength: {peak_wl:.4f} nm (Peak Intensity: {max_intensity:.1f})")
                else:
                    print(f"Step {step:6d} -> Skipped (Peak Intensity {max_intensity:.1f} < {min_intensity_threshold})")

    except KeyboardInterrupt:
        print("\nCalibration scan interrupted manually.")

    # -------------------------------------------------------------------------
    # OUTPUT 1: JSON Calibration File (a * step + b)
    # -------------------------------------------------------------------------
    if len(collected_steps) >= 2:
        a, b = np.polyfit(collected_steps, collected_peak_wavelengths, 1)

        mapping_data = {"a": float(a), "b": float(b)}
        with open(output_json, "w") as f:
            json.dump(mapping_data, f, indent=4)

        print("\n" + "=" * 50)
        print("CALIBRATION SUCCESSFUL")
        print(f"Mapping Equation : Wavelength = {a:.6e} * step + {b:.4f}")
        print(f"JSON saved to    : {output_json}")
    else:
        print("\n" + "=" * 50)
        print(f"CALIBRATION FAILED: Not enough valid data points (>= 2 required, got {len(collected_steps)}) above intensity threshold {min_intensity_threshold}.")

    # -------------------------------------------------------------------------
    # OUTPUT 2: Step-to-Wavelength CSV
    # -------------------------------------------------------------------------
    if collected_steps:
        step_csv = "step_to_wavelength.csv"
        with open(step_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Step Position", "Peak Wavelength (nm)", "Peak Intensity"])
            for step, wl, intensity in zip(collected_steps, collected_peak_wavelengths, collected_peak_intensities):
                writer.writerow([step, f"{wl:.4f}", f"{intensity:.2f}"])

        print(f"Step CSV saved to: {step_csv}")

    # -------------------------------------------------------------------------
    # OUTPUT 3: Intensity-to-Wavelength CSV
    # -------------------------------------------------------------------------
    if last_full_spectrum:
        spectrum_csv = "intensity_to_wavelength.csv"
        with open(spectrum_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Wavelength (nm)", "Intensity"])
            for wl, intensity in zip(wavelengths, last_full_spectrum):
                writer.writerow([f"{wl:.4f}", f"{intensity:.2f}"])

        print(f"Spectrum CSV saved to: {spectrum_csv}")
    
    print("=" * 50 + "\n")

    # -------------------------------------------------------------------------
    # OUTPUT 1: JSON Calibration File (a * step + b)
    # -------------------------------------------------------------------------
    if len(collected_steps) >= 2:
        a, b = np.polyfit(collected_steps, collected_peak_wavelengths, 1)

        mapping_data = {"a": float(a), "b": float(b)}
        with open(output_json, "w") as f:
            json.dump(mapping_data, f, indent=4)

        print("\n" + "=" * 50)
        print("CALIBRATION SUCCESSFUL")
        print(f"Mapping Equation : Wavelength = {a:.6e} * step + {b:.4f}")
        print(f"JSON saved to    : {output_json}")

    # -------------------------------------------------------------------------
    # OUTPUT 2: Step-to-Wavelength CSV
    # -------------------------------------------------------------------------
    step_csv = "step_to_wavelength.csv"
    with open(step_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Step Position", "Peak Wavelength (nm)", "Peak Intensity"])
        for step, wl, intensity in zip(collected_steps, collected_peak_wavelengths, collected_peak_intensities):
            writer.writerow([step, f"{wl:.4f}", f"{intensity:.2f}"])

    print(f"Step CSV saved to: {step_csv}")

    # -------------------------------------------------------------------------
    # OUTPUT 3: Intensity-to-Wavelength CSV
    # -------------------------------------------------------------------------
    spectrum_csv = "intensity_to_wavelength.csv"
    with open(spectrum_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Wavelength (nm)", "Intensity"])
        for wl, intensity in zip(wavelengths, last_full_spectrum):
            writer.writerow([f"{wl:.4f}", f"{intensity:.2f}"])

    print(f"Spectrum CSV saved to: {spectrum_csv}")
    print("=" * 50 + "\n")


def generate_step_to_wavelength_mapping(
    mono_instance, 
    steps_to_scan, 
    output_json="mapping_new.json", 
    output_dir="data sets"
):
    oto_dll, device_handle, framesize, wavelengths = connect_spectrometer()
    if not oto_dll:
        print("Aborting: Spectrometer initialization failed.")
        return

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    collected_steps = []
    collected_peak_wavelengths = []
    collected_peak_intensities = []

    print(f"\n--- Starting Step-to-Wavelength Calibration Scan ---")
    print(f"Individual step spectra will be saved to folder: '{output_dir}/'")

    try:
        for step in steps_to_scan:
            current_pos = mono_instance.get_motor_position()
            move_amount = step - current_pos
            mono_instance.move_motor_relative(move_amount)

            for _ in range(20):
                if mono_instance.get_motor_status() == 'idle':
                    break
                time.sleep(0.5)

            time.sleep(0.5)

            # Read full intensity spectrum
            intensity_data = acquire_full_spectrum(
                oto_dll, device_handle, framesize, wavelengths
            )

            if intensity_data:
                # -------------------------------------------------------------
                # 1. Save Individual Step CSV: Wavelength (nm) vs Intensity
                # -------------------------------------------------------------
                step_file_path = os.path.join(output_dir, f"{step}.csv")
                with open(step_file_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Wavelength (nm)", "Intensity"])
                    for wl, intensity in zip(wavelengths, intensity_data):
                        writer.writerow([f"{wl:.4f}", f"{intensity:.2f}"])

                # -------------------------------------------------------------
                # 2. Record Peak Information for Linear Fitting
                # -------------------------------------------------------------
                max_intensity = max(intensity_data)
                peak_index = intensity_data.index(max_intensity)
                peak_wl = wavelengths[peak_index]

                collected_steps.append(step)
                collected_peak_wavelengths.append(peak_wl)
                collected_peak_intensities.append(max_intensity)

                print(f"Step {step:6d} -> Saved '{step_file_path}' | Peak Wavelength: {peak_wl:.4f} nm | Intensity: {max_intensity:.1f}")

    except KeyboardInterrupt:
        print("\nCalibration scan interrupted manually.")

    # -------------------------------------------------------------------------
    # OUTPUT 2: JSON Calibration File (a * step + b)
    # -------------------------------------------------------------------------
    if len(collected_steps) >= 2:
        a, b = np.polyfit(collected_steps, collected_peak_wavelengths, 1)

        mapping_data = {"a": float(a), "b": float(b)}
        with open(output_json, "w") as f:
            json.dump(mapping_data, f, indent=4)

        print("\n" + "=" * 50)
        print("CALIBRATION SUCCESSFUL")
        print(f"Mapping Equation : Wavelength (nm) = {a:.6e} * step + {b:.4f}")
        print(f"JSON saved to    : {output_json}")
    else:
        print("\n" + "=" * 50)
        print(f"CALIBRATION FAILED: Not enough data points recorded (>= 2 required, got {len(collected_steps)}).")

    # -------------------------------------------------------------------------
    # OUTPUT 3: Step Summary CSV
    # -------------------------------------------------------------------------
    if collected_steps:
        step_csv = "step_to_wavelength.csv"
        with open(step_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Step Position", "Peak Wavelength (nm)", "Peak Intensity"])
            for step, wl, intensity in zip(collected_steps, collected_peak_wavelengths, collected_peak_intensities):
                writer.writerow([step, f"{wl:.4f}", f"{intensity:.2f}"])

        print(f"Peak Summary CSV saved to: {step_csv}")
    
    print("=" * 50 + "\n")