import csv
import os
import shutil
import time
import json

import pyqtgraph as pg
from PyQt6.QtWidgets import QMessageBox, QFileDialog

# from SE1030_FUV_functions import SE1030_FUV


class PlotData:
    def __init__(self, vid, pid, dll_path, plot_widget):
        """
        Initializes the PlotData object with spectrometer device information.
        :param vid: Vendor ID
        :param pid: Product ID
        :param dll_path: Path to the DLL file
        """
        self.cache_location = './spectrometer_data_cache.csv'
        # Default save directory for auto-saving:
        self.default_save_dir = os.path.abspath('./data_saved_here')
        self.config_file = './config.json'
        self.filename = "sample data"
        self.load_save_location()
        os.makedirs(self.default_save_dir, exist_ok=True)

        self.plot_widget = plot_widget
        self.reference_intensity_data = None
        self.current_intensity_data = None
        self.row_count = 0

        self.spectrometer = SE1030_FUV(vid, pid, dll_path)
        self.spectrometer.open_device()
        self.spectrometer.get_device_framesize()
        self.wavelengths_list = self.spectrometer.get_wavelength() # to store the wavelength data

    def get_spectrometer_data(self, integration_time):
        """
        Retrieves the intensity data from the spectrometer.
        :param integration_time: Integration time in milliseconds
        :return: intensities
        """
        intensities = self.spectrometer.get_intensity(integration_time)
        return intensities

    def init_cache(self):
        """ Initialize the CSV file for caching the spectrometer data.
        :param cache_location: Path to the CSV file
        """
        # self.wavelengths_list = self.spectrometer.get_wavelength()
        if not os.path.exists(self.cache_location):
            with open(self.cache_location, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["wavelength"] + self.wavelengths_list)

    def append_row(self, row_count, integration_time, new_row):
        new_row = [f"Spectrum_{row_count}, int_time= {integration_time}"] + new_row
        with open(self.cache_location, 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(new_row)

    def clear_cache(self):
        """Clear the cache file but keep the wavelength header row."""
        with open(self.cache_location, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["wavelength"] + self.wavelengths_list)
            print("Cache cleared but header retained:", ["wavelength"] + self.wavelengths_list)

    def update_plot(self, integration_time, spectrometer_connected):
        """"
        Updates the plot with the current intensity data.
        :param integration_time: Integration time in milliseconds
        :param spectrometer_connected: Boolean indicating if the spectrometer is connected
        :return: -1 if any error occurs"""
        if not spectrometer_connected:
            self.plot_widget.append("Please connect the spectrometer first.")
            return -1

        self.current_intensity_data = self.get_spectrometer_data(integration_time)

        print("Current intensity data length:", len(self.current_intensity_data))
        print("Wavelengths list length:", len(self.wavelengths_list))

        if len(self.wavelengths_list) != len(self.current_intensity_data):
            QMessageBox.critical(None, "Data Error", "Wavelengths list and intensity data lengths do not match.")
            return -1

        self.plot_widget.clear()

        try:
            if self.reference_intensity_data:
                self.plot_widget.plot(self.wavelengths_list, self.reference_intensity_data, pen='b', name='Reference')

            self.plot_widget.plot(self.wavelengths_list, self.current_intensity_data, pen='r', name='Current')
            self.row_count += 1
            self.append_row(self.row_count, integration_time, self.current_intensity_data)
            self.update_plot_properties()

        except Exception as e:
            print(f"An error occurred while plotting: {e}")
            QMessageBox.critical(None, "Plotting Error", f"An error occurred while plotting: {e}")
            return -1

    def update_plot_properties(self):
        self.plot_widget.setLabel('left', 'Intensity')
        self.plot_widget.setLabel('bottom', 'Wavelength (nm)')
        self.plot_widget.setTitle('Spectrometer Data')
        self.plot_widget.addLegend()
        self.plot_widget.showGrid(x=True, y=True)

    def set_reference_plot(self):
        if self.current_intensity_data is None:
            QMessageBox.warning(None, "Warning", "No current data to set as reference.")
            return

        self.reference_intensity_data = self.current_intensity_data
        self.plot_widget.clear()
        self.plot_widget.plot(self.wavelengths_list, self.reference_intensity_data, pen='b', name='Reference')
        self.update_plot_properties()

    def export_csv(self):
        """Prompt user to choose a file location to save the CSV"""
        cache_location = self.cache_location
        new_file_path, _ = QFileDialog.getSaveFileName(
            None,
            "Save CSV",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )

        if new_file_path:
            try:
                shutil.copy(cache_location, new_file_path)
                print(f"File saved to {new_file_path}")
            except Exception as e:
                print(f"Error saving file: {e}")
        else:
            print("Save operation canceled")

    def auto_save(self):
        """Save the data at a different location"""
        cache_location = self.cache_location
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        new_file_name = f"{self.filename}_{timestamp}.csv"
        new_file_path = os.path.join(self.default_save_dir, new_file_name)
        try:
            shutil.copy(cache_location, new_file_path)
            print(f"Auto-saved file to {new_file_path}")
        except Exception as e:
            print(f"Error auto-saving file: {e}")

    def load_save_location(self):
        """Load the default save location from the config file
        :return: The default save location"""
        print(self.default_save_dir)
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as file:
                config = json.load(file)
                self.default_save_dir = config.get('save_dir', self.default_save_dir)
                print(self.default_save_dir)
                return
        else:
            self.save_save_location(self.default_save_dir)  # Create the config file with the default directory
            return self.default_save_dir

    def save_save_location(self, new_dir):
        config = {'save_dir': new_dir}
        with open(self.config_file, 'w') as file:
            json.dump(config, file, indent=4)
