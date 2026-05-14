import time
import pyvisa
from pyvisa.errors import VisaIOError
from PyQt6.QtCore import QObject, pyqtSignal
from typing import Optional

class MonoSignals(QObject):
    """pyqtsignal for GUI update
    """
    log_message_signal = pyqtSignal(str)
    slit_signal = pyqtSignal()
    init_mono_signal = pyqtSignal()
    mono_initialized_signal = pyqtSignal()
    mono_init_failed_signal = pyqtSignal()
    mono_start_init_signal = pyqtSignal()


class Triax320:
    def __init__(self, resource_manager: pyvisa.ResourceManager, GPIB_address: str = "GPIB0::1::INSTR"):
        # Open the instrument
        self.rm = resource_manager
        self.device_address = GPIB_address
        self.device = None
        self.device_connected = False
        self.motor_initialized = False
        self.message = None

        # create signale object for connecting signals to GUI
        self.signals = MonoSignals()


    def connect_device(self):
        """Connect to the device. And enter the main program if not already in it.
        """
        try:
            self.device = self.rm.open_resource(self.device_address)
            print("Device connected")
            self.message = "Monochromator connected"
            self.device_connected = True
            self.log_message_signal(self.message)

        except VisaIOError as e:
            print(f"{e}\nDevice not found.")
            self.log_message_signal(f"{e}\nMonochromator not found.")
            return
        # Check device status:
        returned_message, device_status = self.check_device_status()
        print(f"Device status: {device_status}")
        # Enter the main program:
        if returned_message == "B":
            print("Entering the BOOT program, redirect to the MAIN program.")
            self.log_message_signal("Entering the BOOT program, redirect to the MAIN program.")
            self.start_main_program()
            return
        elif returned_message == "F":
            print("Already in the MAIN program.")
            self.log_message_signal("Already in the MAIN program.")
            # emit mono initialized signal to ui:
            self.signals.init_mono_signal.emit()
            return
        else:
            print(f"Unknown status: {device_status}.\nPlease check the device manual.")
            self.log_message_signal(f"Unknown status: {device_status}.\nPlease check the device manual.")
        return


    def check_device_status(self):
        """
        Check the program state of the device.
        :return: device status, message"""
        if self.device_connected:
            where_am_i = " "
            self.device.write_raw(where_am_i.encode())
            message= self.device.read()

            print(f"Device status: {message} (F for main program, B for boot program)")
            if message == "F":
                return "F", "Device is in the MAIN program."
            elif message == "B":
                return "B", "Device is in the BOOT program."
            else:
                return message, "Unknown device status. Please check the device manual."
        else:
            print("Device not connected")
            return "Device not connected", "Device not connected"

    def start_main_program(self):
        """Enter the main program of the device."""
        if self.device_connected:
            start_main_program = "O2000\x00"
            where_am_i = " "
            self.device.write_raw(start_main_program.encode())
            # check if successfully entered the main program:
            if self.device.read() == "*":
                time.sleep(0.05)
                self.device.write_raw(where_am_i.encode())
                message = self.device.read()
                if message == "F":
                    print("Entered the MAIN program.")
                    self.signals.init_mono_signal.emit()

                    return
                else:
                    print(f"Failed to enter the MAIN program. Current status: {message}")
                    return
            else:
                print("Failed to enter the MAIN program.")
                return
        else:
            print("Device not connected")
            return

    def close_device(self):
        if self.device_connected:
            self.device.close()
            self.device_connected = False
            self.message = "Monochromator disconnected"
            print(f"Device closed at {time.asctime()}.")
            self.log_message_signal("Monochromator closed.")
            return
        else:
            self.log_message_signal("Monochromator not connected.")
            print("Monochromator not connected")
            return

    def init_motor(self):
        """Initialize the motors of the monochromator. If manully change grating we should init again. and perform another calibration"""
        if self.device_connected:
            print("Initializing the motor. Takes about 100 seconds.")
            self.log_message_signal("Motor initialization started.")
            # send start signal to ui:
            self.signals.mono_start_init_signal.emit()
            # Set the timeout to 100 seconds for initialization(required by manual):
            self.device.timeout = 100000
            init_motor = "A"
            self.device.write_raw(init_motor)
            # Check if the motor is initialized:
            # todo: time.sleep removed, check if it works properly, and did not block the countdown at GUI.
            # time.sleep(100)
            message = self.device.read()
            if message == "o":
                print("Motor initialized.")
                self.motor_initialized = True
                # reset timeout to 300 ms:
                self.device.timeout = 300
                self.log_message_signal("Motor initialized")
                # emit mono initialized signal to ui:
                self.signals.mono_initialized_signal.emit()
                return
            else:
                print("Motor initialization failed.")
                self.log_message_signal(f"Motor initialization failed. Message: {message}")
                # emit mono init failed signal to ui:
                self.signals.mono_init_failed_signal.emit()
                return

        else:
            print("Device not connected")
            self.log_message_signal("Monochromator not connected.")
            return

    def get_firmware_version(self):
        read_main_version = "z"
        if self.device_connected:
            self.device.write_raw(read_main_version.encode())
            return print(self.device.read())
        else:
            print("Device not connected")
            return
    # todo: check if the status is correct, and if the message is correct.
    def get_motor_status(self) -> str:
        """Get the status of the motor.
        :return: 'busy', 'idle', 'unknown', 'error' or 'disconnected'"""
        read_motor_status = "E"
        if self.device_connected:
            self.device.write_raw(read_motor_status.encode())
            message = self.device.read()
            # remove later:
            print(f"Message: {message}")
            # ----------------
            # process message:
            if message[0] == "o":
                print("Message received.")
                if message[1] == "q":
                    print(f"Busy status: {message[1]}, motor is busy.")
                    return 'busy'
                elif message[1] == "z":
                    print(f"Busy status: {message[1]}, motor is idle.")
                    return 'idle'
                else:
                    print(f"Unknown status: {message[1]}")
                return 'unknown'
            else:
                print(f"Unknown message: {message}")
                return 'error'
        else:
            print("Device not connected")
            return 'disconnected'

    def get_motor_position(self, motor_number: str = "0") -> Optional[int]:
        """Get the current position of the motor.
        :param motor_number: motor number, default is 0
        :return: current position(int) of the motor or None if not connected or error"""
        read_cur_pos = "H" + motor_number + "\r"
        if self.device_connected:
            self.device.write_raw(read_cur_pos.encode())
            message = self.device.read()
            # remove later:
            print(f"Message: {message}")
            # ----------------
            # process message:
            if message[0] == "o":
                print("Message received.")
                print(f"Motor {motor_number} position: {message[1:]}")
                return int(message[1:])
            else:
                print(f"Unknown message: {message}")
                return None
        else:
            print("Device not connected")
            return None

    def move_motor_relative(self, move_steps: int, motor_number: str = "0") -> None:
        """Move the motor relative to its current position.
        :param move_steps: steps to move, can be negative or positive
        :param motor_number: motor number, default is 0
        :return: None"""

        move_rel = "F" + motor_number + "," + str(move_steps) + "\r"
        if self.device_connected:
            self.device.write_raw(move_rel.encode())
            message = self.device.read()
            # remove later:
            print(f"Message: {message}")
            # ----------------
            # process message:
            if message[0] == "o":
                print("Message received.")
                return
            else:
                print(f"Unknown message: {message}")
                return
        else:
            print("Device not connected")
            return

    def motor_limit_check(self):
        if self.device_connected:
            read_limit = "K"
            self.device.write_raw(read_limit.encode())
            message = self.device.read()
            print(f"Message: {message}")
            return message
        else:
            print("Device not connected")
            return None

    def motor_stop(self):
        if self.device_connected:
            stop_motor = "L"
            self.device.write_raw(stop_motor.encode())
            message = self.device.read()
            print(f"Message: {message}")
            return
        else:
            print("Device not connected")
            return

    def motorbusy_check(self):
        if self.device_connected:
            read_busy = "E"
            self.device.write_raw(read_busy.encode())
            message = self.device.read()
            print(f"Message: {message}")
            return
        else:
            print("Device not connected")
            return

    def slit_control(self, slit_num: int, width: int):
        """
        send slit width control command (absolute position)
        :param slit_num: 0 for entrance, 3 for exit
        :param width: slit width control
        :return none
        """
        if self.device_connected:
            current_width = self.check_slit_position(slit_num)
            move_width = int(width) - current_width
            command = "k0," + str(slit_num) + "," + str(move_width) + "\r"
            print(command)
            self.device.write_raw(command.encode())
            message = self.device.read()
            print(f"Message: {message}")
            if message == "o":
                # self.send_slitsize_update_signal()
                print(f"Slit {slit_num} moved to {width}")
            else:
                self.log_message_signal("Slit control error.")
            return
        else:
            print("Device not connected")
            self.log_message_signal("Device not connected")
            return

    def log_message_signal(self, message):
        """For emitting mono status signal
        """
        self.signals.log_message_signal.emit(message)
        return

    def send_slitsize_update_signal(self):
        """For emitting mono slit size signal
        :return:
        """
        self.signals.slit_signal.emit()

    def check_mono_connection(self):
        pass

    def check_slit_position(self, slit_num):
        """Check the slit position
        :param slit_num: 0 for entrance, 3 for exit
        :return: slit position (width)
        """
        command = "j0," + str(slit_num) + "\r"
        print(command)
        if self.device_connected:
            self.device.write_raw(command.encode())
            message = self.device.read()
            print(f"Message: {message}")
            width = message[1:-1]
            return int(width)
        else:
            print("Device not connected")
            return
        pass
    
    def set_exit_mirror(self, position):
        """
        Sends the mirror switch command to the Triax hardware.
        position 0: Front Exit (Uses 'f0')
        position 1: Side Exit (Uses 'e0')
        """
        if not self.device_connected:
            return
    
    # Map the position integer to the specific hardware command string
    # Based on your finding: 'f0' for Front, 'e0' for Side
        if position == 0:
            command_string = "f0\r"
        else:
            command_string = "e0\r"

        try:
        # Send the encoded string to the hardware
            self.device.write_raw(command_string.encode())
        
        # Mirror motors are mechanical; the manual suggests a delay
            import time
            time.sleep(2.0) 
        
        except Exception as e:
            print(f"Hardware communication error: {e}")
        
    def set_grating(self, position: int):
        """
        Changes the grating position.
        :param position: 0 for Grating 1 (a0), 1 for Grating 2 (b0)
        """
        if not self.device_connected:
            self.log_message_signal("Device not connected")
            return
        # a0 is position 0, b0 is position 1
        command = "a0\r" if position == 0 else "b0\r"
    
        try:
            print(f"Sending grating command: {command.strip()}")
            self.device.write_raw(command.encode())
        
            # Read response from hardware (typically 'o' for OK)
            response = self.device.read()
            if "o" in response:
                self.log_message_signal(f"Grating changed to Position {position + 1}")
            else:
                self.log_message_signal(f"Hardware response: {response}")
        except Exception as e:
            self.log_message_signal(f"Grating switch error: {e}")