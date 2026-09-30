from spectrometer_function import *
import tkinter as tk


# Create the main window
window = tk.Tk()
window.title("Spectrometer Interface")
# global var for device usage:
cache_location = './spectrometer_data_cache.csv'
wave_length = []
cur_intensity = []
ref_intensity = []
initilizingDevice = False
# Example data lists


# create display box:
device_info_label = tk.Label(window, text="Device Information")
device_info_label.grid(row=0, column=0, columnspan=2)
device_info_box = tk.Text(window, height=5, width=50)
device_info_box.grid(row=1, column=0, columnspan=2)
# Create buttons


dataEntry = tk.Label(window, text="Integrating time between 1ms and 900ms; default 10ms")
dataEntry.grid(row=2, column=0)
input_entry = tk.Entry(window)
input_entry.grid(row=3, column=0)
# Create a Button to trigger data retrieval
retrieve_button = tk.Button(window, text="Enter integrating time", command=lambda: retrieve_input(input_entry))
retrieve_button.grid(row=3, column=1)

countEntry = tk.Label(window, text="The number of spectrum to collect: (default 10)")
countEntry.grid(row=4, column=0)
inputCount_entry = tk.Entry(window)
inputCount_entry.grid(row=5, column=0)
# Create a Button to trigger data retrieval
countRetrieve_button = tk.Button(window, text="Enter", command=lambda: retrieve_count(inputCount_entry))
countRetrieve_button.grid(row=5, column=1)
getIntensityButton = tk.Button(window, text="Get ref_intensity", command=lambda: getIntensity(device_handle, device_framesize,
                                                                                              ref_intensity))
getIntensityButton.grid(row=6, column=1)
# initialize device:
device_handle, device_framesize = getDevice(device_info_box, wave_length)
if device_handle != 0:
    getIntensity(device_handle, device_framesize, ref_intensity)
else:
    pass

# Button to display the plot
plot_button = tk.Button(master=window, command=lambda: startPlotting(wave_length, ref_intensity=ref_intensity,
                                                            cur_intensity=cur_intensity, fig= figure,
                                                            canvas=canvas, root=window, device_handle=device_handle,
                                                                     device_framesize=device_framesize),
                        text="Start/Stop plotting")
plot_button.grid(row=6, column=0, columnspan=1)

export_button = tk.Button(window, text="Export CSV", command=lambda: export_data(device_handle=device_handle,
                                                                                 device_framesize=device_framesize,
                                                                                 waveLength=wave_length))
export_button.grid(row=0, column=1)
figure, canvas = create_blank_plot(window, row=8, column=0, horizontalSpan=2)

window.protocol("WM_DELETE_WINDOW", lambda: on_closing(window))
# Start the application
window.mainloop()

