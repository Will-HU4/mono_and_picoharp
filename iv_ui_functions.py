import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog
from mono_ui import Ui_MainWindow  # Import the generated UI class
from pyqt_6220_controller import Keithley6220Qt  # Import Keithley controller
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from datetime import datetime
import pyqtgraph as pg
import numpy as np

class QTextBrowserStream(QObject):
    """Redirects stdout to QTextBrowser."""
    new_text = pyqtSignal(str)  # Define a signal

    def write(self, text):
        """Emit new text to be displayed."""
        self.new_text.emit(text)

    def flush(self):
        """Required for compatibility, but not needed."""
        pass

class IvUiController(QObject):
    def __init__(self,ui: Ui_MainWindow, keithley_controller: Keithley6220Qt):
        super().__init__()
        # self.setupUi(self)  # Setup the UI
        self.ui = ui

        # Initialize Keithley Controller
        self.keithley_controller = keithley_controller  # Adjust address
        # todo: how the signal is emit into a function as params?
        # Connect Signals to UI Updates
        self.keithley_controller.connected_signal.connect(self.update_keithley_status_by_bool)
        self.keithley_controller.error_signal.connect(self.display_error)
        self.keithley_controller.nv_2182a_signal.connect(self.update_2182a_status)
        self.keithley_controller.arm_status_signal.connect(self.update_arm_status)
        self.keithley_controller.output_state_signal.connect(self.update_output_status)
        self.keithley_controller.measurement_signal.connect(self.update_keithley_status_by_bool)
        self.keithley_controller.inner_shield_signal.connect(self.update_inner_shield_status)
        self.keithley_controller.params_set_signal.connect(self.update_param_labels)
        self.keithley_controller.arming_signal.connect(self.update_keithley_status_by_bool)
        self.keithley_controller.abort_signal.connect(self.update_keithley_status_by_bool)
        self.keithley_controller.interlock_signal.connect(self.update_interlock_status)
        self.keithley_controller.iv_data_ready_signal.connect(self.update_iv_plot)
        self.keithley_controller.output_low_signal.connect(self.update_output_low_label)


        # Connect Menu Actions
        self.ui.actionKeithley6220.triggered.connect(self.connect_keithley)
        self.ui.actionKeithley6220_discon.triggered.connect(self.disconnect_keithley)

        # ------------Operation------------------------
        self.ui.actionStart_i_v_measure.triggered.connect(self.start_iv_measure)
        self.ui.actionStop_i_v_measure.triggered.connect(self.abort_process)
        self.ui.actionSet_output_low_GROUND.triggered.connect(self.set_output_low_ground)
        self.ui.actionSet_output_low_FLOAT.triggered.connect(self.set_output_low_float)
        self.ui.actionRetrieve_Data.triggered.connect(self.retrieve_iv_data)
        self.ui.actionStart_measurement.triggered.connect(self.init_measurement)
        self.ui.actionSet_inner_shield_GUARD.triggered.connect(self.set_inner_shield_to_guard)


        # ----------Status check----------------
        self.ui.actionArmed.triggered.connect(self.armed_query)
        self.ui.actionDevice_output_status.triggered.connect(self.query_output_status)
        self.ui.actionError_message.triggered.connect(self.check_error_message)
        self.ui.actionVerify_params.triggered.connect(self.verify_params)
        self.ui.actionInterlock.triggered.connect(self.check_interlock)
        self.ui.actionInner_shield_config.triggered.connect(self.query_inner_shield)
        self.ui.actionOutput_Low_config.triggered.connect(self.query_output_low_setting)
        # ----------Backend func--------------------
        self.ui.actionArm_device.triggered.connect(self.arm_device)
        self.ui.actionStop_arm_query_timer.triggered.connect(self.stop_arm_timer)
        self.ui.actionsave_data.triggered.connect(self.save_data)
        # ----------File------------------
        # self.actionChange_save_location.triggered.connect(self.select_folder)




        # Initialize the output redirection (print function display)
        self.output_stream = QTextBrowserStream()
        self.output_stream.new_text.connect(self.append_output)  # Connect signal to slot
        sys.stdout = self.output_stream  # Redirect stdout to QTextBrowserStream


        # Initialize the plot
        self.plot = self.ui.ui_plot_canva
        self.plot.setBackground("w")  # ✅ White background
        self.plot.setLabel("left", "Voltage (V)")
        self.plot.setLabel("bottom", "Current (A)")
        self.plot.addLegend()
        self.plot.setMouseEnabled(x=False, y=False)

        # Add curve for real-time updates
        self.curve = self.plot.plot([], [], pen=pg.mkPen(color="b", width=2), name="I-V Curve")

        # self.set_file_location_label()
        self.y_range = None

    def append_output(self, text):
        """Appends redirected stdout text to status box."""
        if text.strip():  # Avoid adding empty lines
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"[{timestamp}] {text.strip()}"
            self.ui.console_statusbox.append(message)
            self.ui.console_statusbox_mono.append(message)
            self.ui.picoharb_log_display.append(message)

    # def closeEvent(self, event):
    #     """Restore stdout when closing the application."""
    #     sys.stdout = sys.__stdout__
    #     event.accept()

    def connect_keithley(self):
        """Handles device connection."""
        self.log_message("Connection Keithley 6220 initiating.")
        self.keithley_controller.connect_device()

    def log_message(self, message):
        """Helper function to log messages with a timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.ui.keithley6220_statusbox.append(f"[{timestamp}] {message}")

    def disconnect_keithley(self):
        """Handles device disconnection."""
        self.log_message("Disconnecting.")
        self.keithley_controller.disconnect_device()

    def update_keithley_status_by_bool(self, success, message):

        """Updates the Keithley 6220 status box with a timestamp."""
        if success:
            self.log_message(f"Success: {message}")
        else:
            self.log_message(f"Error: {message}")

    def update_2182a_status(self, message):
        """Updates the Keithley 2182A status label."""
        self.ui.nv_2182a_label.setText(message)

    def update_inner_shield_status(self, status):
        """Updates the Inner Shield Status label."""
        self.log_message(f"Inner shield status is {status}.")
        self.ui.inner_shield_label.setText(status)

    def update_arm_status(self, armed):
        """Updates the Arm Status label."""
        status = "Armed" if armed else "Not Armed"
        self.log_message(f"Armed status is {status}.")
        self.ui.arm_status_label.setText(status)

    def update_output_status(self, status):
        """Updates the Output Status label."""
        self.log_message(f"The output status is: {status}.")
        self.ui.output_status_label.setText(status)

    def display_error(self, message):
        """Displays error messages."""
        self.log_message(f"Error: {message}")

    def arm_device(self) -> bool:
        """Set the params for measurment and arm the Keithley device.
        :returns: True if arming is underprocess, False otherwise."""
        self.log_message("Arming device.")
        try:
            start_current = float(self.ui.start_cur_inputbox.toPlainText())
            stop_current = float(self.ui.stop_cur_inputbox.toPlainText())
            step_size = float(self.ui.cur_step_inputbox.toPlainText())
            delay = float(self.ui.delay_inputbox.toPlainText()) if self.ui.delay_inputbox.toPlainText() else 0.002
            delta = float(self.ui.delta_inputbox.toPlainText()) if self.ui.delta_inputbox.toPlainText() else 1e-5

            # Set measurement parameters
            param_is_set = self.keithley_controller.set_diff_cond_params(start_current, stop_current, step_size, delay, delta)
            if param_is_set:
                self.keithley_controller.arm_device()
                self.log_message("Arming underprocess.")
                return True
            else:
                self.display_error("Failed to set parameters for arming!")
                return False

        except ValueError:
            self.display_error("Invalid input values for arming!")
            return False

    def start_iv_measure(self):
        """Starts IV measurement using the given parameters from UI."""
        self.log_message("Start measurment.")
        try:
            arm_response = self.arm_device()
            if arm_response:
                self.log_message("Arming successful, starting measurement.")
                # Delay calling `init_measurement()` by 5 seconds (5000 ms)
                QTimer.singleShot(5000, self.init_measurement)
            # have to check how the device reponse when under measurement.
        except ValueError:
            self.display_error("Invalid input values!")

        # try:
        #     start_current = float(self.start_cur_inputbox.toPlainText())
        #     stop_current = float(self.stop_cur_inputbox.toPlainText())
        #     step_size = float(self.cur_step_inputbox.toPlainText())
        #     delay = float(self.delay_inputbox.toPlainText()) if self.delay_inputbox.toPlainText() else 0.002
        #     delta = float(self.delta_inputbox.toPlainText()) if self.delta_inputbox.toPlainText() else 1e-5
        #
        #     # Set measurement parameters
        #     self.keithley_controller.set_diff_cond_params(start_current, stop_current, step_size, delay, delta)
        #     self.keithley_controller.initialize_differential_conductance()
        #
        # except ValueError:
        #     self.display_error("Invalid input values!")

    def abort_process(self):
        """Aborts the measurement process."""
        print("Aborting process.")
        self.keithley_controller.abort_process()

    def armed_query(self):
        """Query arm status."""
        self.log_message("Armed query sent.")
        self.keithley_controller.check_arm()
        
    def query_inner_shield(self):
        """Query the inner shield status."""
        self.log_message("Inner shield config query sent.")
        self.keithley_controller.query_inner_shield()
        pass

    def query_output_status(self):
        """Query the output status."""
        self.log_message("Output status query sent.")
        self.keithley_controller.update_output_state()

    def init_measurement(self) -> bool:
        """start the iv measurement.
        :returns: True if successful, False otherwise."""
        self.log_message("Measurement command sent.")
        start_measure = self.keithley_controller.initialize_differential_conductance()
        if start_measure:
            self.log_message("Measurement started successfully.")
            return True
        else:
            self.display_error("Failed to start measurement.")
            return False

    def check_error_message(self):
        """Check for error messages."""
        self.log_message("Error message query sent.")
        self.keithley_controller.check_err_message()



    def verify_params(self):
        """Read inputs and set params to 6220 then verify params are correctly set."""
        self.log_message("Verifying parameters.")
        try:
            start_current = float(self.ui.start_cur_inputbox.toPlainText())
            stop_current = float(self.ui.stop_cur_inputbox.toPlainText())
            step_size = float(self.ui.cur_step_inputbox.toPlainText())
            delay = float(self.ui.delay_inputbox.toPlainText()) if self.ui.delay_inputbox.toPlainText() else 0.002
            delta = float(self.ui.delta_inputbox.toPlainText()) if self.ui.delta_inputbox.toPlainText() else 1e-5

            # Set measurement parameters
            self.keithley_controller.set_diff_cond_params(start_current, stop_current, step_size, delay, delta)
            self.keithley_controller.verify_params()
        except ValueError:
            self.display_error("Invalid input values!")

    def update_param_labels(self, total_points, estimated_time):
        """Update differential conductance parameters, total points and estimated time in ui label."""
        self.log_message("Parameters updated.")
        self.ui.start_current_lab.setText(str(self.keithley_controller.start))
        self.ui.stop_current_lab.setText(str(self.keithley_controller.stop))
        self.ui.current_step_lab.setText(str(self.keithley_controller.step))
        self.ui.delay_label.setText(str(self.keithley_controller.delay))
        self.ui.delta_label.setText(str(self.keithley_controller.delta))
        self.ui.remain_time_label.setText(str(estimated_time))
        self.ui.totalpoint_label.setText(str(total_points))

    def set_inner_shield_to_guard(self):
        self.log_message("Setting inner shield to GUARD.")
        self.keithley_controller.set_inner_shield_to_guard()

    def check_interlock(self):
        self.log_message("Query interlock status")
        self.keithley_controller.check_interlock()

    def update_interlock_status(self, status):
        if status:
            self.ui.interlock_label.setText("LOCKED")
        else:
            self.ui.interlock_label.setText("OPEN")

    def update_iv_plot(self):
        """Plots the stored I-V data using PyQtGraph."""
        self.log_message("Plotting I-V data.")
        # set range for y-axis if specified
        x_vals = self.keithley_controller.current_values
        y_vals = self.keithley_controller.voltage_values
        # set the y-range if specified
        if self.y_range is not None:
            y_min, y_max = self.y_range
        else:
            # Automatically calculate a reasonable y-range based on the IQR method
            y_min, y_max = self.get_sane_yrange(y_vals)
            print(f"[Auto Range] y_range estimated as: ({y_min:.3f}, {y_max:.3f})")
            # set the y-range label
            self.ui.y_range_label.setText(f"Y Range: [{y_min:.3f}, {y_max:.3f}]")
        self.plot.setYRange(y_min, y_max)

        # Mask y-values that are out of the specified range
        x_vals, y_masked_vals = self.mask_y_for_plot(x_vals, y_vals, y_min, y_max)

        # Enable auto range for x-axis
        self.plot.enableAutoRange(axis='x', enable=True)
        # Update the plot with the new data
        self.curve.setData(x_vals, y_masked_vals)

    def retrieve_iv_data(self):
        """Retrieve the I-V data from the Keithley device."""
        self.log_message("Retrieving I-V data.")
        self.keithley_controller.retrieve_iv_data()

    def stop_arm_timer(self):
        """Special function for stopping the arming timer. """
        self.log_message("Stop arm timer.")
        self.keithley_controller.stop_arming_monitor()

    # def select_folder(self):
    #     """Select the folder to save the data."""
    #     self.log_message("Selecting folder to save data.")
    #     self.keithley_controller.select_directory()
    #     self.set_file_location_label()

    # def set_file_location_label(self):
    #     """Set the file location to save the data."""
    #     location = self.keithley_controller.get_saved_directory()
    #     self.ui.file_location_label.setText(f"{self.keithley_controller.save_directory}")
    #     self.log_message(f"Save location set to: {self.keithley_controller.save_directory}")
    #     print(f"{location}")

    def save_data(self):
        """Save the data to a file."""
        self.log_message("Saving data.")
        data = (
            "-2.55496531E-08VDC,+0.000SECS,+1.5000E-05ADC,TCMPL,+3.98611655E-06VDC,+00000RDNG#,-7.22662719E-07VDC,+0.088SECS,"
            "+1.7000E-05ADC,TCMPL,+4.32040360E-06VDC,+00001RDNG#,-1.09323287E-06VDC,+0.175SECS,+1.9000E-05ADC,TCMPL,+4.77228332E-06VDC,"
            "+00002RDNG#,-8.66215430E-07VDC,+0.263SECS,+2.1000E-05ADC,TCMPL,+4.58538170E-06VDC,+00003RDNG#,-7.59716784E-07VDC,+0.351SECS,"
            "+2.3000E-05ADC,TCMPL,+4.34272442E-06VDC,+00004RDNG#")
        self.keithley_controller.save_raw_iv_data(data)

    def set_output_low_ground(self):
        self.log_message("Setting output to low ground.")
        self.keithley_controller.set_output_low_grounded_controller()

    def set_output_low_float(self):
        self.log_message("Setting output to low float.")
        self.keithley_controller.set_output_low_floating_controller()

    def query_output_low_setting(self):
        """Query the output_low pin setting."""
        self.log_message("Querying output low config.")
        self.keithley_controller.query_output_low_setting()

    def update_output_low_label(self, response):
        """Updates the log message based on the Output Low setting response."""
        status = "FLOAT" if response == "0" else "GROUND"
        self.log_message(f"The output_low setting is {status}")
        self.ui.output_low_config_label.setText(status)

    def ui_read_y_range(self):
        """Read the y-range from the plot widget."""
        text = self.ui.y_range_input.toPlainText().strip()

        if not text:
            self.y_range = None
            self.ui.y_range_label.setText("Y Range: None set")
            print("[Y Range] No input provided, y_range set to None.")
            return

        try:
            # parse the input text for y-range
            cleaned = text.replace("[", "").replace("]", "")
            parts = cleaned.split(",")

            if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
                raise ValueError("Y range must be in the format '[min, max]' and both values must be valid numbers")

            y_min = float(parts[0].strip())
            y_max = float(parts[1].strip())

            if y_min >= y_max:
                raise ValueError("y_min must be less than y_max")

            self.y_range = [y_min, y_max]
            self.ui.y_range_label.setText(f"Y Range: {self.y_range}")
            print(f"[Y Range] Set to: {self.y_range}")

        except Exception as e:
            self.y_range = None
            self.ui.y_range_label.setText("Y Range: None set")
            print(f"[Y Range Error]：'{text}' → {e}")

    def get_sane_yrange(self, y_vals, multiplier=1.5, fallback_range=(-5, 5)):
        """Calculate a reasonable y-range based on the IQR method."""
        y_vals = np.array(y_vals, dtype=np.float64)
        y_vals = y_vals[np.isfinite(y_vals)]

        if len(y_vals) == 0:
            return fallback_range

        q1 = np.percentile(y_vals, 25)
        q3 = np.percentile(y_vals, 75)
        iqr = q3 - q1

        lower_bound = q1 - multiplier * iqr
        upper_bound = q3 + multiplier * iqr


        if not np.isfinite(lower_bound) or not np.isfinite(upper_bound):
            return fallback_range


        if abs(upper_bound - lower_bound) < 1e-6 or abs(upper_bound) > 1e6:
            return fallback_range

        return lower_bound, upper_bound

    def mask_y_for_plot(self, x_vals, y_vals, y_min, y_max):
        """Mask y-values that are out of the specified range."""
        x_vals = np.array(x_vals, dtype=np.float64)
        y_vals = np.array(y_vals, dtype=np.float64)

        # mask out of bound y val with np.nan
        y_masked = np.where((y_vals >= y_min) & (y_vals <= y_max), y_vals, np.nan)
        return x_vals, y_masked

# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     window = IVMainWindow()
#     window.show()
#     sys.exit(app.exec())
