import csv
import json
import os
import shutil
import time

class FileIO:
    def __init__(self):
        self.cache_file = "./data_cache.csv"
        self.file_name = "data"
        self.saved_location = "."
        # load user previous settings:
        self.load_config()

    def init_cache(self, header: list):
        """ Initialize the CSV file for storing data.
        :param header: header for the CSV file
        """
        with open(self.cache_file, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(header)

    def append_row(self, new_row: list, header: list = None):
        """ Append a row to the CSV file.
        :param new_row: row to be appended
        :param header: header for the CSV file if it does not exist
        """
        if os.path.exists(self.cache_file):
            with open(self.cache_file, 'a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(new_row)
        else:
            self.init_cache(header)

    def manual_save_file(self, file_location: str):
        """Save cache file ot desired directory and filename"""
        try:
            shutil.copy(self.cache_file, file_location)
            print(f"File saved to {file_location}")
        except Exception as e:
            print(f"Error saving file: {e}")

    def auto_save_file(self):
        """automatically saved cache to fixed location."""
        try:
            saved_location = self.saved_location+ "/" + self.file_name + "_" + time.strftime("%Y%m%d-%H%M%S") + ".csv"
            shutil.copy(self.cache_file, saved_location)
            print(f"File saved to {saved_location}")
        except Exception as e:
            print(f"Error saving file: {e}")

    def load_config(self):
        """Load the default save location from the config file
        """
        if os.path.exists("config.json"):
            with open("config.json", 'r') as file:
                config = json.load(file)
                try:
                    self.saved_location = config.get('save_dir', self.saved_location)
                except Exception as e:
                    self.saved_location = self.saved_location
                try:
                    self.cache_file = config.get('cache_file', self.cache_file)
                except Exception as e:
                    self.cache_file = self.cache_file
                try:
                    self.file_name = config.get('file_name', self.file_name)
                except Exception as e:
                    self.file_name = self.file_name
        else:
            pass

    def change_saved_location(self, new_dir):
        """Change save location and update the config file to automatically load the new location
        :param new_dir: new save location"""
        if not os.path.exists("./config.json"):
            config = {'save_dir': new_dir}
            with open("./config.json", 'w') as file:
                json.dump(config, file, indent=4)
            self.saved_location = new_dir
            print(f"Save location changed to {new_dir}")

        elif os.path.exists("./config.json"):
            with open("./config.json", 'r') as file:
                config = json.load(file)
            config['save_dir'] = new_dir
            with open("config.json", 'w') as file:
                json.dump(config, file, indent=4)
            self.saved_location = new_dir
            print(f"Save location changed to {new_dir}")

        else:
            print("Error changing save location.")


    def change_cache_file(self, new_file):
        if not os.path.exists("config.json"):
            config = {'cache_file': new_file}
            with open("config.json", 'w') as file:
                json.dump(config, file, indent=4)
            self.cache_file = new_file
            print(f"Cache file changed to {new_file}")
        elif os.path.exists("config.json"):
            with open("config.json", 'r') as file:
                config = json.load(file)
            config['cache_file'] = new_file
            with open("config.json", 'w') as file:
                json.dump(config, file, indent=4)
            self.cache_file = new_file
            print(f"Cache file changed to {new_file}")
        else:
            print("Error changing cache file.")

    def change_file_name(self, new_name):
        """Change the file name and update the config file to automatically load the new name
        and update the self.file_name attribute.
        :param new_name: new file name"""
        if not os.path.exists("config.json"):
            config = {'file_name': new_name}
            with open("config.json", 'w') as file:
                json.dump(config, file, indent=4)
            self.file_name = new_name
            print(f"File name changed to {new_name}")
        elif os.path.exists("config.json"):
            with open("config.json", 'r') as file:
                config = json.load(file)
            config['file_name'] = new_name
            with open("config.json", 'w') as file:
                json.dump(config, file, indent=4)  # 'indent=4' makes the JSON file more readable
            print(f"{config}")  # This will print the updated config to the console
            self.file_name = new_name

        else:
            print("Error changing file name.")

# todo: kept mono functinos and remove anything else
# todo: combine the current source and voltmeter ui
# todo: iv-curve in each wavelength by mono