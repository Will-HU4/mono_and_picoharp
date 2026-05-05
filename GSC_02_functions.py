import serial
import serial.tools.list_ports
import time
import threading
from PyQt6.QtCore import QObject, pyqtSignal
import numpy as np

class StepSignal(QObject):
    remaining_step_signal = pyqtSignal(int)
    plot_update_signal = pyqtSignal()
    auto_save_signal = pyqtSignal()


def pico_to_pulses(pico_seconds, speed_of_light=3e8):
    """Convert pico seconds to pulses
    :param pico_seconds: time in pico seconds
    :param speed_of_light: speed of light in m/s
    :return:(int) pulses of interest"""
    # calculate distance to move
    try:
        pico_seconds = float(pico_seconds)
    except ValueError:
        return print("Invalid input")
    distance = (pico_seconds * 1e-12) * speed_of_light
    # convert distance to pulses in integer
    pulses_of_interest = round(distance * 1e6 / 2)
    return pulses_of_interest


def pulses_to_pico(pulses, speed_of_light=3e8):
    """Convert pulses to pico seconds
    :param pulses: pulses of interest
    :param speed_of_light: speed of light in m/s
    :return:(str) time in pico seconds"""
    # calculate time to move
    try:
        pulses = int(pulses)
    except ValueError:
        return print("Invalid input")
    distance_of_interest = pulses * 2e-6
    # convert time to pico seconds in integer
    pico_seconds = round(float(distance_of_interest / speed_of_light) * 1e12, 2)
    return pico_seconds


# def update_port_list():
#     """get list of available ports
#     :return: list of available ports
#     """
#     print("Updating port list...")
#     ports = serial.tools.list_ports.comports()
#     port_list = []
#     for port in ports:
#         try:
#             ser = serial.Serial(port.device)
#             ser.close()
#             print(f"Found port: {port.device}")
#             port_list.append(port.device)
#         except (OSError, serial.SerialException):
#             print(f"Port {port.device} is occupied")
#             pass
#     return port_list


class GSC02Controller:
    def __init__(self):
        # device communication protocol:
        self.baudrate = 9600
        self.timeout = 5
        # device connected stage:
        self.axis = str(1)
        # device object:
        self.gsc02_device = None
        # device status:
        self.start_point = 0
        self.end_point = 0
        self.step_size = 0
        self.total_steps = 0
        self.remaining_steps = 0
        # todo: should be set by user considering the update plot takes time.
        self.waiting_time = 0.5  # in seconds
        self.ready_to_move = False

        self.device_message = ""
        self.ps_values = []  # to store pico seconds values
        self.pulse_values = []  # to store pulse values
        self.ps_from_pulses = []  # to store pico seconds values from pulses

    def connect(self, port):
        """Connect to the device
        :param port: port to connect to the device
        """
        self.gsc02_device = serial.Serial(port)
        self.gsc02_device.baudrate = self.baudrate
        self.gsc02_device.BYTESIZES = serial.EIGHTBITS
        self.gsc02_device.PARITIES = serial.PARITY_NONE
        self.gsc02_device.STOPBITS = serial.STOPBITS_ONE
        self.gsc02_device.timeout = self.timeout
        self.gsc02_device.rtscts = False  # rtscts control gives error response
        # return device status of connection
        if self.gsc02_device.is_open:
            message = f"Connected to device on port {port}"
            return print(message)
        else:
            message = f"Failed to connect to device on port {port}"
            return print(message)

    def disconnect(self):
        """Disconnect from the device
        """
        if self.gsc02_device.is_open:
            self.gsc02_device.close()
            message = "Disconnected from device"
            return print(message)
        else:
            message = "Device is not connected"
            return print(message)

    def stop_command(self, axis):
        """Stop the device on the specified axis
        :param axis: axis to stop aixs 1 or 2, W for both, E for emergency stop
        :return: None
        """
        command = 'L:' + axis + '\r\n'
        message = f"Command:{command}, Stopped axis {axis}"
        self.gsc02_device.write(command.encode())
        return print(message)

    def go_to_mechanical_origin_command(self, origin_of_interest='-'):
        """Go to mechanical origin on the specified axis
        :param origin_of_interest: origin of interest, default is "-" for negative origin"
        :return: None
        """
        print("Going to mechanical origin...")
        if self.gsc02_device is None:
            message = "Device not connected"
            return print(message)
        elif self.gsc02_device.is_open:
            # go to "-" origin
            command = 'H:' + self.axis + "-" + '\r\n'
            print(command)
            self.gsc02_device.write(command.encode())
            message = f"Command:{command}, Going to mechanical origin on axis {self.axis}"
            return print(message)
        else:
            message = "Failed to connect to device try to reconnect the device."
            return print(message)

    def drive_device_command(self):
        """Drive the device
        :return: None
        """
        command = 'G:\r\n'
        print(command)
        self.gsc02_device.write(command.encode())

    def check_position_command(self):
        """Check the position of the device
        :return:(int) position of the device in pulses, -1 for error
        """
        command = 'Q:' + '\r\n'
        print(command)
        if self.gsc02_device is None:
            self.device_message = "Device not connected"
            return -1
        elif self.gsc02_device.is_open:
            self.gsc02_device.write(command.encode())
            rdata = self.gsc02_device.readline()
            # to get return data from Axis 1:
            if self.axis == '1':
                axis_1_data = rdata[0:10].decode('utf-8')
                axis_1_data = int(axis_1_data.strip())
                return axis_1_data
            # to get return data from Axis 2:
            elif self.axis == '2':
                axis_2_data = rdata[10:20].decode('utf-8')
                axis_2_data = int(axis_2_data.strip())
                return axis_2_data
            else:
                return -1
        else:
            self.device_message = "Failed to connect to device try to reconnect the device."
            return -1

    def move_command(self, direction:str, pulses:str):
        """Move the device in the specified direction
        :param direction: direction to move the device, + for positive, - for negative
        :param pulses: number of pulses to move the device
        :return: None
        """
        if direction == '+':
            command = 'M:' + self.axis + '+' + 'P' + pulses + '\r\n'
        elif direction == '-':
            command = 'M:' + self.axis + '-' + 'P' + pulses + '\r\n'
        elif direction == "At the desired position":
            self.device_message = "At the desired position"
            return
        else:
            self.device_message = "Invalid direction"
            return

        self.gsc02_device.write(command.encode())
        # todo: test the delay time minimum:
        time.sleep(0.5)
        # set the device to move
        self.drive_device_command()
        self.device_message = f"Command:{command}, Moving device in direction {direction} with {pulses} pulses"
        return

    def movement(self, desired_position):
        """Determine the direction of movement
        :param desired_position: desired position of the device in pulses
        :return:(str) direction of movement + for positive, - for negative and distance
        """
        current_position = self.check_position_command()
        try:
            desired_position = int(desired_position)
        except ValueError:
            return print("Invalid input")
        # compare to get direction of movement:
        distance = desired_position - current_position
        if distance > 0:
            return '+', abs(distance)
        elif distance < 0:
            return '-', abs(distance)
        else:
            message = "At the desired position"
            return message, 0

    def move_to_position(self, desired_position):
        """Move the device to the desired position
        :param desired_position: desired position of the device in pulses
        :return: None
        """
        if self.gsc02_device is None:
            self.device_message = "Device not connected"
            return
        elif self.gsc02_device.is_open:
            direction, pulses = self.movement(desired_position)
            print(f'Moving device to position {desired_position} in direction {direction} with {pulses} pulses')
            self.move_command(direction, str(pulses))
            return
        else:
            self.device_message = "Failed to connect to device try to reconnect the device."
            return

    def check_point(self, start_point, end_point, step_size):
        """Check the input parameters of the stage for stepping in pico seconds and move the stage to the start point.
        Create a range of pico seconds values (self.ps_values) based on the input parameters.
        :param start_point: start point of the range
        :param end_point: end point of the range
        :param step_size: step size
        :return: (int) status of the input, (str) message
        """
        try:
            start_point = float(start_point)
            end_point = float(end_point)
            step_size = float(step_size)
        except ValueError:
            return -1, "Invalid input, should be numbers."
        if start_point < 0 or end_point < 0 or step_size < 0:
            return -1, "Invalid input, should be positive"
        elif start_point > 662.8 or end_point > 662.8:
            return -1, "Invalid input, should be less than 662.8 ps"
        elif start_point >= end_point:
            return -1, "Invalid input, start point should be less than end point"
        elif step_size == 0:
            return -1, "Invalid input, step size should be greater than 0"
        elif step_size > (end_point - start_point):
            return -1, "Invalid input, step size should be less than the difference between start and end"
        # set the parameters:
        self.start_point = start_point
        self.end_point = end_point
        self.step_size = step_size
        # Calculate the pico seconds values for the range
        self.ps_values = np.arange(start_point, end_point , step_size).tolist()
        if self.ps_values[-1] != end_point:
            self.ps_values.append(end_point)
        print(f"Calculated pico seconds values: {self.ps_values}")
        # Calculate the difference and round it to mitigate floating-point arithmetic errors
        # difference = round(self.end_point - self.start_point, 2)  # Adjust the precision as needed
        # self.total_steps = int(difference / step_size)
        #
        # if difference / step_size - self.total_steps > 0:
        #     self.remaining_steps = self.total_steps + 1
        # else:
        #     self.remaining_steps = self.total_steps

        self.total_steps = len(self.ps_values)
        self.remaining_steps = self.total_steps
        print(f"Parameters confirmed: start point:{self.start_point}, end point:{self.end_point}, "
              f"step size:{self.step_size}, total steps:{self.total_steps}")
        # Calculate corresponding pulse values
        self.pulse_values = [pico_to_pulses(ps) for ps in self.ps_values]

        # Optional: Also store the converted-back pico values (from pulses) to verify round-trip consistency
        self.ps_from_pulses = [float(pulses_to_pico(p)) for p in self.pulse_values]
        print(f"Converted to pulse values: {self.pulse_values}")
        print(f"Pulse values back to pico seconds: {self.ps_from_pulses}")
        # move to start point:
        print(f"Moving to start point {self.start_point}...")
        self.move_to_position(pico_to_pulses(self.start_point))

        # self.ready_to_move = True
        return 0, "parameters confirmed, moving to start point"

    def start_moving(self, signals: StepSignal):
        """Start moving the device
        :return: None
        """
        if self.gsc02_device is None:
            self.device_message = "Device not connected"
            return
        elif self.gsc02_device.is_open:
            for i in range(self.total_steps):
                if self.ready_to_move:

                    self.move_to_position(pico_to_pulses(self.start_point + (i+1) * self.step_size))
                    signals.plot_update_signal.emit()  # Emit the plot update signal
                    self.remaining_steps -= 1
                    signals.remaining_step_signal.emit(self.remaining_steps)

                    print(f"Remaining steps: {self.remaining_steps}")

                    time.sleep(self.waiting_time)
                else:
                    self.device_message = "Device not ready to move"
                    return
            cur_position = self.check_position_command()
            if cur_position == pico_to_pulses(self.end_point):
                self.device_message = "Device reached the end point"
                self.ready_to_move = False
                signals.auto_save_signal.emit()  # Emit the auto save signal
                return
            else:
                self.move_to_position(pico_to_pulses(self.end_point))
                signals.plot_update_signal.emit()  # Emit the plot update signal
                signals.remaining_step_signal.emit(0)
                signals.auto_save_signal.emit()  # Emit the auto save signal
                self.device_message = "Device reached the end point"
                return
        else:
            self.device_message = "Failed to connect to device try to reconnect the device."
            return

    def start_threaded_stepping(self, signals: StepSignal):
        thread = threading.Thread(target=self.start_moving, args=(signals,))
        thread.start()
        return thread, "Stepping started."
