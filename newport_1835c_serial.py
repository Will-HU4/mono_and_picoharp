import serial
import time
from PyQt6.QtCore import QObject, pyqtSignal
from typing import Optional

class PowerMeterSignal(QObject):
    log_message_signal = pyqtSignal(str)
    update_readings_signal = pyqtSignal(float)

class Newport1835C:
    def __init__(self, baudrate: int = 9600, timeout: float = 1.0):
        self.baudrate = baudrate
        self.timeout = timeout
        self.device = None
        self.device_connected = False
        self.device_info = None
        self.device_unit = None
        self.message = None
        self.signals = PowerMeterSignal()

    def connect_device(self, port: str = "COM4"):
        try:
            self.device = serial.Serial(
                port=port,
                baudrate=self.baudrate,
                timeout=self.timeout
            )
            print("Device connected via RS-232")
            self.message = "Power meter connected via RS-232"
            self.device_connected = True
            self.log_message_signal("Power meter connected via RS-232")

            # Wait for the device to warm up (adjust timing as necessary)
            time.sleep(2)

        except serial.SerialException as e:
            print(f"{e}\nDevice not found or cannot be opened.")
            self.message = f"{e}\nPower meter not found or cannot be opened."
            self.log_message_signal(f"{e}\nPower meter not found or cannot be opened.")
            return

        # Set up basic info
        self.device_info = self.send_command("*IDN?")
        print(f"Device info: {self.device_info}")
        self.log_message_signal(f"Power meter info: {self.device_info}")

        # Ensure the device has completed the previous operation
        self.send_command('*OPC?')

        # Set up the device to read data
        time.sleep(0.1)  # Adjust this delay if necessary
        print("Setting up the device to read data")

        # Send "R?" and read the response
        data = self.send_command("R?")
        print(f"Initial data read: {data}")
        return

    def disconnect_device(self):
        if self.device_connected:
            self.device.close()
            self.device_connected = False
            self.message = f"Power meter disconnected"
            self.log_message_signal("Power meter disconnected")
            print(self.message)
        else:
            self.message = "Power meter not connected"
            self.log_message_signal("Power meter not connected")
            print("Device not connected")

    def send_command(self, command: str):
        if self.device_connected:
            command = command+'\n'
            self.device.write(command.encode())
            response = self.device.readline().decode().strip()
            return response
        else:
            print("Device not connected")
            return None

    def read_data(self) -> Optional[str]:
        """Read the data from the power meter
        :return: readings or None if not connected"""
        if self.device_connected:
            data = self.send_command("R?")
            print(data)
            return data
        else:
            print("Device not connected")
            return None

    def get_unit(self):
        """Get the unit of the power meter and store it in self.device_unit
        :return: unit (str)"""
        if self.device_connected:
            unit = self.send_command("UNITS?")
            self.device_unit = unit
            print(f"Unit: {unit}")
            return unit
        else:
            print("Device not connected")
            return None

    def get_idn(self):
        if self.device_connected:
            idn = self.send_command("*IDN?")
            print(f"IDN: {idn}")
            return
        else:
            print("Device not connected")
            return None

    def log_message_signal(self, message: str):
        """Emit log message signal to GUI text browser"""
        self.signals.log_message_signal.emit(message)
