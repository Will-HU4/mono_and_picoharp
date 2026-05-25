import random
import fileIO
import newport_1835c_serial
import plotting_module
import serial_manage
from PyQt6.QtCore import pyqtSlot, QTimer, Qt, pyqtSignal, QCoreApplication, QObject
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QMessageBox, QFileDialog
import pyqtgraph as pg
from PyQt6.QtGui import QPalette, QColor
import time
import datetime
import triax_320
from mono_ui import Ui_MainWindow  # Import the generated UI class
import GSC_02_functions as gsc_functions
import pyvisa
import threading
import json
import os
import numpy as np
from pyqt_6220_controller import Keithley6220Qt
import sys
import iv_ui_functions
import picoharp300_controller

POWERMETER_SAMPLES = 5

from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt

def get_dark_palette():
    palette = QPalette()
    # 真正的深色模式背景 (深灰/接近黑)
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    
    # 輸入框、列表的背景 (稍微淺一點的深灰，拉出立體感)
    palette.setColor(QPalette.ColorRole.Base, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(55, 55, 55)) # 微調交替色
    
    # 提示框：黑底白字或黑底黃字
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(10, 10, 10))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 215, 0)) # 黃色字很適合深色提示
    
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    
    # 按鈕顏色
    palette.setColor(QPalette.ColorRole.Button, QColor(50, 50, 50))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    
    # 科技藍高亮
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white) # 選取時字變白比較好讀
    return palette

def get_light_palette():
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.black)
    palette.setColor(QPalette.ColorRole.Base, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(233, 233, 233))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 225))
    palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.black)
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.black)
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(120, 120, 120)) # 修正輸入框提示字的白字殘留
    palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.black)
    palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    palette.setColor(QPalette.ColorRole.Midlight, QColor(227, 227, 227))
    palette.setColor(QPalette.ColorRole.Mid, QColor(160, 160, 160))
    palette.setColor(QPalette.ColorRole.Dark, QColor(115, 115, 115))
    palette.setColor(QPalette.ColorRole.Shadow, QColor(105, 105, 105))
    palette.setColor(QPalette.ColorRole.Link, QColor(0, 120, 215))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 215))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    
    return palette

# picoharp heatmap plot class:
class PicoHarpHeatmapView(pg.GraphicsLayoutWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=False)

        # upper part: heatmap
        self.p1 = self.addPlot(row=0, col=0)
        self.p1.setLabel('bottom', 'Wavelength index')
        self.p1.setLabel('left', 'Time', units='ns')
        self.img = pg.ImageItem()
        self.p1.addItem(self.img)

        # right side: total counts vs wavelength index
        # self.p2 = self.addPlot(row=0, col=1)
        # self.p2.setLabel('bottom', 'Wavelength index')
        # self.p2.setLabel('left', 'Total counts / ms')
        # self.total_curve = self.p2.plot(pen=None, symbol='o', symbolSize=4)

        # lower part: single decay curve
        self.p3 = self.addPlot(row=0, col=1)
        self.p3.setLabel('bottom', 'Time', units='ns')
        self.p3.setLabel('left', 'Counts')
        self.decay_curve = self.p3.plot()

        # state variables
        self.heat = None
        self.rebin_factor = 64
        self.time_bin_ps = None
        self.N_points = None
        self.wavelengths = None
        self._log_z = False

        # interaction - hover to see single decay
        self.p1.scene().sigMouseMoved.connect(self._on_mouse)


    def _rebin_hist(self, counts: np.ndarray, factor: int) -> np.ndarray:
        """Rebin a 1D histogram by summing over 'factor' bins to reduce ui loading.
        :param counts: 1D array of histogram counts
        :param factor: rebin factor (must be integer > 1)
        :returns: rebinned 1D array"""

        arr = np.asarray(counts, dtype=np.uint32)
        n = arr.size - (arr.size % factor)
        return arr[:n].reshape(-1, factor).sum(axis=1)


    def begin_scan(self, N_points, resolution_ps, rebin_factor=64, x_values=None, wavelengths=None):
        """Initialize the heatmap for a new scan.
        :param N_points: number of wavelength points (x axis)
        :param resolution_ps: time resolution per bin (y axis) in picoseconds
        :param rebin_factor: rebin factor to reduce y axis bins (default: 64)
        :param wavelengths: optional array of actual wavelength values for x axis (default: None)"""

        self.rebin_factor = rebin_factor
        self.time_bin_ps = resolution_ps
        self.N_points = N_points

        # rebin original bins and create empty heatmap array
        bins_rebinned = 65536 // rebin_factor
        self.heat = np.zeros((bins_rebinned, N_points), dtype=np.float32)

        # add image to plot and scale axes
        self.img.setImage(self.heat, autoLevels=True)
        self.img.resetTransform()

        # y axis: rebin_factor * resolution_ps（ps）→ ns
        y_scale_ns_per_pix = (rebin_factor * resolution_ps) * 1e-3
        self.img.scale(1.0, y_scale_ns_per_pix)
        self.p1.setLabel('left', 'Time', units='ns')


        # x axis: index, mono steps, or wavelengths
        if wavelengths is not None:
            self.wavelengths = np.asarray(wavelengths, dtype=float)
            self._x_coords = self.wavelengths
            # sparse ticks (≤10)
            if N_points > 0:
                idxs = np.linspace(0, N_points - 1, num=min(N_points, 10), dtype=int)
                ticks = [(int(i), f"{self._x_coords[i]:.1f}") for i in idxs]
                self.p1.getAxis('bottom').setTicks([ticks])
            self.p1.setLabel('bottom', 'Wavelength', units='nm')

        elif x_values is not None:
            self.wavelengths = None
            self._x_coords = np.asarray(x_values)
            if N_points > 0:
                idxs = np.linspace(0, N_points - 1, num=min(N_points, 10), dtype=int)
                ticks = [(int(i), str(self._x_coords[i])) for i in idxs]
                self.p1.getAxis('bottom').setTicks([ticks])
            self.p1.setLabel('bottom', 'Mono step')

        else:
            self.wavelengths = None
            self._x_coords = np.arange(N_points)
            self.p1.setLabel('bottom', 'Index')

        self.p1.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)


    def update_point(self, i: int, counts, tacq_ms: int, log_z: bool = True):
        """Update the heatmap with a new histogram at point i."""
        if self.heat is None:
            raise RuntimeError("Call begin_scan() before update_point().")

        self._log_z = log_z

        # fill in heatmap column i
        reb = self._rebin_hist(counts, self.rebin_factor).astype(np.float32)
        self.heat[:, i] = reb

        # heatmap image
        arr = np.log1p(self.heat) if self._log_z else self.heat
        self.img.setImage(arr, autoLevels=(i == 0))

        # total_curve removed (p2 plot is commented out)


    def _on_mouse(self, pos):
        """Show the decay curve at the hovered x position."""
        if self.heat is None:
            return

        vb = self.p1.getViewBox()
        mp = vb.mapSceneToView(pos)
        x_idx = int(round(mp.x()))  # x index (wavelength index or step index)

        if x_idx < 0 or x_idx >= self.N_points:
            return

        # time axis in ns
        bins_rebinned = self.heat.shape[0]
        t_ns = (np.arange(bins_rebinned) * self.rebin_factor * self.time_bin_ps) * 1e-3
        y = self.heat[:, x_idx]
        self.decay_curve.setData(t_ns, y)

        # label with wavelength or step
        if getattr(self, "wavelengths", None) is not None:
            x_label = f"λ={self.wavelengths[x_idx]:.1f} nm"
        else:

            x_val = self._x_coords[x_idx] if hasattr(self, "_x_coords") else x_idx
            x_label = f"step={x_val}"

        self.p3.setTitle(f"Decay @ {x_label} (idx {x_idx})")


# picoharp signals:
class PicoSignals(QObject):
    """Signals for PicoHarp worker thread to communicate with the main thread."""
    # (N_points, resolution_ps, rebin_factor, x_values, x_mode)
    # x_mode: 'index' | 'step' | 'wavelength'
    begin_scan = pyqtSignal(int, float, int, object, object)

    # (index, result_dict, tacq_ms, log_z)
    new_point = pyqtSignal(int, object, int, bool)
    #
    update_pico_serial_signal = pyqtSignal()
    #
    update_pico_init_status_signal = pyqtSignal(bool)
    #
    update_pico_hardware_status_signal = pyqtSignal()
    # binning, offset, sync_divider, cfd_level_0, cfd_zc_0, cfd_level_1, cfd_zc_1
    update_labels = pyqtSignal(int, int, int, float, float, float, float)


class QTextBrowserStream(QObject):
    """Redirects stdout to QTextBrowser."""
    new_text = pyqtSignal(str)  # Define a signal

    def write(self, text):
        """Emit new text to be displayed."""
        self.new_text.emit(text)

    def flush(self):
        """Required for compatibility, but not needed."""
        pass

class UiSignal(QObject):
    """Signals for safely updating UI from worker threads."""
    mono_powermeter_log_signal = pyqtSignal(str)
    update_powermeter_unit_signal = pyqtSignal(str)
    update_power_lcd_signal = pyqtSignal(float)
    update_filename_signal = pyqtSignal(str)


class MainWindow(QMainWindow):
    upadte_powermeter_plot_signal = pyqtSignal()
    update_monoscan_remainstep_signal = pyqtSignal(int)
    updare_monoscan_remaintest_signal = pyqtSignal(int)
    def __init__(self):
        """Initializes the MainWindow object with the spectrometer device information.
        """
        super().__init__()
        self.ui = Ui_MainWindow()  # Create an instance of the UI class
        self.ui.setupUi(self)  # Set up the UI

        # Device state:
        self.stage_started = False
        self.spectrometer_connected = False  # kept for legacy attribute checks
        self.stage_connected = False
        self.plotting_started = False
        # Track the current mode:
        self.is_dark_mode = True
        self.setPalette(get_dark_palette())  # Set the initial palette
        # To keep track of the row count for caching:
        self.row_count = 0
        # for mono scan function and plot update:
        self.x_values = []
        self.mono_wavelengths = []
        self.y_values = []
        self.mapping_exists: bool = False
        self.mapping_coefficients: tuple[float | None, float | None] = (None, None)
        self.min_resolution: float | None = None
        self.test_num = 0

        # flag for mono scan loop:
        self.mono_stop_flag = threading.Event()
        self.mono_stop_flag.set()

        # Initialize objects for mono initilization dialog:
        self.msg_box = None
        self.mono_init_countdown = 100
        self.mono_init_timer = QTimer(self)
        self.mono_init_timer.timeout.connect(self.update_mono_init_dialog_countdown)

        # Initialize the plot data object:
        self.plot_data = None
        # Initialize the worker thread object:
        self.thread = None

        self.stage = gsc_functions.GSC02Controller()

        # Create a PyQtGraph plot widget and add it to the plotwidget:
        self.plot_widget = pg.PlotWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.plot_widget)
        self.ui.plotwidget.setLayout(layout)

        # Initialize the start position check timer:
        self.position_check_timer = QTimer(self)
        self.position_check_timer.timeout.connect(self.check_device_position)
        self.check_time = 2000
        self.check_position_retries = 0
        self.max_retries = 15  # Timeout after 15 retries (30 secs)


        # create power meter object:
        self.power_meter = newport_1835c_serial.Newport1835C()
        # create mono object:
        rm = pyvisa.ResourceManager()
        self.mono = triax_320.Triax320(resource_manager=rm)
        # file handling:
        self.file = fileIO.FileIO()
        self.plot = plotting_module.PlotData(self.plot_widget)
        self.ui_signal = UiSignal()  # Instantiate the signal container
        self.ui_functions_init()
        self.ui_set_labels()
        self.signals_connect()
        self.initialize_ui_mode()

        # Start the power meter readings timer with a 500 ms interval
        self.start_power_meter_timer(timer_interval=500)
        # motor check status timer for mono goto button:
        self.setup_motor_status_timer()

        # Initialize the output redirection (print function display)
        # self.output_stream = QTextBrowserStream()
        # self.output_stream.new_text.connect(self.append_output)  # Connect signal to slot
        # sys.stdout = self.output_stream  # Redirect stdout to QTextBrowserStream

        # picoharp controller
        # todo: picoharp dll path setting
        self.picoharp = picoharp300_controller.PicoHarpController()
        self._pico_hw_busy = False
        # flag for pico measurement loop:
        self.pico_meas_stop_flag = threading.Event()
        self.pico_meas_stop_flag.set()
        # ----- pico plot init -----
        self.pico_sig = PicoSignals()
        self.pico_view = PicoHarpHeatmapView(parent=self.ui.picoharp_plot)
        pico_layout = QVBoxLayout(self.ui.picoharp_plot)
        pico_layout.addWidget(self.pico_view)

        # ----- pico signal connect -----
        self.pico_sig.begin_scan.connect(
            lambda N, res_ps, rbin, xvals, wl:
            self.pico_view.begin_scan(N, res_ps, rbin, x_values=xvals, wavelengths=wl)
        )

        self.pico_sig.new_point.connect(
            lambda i, res, tacq, logz:
            self.pico_view.update_point(i, res, tacq, log_z=logz)
        )
        self.pico_sig.update_pico_serial_signal.connect(self.update_pico_serial_label)
        self.pico_sig.update_pico_init_status_signal.connect(lambda init:
                                                             self.update_pico_init_label(inited=init))
        self.pico_sig.update_labels.connect(
            lambda binning, offset, sync_div, lev0, zc0, lev1, zc1:
            self.update_pico_labels(binning, offset, sync_div, lev0, zc0, lev1, zc1)
        )

    # def append_output(self, text):
    #     """Appends redirected stdout text to status box."""
    #     if text.strip():  # Avoid adding empty lines
    #         timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    #         self.ui.console_statusbox.append(f"[{timestamp}] {text.strip()}")

    def signals_connect(self):
        """Connect qt signals with the functions to perform"""
        # plot update signal

        #self.upadte_powermeter_plot_signal.connect(lambda: self.plot.update_plot(self.x_values, self.y_values,
                                                                                 #unit=self.power_meter.device_unit))
        self.upadte_powermeter_plot_signal.connect(
            lambda: self.plot.update_plot(
                self.mono_wavelengths if self.mono_wavelengths else self.x_values,
                self.y_values,
                unit=self.power_meter.device_unit,
                mono_unit='nm' if self.mono_wavelengths else 'step'
            )
        )

        self.ui.mono_wl_spinbox.valueChanged.connect(self.update_step_display)

        # mono signals:
        self.mono.signals.log_message_signal.connect(self.mono_and_power_meter_log)
        self.mono.signals.slit_signal.connect(self.mono_slit_label_set_text)
        self.mono.signals.init_mono_signal.connect(self.prompt_initmono_at_start)
        self.mono.signals.mono_start_init_signal.connect(self.show_initialization_dialog)
        self.mono.signals.mono_initialized_signal.connect(self.close_mono_init_dialog)
        self.mono.signals.mono_init_failed_signal.connect(self.close_mono_init_dialog)

        # power meter signals:
        self.power_meter.signals.log_message_signal.connect(self.mono_and_power_meter_log)
        # mono_scan_signals:
        self.update_monoscan_remainstep_signal.connect(self.mono_remaining_step)
        self.updare_monoscan_remaintest_signal.connect(self.mono_remaining_test)
        # Initialize the signals object for worker threads to control main window from stage stepping threads:
        self.signals = gsc_functions.StepSignal()
        self.signals.remaining_step_signal.connect(self.update_remaining_steps)
        self.signals.plot_update_signal.connect(self.update_plot)
        self.signals.auto_save_signal.connect(self.auto_save)
        # message logging signal:
        self.ui_signal.mono_powermeter_log_signal.connect(self.mono_and_power_meter_log)
        # power meter unit update signal:
        self.ui_signal.update_powermeter_unit_signal.connect(self.update_powermeter_unit_label)
        # power meter readings LCD update signal:
        self.ui_signal.update_power_lcd_signal.connect(self.update_power_readings_display)
        # filename update signal:
        self.ui_signal.update_filename_signal.connect(self.change_save_filename)

    def ui_functions_init(self):
        """initialized ui's functions"""
        self.connect_button_signal()
        self.connect_Qaction_signals()
        self.update_port_list()

    def update_remaining_steps(self, remaining_steps):
        """Update the remaining stage steps label in the UI."""
        self.ui.remaining_steps_label.setText(f"{remaining_steps}/{self.stage.total_steps}")

    def connect_button_signal(self):
        """Connect UI buttons to their respective methods.
        """
        self.ui.update_port_button.clicked.connect(self.update_port_list)
        self.ui.get_position_button.clicked.connect(self.get_stage_position)
        self.ui.goto_position_button.clicked.connect(self.goto_position)
        self.ui.confir_input_button.clicked.connect(self.confirm_stage_parameters_input)
        self.ui.start_stage_button.clicked.connect(self.start_stepping)
        self.ui.stop_stage_button.clicked.connect(self.stop_stepping)
        self.ui.test_button.clicked.connect(self.test_function)
        self.ui.start_mono_button.clicked.connect(self.start_mono_scan)
        self.ui.stop_mono_button.clicked.connect(self.stop_mono_scan)
        self.ui.mono_confirm_slit_size_button.clicked.connect(self.adjust_mono_slit)
        self.ui.test_button2.clicked.connect(self.test_function_2)
        self.ui.emergenency_stop_botton.clicked.connect(self.ultimate_stop)
        self.ui.mono_goto_button.clicked.connect(self.mono_goto_button_clicked)
        self.ui.run_all_pushButton.clicked.connect(self.ui_start_mono_stage_scan)
        self.ui.stop_all_pushButton.clicked.connect(self.ui_stop_mono_stage_scan)
        self.ui.start_iv_meas_button.clicked.connect(self.ui_start_iv_curve_meas)
        self.ui.stop_iv_meas_button.clicked.connect(self.ui_stop_iv_curve_meas)
        self.ui.start_mono_iv_button.clicked.connect(self.ui_start_mono_iv_curve_meas)
        self.ui.stop_mono_iv_button.clicked.connect(self.ui_stop_mono_iv_curve_meas)
        self.ui.picoharp_connect_button.clicked.connect(self.ui_connect_picoharp)
        self.ui.picoharp_disconnect_button.clicked.connect(self.ui_disconnect_picoharp)
        self.ui.picoharp_start_mono_button.clicked.connect(self.start_pico_mono_scan)
        self.ui.picoharp_stop_mono_button.clicked.connect(self.stop_pico_mono_scan)
        self.ui.exit_toggle_btn.clicked.connect(self.handle_mirror_switch)
        self.ui.grating_toggle_btn.clicked.connect(self.handle_grating_switch)

    def connect_Qaction_signals(self):
        """Connect the QAction signals to their respective methods.
        """
        self.ui.actionDark_Light_mode.triggered.connect(self.toggle_palette)
        self.ui.actionConnect_stage.triggered.connect(self.connect_stage)
        self.ui.actionClose_stage.triggered.connect(self.close_connection)
        self.ui.actionClose_spectrometer.triggered.connect(self.close_spectrometer)
        self.ui.actionChange_data_directory.triggered.connect(self.change_save_location)
        self.ui.actionExport.triggered.connect(self.export_csv)
        self.ui.actionReturn_to_home.triggered.connect(self.stage.go_to_mechanical_origin_command)
        self.ui.actionStart_ploting.triggered.connect(self.start_continuous_update)
        self.ui.actionStop_plotting.triggered.connect(self.stop_continuous_update)
        self.ui.actionConnec_power_meter.triggered.connect(lambda: self.power_meter.connect_device(
            port=self.ui.com_port_comboBox.currentText()))
        self.ui.actionClose_power_meter.triggered.connect(self.power_meter.disconnect_device)
        self.ui.actionConnect_monochromator.triggered.connect(self.mono.connect_device)
        self.ui.actionclose_monochromator.triggered.connect(self.mono.close_device)
        self.ui.actionInitialize_monochromator.triggered.connect(self.initialize_motor_with_prompt)
        self.ui.actionCheck_monochromator_state.triggered.connect(self.check_mono_program_state_ui)
        self.ui.actionEnter_main_program.triggered.connect(self.mono_enter_main_program_ui)
        self.ui.actionGet_current_position.triggered.connect(self.set_mono_pos_label)
        self.ui.actionCheck_limit.triggered.connect(self.ui_check_motor_limit)
        
    
    def handle_mirror_switch(self):
        if not self.mono.device_connected:
            self.mono_and_power_meter_log("Error: Monochromator not connected.")
            return

        if not self.mono_stop_flag.is_set():
            self.mono_and_power_meter_log("Cannot switch ports during active scan!")
            return

    # READ FROM DROPDOWN: 0 for Front, 1 for Side
        target_pos = self.ui.mono_mirror_select_comboBox_2.currentIndex()

    # Send command to hardware (o0 or o1)
        self.mono.set_exit_mirror(target_pos)
        self.mono.current_mirror_pos = target_pos

    # Update the "Current Position" label to match the movement
        port_text = "Side" if target_pos == 1 else "Front"
        self.ui.Mirror_current_position_label.setText(f'Mirror exit: {port_text}')
    
        self.mono_and_power_meter_log(f"Mirror command sent: Moving to {port_text} Exit.")

    '''def sync_mirror_from_hardware(self):
        """Force hardware to Side Exit on connect and verify."""
        if not self.mono.device_connected:
            return

        # 1. Force move to Side Exit (Position 1)
        self.mono.set_exit_mirror(1)
        self.mono_and_power_meter_log("Initializing mirror to Side Exit...")
        time.sleep(0.5)  # Give hardware a moment to react

        # 2. Query to confirm using pyvisa device (not self.mono.ser which doesn't exist)
        try:
            self.mono.device.write_raw(b"w\r")
            time.sleep(0.1)
            response = self.mono.device.read().strip()
        except Exception as e:
            self.mono_and_power_meter_log(f"Mirror sync query failed: {e}")
            response = ""

        # 3. Update UI based on confirmed truth
        if "1" in response:
            self.ui.Mirror_current_position_label.setText(f'Mirror exit: {port_text}')
            self.ui.mono_mirror_select_comboBox_2.setCurrentIndex(1)
            self.mono_and_power_meter_log("Hardware Check: Side Exit confirmed.")
        else:
            self.ui.Mirror_current_position_label.setText("Front")
            self.ui.mono_mirror_select_comboBox_2.setCurrentIndex(0)'''

    def setup_motor_status_timer(self, timer_interval=1000, max_wait=10000):
        """Set up the timer in __init__ to check the mono motor status.
        :param timer_interval: number of milliseconds to wait between checks
        :param max_wait: maximum time to wait for the motor to become idle"""
        self.motor_status_timer = QTimer(self)
        self.motor_status_timer.setInterval(timer_interval)  # 1000 ms
        # connect the timeout signal to the check_motor_idle method
        self.motor_status_timer.timeout.connect(self.check_motor_idle)
        self.motor_wait_elapsed = 0
        self.motor_max_wait = max_wait  # 10 seconds

    def sync_hardware_exit_port(self):
        """Query the Triax hardware to see which exit mirror is currently active."""
        if self.mono.device_connected:
        # Send the 'w' or 'r' status command to the Triax
        # You may need to implement get_mirror_status() in your triax_320.py
            actual_pos = self.mono.get_mirror_status() 
        
            self.mono.current_mirror_pos = actual_pos
            port_text = "Side Exit" if actual_pos == 1 else "Front Exit"
            self.ui.current_exit_label.setText(f"Active Port: {port_text}")
            self.mono_and_power_meter_log(f"Hardware Sync: Detected {port_text} active.")

    def check_motor_idle(self):
        """Check the mono motor status and update the UI accordingly."""
        status = self.mono.get_motor_status()
        # for testing purpose----------------:
        # status = random.choice(["idle", "busy", "error", "disconnected", "unknown"])
        # status = "busy"
        # --------------------------------
        print(f"Motor status: {status}")
        # if the motor is idle, stop the timer and update the UI
        if status == 'idle':
            self.motor_status_timer.stop()
            self.set_mono_pos_label()
            self.mono_and_power_meter_log("Motor reached target position.")
        # if the motor is not as expected, log the error and stop the timer
        elif status in ('error', 'disconnected', 'unknown'):
            self.motor_status_timer.stop()
            self.mono_and_power_meter_log("Motor error/disconnected.")
        # if the motor is stillmoving, increment the elapsed time
        elif status == 'busy':
            self.motor_wait_elapsed += self.motor_status_timer.interval()
            self.mono_and_power_meter_log(f"Motor is busy, waiting for {self.motor_wait_elapsed} ms.")
            if self.motor_wait_elapsed >= self.motor_max_wait:
                self.motor_status_timer.stop()
                self.mono_and_power_meter_log("Timeout waiting for motor idle.")

    def start_motor_status_timer(self):
        """Start the mono motor status timer to check the motor status periodically."""
        self.motor_wait_elapsed = 0
        self.motor_status_timer.start()

    def start_power_meter_timer(self, timer_interval=1000):
        """Start the timer to read power meter data periodically.
        :param timer_interval: number of milliseconds to wait between readings"""
        self.power_timer = QTimer(self)
        self.power_timer.timeout.connect(self.ui_read_power_meter)
        self.power_timer.start(timer_interval)  # every 1000 ms = 1 second

    def ui_set_labels(self):
        """Initialized the labels in the UI"""
        self.ui.file_location_label.setText(f"{self.file.saved_location}")
        self.ui.current_filename_label.setText(f"{self.file.file_name}")
    
        self.ui.mono_mirror_select_comboBox_2.setCurrentIndex(1) # Visual index for Side
        self.ui.Mirror_current_position_label.setText(f'Mirror exit: Side')
        self.ui.Grating_current_position_label.setText(f'Grating : 1')
        self.ui.mono_grating_select_comboBox_3.setCurrentIndex(0)
    
    def handle_grating_switch(self):
        """Triggered by grating_toggle_btn to move the turret."""
        if not self.mono.device_connected:
            self.mono_and_power_meter_log("Error: Monochromator not connected.")
            return

        # Use index: 0 for Grating 1 (a0), 1 for Grating 2 (b0)
        target_pos = self.ui.mono_grating_select_comboBox_3.currentIndex()
        self.ui.Grating_current_position_label.setText(f'Grating : {target_pos}')
        self.mono_and_power_meter_log(f"Move to grating {target_pos}")

        self.mono.set_grating(target_pos)

    def mono_and_power_meter_log(self, message):
        """Log messages to the mono and power meter log browser"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.ui.mono_powermeter_log.append(f"{timestamp}: "+ message)

    '''def connect_spectrometer(self):
        """Set the default mirror to Side Exit when monochromator is connected."""
        if self.mono.device_connected:
            self.mono_and_power_meter_log("Triax connected. Setting default mirror to Side...")

            # 1. MOVE TO SIDE DEFAULT (e0 command)
            self.mono.set_exit_mirror(1)
            self.mono.current_mirror_pos = 1

            # 2. UPDATE UI TO MATCH
            self.ui.Mirror_current_position_label.setText("Side")
            self.ui.mono_mirror_select_comboBox_2.setCurrentIndex(1)

            # Optional: Ask the hardware to confirm it arrived
            self.sync_mirror_from_hardware()'''

    @pyqtSlot()
    def set_reference_plot(self):
        """(No use)"""
        pass

    @pyqtSlot()
    def update_plot(self):
        """(No use)"""
        pass
        # if not self.spectrometer_connected:
        #     self.stop_continuous_update()
        #     self.ui.spec_status.append("Please connect the spectrometer first.")
        #     return
        # else:
        #     result = self.plot_data.update_plot(self.integration_time, self.spectrometer_connected)
        #     if result == -1:
        #         if self.stage_started:
        #             self.stop_stepping()
        #         if self.plotting_started:
        #             self.stop_continuous_update()

    def update_port_list(self):
        """Update the list of available COM ports in the UI
        """
        port_list = serial_manage.update_port_list()
        self.ui.com_port_comboBox.clear()
        for port in port_list:
            self.ui.com_port_comboBox.addItem(port)

    def connect_stage(self):
        """Establish the connection of the stage to the selected COM port and set the stage_connected flag.
        """
        self.stage.connect(self.ui.com_port_comboBox.currentText())
        if self.stage.gsc02_device.is_open:
            self.ui.stage_status_Browser.append("Connected to device")
            self.stage_connected = True
        else:
            self.ui.stage_status_Browser.append("Failed to connect to device")

    def close_connection(self):
        """Close the connection to the stage
        """
        self.stage.disconnect()
        if not self.stage.gsc02_device.is_open:
            self.ui.stage_status_Browser.append("Connection closed")
            self.stage_connected = False
        else:
            self.ui.stage_status_Browser.append("Failed to close connection")

    def get_stage_position(self):
        """Get the current position of the stage
        """
        if self.stage.ready_to_move:
            self.ui.stage_status_Browser.append("Device is currently moving. Please wait or stop the process.")
            return
        data = self.stage.check_position_command()
        if data == -1:
            self.ui.stage_status_Browser.append(self.stage.device_message)
            return
        self.ui.position_browser.append(f"Device at position in pulses: {data}")
        self.ui.position_browser.append(f"Device at position in ps: {gsc_functions.pulses_to_pico(data)}")

    def goto_position(self):
        """Move the stage to the specified position
        """
        if self.stage.ready_to_move:
            self.ui.stage_status_Browser.append("Device is currently moving. Please wait or stop the process.")
            return
        position_in_ps = self.ui.goto_position_text_input.toPlainText()
        # Check if the input is a valid number
        try:
            position_in_ps = float(position_in_ps)
        except ValueError:
            self.ui.stage_status_Browser.append("Invalid input")
            return
        # Check if the input is within the range of the stage
        if 0 <= position_in_ps < 662.8:
            position_in_pulse = gsc_functions.pico_to_pulses(position_in_ps)
            self.stage.move_to_position(position_in_pulse)
            self.ui.stage_status_Browser.append(self.stage.device_message)
        else:
            self.ui.stage_status_Browser.append("Invalid position input. Please enter a value between 0 and 662.8 ps")
        # self.get_stage_position()

    def confirm_stage_parameters_input(self):
        """Confirm the input parameters for the stage and move stage to the start position.
        :returns: 0 if the input parameters are valid and the stage is ready to move,
        """

        start_point = self.ui.start_position_input.toPlainText()

        end_point = self.ui.stop_position_input.toPlainText()

        step_size = self.ui.step_size_input.toPlainText()
        # send the input parameters to the stage for checking and move to start position:
        check_code, check_message = self.stage.check_point(start_point, end_point, step_size)
        # if the input parameters are valid, set the stage parameters and update the UI:
        if check_code == 0:
            self.ui.stage_status_Browser.append(check_message)
            # set the stage parameters in the UI:
            self.ui.start_position_label.setText(f"Start Point: {self.stage.start_point}")
            self.ui.stop_position_label.setText(f"Stop Point: {self.stage.end_point}")
            self.ui.step_size_label.setText(f"Step Size: {self.stage.step_size}")
            self.ui.total_steps_label.setText(f"Total Steps: {self.stage.total_steps}")
            self.ui.remaining_steps_label.setText(f"Remaining Steps: {self.stage.remaining_steps}")
            # only set the spectro filename if the spectrometer is connected:
            if self.spectrometer_connected:
                self.input_step_waiting_time()
                self.ui.spec_status.append("Spectrometer connected successfully.")
                self.ui.filename_label.setText(f"Filename: {self.plot_data.filename}")
            return 0

        # not valid input
        elif check_code == -1:
            self.ui.stage_status_Browser.append(check_message)
            return -1
        else:
            self.ui.stage_status_Browser.append("Error, please check the input parameters.")
            return -1

    def start_stepping(self):
        """Start the stage stepping process
        """
        # check if the stage is connected and ready to move:
        if not self.stage_connected:
            self.ui.stage_status_Browser.append("Please connect to the stage first.")
            return False

        if not self.spectrometer_connected:
            self.ui.spec_status.append("Please connect the spectrometer first.")
            return

        # check the stage parameters input and check if the stage is at start point:
        if self.confirm_stage_parameters_input() == 0:
            # check if the device reach the start point
            self.check_position_retries = 0
            self.ui.stage_status_Browser.append("Checking device position...")
            self.position_check_timer.start(2000)
        else:
            self.ui.stage_status_Browser.append("Please check the input parameters")
            return False

    def stop_stepping(self):
        """Stop the stepping process
        """
        self.ui.stage_status_Browser.append("Stop stepping")
        self.stage.ready_to_move = False
        self.stage_started = False
        self.auto_save()
        pass

    def check_device_position(self) -> bool:
        """Check if the stage has reached the start point or not
        :return: True if the stage has reached the start point, False otherwise"""
        current_position = self.stage.check_position_command()
        start_position = gsc_functions.pico_to_pulses(self.stage.start_point)

        # test:
        # current_position = 0
        # start_position = 0
        #---------------

        # if the stage has reached the start point, start the stepping process:
        if current_position == start_position:
            # if using QTimer, stop the timer:
            if self.position_check_timer.isActive():
                self.position_check_timer.stop()
            # todo: use the signals to update the UI instead of directly appending to the browser
            # self.ui.stage_status_Browser.append(f"Device reached start point at "
            #                                     f"{gsc_functions.pulses_to_pico(current_position):.2f} ps, "
            #                                     f"{current_position} pulses. "
            #                                     f"Start point is {self.stage.start_point:.2f} ps, {start_position} pulses. "
            #                                     f"Starting stepping process...")
            self.ui_signal.mono_powermeter_log_signal.emit(f"Device reached start point at "
                                                f"{gsc_functions.pulses_to_pico(current_position):.2f} ps, "
                                                f"{current_position} pulses. "
                                                f"Start point is {self.stage.start_point:.2f} ps, {start_position} pulses. "
                                                f"Starting stepping process...")
            self.stage_started = True
            self.stage.ready_to_move = True

            # start the stage and spectrometer stepping process:
            # if self.spectrometer_connected:
            #     print("Starting spectrometer stepping process...")
            #     # clear the plot data cache and reset the row count for spectrometer data:
            #     self.plot_data.clear_cache()
            #     self.plot_data.row_count = 0
            #     # start the working thread for stepping and acquiring spectrometer data:
            #     self.thread, message = self.stage.start_threaded_stepping(self.signals)
            #     self.ui.stage_status_Browser.append(message)

            return True
        # Not yet reach the start point:
        else:

            # self.ui.stage_status_Browser.append("Device not at start point. Moving to start point...")
            self.ui_signal.mono_powermeter_log_signal.emit("Device not at start point. Moving to start point...")
            # using Qtimer as a retry mechanism:
            if self.position_check_timer.isActive():
                self.check_position_retries += 1
                # if the stage has timeout, stop the position check timer and log an error:
                if self.check_position_retries >= self.max_retries:
                    self.position_check_timer.stop()
                    # self.ui.stage_status_Browser.append("Failed to reach the start point. Please check the device.")
                    self.ui_signal.mono_powermeter_log_signal.emit("Failed to reach the start point. "
                                                                   "Please check the device.")
                    return False

            # use multithreading to wait for the stage to reach the start point:
            self.stage_started = False
            # reset the ready_to_move flag:
            self.stage.ready_to_move = False
            return False

    def input_integration_time(self):
        """(No use)Get the integration time input from the user
        """
        pass
        # integration_time = self.ui.integration_time_input.toPlainText()
        # try:
        #     integration_time = int(integration_time)
        # except ValueError:
        #     self.ui.spec_status.append("Invalid input. Please enter a valid integer.")
        #     return
        # if 900 >= integration_time >= 1:
        #     self.integration_time = integration_time
        #     self.ui.spec_status.append(f"Integration time set to {integration_time} ms.")
        #     self.ui.integration_time_label.setText(f"Integration time: {integration_time} ms")
        # else:
        #     self.ui.spec_status.append("Invalid input. Please enter a value between 1 and 900.")
        #     self.ui.integration_time_label.setText(f"Integration time: {self.integration_time} ms")

    def input_step_waiting_time(self):
        """Get the step waiting time input from the user
        """
        step_waiting_time = self.ui.waittime_input.toPlainText()
        if step_waiting_time == "":
            return # No input

        try:
            step_waiting_time = float(step_waiting_time)
        except ValueError:
            self.ui.spec_status.append("Invalid input. Please enter a valid integer.")
            return
        if 10 >= step_waiting_time > 0:
            self.stage.waiting_time = step_waiting_time + (self.integration_time*0.001 + 0.05)
            self.ui.stage_status_Browser.append(f"Step waiting time set to {self.stage.waiting_time} s.")
            self.ui.waiting_time_label.setText(f"Step waiting time: {self.stage.waiting_time} s")
            print(f"Step waiting time: {self.stage.waiting_time}")
        else:
            self.ui.stage_status_Browser.append("Invalid input. Please enter a value between 0 and 10.")
            self.ui.waiting_time_label.setText(f"Step waiting time: {self.stage.waiting_time} ms")
            print(f"Step waiting time: {self.stage.waiting_time}")

    def export_csv(self):
        """Prompt user to choose a file location to save the CSV
        """
        if self.stage_started:
            self.ui.stage_status_Browser.append("Please stop the stage before exporting the data.")
            return
        elif self.plotting_started:
            self.ui.spec_status.append("Please stop the spectrometer update before exporting the data.")
            return
        elif not self.mono_stop_flag.is_set():
            self.mono_and_power_meter_log("Please stop the monochromator scan before exporting the data.")
            return
        else:
            directory = QFileDialog.getSaveFileName(
                self,
                "Save CSV",
                "",
                "CSV Files (*.csv);;All Files (*)"
            )
            if directory:
                self.file.manual_save_file(directory[0])
                self.mono_and_power_meter_log(f"Data saved to {directory[0]}")
            else:
                self.mono_and_power_meter_log("Data export canceled.")

    def auto_save(self):
        """(No use)Save the data at a different location
        """
        pass
        # self.plot_data.auto_save()

    def start_continuous_update(self):
        """(No use)Start continuously updating the plot."""
        # if not self.spectrometer_connected:
        #     self.ui.spec_status.append("Please connect the spectrometer first.")
        #     return
        # if self.stage_started:
        #     self.ui.spec_status.append("Please stop the stage before updating the spectrometer.")
        #     return
        # if self.plotting_started:
        #     self.ui.spec_status.append("Spectrometer update already started.")
        #     return
        # if self.spectrometer_connected:
        #     self.plotting_timer.start(self.plot_update_interval)  # Adjust the interval (in milliseconds) as needed
        #     self.plotting_started = True
        pass

    def stop_continuous_update(self):
        """(No use) Stop continuously updating the plot."""
        # if self.plotting_started:
        #     self.plotting_timer.stop()
        #     self.plotting_started = False
        #     self.ui.spec_status.append("Spectrometer update stopped.")
        #     return
        # else:
        #     self.ui.spec_status.append("Spectrometer update not started.")
        pass

    def change_save_location(self):
        """Change save file direction"""
        new_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Save Directory",
            ""
        )
        if new_dir:
            self.file.change_saved_location(new_dir)
            print(f"Save directory changed to {self.file.saved_location}")
            self.ui.file_location_label.setText(f"{new_dir}")
        else:
            print("Save location change canceled")

    def toggle_palette(self):
        """Change GUI color mode"""
        app = QApplication.instance()
        if self.is_dark_mode:
            app.setStyle("Fusion")
            QApplication.instance().setPalette(get_light_palette())
            self.ui.centralwidget.setStyleSheet("background-color: white;")
            self.ui.menubar.setStyleSheet("""
                        QMenuBar {
                            background-color: white;
                            color: black;
                        }
                        QMenuBar::item {
                            background-color: white;
                            color: black;
                        }
                        QMenuBar::item:selected {
                            background-color: rgb(230, 230, 230);
                            color: black;
                        }
                        QMenuBar::item:pressed {
                            background-color: rgb(200, 200, 200);
                            color: black;
                        }
                        QMenu {
                            background-color: white;
                            color: black;
                        }
                        QMenu::item {
                            background-color: white;
                            color: black;
                        }
                        QMenu::item:selected {
                            background-color: rgb(230, 230, 230);
                            color: black;
                        }
                        QMenu::item:pressed {
                            background-color: rgb(200, 200, 200);
                            color: black;
                        }
                    """)
        else:
            app.setStyle("Fusion")
            QApplication.instance().setPalette(get_dark_palette())
            self.ui.centralwidget.setStyleSheet("background-color: rgb(35, 35, 35);")
            self.ui.menubar.setStyleSheet("""
                        QMenuBar {
                            background-color: rgb(53, 53, 53);
                            color: white;
                        }
                        QMenuBar::item {
                            background-color: rgb(53, 53, 53);
                            color: white;
                        }
                        QMenuBar::item:selected {
                            background-color: rgb(75, 75, 75);
                            color: white;
                        }
                        QMenuBar::item:pressed {
                            background-color: rgb(100, 100, 100);
                            color: white;
                        }
                        QMenu {
                            background-color: rgb(53, 53, 53);
                            color: white;
                        }
                        QMenu::item {
                            background-color: rgb(53, 53, 53);
                            color: white;
                        }
                        QMenu::item:selected {
                            background-color: rgb(75, 75, 75);
                            color: white;
                        }
                        QMenu::item:pressed {
                            background-color: rgb(100, 100, 100);
                            color: white;
                        }
                    """)
        self.is_dark_mode = not self.is_dark_mode

    def change_save_filename(self, name_label=""):
        """Save user input filename from ui textinput box.
        :param name_label: Optional label for filename.
        :return: 0 if successful, -1 if failed
        """
        new_file_name = self.ui.filenam_input.toPlainText()
        if new_file_name == "":
            self.mono_and_power_meter_log("Please enter a valid filename.")
            return -1
        else:
            file_name = new_file_name + "_" + name_label
            print(f"Filename changed to {file_name}")
            self.file.change_file_name(new_name=file_name)
            self.mono_and_power_meter_log(f"Filename changed to {file_name}")
            self.ui.current_filename_label.setText(f"{self.file.file_name}")
            return 0

    def close_spectrometer(self):
        """(No use)call the close_device method from the spectrometer class
        """
        pass
        # if self.spectrometer_connected:
        #     self.plot_data.spectrometer.close_device()
        #     self.spectrometer_connected = False
        #     self.ui.spec_status.append(f"{self.plot_data.spectrometer.device_handle} closed successfully.")
        # else:
        #     self.ui.spec_status.append("No spectrometer connected.")

    def closeEvent(self, event):
        """
        Override the close event to ensure the device is properly disconnected before the application exits.
        """
        # Check if the device is connected and then disconnect
        if self.stage.gsc02_device and self.stage.gsc02_device.is_open:
            self.stage.disconnect()
            print("Device disconnected successfully.")
        # Close mono while exiting the GUI:
        if self.mono.device_connected:
            self.mono.close_device()
            self.mono_and_power_meter_log("Monochromator closed.")
        # disconnect power meter if connected
        if self.power_meter.device_connected:
            self.power_meter.disconnect_device()
            self.mono_and_power_meter_log("Powermeter closed.")

        # Prompt user to save data file or not:
        reply = QMessageBox.question(
            self,
            'Message',
            "Do you want to save your data before exiting?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Stop the power meter timer if it's running
            if hasattr(self, 'power_timer') and self.power_timer.isActive():
                self.power_timer.stop()
            # Export the data to CSV and close ui
            self.export_csv()
            sys.stdout = sys.__stdout__
            event.accept()
        elif reply == QMessageBox.StandardButton.No:
            # Stop the power meter timer if it's running
            if hasattr(self, 'power_timer') and self.power_timer.isActive():
                self.power_timer.stop()
            # Close ui without saving
            sys.stdout = sys.__stdout__
            event.accept()
        else:
            event.ignore()

    def test_function(self):
        """for testing purpose"""

        print("function executed.")
        self.ui_connect_picoharp300()

    def test_function_2(self):
        """for testing purpose"""
        print("function 2 executed.")
        self.check_device_position()

    def update_step_display(self):
        """update wavelength stepsize via wl spinbox controlled by spinbox signal"""
        if self.min_resolution is None:
            self.ui.stepsize_mono_pos_label.setText("N/A")
            return
        multiplier = self.ui.mono_wl_spinbox.value()
        wl_step = multiplier * self.min_resolution
        self.ui.stepsize_mono_pos_label.setText(f"{wl_step:.5f}")

    def load_mapping_and_resolution(self, filepath="mapping.json"):
        """Load step-to-wavelength mapping and calculate resolution."""
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                mapping = json.load(f)
            a = round(float(mapping["a"]), 5)  # round to 5 decimals
            b = float(mapping["b"])
            self.min_resolution = abs(a)  # nm per step
            self.mapping_exists = True
            self.mapping_coefficients = (a, b)
            self.ui.start_mono_pos_label.setText(f">={self.mapping_coefficients[1]}")
            self.ui.end_mono_pos_label.setText(f"<=1500")
            print(f"Loaded mapping: wavelength = {self.mapping_coefficients[0]} * step + {self.mapping_coefficients[1]}")
            print(f"Minimum resolution: {self.min_resolution} nm/step")
        else:
            self.min_resolution = None
            self.mapping_exists = False
            self.mapping_coefficients = (None, None)
            self.ui.start_mono_pos_label.setText(">=-250000")
            self.ui.end_mono_pos_label.setText("<=750000")
            #For triax 320
            #self.ui.start_mono_pos_label.setText(">=0")
            #self.ui.end_mono_pos_label.setText("<=32000")

    def toggle_input_mode(self, use_wavelength):
        """toggle step size from using steps (textbox) or wavelength (spinbox) as input"""
        if use_wavelength:
            self.ui.mono_wl_spinbox.setVisible(True)
            self.ui.mono_stepsize_input.setVisible(False)
        else:
            self.ui.mono_wl_spinbox.setVisible(False)
            self.ui.mono_stepsize_input.setVisible(True)

    def initialize_ui_mode(self):
        """init ui to using step mode or wavelength mode and load mapping params if json exists"""
        self.mapping_exists = os.path.exists("mapping.json")
        if self.mapping_exists:
            self.ui.unit_label.setText("nm")
            self.ui.unit_label_2.setText("nm")
            self.ui.unit_label_3.setText("nm")
            self.ui.unit_label_4.setText("nm")

            self.toggle_input_mode(use_wavelength=True)
            self.load_mapping_and_resolution()
            self.ui.mono_range_mode_label.setText(f"Wavelength Mode\nResolution: {self.mapping_coefficients[0]} nm/step ")
            self.ui.position_limit_label.setText(f"{self.mapping_coefficients[1]}nm <= wl <= 1500nm")
        else:
            self.ui.mono_range_mode_label.setText("Step Mode")
            self.ui.unit_label.setText("step")
            self.ui.unit_label_2.setText("step")
            self.ui.unit_label_3.setText("step")
            self.ui.unit_label_4.setText("step")
            self.toggle_input_mode(use_wavelength=False)
            self.ui.position_limit_label.setText("-250000 <= step <= 750000")
            #For triax 320
            #self.ui.position_limit_label.setText("0 <= step <= 32000")

    def validate_mono_parameters(self, step_start, step_end, step_size, test_num):
        """validate monochromator parameters to fit within safety limits"""
        if step_start < 0 or step_end < 0:
            self.mono_and_power_meter_log("Start and end positions must be non-negative.")
            return False
        if step_size <= 0:
            self.mono_and_power_meter_log("Step size must be positive.")
            return False
        if test_num <= 0:
            self.mono_and_power_meter_log("Test cycles must be positive.")
            return False
        if step_start > step_end:
            self.mono_and_power_meter_log("Start position cannot be greater than end position.")
            return False
        if step_end > 750000:
            self.mono_and_power_meter_log("End position must be 750000 or less.")
            return False
        
        #For triax 320
        #if step_end > 32000:
        #    self.mono_and_power_meter_log("End position must be 32000 or less.")
        #    return False

        return True

    def validate_x_values(self):
        """Check that x_values are all integers within [-250000, 750000]"""
        if not hasattr(self, "x_values"):
            self.mono_and_power_meter_log("x_values not defined.")
            return False

        invalid = [x for x in self.x_values if not isinstance(x, int) or x < -250000 or x > 750000]
        #For triax 320
        #invalid = [x for x in self.x_values if not isinstance(x, int) or x < 0 or x > 32000]

        if invalid:
            self.mono_and_power_meter_log(f"Invalid x_values: {invalid}")
            return False

        return True

    # todo: convert wl inputs into step
    def get_scan_parameters(self) -> bool:
        """Unified interface to read and validate mono scan parameters (step or wavelength).
        it will handle self.test_num, self.x_values, self.mono_wavelengths, and set the labels in the GUI.
        :returns: True if parameters are valid, False otherwise."""
        # handles test cycles first
        try:
            test_num = int(self.ui.mono_test_cycle_input.toPlainText())
            if test_num <= 0:
                self.mono_and_power_meter_log("Test cycles must be positive.")
                return False
        except ValueError:
            self.mono_and_power_meter_log("Please enter a valid number for test cycles.")
            return False
        # Handle wavelength mode
        if self.mapping_exists:

            try:
                wl_start = float(self.ui.mono_start_pos_input.toPlainText())
                wl_end = float(self.ui.mono_end_pos_input.toPlainText())
                multiplier = self.ui.mono_wl_spinbox.value()  # Already validated to be > 0
            except ValueError:
                self.mono_and_power_meter_log("Please enter valid numbers for wavelength input.")
                return False

            if wl_start > wl_end:
                self.mono_and_power_meter_log("Wavelength start cannot be greater than end.")
                return False

            # Get mapping coefficients
            a, b = self.mapping_coefficients
            if a is None:
                self.mono_and_power_meter_log("Mapping coefficients not loaded.")
                return False

            # turn multiplier into step size in wl
            wl_step = multiplier * self.min_resolution
            # Calculate start and end steps
            wavelengths_raw = np.arange(wl_start, wl_end + wl_step/2 , wl_step)
            print(f"Raw wavelengths: {wavelengths_raw}")
            steps_rounded = [round((wl - b) / a) for wl in wavelengths_raw]

            # remove duplicates and sort to a new list
            unique_steps = sorted(set(steps_rounded))

            # from steps to wavelengths to ensure correct mapping
            wavelengths = [a * s + b for s in unique_steps]

            # check if steps are within range
            if any(step < -250000 or step > 750000 for step in unique_steps):
                self.mono_and_power_meter_log("Computed step out of range (-250000 to 750000).")
                return False
            
            #For traix 320
            #if any(step < 0 or step > 32000 for step in unique_steps):
                self.mono_and_power_meter_log("Computed step out of range (0 to 32000).")
                return False

            # save to attributes
            self.x_values = unique_steps
            # validate the x_values
            if not self.validate_x_values():
                return False
            # save wavelengths
            self.mono_wavelengths = wavelengths
            self.test_num = test_num
            # set the labels in the GUI:
            self.set_mono_parameters_labels(wavelengths[0], wavelengths[-1], wl_step, test_num)
            # testing
            print(f"Computed steps: {self.x_values}")
            print(f"Computed wavelengths: {self.mono_wavelengths}")

            return True
        # Handle step mode
        else:

            try:
                step_start = int(self.ui.mono_start_pos_input.toPlainText())
                step_end = int(self.ui.mono_end_pos_input.toPlainText())
                step_size = int(self.ui.mono_stepsize_input.toPlainText())
            except ValueError:
                self.mono_and_power_meter_log("Please enter valid numbers for step input.")
                return False

            if not self.validate_mono_parameters(step_start, step_end, step_size, test_num):
                return False

            self.x_values = list(range(step_start, step_end + 1, step_size))
            # validate the x_values
            if not self.validate_x_values():
                return False
            # wl not available
            self.mono_wavelengths = []
            self.test_num = test_num
            # set the labels in the GUI:
            self.set_mono_parameters_labels(step_start, step_end, step_size, test_num)

            print(f"Computed steps: {self.x_values}")
            print(f"Computed wavelengths: {self.mono_wavelengths}")
            return True
# todo: add send motor to specific position function

    # mono scan function:
    def mono_scan(self):
        """Scan through the mono with powermeter"""
        # Check if devices are connected return if not connected
        if not (self.mono.device_connected and self.power_meter.device_connected):
            self.mono_and_power_meter_log("Device not connected.")
            return

        # If device connected then check if parameters are valid
        if self.mono.device_connected and self.power_meter.device_connected:
        # Check if scan parameters are valid if not return
        # todo: not thread safety so removed and moved to mono_start_scan_button_clicked

        #     if not self.get_scan_parameters():
        #         return
#----------------------------------------------------------------------------------------------------
            # # accquire the parameters from the user input
            # try:
            #     step_start = int(self.ui.mono_start_pos_input.toPlainText())
            #     step_end = int(self.ui.mono_end_pos_input.toPlainText())
            #     step_size = int(self.ui.mono_stepsize_input.toPlainText())
            #     test_num = int(self.ui.mono_test_cycle_input.toPlainText())
            # except ValueError:
            #     self.mono_and_power_meter_log("Please enter valid numbers.")
            #     return
            # # todo: implement a check input
            # if not self.validate_mono_parameters(step_start, step_end, step_size, test_num):
            #     return
            # # set the labels in the GUI:
            # self.set_mono_parameters_labels(step_start, step_end, step_size, test_num)

            # # Generate the x axis list using range
            # self.x_values = list(range(step_start, step_end, step_size))
            # if self.x_values[-1] != step_end:
            #     self.x_values.append(step_end)
            # print(self.x_values)
            # # todo: use wavelength to input if json exist

            # -----------mapping mono step to wavelength----------------
            # if os.path.exists('mapping.json'):
            #     with open('mapping.json', 'r') as f:
            #         mapping = json.load(f)
            #
            #     a = mapping["a"]
            #     b = mapping["b"]
            #
            #     # steps to mono_wavelengths
            #     self.mono_wavelengths = [a * x + b for x in self.x_values]
            #
            #     print("Wavelengths:", self.mono_wavelengths)
            # else:
            #     print("mapping.json not found. Skipping wavelength calculation.")
# ------------------------------------------------------------
            # todo: no thread safety and need to use signal to handle
            # get the file name from GUI:
            self.change_save_filename()

            # get the power meter unit:
            self.power_meter.get_unit()
            power_meter_unit = self.power_meter.device_unit
            # set the power meter unit label in the GUI:
            self.ui.powermeter_unit_label.setText(f"{power_meter_unit}")
            # Double check the x_values list is not empty
            if self.x_values == []:
                self.mono_and_power_meter_log("No steps to scan. Please check the parameters.")
                return
            # double check the parameters are correct range
            invalid_steps = [s for s in self.x_values if s < -250000 or s > 750000]
            #For triax 320
            #invalid_steps = [s for s in self.x_values if s < 0 or s > 32000]

            if invalid_steps:
                self.mono_and_power_meter_log(f"Invalid steps detected: {invalid_steps}")
                return

            # init data file:
            self.file.init_cache(["mono position", f"powermeter unit: {power_meter_unit}"] + self.x_values)
            # set the wavelengths row if mono_wavelengths exist:
            if self.mono_wavelengths:
                wl_row = [" ", "wavelength (nm)"] + [f"{wl:.4f}" for wl in self.mono_wavelengths]
                self.file.append_row(wl_row)

            # clear the stop flag and set the mono scan loop to running:
            self.mono_stop_flag.clear()
            self.mono_and_power_meter_log("Monochromator scan started.")

            # start the mono scan loop:
            for test in range(self.test_num):
                # stop the loop:
                if self.mono_stop_flag.is_set():
                    break
                print(f"Test {test}")
                # update remaining test label:
                self.updare_monoscan_remaintest_signal.emit(self.test_num - test)
                # initialize y list to all zero for plotting function to work properly:
                self.y_values = [0] * len(self.x_values)
                # move to start position:
                current_pos = self.mono.get_motor_position()
                move_steps = self.x_values[0] - current_pos
                print(f"Move steps: {move_steps}")
                self.mono.move_motor_relative(move_steps)
                # ------------------------------------------

                for _ in range(20):
                    # motor busy check loop (the scan is in a working thread so non-blocking to UI):
                    if self.mono_stop_flag.is_set():
                        # cloes scan update ui and save the file:
                        self.updare_monoscan_remaintest_signal.emit(0)
                        self.file.auto_save_file()
                        return
                    status = self.mono.get_motor_status()
                    print(f"Motor status: {status}")
                    # Check if the motor is idle, error, or disconnected
                    if status == 'idle':
                        break
                    elif status in ('error', 'disconnected'):
                        self.mono_and_power_meter_log("Motor status read error or disconnected. Stopping scan.")
                        self.mono_stop_flag.set()
                        self.updare_monoscan_remaintest_signal.emit(0)
                        self.file.auto_save_file()
                        return
                    time.sleep(1)
                else:
                    # If the loop completes without breaking, it means the motor is still busy (timeout)
                    self.mono_and_power_meter_log("Timeout waiting for motor idle.")
                    self.mono_stop_flag.set()
                    # cloes scan update ui and save the file:
                    self.updare_monoscan_remaintest_signal.emit(0)
                    self.file.auto_save_file()
                    return
# todo: add safety check for motor position
                # ------------------------------------------
                motor_pos_cur = self.x_values[0] # simulation of motor
                for index, next_pos in enumerate(self.x_values):
                    # stop the loop:
                    if self.mono_stop_flag.is_set():
                        break
                    print(f"Step: {index}")
                    # move motor:
                    motor_move = next_pos - motor_pos_cur
                    # safety check for motor to move only towards the end position:
                    if motor_move < 0:
                        self.mono_and_power_meter_log(
                            f"Aborting scan: motor would move backwards ({motor_move}) at index {index}."
                        )
                        self.mono_stop_flag.set()
                        # cloes scan update ui and save the file:
                        self.updare_monoscan_remaintest_signal.emit(0)
                        self.file.auto_save_file()
                        return
                    # move the motor relative to the current position:
                    self.mono.move_motor_relative(motor_move)
                    # simulation of motor behavior:
                    print(f"motor move {motor_move}")
                    motor_pos_cur += motor_move
                    print(f"motor at {motor_pos_cur}")
                    # power meter get intensity and store it to y value list:
                    print(f"power meter get intensity at {motor_pos_cur}.")

                    # todo: add sample times to even out the power meter reading.(need verify)
                    self.y_values[index] = self.average_power_reading(samples=5, delay=0.05)

                    # ------------------------------
                    # self.y_values[index] = float(self.power_meter.read_data())
                    # self.y_values[index] = motor_pos_cur

                    # send update plot signal to main thread:
                    self.upadte_powermeter_plot_signal.emit()
                    # send update mono remain step tp main thread:
                    self.update_monoscan_remainstep_signal.emit(len(self.x_values)-index)
                    # prevent mono to overload:
                    time.sleep(0.5)

                self.update_monoscan_remainstep_signal.emit(0)
                # timestamp (YYYY-MM-DD HH:MM:SS）
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # append the data to the file:
                self.file.append_row([timestamp,f"Test: {test+1}"]+self.y_values)
                time.sleep(0.05)

            # update remaining mono scan test:
            self.updare_monoscan_remaintest_signal.emit(0)
            # autosave data chche with timstamp:
            self.file.auto_save_file()
            # set the mono scan loop to set to indicate scan finished:
            self.mono_stop_flag.set()
            #
            self.mono_and_power_meter_log("Scan finished.")
        else:
            self.mono_and_power_meter_log("Device not connected.")

    def average_power_reading(self, samples=5, delay=0.05) -> float:
        """Read power meter data multiple times and return the average.
        :param samples: Number of samples to read
        :param delay: Delay between readings in seconds
        :return: Average power reading or 0.0 if no valid readings"""
        readings = []
        for _ in range(samples):
            try:
                val = float(self.power_meter.read_data())
                readings.append(val)
            except Exception as e:
                print(f"Power read error: {e}")
            time.sleep(delay)
        return sum(readings) / len(readings) if readings else 0.0

    def ultimate_stop(self):
        """Force stop motor and scan thread immediately."""
        self.mono_and_power_meter_log("Ultimate stop.")
        print("Ultimate stop.")
        print(f" mono stop flag set: {self.mono_stop_flag.is_set()}")
        self.mono_stop_flag.set()
        print(f" mono stop flag set: {self.mono_stop_flag.is_set()}")
        print(f"iv mono stop flag set: {self.iv_meas_stop_flag.is_set()}")
        self.iv_meas_stop_flag.set()
        print(f"iv mono stop flag set: {self.iv_meas_stop_flag.is_set()}")
        # 1. Force stop the motor hardware
        self.mono.motor_stop()

        # 2. Do NOT join the thread here — that would block the UI.
        # The stop flags above will cause the worker threads to exit cleanly.

        # 3. Notify in GUI
        self.mono_and_power_meter_log("Ultimate stop: motor and scan forcibly stopped.")

    def start_mono_scan(self):
        """Start the monochromator scan in a separate thread."""
        # Check if devices are connected
        if not (self.mono.device_connected and self.power_meter.device_connected):
            self.mono_and_power_meter_log("Device not connected.")
            return
        # If device connected then check if parameters are valid
        if self.get_scan_parameters() is True:
            # Check if the mono scan thread is already running
            if self.thread is None or not self.thread.is_alive():
                # Clear the stop flag and set the mono scan loop to running:
                self.mono_stop_flag.clear()
                self.mono_and_power_meter_log("Monochromator scan started.")
                # Start the mono scan in a separate thread
                self.thread = threading.Thread(target=self.mono_scan)
                self.thread.start()
            # if the thread is running, do not start a new one
            else:
                self.mono_and_power_meter_log("Monochromator scan already running.")
        else:
            self.mono_and_power_meter_log("Parameters not valid. Scan not start.")
            return


    def stop_mono_scan(self):
        if not self.mono_stop_flag.is_set():
            self.mono_stop_flag.set()
            # Do NOT call thread.join() here — it would block the UI thread.
            self.mono_and_power_meter_log("Monochromator scan stop requested.")
        else:
            self.mono_and_power_meter_log("Monochromator scan already stopped.")

    def set_mono_parameters_labels(self, start, end, step, test):
        self.ui.start_mono_pos_label.setText(f"{start}")
        self.ui.end_mono_pos_label.setText(f"{end}")
        self.ui.stepsize_mono_pos_label.setText(f"{step}")
        self.ui.test_cycles_label.setText(f"{test}")

    def prompt_initmono_at_start(self):
        """
        Create a message box to prompt user to initilize mono if needed"""
        # todo: check if working
        msg_box = QMessageBox()
        msg_box.setWindowTitle("First Time Initialization?")
        msg_box.setText("If first time power on the monochromator, please initialize the motor.\nStart initialization?")
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)

        # Execute the message box and capture the response
        response = msg_box.exec()

        if response == QMessageBox.StandardButton.Yes:
            self.initialize_motor_with_prompt()

    def initialize_motor_with_prompt(self):
        """pop up message box to confrim the init mono process"""
        reply = QMessageBox.question(
            self,
            "Confirm Initialization",
            "Are you sure you want to initialize the motor?\nThis process will take 100 seconds.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:

            # todo: make init into another thread (solved, check if working)
            init_thread = threading.Thread(target=self.mono.init_motor)
            port_text = "Side"
            init_thread.start()

    def show_initialization_dialog(self):
        """Show a modal dialog with a countdown for motor initialization and disable GUI function for 100s."""
        print("init triggerd.")
        # todo: the for loop will bloock the ui, need to fix it by sending signal to kill the message box while the countdown continues.(done check if it works)
        self.msg_box = QMessageBox(self)
        self.msg_box.setWindowTitle("Initializing Motor")
        self.msg_box.setText("The motor is initializing, please wait...")
        self.msg_box.setStandardButtons(QMessageBox.StandardButton.NoButton)
        self.msg_box.setModal(False)  # Make the dialog modal
        self.msg_box.show()
        self.countdown = 100
        # start the countdown:
        self.mono_init_timer.start(1000)

    def update_mono_init_dialog_countdown(self):
        """Update the countdown in the message box."""
        self.msg_box.setText(f"Initializing... {self.countdown} seconds remaining")
        self.countdown -= 1
        if self.countdown <= 0:
            self.mono_init_timer.stop()
            self.msg_box.accept()
            print("init done.")

    def close_mono_init_dialog(self):
        """Close the initialization dialog."""
        self.mono_init_timer.stop()
        self.msg_box.accept()

    def adjust_mono_slit(self):
        # todo: add slit control function to adjust mono slit number for entrance or exit slit.
        slit_selection = self.ui.mono_slit_select_comboBox.currentText()
        print(slit_selection)
        slit_width = self.ui.mono_slit_size_select_spinBox.value()
        if slit_selection == "Entrance_0":
            # slit number 0 = entrance slit:
            slit_num = 0
            # send slit command
            self.mono.slit_control(slit_num = slit_num, width=slit_width)
            print("Slit at entrance 0")
            print(f'slit width set to {slit_width}')
            self.ui.entrance_slit_size_label.setText(f'Entrance_0 size: {slit_width}')
            # print(f'slit width {self.mono.check_slit_position(0)}')
        elif slit_selection == "Entrance_1":
            # slit number 1 for entrance slit:
            slit_num = 1
            # send slit command:
            self.mono.slit_control(slit_num=slit_num, width=slit_width)
            print("Slit at entrance 1.")
            print(f'slit width set to {slit_width}')
            self.ui.entrance_1_slit_size_label.setText(f'Entrance_1 size: {slit_width}')
            # print(f'slit width {self.mono.check_slit_position(1)}')
        elif slit_selection == "Exit_2":
            # slit number 2 for exit slit:
            slit_num = 2
            # send slit command:
            self.mono.slit_control(slit_num=slit_num, width=slit_width)
            print("Slit at exit 2.")
            print(f'slit width set to {slit_width}')
            self.ui.exit_2_slit_size_label.setText(f'Exit_2 size: {slit_width}')
            # print(f'slit width {self.mono.check_slit_position(2)}')
        elif slit_selection == "Exit_3":
            # slit number 3 for exit slit:
            slit_num = 3
            # send slit command:
            self.mono.slit_control(slit_num=slit_num, width=slit_width)
            print("Slit at exit.")
            print(f'slit width set to {slit_width}')
            self.ui.exit_slit_size_label.setText(f'Exit_3 size: {slit_width}')
            # print(f'slit width {self.mono.check_slit_position(3)}')
        else:
            self.mono_and_power_meter_log("Unknown slit selection.")
            print("unknown.")

    def mono_slit_label_set_text(self):
        """setting up mono slit width label by signal emitted from slit control command."""

        slit_selection = self.ui.mono_slit_select_comboBox.currentText()
        print(slit_selection)
        slit_width = self.ui.mono_slit_size_select_spinBox.value()
        if slit_selection == "Entrance":
            self.ui.entrance_slit_size_label.setText(f'{slit_width}')
            print(f'slit width {self.mono.check_slit_position(0)}')
        elif slit_selection == "Exit":
            self.ui.exit_slit_size_label.setText(f'{slit_width}')
            print(f'slit width {self.mono.check_slit_position(3)}')
        else:
            self.mono_and_power_meter_log("Unknown error")
            print("unknown.")

    def mono_remaining_step(self, remain_steps):
        print(f"step remaing:{remain_steps}")
        self.ui.mono_scan_remaing_step_label.setText(f"{remain_steps}")


    def mono_remaining_test(self, remain_test):
        print(f"test remaining:{remain_test}")
        self.ui.mono_scan_remaing_test_label.setText(f"{remain_test}")

    def check_mono_program_state_ui(self):
        """Check the status of the monochromator program and update the UI label."""
        mono_state, message = self.mono.check_device_status()
        self.ui.mono_program_state_label.setText(f"{mono_state}")
        self.mono_and_power_meter_log(message)

    def mono_enter_main_program_ui(self):
        """Enter the main program of the monochromator."""
        self.mono.start_main_program()
        QTimer.singleShot(100, self.check_mono_program_state_ui)

    def set_mono_pos_label(self):
        """Set the monochromator position label query the current motor position."""
        # if not self.mono.device_connected:
        #     self.mono_and_power_meter_log("Mono not connected.")
        #     return
        # Get mono motor position:
        mono_pos = self.mono.get_motor_position()
        # for testing purpose----------------:
        # mono_pos = random.randint(-250000, 750000)
        # -----------------------------------
        # Check if mapping exists to convert step to wavelength
        if self.mapping_exists:
            a, b = self.mapping_coefficients
            if a is None:
                self.mono_and_power_meter_log("Mapping coefficients not loaded.")
                return
            # Convert current step position to wavelength and display
            mono_wavelength = mono_pos * a + b
            self.ui.mono_pos_label.setText(f"{mono_pos} ({mono_wavelength:.4f} nm)")
        # display step position if no mapping exists
        else:
            self.ui.mono_pos_label.setText(f"{mono_pos}")

# todo: add update mono position
    def mono_goto_button_clicked(self):
        """Handle user clicking 'Goto' to move motor to specific step."""
        # if not self.mono.device_connected:
        #     self.mono_and_power_meter_log("Mono not connected.")
        #     return

        # if mapping exists, convert input wavelength value to step
        if self.mapping_exists:
            a, b = self.mapping_coefficients
            if a is None:
                self.mono_and_power_meter_log("Mapping coefficients not loaded.")
                return
            # take input wavelength from the text box into float
            try:
                input_text = self.ui.mono_pos_input.toPlainText()
                input_value = float(input_text)
            except ValueError:
                self.mono_and_power_meter_log("Please enter a valid number.")
                return
            # convert input wavelength value to nearest step
            position = round((input_value - b) / a)
            actual_wavelength = a * position + b
            self.mono_and_power_meter_log(f"Converted nearest wavelength {actual_wavelength:.4f} nm to step {position}")

        # if no mapping exists, take input step value from the text box
        else:
            try:
                position = int(self.ui.mono_pos_input.toPlainText())
                self.mono_and_power_meter_log(f"Mono goes to position: {position}")
            except ValueError:
                self.mono_and_power_meter_log("Please enter a valid integer for motor position.")
                return

        # if position within range send motor to absolute position
        if isinstance(position, int) and -250000 <= position <= 750000:\
        #For triax 320
        #if isinstance(position, int) and 0 <= position <= 32000:    
            try:
                # Get current position of the motor
                current_pos = self.mono.get_motor_position()
                move_amount = position - current_pos
                self.mono_and_power_meter_log(f"Moving motor from {current_pos} to {position} (Δ = {move_amount})")
                # Move motor relative to current position
                self.mono.move_motor_relative(move_amount)
                # QTimer to update the position label after moving
                # todo: need verify
                self.start_motor_status_timer()
            except Exception as e:
                self.mono_and_power_meter_log(f"Failed to move motor: {e}")
        else:
            self.mono_and_power_meter_log("Target step must be between -250000 and 750000.")
            #For triax 320
            #self.mono_and_power_meter_log("Target step must be between 0 and 32000.")
            return

    def ui_check_motor_limit(self):
        """Check if the motor is within limits and log the result."""
        self.mono_and_power_meter_log("Check Mono motor limits...")
        if not self.mono.device_connected:
            self.mono_and_power_meter_log("Mono not connected.")
            return
        msg = self.mono.motor_limit_check()
        self.mono_and_power_meter_log(msg)

    def ui_check_motor_status(self):
        """Check the motor status and log it."""
        self.mono_and_power_meter_log("Check Mono motor status...")
         # Check if the device is connected
        if not self.mono.device_connected:
            self.mono_and_power_meter_log("Mono not connected.")
            return
        status = self.mono.get_motor_status()
        print(f"Motor status: {status}")
        self.mono_and_power_meter_log(f"[Motor Status] {status}")

# todo: add power meter readings display (need verify)
    def ui_read_power_meter(self):
        """Read power meter data and display it in the GUI."""
        # Check if the power meter is connected
        if not self.power_meter.device_connected:
            return
        # Check if the mono stop flag is set to prevent reading during scan
        if hasattr(self, "mono_stop_flag") and not self.mono_stop_flag.is_set():
            return
        # Attempt to read power meter data and handle any exceptions
        try:
            # Read power meter data and unit
            power_value = float(self.power_meter.read_data())
            power_unit = self.power_meter.get_unit()
            # for testing purpose
            # power_value = random.uniform(1.40e-9, 15.0e-9)
            # power_unit = "W"
            # --------------------------------------

            # Display the power value and unit in the GUI
            self.ui.power_readings_lcdNumber.display(f"{power_value:.4e}")
            self.ui.power_readings_unit_label.setText(f"{power_unit}")

        except Exception as e:
            self.mono_and_power_meter_log(f"Failed to read power meter: {e}")
            return

    def update_power_readings_display(self, power_value: float):
        """update powermeter LCD display with the given power value.
        :param power_value: power value to display"""
        self.ui.power_readings_lcdNumber.display(f"{power_value:.4e}")

    def update_powermeter_unit_label(self, unit: str):
        self.ui.powermeter_unit_label.setText(unit)
        self.ui.power_readings_unit_label.setText(unit)

    def wait_for_mono_motor_idle(self, timeout=20, check_interval=1) -> bool:
        """
        Wait until the mono motor becomes idle or timeout occurs.

        :param timeout: maximum time to wait (in seconds)
        :param check_interval: time between checks (in seconds)
        :return: True if motor becomes idle, False if timeout or error/disconnected
        """
        elapsed = 0
        while elapsed < timeout:
            if self.mono_stop_flag.is_set():
                return False  # stop requested externally

            status = self.mono.get_motor_status()
            print(f"[Motor check] status: {status}")

            if status == "idle":
                return True  # motor ready
            elif status in ("error", "disconnected"):
                self.mono_and_power_meter_log("Motor status read error or disconnected. Stopping scan.")
                self.mono_stop_flag.set()
                return False

            time.sleep(check_interval)
            elapsed += check_interval

        # timeout case
        self.mono_and_power_meter_log("Timeout waiting for mono motor to become idle.")
        self.mono_stop_flag.set()
        return False

    def mono_and_stage_scan(self):
        """move the satge each stage step and do the mono scan with the mono scan range settings.
        """
        # Check if devices are connected return if not connected
        if not (self.mono.device_connected and self.stage_connected and self.power_meter.device_connected):
            # self.mono_and_power_meter_log("Device not connected.")
            self.ui_signal.mono_powermeter_log_signal.emit("Device not connected.")
            return

        # If device connected then check if mono parameters are valid and stage parameters are set:
        if self.mono.device_connected and self.stage_connected and self.power_meter.device_connected:
            # Check if mono scan parameters are valid if not return
            # todo: move to button click function
            # if not self.get_scan_parameters():
            #     return
            # setup the satge parameters and prepare the stage to wait at the start position:
            # todo: move to button click function
            # if self.confirm_stage_parameters_input() != 0:
            #     return
            # for loop to see if the stage is ready to move at the start position:
            for _ in range(20):
                # stage is ready at start position:
                if self.check_device_position():
                    self.ui_signal.mono_powermeter_log_signal.emit("Stage at start position.")
                    break
                self.ui_signal.mono_powermeter_log_signal.emit("Stage not yet at start position. Waiting...")
                time.sleep(1)
            else:
                # If the loop completes without breaking, it means the stage timeout
                self.ui_signal.mono_powermeter_log_signal.emit("Stage timeout waiting for start position.")
                return

        # todo: stage function
        # if stage parameters are not set or empty, return
        if not self.stage.ps_values:
            # self.mono_and_power_meter_log("Stage parameters not set or empty.")
            self.ui_signal.mono_powermeter_log_signal.emit("Stage parameters not set or empty.")
            return



        # start the stage + mono scan loop:
        for index, ps in enumerate(self.stage.ps_values):
            # if mono flag is set （stop） then stop the loop:
            if self.mono_stop_flag.is_set():
                # close scan update ui and save the file:
                # self.mono_and_power_meter_log("Monochromator scan stopped.")
                self.ui_signal.mono_powermeter_log_signal.emit("Monochromator scan stopped.")
                # todo: check if needed
                # self.file.auto_save_file()

                return

            # move the stage to the current position:
            if self.stage.ready_to_move:
                # move the stage to the current position in pico steps:
                pulse = gsc_functions.pico_to_pulses(ps)
                self.stage.move_to_position(pulse)
                # update the remaining steps in the stage:
                self.stage.remaining_steps = self.stage.total_steps - index
                self.signals.remaining_step_signal.emit(self.stage.remaining_steps)
                print(f"Remaining steps: {self.stage.remaining_steps} out of {self.stage.total_steps}")
            else:
                self.ui_signal.mono_powermeter_log_signal.emit("Stage is not ready to move.")
                # self.device_message = "Device not ready to move"
                # set the stop flag to stop the scan:
                self.mono_stop_flag.set()
                return


        # cur_position = self.check_position_command()
        # if cur_position == pico_to_pulses(self.end_point):
        #     self.device_message = "Device reached the end point"
        #     self.ready_to_move = False
        #     signals.auto_save_signal.emit()  # Emit the auto save signal
        #     return
        # else:
        #     self.move_to_position(pico_to_pulses(self.end_point))
        #     signals.plot_update_signal.emit()  # Emit the plot update signal
        #     signals.remaining_step_signal.emit(0)
        #     signals.auto_save_signal.emit()  # Emit the auto save signal
        #     self.device_message = "Device reached the end point"
        #     return
            # todo: set up mono scan part function

            # get the file name from GUI + specify the stage position:
            name_label = f"stage_at_{ps:06.2f}".replace('.', '_')
            # self.change_save_filename(name_label=name_label)
            self.ui_signal.update_filename_signal.emit(name_label)

            # get the power meter unit:
            self.power_meter.get_unit()
            power_meter_unit = self.power_meter.device_unit
            # set the power meter unit label in the GUI:
            # self.ui.powermeter_unit_label.setText(f"{power_meter_unit}")
            # self.ui.power_readings_unit_label.setText(f"{power_unit}")
            self.ui_signal.update_powermeter_unit_signal.emit(power_meter_unit)

            # double check the parameters are correct range
            invalid_steps = [s for s in self.x_values if s < -250000 or s > 750000]
            #For triax 320
            #invalid_steps = [s for s in self.x_values if s < -0 or s > 32000]
            
            if invalid_steps:
                # self.mono_and_power_meter_log(f"Invalid steps detected: {invalid_steps}")
                self.ui_signal.mono_powermeter_log_signal.emit(f"Invalid steps detected: {invalid_steps}")
                # set the stop flag to stop the scan:
                self.mono_stop_flag.set()
                return

            # init data file for this stage position mono scan:
            self.file.init_cache([f"stage at {ps}", "Mono position:"] + self.x_values)
            # set the wavelengths row if mono_wavelengths exist:
            if self.mono_wavelengths:
                wl_row = [f" ", "wavelength (nm)"] + [f"{wl:.4f}" for wl in self.mono_wavelengths]
                self.file.append_row(wl_row)

            # log message of the start of the mono scan:
            # self.mono_and_power_meter_log(f"Monochromator scan started at stage position {ps}.")
            self.ui_signal.mono_powermeter_log_signal.emit(f"Monochromator scan started at stage position {ps}.")
            # start the mono scan loop:
            for test in range(self.test_num):
                # stop the mono scan loop:
                if self.mono_stop_flag.is_set():
                    return
                print(f"Test {test}")
                # update remaining test label:
                self.updare_monoscan_remaintest_signal.emit(self.test_num - test)
                # initialize y list to all zero for plotting function to work properly:
                self.y_values = [0] * len(self.x_values)
                # move to start position:
                current_pos = self.mono.get_motor_position()
                move_steps = self.x_values[0] - current_pos
                print(f"Move steps: {move_steps}")
                self.mono.move_motor_relative(move_steps)

                # check if the motor is at starting position:
                for _ in range(20):
                    # motor busy check loop (the scan is in a working thread so non-blocking to UI):
                    if self.mono_stop_flag.is_set():
                        # cloes scan update ui and save the file:
                        self.updare_monoscan_remaintest_signal.emit(0)
                        self.file.auto_save_file()
                        return
                    status = self.mono.get_motor_status()
                    print(f"Motor status: {status}")
                    # Check if the motor is idle, error, or disconnected
                    if status == 'idle':
                        break
                    elif status in ('error', 'disconnected'):

                        # self.mono_and_power_meter_log("Motor status read error or disconnected. Stopping scan.")
                        self.ui_signal.mono_powermeter_log_signal.emit(
                            "Motor status read error or disconnected. Stopping scan.")
                        self.mono_stop_flag.set()
                        self.updare_monoscan_remaintest_signal.emit(0)
                        self.file.auto_save_file()
                        return
                    time.sleep(1)
                else:
                    # If the loop completes without breaking, it means the motor is still busy (timeout)
                    # self.mono_and_power_meter_log("Timeout waiting for motor idle.")
                    self.ui_signal.mono_powermeter_log_signal.emit(
                        "Timeout waiting for motor idle.")
                    self.mono_stop_flag.set()
                    # cloes scan update ui and save the file:
                    self.updare_monoscan_remaintest_signal.emit(0)
                    self.file.auto_save_file()
                    return
                # todo: add safety check for motor position
                # ------------------------------------------
                motor_pos_cur = self.x_values[0]  # simulation of motor
                for index, next_pos in enumerate(self.x_values):
                    # stop the scan loop:
                    if self.mono_stop_flag.is_set():
                        # self.mono_and_power_meter_log(
                        #     f"Aborting scan: scan stopped at index {index} by flag."
                        # )
                        self.ui_signal.mono_powermeter_log_signal.emit(
                            f"Aborting scan: scan stopped at index {index} by flag.")
                        # cloes scan update ui and save the file:
                        self.updare_monoscan_remaintest_signal.emit(0)
                        self.file.auto_save_file()
                        return

                    print(f"Step: {index}")
                    # move motor:
                    motor_move = next_pos - motor_pos_cur
                    # safety check for motor to move only towards the end position:
                    if motor_move < 0:
                        # self.mono_and_power_meter_log(
                        #     f"Aborting scan: motor would move backwards ({motor_move}) at index {index}."
                        # )
                        self.ui_signal.mono_powermeter_log_signal.emit(
                            f"Aborting scan: motor would move backwards ({motor_move}) at index {index}.")
                        self.mono_stop_flag.set()
                        # cloes scan update ui and save the file:
                        self.updare_monoscan_remaintest_signal.emit(0)
                        self.file.auto_save_file()
                        return

                    # move the motor relative to the current position:
                    self.mono.move_motor_relative(motor_move)
                    # simulation of motor behavior:
                    print(f"motor move {motor_move}")
                    motor_pos_cur += motor_move
                    print(f"motor at {motor_pos_cur}")
                    # power meter get intensity and store it to y value list:
                    print(f"power meter get intensity at {motor_pos_cur}.")

                    # take power meter reading with average over multiple samples:
                    # self.y_values[index] = self.average_power_reading(samples=POWERMETER_SAMPLES, delay=0.05)
                    ave_pow_readings = self.average_power_reading(samples=POWERMETER_SAMPLES, delay=0.05)
                    # store the average power reading to y_values list for plotting:
                    self.y_values[index] = ave_pow_readings
                    # update the power meter LCD display with the average reading:
                    self.ui_signal.update_power_lcd_signal.emit(ave_pow_readings)

                    # send update plot signal to main thread:
                    self.upadte_powermeter_plot_signal.emit()
                    # send update mono remain step tp main thread:
                    self.update_monoscan_remainstep_signal.emit(len(self.x_values) - index)
                    # prevent mono to overload:
                    time.sleep(0.5)

                self.update_monoscan_remainstep_signal.emit(0)
                # timestamp (YYYY-MM-DD HH:MM:SS）
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # append the data to the file:
                self.file.append_row([timestamp, f"Test: {test + 1} readings unit: ({power_meter_unit})"] + self.y_values)
                time.sleep(0.05)

            # update remaining mono scan test:
            self.updare_monoscan_remaintest_signal.emit(0)
            # autosave data chche with timstamp:
            self.file.auto_save_file()

        # set the stage + mono scan loop to set to indicate scan finished:
        self.mono_stop_flag.set()
        # log the end of the scan:
        # self.mono_and_power_meter_log("stage and mono scan finished.")
        self.ui_signal.mono_powermeter_log_signal.emit("stage and mono scan finished.")

    def ui_start_mono_stage_scan(self):
        """Start the monochromator and stage scan in a separate thread."""
        # Check if devices are connected
        if not (self.mono.device_connected and self.stage_connected and self.power_meter.device_connected):
            # self.mono_and_power_meter_log("Device not connected.")
            self.ui_signal.mono_powermeter_log_signal.emit("Device not connected.")
            return
        # If device connected then check if parameters are valid
        if (self.get_scan_parameters() and self.confirm_stage_parameters_input() == 0):
            # Check if the mono scan thread is already running
            if self.thread is None or not self.thread.is_alive():
                # Clear the stop flag and set the mono scan loop to running:
                self.mono_stop_flag.clear()
                # self.mono_and_power_meter_log("Monochromator scan started.")
                self.ui_signal.mono_powermeter_log_signal.emit("Monochromator scan started.")
                # Start the mono scan in a separate thread
                self.thread = threading.Thread(target=self.mono_and_stage_scan)
                self.thread.start()
            # if the thread is running, do not start a new one
            else:
                self.mono_and_power_meter_log("Monochromator scan already running in thread.")
                return
        else:
            # self.mono_and_power_meter_log("Parameters not valid. Scan not start.")
            self.ui_signal.mono_powermeter_log_signal.emit("Parameters not valid. Scan not start.")
            return

    def ui_stop_mono_stage_scan(self):
        """Stop the monochromator and stage scan."""
        # set the stop flag to stop the scan:
        self.ui_signal.mono_powermeter_log_signal.emit("Stopping monochromator scan...")
        self.mono_stop_flag.set()
        # Do NOT call thread.join() here — it would block the UI thread.

    def ui_start_mono_iv_curve_meas(self):
        """Start the monochromator IV curve measurement in a separate thread."""
        # read y range from UI
        self.iv_ui_controller.ui_read_y_range()
        # Check if devices are connected
        if not (self.mono.device_connected and self.keithley_controller.vm2182_connected and self.keithley_controller.cs6220_connected):
            self.ui_signal.mono_powermeter_log_signal.emit("Device not connected.")
            return
        # If device connected then check if parameters are valid
        if self.get_scan_parameters() is not True:
            self.ui_signal.mono_powermeter_log_signal.emit("Parameters not valid. Measurement not start.")
            return
        # check if iv parameters are valid and setup arming process:
        arming_underprocess = self.iv_ui_controller.arm_device()
        if arming_underprocess is not True:
            self.iv_ui_controller.log_message("Keithley 6220 not armed. Measurement not start.")
            return
        # Check if the mono scan thread is already running
        if self.thread is None or not self.thread.is_alive():
            # change file name
            self.change_save_filename()
            # Clear the stop flag and set the mono scan loop to running:
            # todo: implement flag
            self.iv_meas_stop_flag.clear()
            self.ui_signal.mono_powermeter_log_signal.emit("Monochromator IV curve measurement started.")
            # Start the mono iv scan in a separate thread
            # todo: implement mono iv curve measurement function
            self.thread = threading.Thread(target=self.mono_iv_scan)
            self.thread.start()
        else:
            self.ui_signal.mono_powermeter_log_signal.emit("Thread occupied.")
            return

    def ui_stop_mono_iv_curve_meas(self):
        """Stop the monochromator IV curve measurement."""
        # set the stop flag to stop the scan:
        self.ui_signal.mono_powermeter_log_signal.emit("Stopping monochromator IV curve measurement...")
        self.iv_meas_stop_flag.set()
        # No self thread.join() here, as it will block the UI.
        if threading.current_thread() != self.thread:
            self.thread.join()
            self.ui_signal.mono_powermeter_log_signal.emit("Monochromator IV curve measurement stopped.")
            self.iv_ui_controller.abort_process()

    def mono_iv_scan(self):
        """Perform the monochromator IV curve measurement."""
        # Check arming status of the Keithley 6220:
        for _ in range(20):
            if self.keithley_controller.under_arming is False:
                self.iv_ui_controller.log_message("Keithley 6220 finished arming.")
                break
            self.iv_ui_controller.log_message("Keithley 6220 under arming process.")
            time.sleep(1)
        else:
            self.iv_ui_controller.log_message("Keithley 6220 arming timeout. Measurement not start.")
            return
        # check if cs6220 is armed:
        if self.keithley_controller.is_armed is not True:
            self.iv_ui_controller.log_message("Keithley 6220 not armed. Measurement not start.")
            return

        # double check the mono parameters are correct range
        invalid_steps = [s for s in self.x_values if s < -250000 or s > 750000]
        #For triax 320
        #invalid_steps = [s for s in self.x_values if s < -0 or s > 32000]

        if invalid_steps:
            # self.mono_and_power_meter_log(f"Invalid steps detected: {invalid_steps}")
            self.ui_signal.mono_powermeter_log_signal.emit(f"Invalid steps detected: {invalid_steps}")
            # set the stop flag to stop the scan:
            self.iv_meas_stop_flag.set()
            return

        # log message of the start of the mono scan:
        self.ui_signal.mono_powermeter_log_signal.emit(f"Monochromator iv curve measurement started.")
        # start the mono iv curve measurement loop:
        for test in range(self.test_num):
            # stop the mono scan loop:
            if self.iv_meas_stop_flag.is_set():
                return
            print(f"Mono iv curve scan test No.{test}")
            # update remaining test label:
            self.updare_monoscan_remaintest_signal.emit(self.test_num - test)
            # mono move to start position:
            current_pos = self.mono.get_motor_position()
            move_steps = self.x_values[0] - current_pos
            print(f"Move steps: {move_steps}")
            self.mono.move_motor_relative(move_steps)
            # check if the mono motor is at starting position:
            for _ in range(20):
                # motor busy check loop (the scan is in a working thread so non-blocking to UI):
                if self.iv_meas_stop_flag.is_set():
                    # cloes scan update ui and save the file:
                    self.updare_monoscan_remaintest_signal.emit(0)
                    print("mono iv stop flag set.")

                    return
                # Check if the motor is idle, error, or disconnected
                status = self.mono.get_motor_status()
                print(f"Motor status: {status}")

                if status == 'idle':
                    # mono motor is ready at starting position break for loop:
                    break
                elif status in ('error', 'disconnected'):
                    # mono motor status read error or disconnected:

                    self.ui_signal.mono_powermeter_log_signal.emit(
                        "Motor status read error or disconnected. Stopping scan.")
                    self.iv_meas_stop_flag.set()
                    self.updare_monoscan_remaintest_signal.emit(0)

                    return
                time.sleep(1)
            else:
                # If the loop completes without breaking, it means the motor is still busy (timeout)

                self.ui_signal.mono_powermeter_log_signal.emit(
                    "Timeout waiting for motor idle.")
                self.iv_meas_stop_flag.set()
                # cloes scan update ui and save the file:
                self.updare_monoscan_remaintest_signal.emit(0)
                return
            # mono start the position stepping loop:
            motor_pos_cur = self.x_values[0]
            # mono stepping loop:
            for index, next_pos in enumerate(self.x_values):
                # stop the scan loop:
                if self.iv_meas_stop_flag.is_set():

                    self.ui_signal.mono_powermeter_log_signal.emit(
                        f"Aborting scan: scan stopped at index {index} by flag.")
                    # cloes scan update ui and save the file:
                    self.updare_monoscan_remaintest_signal.emit(0)

                    # todo: save the file
                    self.file.auto_save_file()
                    return

                print(f"Mono iv curve scan at mono step: {index}")
                # move motor:
                motor_move = next_pos - motor_pos_cur
                # safety check for motor to move only towards the end position:
                if motor_move < 0:
                    # mono motor move backwards:
                    self.ui_signal.mono_powermeter_log_signal.emit(
                        f"Aborting scan: motor would move backwards ({motor_move}) at index {index}.")
                    self.iv_meas_stop_flag.set()
                    # cloes scan update ui and save the file:
                    self.updare_monoscan_remaintest_signal.emit(0)

                    # todo: save the file
                    self.file.auto_save_file()
                    return


                # move the motor relative to the current position:
                self.mono.move_motor_relative(motor_move)
                # simulation of motor behavior:
                print(f"motor move {motor_move}")
                motor_pos_cur += motor_move
                print(f"motor at {motor_pos_cur}")
                # measure iv curve at the current mono position:
                print(f"iv curve measured at mono: {motor_pos_cur}.")
                # todo: call the keithley 6220 to measure iv curve at the current mono position:
                start_iv_meas = self.iv_ui_controller.init_measurement()
                # todo: update plot of iv curve
                if start_iv_meas:
                    self.ui_signal.mono_powermeter_log_signal.emit("IV curve measurement started.")
                    self.iv_ui_controller.retrieve_iv_data()
                    # todo: save the iv curve data to the file:
                    # timestamp (YYYY-MM-DD HH:MM:SS）
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if index == 0:
                        # Write header on first run
                        header = ["Timestamp", "Wavelength (nm)", "Motor position(steps)", "Current (A)"] + [f"{i:.2e} A" for i in
                                                                           self.keithley_controller.current_values]
                        self.file.init_cache(header)

                    # Determine x-axis value: wavelength or motor position
                    if self.mono_wavelengths:
                        wavelength = self.mono_wavelengths[index]
                    else:
                        wavelength = ""

                    motor_position = motor_pos_cur
                    # x_value = self.mono_wavelengths[index] if self.mono_wavelengths else motor_pos_cur

                    # Create and append row
                    row = [timestamp, wavelength, motor_position, "VDC"] + self.keithley_controller.voltage_values
                    self.file.append_row(row)

                else:
                    self.ui_signal.mono_powermeter_log_signal.emit(f"IV curve measurement failed, "
                                                                   f"skipping {motor_pos_cur} to next mono position.")




                # send update mono remain step tp main thread:
                self.update_monoscan_remainstep_signal.emit(len(self.x_values) - index)
                # to next mono position in for loop
        self.file.auto_save_file()

        return

    def ui_start_iv_curve_meas(self):
        """Start the IV curve measurement in a separate thread."""
        # read y range from UI
        self.iv_ui_controller.ui_read_y_range()
        # Check if devices are connected
        if not (self.keithley_controller.vm2182_connected and self.keithley_controller.cs6220_connected):
            self.iv_ui_controller.log_message("Device not connected.")
            return
        # start the thread
        # check if iv parameters are valid and set arming is done:
        arming_underprocess = self.iv_ui_controller.arm_device()
        if arming_underprocess is not True:
            self.iv_ui_controller.log_message("Keithley 6220 not armed. Measurement not start.")
            return

        # Check if the scan thread is already running
        if self.thread is None or not self.thread.is_alive():

            self.iv_ui_controller.log_message("IV curve measurement started.")
            # Start the iv scan in a separate thread
            # todo: implement iv curve measurement function
            self.thread = threading.Thread(target=self.iv_curve_meas)
            self.thread.start()
        else:
            self.iv_ui_controller.log_message("Thread occupied.")
            return

    def iv_curve_meas(self):
        """Start the IV curve measurement logic."""
        # Check arming status of the Keithley 6220:
        for _ in range(20):
            if self.keithley_controller.under_arming is False:
                self.iv_ui_controller.log_message("Keithley 6220 finished arming.")
                break
            self.iv_ui_controller.log_message("Keithley 6220 under arming process.")
            time.sleep(1)
        else:
            self.iv_ui_controller.log_message("Keithley 6220 arming timeout. Measurement not start.")
            return
        # check if cs6220 is armed:
        if self.keithley_controller.is_armed is not True:
            self.iv_ui_controller.log_message("Keithley 6220 not armed. Measurement not start.")
            return

        start_iv_meas = self.iv_ui_controller.init_measurement()
        # todo: update plot of iv curve
        if start_iv_meas:
            self.iv_ui_controller.log_message("IV curve measurement started.")
            self.iv_ui_controller.retrieve_iv_data()
            # Create file and append row
            header = ["Timestamp", "Current(A)"] + [f"{i:.2e} A" for i in
                                                               self.keithley_controller.current_values]
            self.file.init_cache(header)

            # timestamp (YYYY-MM-DD HH:MM:SS）
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = [timestamp + "VDC"] + self.keithley_controller.voltage_values
            self.file.append_row(row)
            self.file.auto_save_file()
            # disarm the keithley 6220 after measurement
            time.sleep(0.5)
            self.iv_ui_controller.abort_process()

            return
        else:
            self.iv_ui_controller.log_message("IV curve measurement not complete.")
            return

    def ui_stop_iv_curve_meas(self):
        """Stop iv curve measurement."""
        self.iv_ui_controller.log_message("IV curve measurement stopped.")
        self.iv_ui_controller.abort_process()
        if hasattr(self, "thread") and self.thread is not None:
            print("Stopping iv curve measurement thread.")
            # prevent killing thread in thread
            if threading.current_thread() != self.thread:
                self.thread.join()


    # def connect_keithley(self):
    #     """Handles device connection."""
    #     self.log_message("Connection initiating.")
    #     self.keithley_controller.connect_device()
    #
    # def log_message(self, message):
    #     """Helper function to log messages with a timestamp."""
    #     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    #     self.ui.keithley6220_statusbox.append(f"[{timestamp}] {message}")
    #
    # def disconnect_keithley(self):
    #     """Handles device disconnection."""
    #     self.log_message("Disconnecting.")
    #     self.keithley_controller.disconnect_device()
    #
    # def update_keithley_status_by_bool(self, success, message):
    #
    #     """Updates the Keithley 6220 status box with a timestamp."""
    #     if success:
    #         self.log_message(f"Success: {message}")
    #     else:
    #         self.log_message(f"Error: {message}")
    #
    # def update_2182a_status(self, message):
    #     """Updates the Keithley 2182A status label."""
    #     self.ui.nv_2182a_label.setText(message)
    # todo: add mono steps
    # todo: fix scaling

    # -----------ui picoharp300 functions---------------
    # def ui_connect_picoharp300(self):
    #     """Connect to PicoHarp 300 with full error handling."""
    #     print("[Connect] Scanning for PicoHarp devices...")
    #     # Connect to PicoHarp by API function
    #     try:
    #         ok = self.picoharp.connect()
    #         if ok:
    #             print("[Connect] PicoHarp Connected successfully.")
    #         else:
    #             print("[Connect] No available PicoHarp devices were found.")
    #     # OS or DLL error
    #     except OSError as e:
    #         print(f"[Connect] PicoHarp OS/DLL error while connecting: {e}")
    #     # Other unexpected errors
    #     except Exception as e:
    #         print(f"[Connect] Unexpected PicoHarp error while connecting: {e}")
    #     finally:
    #         print("[Connect] Connect PicoHarp attempt finished.")

    def ui_connect_picoharp(self):
        """Connect to PicoHarp 300 with full error handling and user prompt to init picoharp."""
        print("[Connect] Scanning for PicoHarp devices...")
        try:
            ok = self.picoharp.connect()
            # If no devices found, return early
            if not ok:
                print("[Connect] No available PicoHarp devices were found.")
                print("[Connect] Connect PicoHarp attempt finished.")
                return
            # If connected successfully, proceed
            print("[Connect] PicoHarp Connected successfully.")
            print("[Connect] Connect PicoHarp attempt finished.")

            # Prompt user to initialize and setup
            reply = QMessageBox.question(
                self,
                "Initialize & Setup?",
                "Device connected.\nDo you want to Initialize and apply default Setup now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No # default to No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Initialize and setup the first device (index 0)
                self.ui_init_then_setup(index=0)
        # OS or DLL error
        except OSError as e:
            print(f"[Connect] PicoHarp OS/DLL error while connecting: {e}")
            print("[Connect] Connect PicoHarp attempt finished.")
            return
        # Other unexpected errors
        except Exception as e:
            print(f"[Connect] Unexpected PicoHarp error while connecting: {e}")
            print("[Connect] Connect PicoHarp attempt finished.")
            return

    def ui_disconnect_picoharp(self):
        """Disconnect from PicoHarp 300 with full error handling."""
        print("[Disconnect] Closing PicoHarp devices...")
        # Disconnect from PicoHarp by API function
        try:
            self.picoharp.disconnect()
            print("[Disconnect] PicoHarp Disconnected successfully.")
        except OSError as e:
            print(f"[Disconnect] OS/DLL error while disconnecting: {e}")
        except Exception as e:
            print(f"[Disconnect] Unexpected error while disconnecting: {e}")
        finally:
            print("[Disconnect] Disconnect PicoHarp attempt finished.")

    def _run_pico_thread_task(self, func):
        """picoharp threading helper to run hardware tasks in a separate thread.
        :param func: Function to run in a separate thread."""

        # Prevent overlapping hardware tasks (prevent DLL racing condition)
        if self._pico_hw_busy:
            print("[HW] Busy, please wait...")
            return
        self._pico_hw_busy = True
        # Run the hardware task in a separate thread
        def task():
            try:
                func()
            except Exception as e:
                print(f"[HW] Error: {e}")
            finally:
                self._pico_hw_busy = False
        # Daemon thread to not block app exit
        threading.Thread(target=task, daemon=True).start()

    def ui_init_then_setup(self, index: int = 0):
        """(for after connect to picoharp) \n
        Initialize and setup PicoHarp device with default parameters.
        :param index: Device index to initialize and setup (default is 0)."""
        def job():
            print(f"[Init+Setup] Start PicoHarp 300.(index={index})")
            t0 = time.time()
            # Initialize device
            ok = self.picoharp.initialize_device(index)
            if not ok:
                print("[Init+Setup] Init failed, abort.")
                return
            print("[Init+Setup] Init OK. Proceed to Setup...")
            # Emit signal to update UI init status
            self.pico_sig.update_pico_init_status_signal.emit(True)

            # Setup device with default parameters
            ok2 = self.picoharp.setup_device(
                index=index,
                binning=0, offset=0,
                sync_divider=1,
                cfd_level_0=100, cfd_zc_0=10,
                cfd_level_1=50, cfd_zc_1=10
            )
            dt = time.time() - t0
            print(f"[Init+Setup] {'All OK' if ok2 else 'Setup failed'} in {dt:.3f} s")

            if ok2:
                # signal to update UI setup status
                self.pico_sig.update_labels.emit(
                    0,  # binning
                    0,  # offset
                    1,  # sync_divider
                    100.0,  # cfd_level_0
                    10.0,  # cfd_zc_0
                    50.0,  # cfd_level_1
                    10.0  # cfd_zc_1
                )


        # Run the job in a separate thread with hardware task handler
        self._run_pico_thread_task(job)

    def ui_init_picoharp(self, index: int = 0):
        """Initialize PicoHarp device.
        :param index: Device index to initialize (default is 0)."""

        def job():
            print(f"[Init] Start (index={index})")
            t0 = time.time()
            ok = self.picoharp.initialize_device(index)
            print(f"[Init] {'OK' if ok else 'Fail'} in {time.time() - t0:.3f}s")
            if ok:
                # Emit signal to update UI init status
                self.pico_sig.update_pico_init_status_signal.emit(True)

        self._run_pico_thread_task(job)

    def ui_setup_picoharp(self, index: int = 0):
        """Setup PicoHarp device with parameters from UI controls.
        :param index: Device index to setup (default is 0)."""
        # can get parameters from UI here, e.g.:
        # binning = self.ui.spinBinning.value()
        # And make it into params = dict(
        #     index=index,
        #     binning=0, offset=0,
        #     sync_divider=1,
        #     cfd_level_0=100, cfd_zc_0=10,
        #     cfd_level_1=50, cfd_zc_1=10 )
        # then call: ok = self.picoharp.setup_device(**params)

        # for simplicity, using fixed parameters here(as default shown in github demo):
        def job():
            print(f"[Setup] Start (index={params['index']})")
            t0 = time.time()
            ok = self.picoharp.setup_device(
                index=index,
                binning=0,
                offset=0,
                sync_divider=1,
                cfd_level_0=100,
                cfd_zc_0=10,
                cfd_level_1=50,
                cfd_zc_1=10
            )
            if ok:
                self.pico_sig.update_labels.emit(
                    0,  # binning
                    0,  # offset
                    1,  # sync_divider
                    100.0,  # cfd_level_0
                    10.0,  # cfd_zc_0
                    50.0,  # cfd_level_1
                    10.0  # cfd_zc_1
                )
            print(f"[Setup] {'OK' if ok else 'Fail'} in {time.time() - t0:.3f}s")

        self._run_pico_thread_task(job)

    def mono_pico_scan(self, device_index=0, tacq_ms=1000, block=0,
                       stop_on_overflow=True, overflow_limit=65535):
        """
        Perform the monochromator scan and measure PicoHarp histogram at each step.
        WARNINGS: large data cache possible (~100MB for 100 mono wavelength steps and might not be linear growth)
        and plot is reduceed by some degree of resolution for better ui performance.
        - device_index: PicoHarp device index (default 0)
        - tacq_ms: picoharp acquisition time in ms (default 1000 ms)
        - block: histogram block（default 0）
        - stop_on_overflow / overflow_limit: overflow handling (default True/65535)
        """
        # 0) picoharp measurement integration time setting
        tacq = tacq_ms

        # 1) Check mono steps validity
        invalid_steps = [s for s in self.x_values if s < -250000 or s > 750000]
        #For triax 320
        #invalid_steps = [s for s in self.x_values if s < -0 or s > 32000]

        if invalid_steps:
            print(f"Invalid MONO steps detected: {invalid_steps}")
            self.pico_meas_stop_flag.set()
            return # stop the scan if invalid steps found

        # 2) log start message
        print("Monochromator PicoHarp histogram scan started.")

        header_written = False
        # 3) test cycle loop:
        for test in range(self.test_num):
            #　check scan flag:
            if self.pico_meas_stop_flag.is_set():
                return # stop the scan loop if flag is set

            # test start log and update remain test label
            print(f"Mono PicoHarp scan test No.{test}")
            self.updare_monoscan_remaintest_signal.emit(self.test_num - test)
            # prepare picharp scan plot:
            try:
                # obtain resolution in ps
                resolution_ps = float(self.picoharp.get_resolution(device_index))
            except Exception:
                resolution_ps = 4.0  # as default 4 ps if error
            # prepare picoharp scan plot signal:
            N_points = len(self.x_values)
            rebin_factor = 64  # rebin factor for picoharp plot
            # wavelengths list or None if not available
            wavelengths = getattr(self, "mono_wavelengths", None)
            # emit signal to main thread to prepare picoharp plot
            self.pico_sig.begin_scan.emit(
                N_points, resolution_ps, rebin_factor,
                self.x_values,
                wavelengths
            )
            # 3.1) move mono to start position
            current_pos = self.mono.get_motor_position()
            move_steps = self.x_values[0] - current_pos
            print(f"MONO Move steps: {move_steps}")
            self.mono.move_motor_relative(move_steps)

            # 3.2) wait and check if the mono motor is at starting position:
            for _ in range(20):
                # check scan flag:
                if self.pico_meas_stop_flag.is_set():
                    self.updare_monoscan_remaintest_signal.emit(0)
                    print("mono pico stop flag set.")
                    return # stop the scan loop if flag is set

                # Check if the motor is idle, error, or disconnected
                status = self.mono.get_motor_status()
                print(f"Motor status: {status}")
                # check motor status
                if status == 'idle':
                    break # mono motor is ready at starting position break for loop

                # mono motor status read error or disconnected
                elif status in ('error', 'disconnected'):
                    self.ui_signal.mono_powermeter_log_signal.emit(
                        "Motor status read error or disconnected. Stopping scan.")
                    self.pico_meas_stop_flag.set()
                    self.updare_monoscan_remaintest_signal.emit(0)
                    return # stop scan if motor error or disconnected

                # check interval for mono motor status:
                time.sleep(1)
            # for loop timeout waiting for motor idle:
            else:
                self.ui_signal.mono_powermeter_log_signal.emit("Timeout waiting for motor idle.")
                self.pico_meas_stop_flag.set()
                self.updare_monoscan_remaintest_signal.emit(0)
                return # stop scan if motor timeout

            # 4) mono position stepping loop:
            motor_pos_cur = self.x_values[0]

            # mono stepping loop:
            for index, next_pos in enumerate(self.x_values):
                # 4.1) scan stop flag check
                if self.pico_meas_stop_flag.is_set():
                    print(f"Aborting scan: stopped at index {index} by flag.")
                    self.updare_monoscan_remaintest_signal.emit(0)
                    self.file.auto_save_file()
                    return

                print(f"Mono PicoHarp scan at mono step: {index}")


                motor_move = next_pos - motor_pos_cur
                # 4.2) only positive step allowed
                if motor_move < 0:
                    self.ui_signal.mono_powermeter_log_signal.emit(
                        f"Aborting scan: motor would move backwards ({motor_move}) at index {index}.")
                    self.pico_meas_stop_flag.set()
                    self.updare_monoscan_remaintest_signal.emit(0)
                    self.file.auto_save_file()
                    return

                # 4.3) mono move motor to next position
                self.mono.move_motor_relative(motor_move)
                print(f"motor move {motor_move}")
                motor_pos_cur += motor_move
                print(f"motor at {motor_pos_cur}")


                # 4.4) Check and initialize header if not done yet
                if not header_written:
                    # create header with meta cols + 65536 bin cols (very wide!)
                    meta_cols = [
                        "Test No.","Index", "Timestamp", "Wavelength_nm", "Motor_steps",
                        "Resolution_ps", "Tacq_ms", "CountRate_Ch0", "CountRate_Ch1",
                        "Overflow", "Total_counts",
                        "Status", "ErrorMessage"
                    ]
                    bin_cols = [f"Bin{i}" for i in range(65536)]
                    header = meta_cols + bin_cols
                    # write header to file
                    self.file.init_cache(header)
                    header_written = True

                # 4.5) PicoHarp histogram measurement at current mono position
                print(f"histogram measured at mono: {motor_pos_cur}.")
                try:
                    result = self.picoharp.measure_histogram(
                        index=device_index,
                        tacq_ms=tacq_ms,
                        block=block,
                        stop_on_overflow=stop_on_overflow,
                        overflow_limit=overflow_limit,
                        cancel_event=self.pico_meas_stop_flag  # stop event
                    )
                    # update picoharp plot in main thread via signal
                    self.pico_sig.new_point.emit(
                        index,
                        result["counts"],
                        result.get("tacq_ms", tacq_ms),
                        True
                    )
                    # 4.6) retrieve result successfully and write to file
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    wavelength = self.mono_wavelengths[index] if getattr(self, "mono_wavelengths", None) else ""

                    # overflow status string
                    status_str = "OK_OVERFLOW" if bool(result["overflow"]) else "OK"

                    row = [
                              test,index, timestamp, wavelength, motor_pos_cur,
                              result["resolution_ps"], result["tacq_ms"],
                              result["count_rate_ch0"], result["count_rate_ch1"],
                              result["overflow"], result["total_counts"],
                              status_str, ""  # ErrorMessage empty if no error
                          ] + result["counts"]

                    self.file.append_row(row)

                # 4.6.1) PicoHarp measurement failed, log error and write error row
                except Exception as e:
                    self.ui_signal.mono_powermeter_log_signal.emit(
                        f"PicoHarp measurement failed at pos {motor_pos_cur}: {e}. Skipping.")
                    # write error row with empty bins
                    empty_bins = [0] * 65536
                    # update picoharp plot in main thread via signal with empty bins
                    self.pico_sig.new_point.emit(
                        index,
                        empty_bins,
                        tacq_ms,
                        True
                    )
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    wavelength = self.mono_wavelengths[index] if getattr(self, "mono_wavelengths", None) else ""
                    row = [
                              test,index, timestamp, wavelength, motor_pos_cur,
                              "", "", "", "", "", "",
                              "ERROR", str(e)
                          ] + empty_bins
                    self.file.append_row(row)
                    # continue to next mono position
                    self.update_monoscan_remainstep_signal.emit(len(self.x_values) - index)
                    continue

                # 4.7) UI update remain step
                self.update_monoscan_remainstep_signal.emit(len(self.x_values) - index)
                time.sleep(0.1)  # slight delay to avoid UI overload

        # 5) auto save file at end of all tests
        self.file.auto_save_file()
        return

    def start_pico_mono_scan(self):
        """Start the monochromator and pico scan in a separate thread."""
        # Check if devices are connected
        if not (self.mono.device_connected and self.picoharp.connected):
            print("Device not connected.")
            return
        # If device connected then check if parameters are valid
        if self.get_scan_parameters() is True:
            # Check if the mono scan thread is already running
            if self.thread is None or not self.thread.is_alive():
                # Clear the stop flag and set the mono scan loop to running:
                self.pico_meas_stop_flag.clear()
                print("Monochromator scan started.")
                # Start the mono scan in a separate thread
                self.thread = threading.Thread(target=self.mono_pico_scan)
                self.thread.start()
            # if the thread is running, do not start a new one
            else:
                print("One scan already running.")
        else:
            print("MONO Parameters not valid. Scan not start.")
            return

    def stop_pico_mono_scan(self):
        """Stop the monochromator and pico scan."""
        if not self.pico_meas_stop_flag.is_set():
            self.pico_meas_stop_flag.set()
            # Do NOT call thread.join() here — it would block the UI thread.
            print("PICO/Monochromator scan stop requested.")
        else:
            print("PICO/Monochromator scan already stopped.")

    def update_pico_serial_label(self):
        """Update the picoharp serial number label in the UI."""
        serial = self.picoharp.hwSerial.value.decode(errors='ignore')
        self.picoharp_serial_lab.setText(str(serial))

    def update_pico_init_label(self, inited: bool):
        """Update the picoharp init status label in the UI."""
        self.ui.picoharp_init_status_lab.setText("Yes" if inited else "No")

    def update_pico_labels(self,
                           binning: int = 0,
                           offset: int = 0,
                           sync_divider: int = 1,
                           cfd_level_0: float = 100,
                           cfd_zc_0: float = 10,
                           cfd_level_1: float = 50,
                           cfd_zc_1: float = 10):
        """Update the picoharp setup parameter labels in the UI by setup function."""
        # --- Resolution label ---
        if binning == 0:
            self.picoharp_resolution_lab.setText("4 ps")

        # --- Offset / Sync divider ---
        self.picoharp_offset_lab.setText(str(offset))
        self.picoharp_sync_divider_lab.setText(str(sync_divider))

        # --- CFD settings: CH0 ---
        self.picoharp_cfd_lev_0_lab.setText(f"{float(cfd_level_0):.1f}")
        self.picoharp_cfd_zc_0_lab.setText(f"{float(cfd_zc_0):.1f}")

        # --- CFD settings: CH1 ---
        self.picoharp_cfd_lev_1_lab.setText(f"{float(cfd_level_1):.1f}")
        #
        self.picoharp_cfd_zc_0_lab_2.setText(f"{float(cfd_zc_1):.1f}")
