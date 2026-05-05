import time
import ctypes as ct
from ctypes import byref

class PicoHarpController:
    def __init__(self, dll_path="./PHLib64.dll", max_devnum=8):
        # constants
        self.HISTCHAN = 65536
        self.MAXDEVNUM = max_devnum
        self.MODE_HIST = 0
        self.FLAG_OVERFLOW = 0x0040

        # load dll
        self.dll = ct.CDLL(dll_path)

        # -----------------------------
        # declare argtypes / restype
        # -----------------------------
        c_int = ct.c_int
        c_uint = ct.c_uint
        c_double = ct.c_double
        c_char_p = ct.c_char_p

        # strings are passed as buffers; functions fill them in-place
        self.dll.PH_GetLibraryVersion.argtypes = [ct.c_char_p]
        self.dll.PH_GetLibraryVersion.restype = c_int

        self.dll.PH_OpenDevice.argtypes = [c_int, ct.c_char_p]
        self.dll.PH_OpenDevice.restype = c_int

        self.dll.PH_CloseDevice.argtypes = [c_int]
        self.dll.PH_CloseDevice.restype = None

        self.dll.PH_GetErrorString.argtypes = [ct.c_char_p, c_int]
        self.dll.PH_GetErrorString.restype = None

        self.dll.PH_Initialize.argtypes = [c_int, c_int]
        self.dll.PH_Initialize.restype = c_int

        self.dll.PH_GetHardwareInfo.argtypes = [c_int, ct.c_char_p, ct.c_char_p, ct.c_char_p]
        self.dll.PH_GetHardwareInfo.restype = c_int

        self.dll.PH_Calibrate.argtypes = [c_int]
        self.dll.PH_Calibrate.restype = c_int

        self.dll.PH_SetSyncDiv.argtypes = [c_int, c_int]
        self.dll.PH_SetSyncDiv.restype = c_int

        self.dll.PH_SetInputCFD.argtypes = [c_int, c_int, c_int, c_int]
        self.dll.PH_SetInputCFD.restype = c_int

        self.dll.PH_SetBinning.argtypes = [c_int, c_int]
        self.dll.PH_SetBinning.restype = c_int

        self.dll.PH_SetOffset.argtypes = [c_int, c_int]
        self.dll.PH_SetOffset.restype = c_int

        self.dll.PH_GetResolution.argtypes = [c_int, ct.POINTER(c_double)]
        self.dll.PH_GetResolution.restype = c_int

        self.dll.PH_GetCountRate.argtypes = [c_int, c_int, ct.POINTER(c_int)]
        self.dll.PH_GetCountRate.restype = c_int

        self.dll.PH_SetStopOverflow.argtypes = [c_int, c_int, c_int]
        self.dll.PH_SetStopOverflow.restype = c_int

        self.dll.PH_ClearHistMem.argtypes = [c_int, c_int]
        self.dll.PH_ClearHistMem.restype = c_int

        self.dll.PH_StartMeas.argtypes = [c_int, c_int]
        self.dll.PH_StartMeas.restype = c_int

        self.dll.PH_CTCStatus.argtypes = [c_int, ct.POINTER(c_int)]
        self.dll.PH_CTCStatus.restype = c_int

        self.dll.PH_StopMeas.argtypes = [c_int]
        self.dll.PH_StopMeas.restype = c_int

        self.dll.PH_GetHistogram.argtypes = [c_int, ct.POINTER(c_uint), c_int]
        self.dll.PH_GetHistogram.restype = c_int

        self.dll.PH_GetFlags.argtypes = [c_int, ct.POINTER(c_int)]
        self.dll.PH_GetFlags.restype = c_int

        # device state
        self.dev_indices = []
        self.connected = False

        # Buffers
        self.libVersion = ct.create_string_buffer(8)
        self.hwSerial  = ct.create_string_buffer(8)
        self.hwPartno  = ct.create_string_buffer(8)
        self.hwVersion = ct.create_string_buffer(8)
        self.hwModel   = ct.create_string_buffer(16)
        self.errorString = ct.create_string_buffer(40)

        # DLL Version
        self.tryfunc(self.dll.PH_GetLibraryVersion(self.libVersion), "GetLibraryVersion")
        print(f"[DLL] Library version: {self.libVersion.value.decode(errors='ignore')}")

    def tryfunc(self, retcode, func_name):
        """ Check return code from DLL function call."""
        if retcode < 0:
            self.dll.PH_GetErrorString(self.errorString, ct.c_int(retcode))
            # decode with utf-8, replace errors with �
            msg = self.errorString.value.decode("utf-8", errors="replace")

            raise RuntimeError(f"[{func_name}] Error {retcode}: {msg}")

    # ---------- device management ----------
    def connect(self):
        """ Scan and connect to available PicoHarp devices.
        :returns: True if at least one device connected, False otherwise"""
        print("[Connect] Scanning for PicoHarp devices...")
        # prevent duplicate connections
        if self.connected:
            print("[Connect] Already connected. Skipping scan.")
            return True
        # for each possible device index, try to open
        for i in range(self.MAXDEVNUM):
            retcode = self.dll.PH_OpenDevice(ct.c_int(i), self.hwSerial)
            # successful connection at index i
            if retcode == 0:
                serial = self.hwSerial.value.decode(errors='ignore')
                print(f"[Connect] Device {i} connected: S/N {serial}")
                self.dev_indices.append(i)
            # no device at index i
            elif retcode == -1:
                print(f"[Connect] Device {i}: no device")
            # error handling for other return codes
            else:
                self.dll.PH_GetErrorString(self.errorString, ct.c_int(retcode))
                print(f"[Connect] Device {i} error: {self.errorString.value.decode(errors='ignore')}")
        # no devices found after scan loop
        if not self.dev_indices:
            print("[Connect] No available devices.")
            return False
        # connect to the first device by default
        print(f"[Connect] Using device #{self.dev_indices[0]}")
        self.connected = True
        return True

    def disconnect(self):
        """ Close all connected devices with for loop scanning."""
        print("[Disconnect] Closing devices...")
        # close all possible device indices
        for i in range(self.MAXDEVNUM):
            self.dll.PH_CloseDevice(ct.c_int(i))
        # reset state
        self.connected = False
        self.dev_indices.clear()
        print("[Disconnect] Done.")

    # ---------- configuration & info ----------
    def initialize_device(self, index=0):
        """ Initialize the device at given index.
        :param index: device index (default 0)"""


        if not self.connected or index >= len(self.dev_indices):
            print("[Init] No device connected or invalid index.")
            return False
        # connect to device at index
        device_id = self.dev_indices[index]
        print(f"[Init] Initializing device #{device_id}...")

        # call init and get hardware info
        # Note: after Init or SetSyncDiv you must allow 100 ms for valid count rate readings
        self.tryfunc(self.dll.PH_Initialize(ct.c_int(device_id), ct.c_int(self.MODE_HIST)), "Initialize")
        self.tryfunc(self.dll.PH_GetHardwareInfo(ct.c_int(device_id),
                                                 self.hwModel, self.hwPartno, self.hwVersion), "GetHardwareInfo")
        print(f"[Init] Model: {self.hwModel.value.decode(errors='ignore')} | "
              f"PartNo: {self.hwPartno.value.decode(errors='ignore')} | "
              f"Version: {self.hwVersion.value.decode(errors='ignore')}")

        # calibrate the device
        print("[Init] Calibrating...")
        self.tryfunc(self.dll.PH_Calibrate(ct.c_int(device_id)), "Calibrate")
        return True

    def setup_device(self, index=0, binning=0, offset=0,
                     sync_divider=1,
                     cfd_level_0=100, cfd_zc_0=10,
                     cfd_level_1=50,  cfd_zc_1=10):
        """ Set measurement parameters for the device at given index.
        :param index: device index (default 0)
        :param binning: histogram binning (0=4ps)
        :param offset: histogram offset
        :param sync_divider: sync trigger divider
        :param cfd_level_0: CFD level for channel 0
        :param cfd_zc_0: CFD zero-crossing for channel 0
        :param cfd_level_1: CFD level for channel 1
        :param cfd_zc_1: CFD zero-crossing for channel 1
        :returns: True if setup successful, False otherwise"""

        if not self.connected or index >= len(self.dev_indices):
            print("[Setup] No device connected or invalid index.")
            return False

        device_id = self.dev_indices[index]
        print(f"[Setup] Setting parameters for device #{device_id}")
        # sync trigger divider = 1 means all signals
        # Note: after Init or SetSyncDiv you must allow 100 ms for valid count rate readings
        self.tryfunc(self.dll.PH_SetSyncDiv(ct.c_int(device_id), ct.c_int(sync_divider)), "SetSyncDiv")
        # set up channel 0 threshold and zero-crossing
        self.tryfunc(self.dll.PH_SetInputCFD(ct.c_int(device_id), ct.c_int(0),
                                             ct.c_int(cfd_level_0), ct.c_int(cfd_zc_0)), "SetInputCFD CH0")
        # set up channel 1 threshold and zero-crossing
        self.tryfunc(self.dll.PH_SetInputCFD(ct.c_int(device_id), ct.c_int(1),
                                             ct.c_int(cfd_level_1), ct.c_int(cfd_zc_1)), "SetInputCFD CH1")
        # set up histogram scale binning = 0 is 4ps
        self.tryfunc(self.dll.PH_SetBinning(ct.c_int(device_id), ct.c_int(binning)), "SetBinning")
        # set up offset
        self.tryfunc(self.dll.PH_SetOffset(ct.c_int(device_id), ct.c_int(offset)), "SetOffset")

        print("[Setup] Parameter setup complete. Waiting 200 ms before reading rates...")
        # time gap for settings to take effect as in gitHub demo
        time.sleep(0.2)

        return True

    def get_resolution(self, index=0):
        """ Get the time resolution of the device at given index.
        :returns: resolution in picoseconds (ps)"""
        device_id = self.dev_indices[index]
        res = ct.c_double()
        self.tryfunc(self.dll.PH_GetResolution(ct.c_int(device_id), byref(res)), "GetResolution")
        return res.value

    def get_count_rates(self, index=0):
        """ Get the current count rates of the device at given index.
        :returns: (count_rate_ch0, count_rate_ch1) in counts per second (cps)"""
        device_id = self.dev_indices[index]
        cr0 = ct.c_int()
        cr1 = ct.c_int()
        self.tryfunc(self.dll.PH_GetCountRate(ct.c_int(device_id), ct.c_int(0), byref(cr0)), "GetCountRate CH0")
        self.tryfunc(self.dll.PH_GetCountRate(ct.c_int(device_id), ct.c_int(1), byref(cr1)), "GetCountRate CH1")
        return cr0.value, cr1.value

    # ---------- measurement helpers ----------
    def set_stop_overflow(self, index=0, enable=True, limit=65535):
        """ Enable or disable stop on overflow. (prevent histogram distortion)
        :param index: device index (default 0)
        :param enable: True to enable stop on overflow, False to disable
        :param limit: overflow limit (max 65535)
        """
        device_id = self.dev_indices[index]
        self.tryfunc(self.dll.PH_SetStopOverflow(ct.c_int(device_id),
                                                 ct.c_int(1 if enable else 0),
                                                 ct.c_int(limit)), "SetStopOverflow")

    def clear_hist(self, index=0, block=0):
        """ Clear histogram memory before measurement.
        :param index: device index (default 0)
        :param block: histogram block number (default 0)"""
        device_id = self.dev_indices[index]
        self.tryfunc(self.dll.PH_ClearHistMem(ct.c_int(device_id), ct.c_int(block)), "ClearHistMem")

    def start(self, index=0, tacq_ms=1000):
        """ Start measurement for given acquisition time in milliseconds.
        :param index: device index (default 0)
        :param tacq_ms: acquisition time in milliseconds (default 1000 ms)"""
        device_id = self.dev_indices[index]
        self.tryfunc(self.dll.PH_StartMeas(ct.c_int(device_id), ct.c_int(tacq_ms)), "StartMeas")



    def wait_done(self,
                  index=0,
                  tacq_ms=1000,
                  check_interval=0.5,
                  cancel_event=None):
        """
        Wait until measurement is done, with timeout and optional user cancel.


        :param index: device index (default 0)
        :param tacq_ms: measurement time in milliseconds (default 1000 ms)

        :param check_interval: interval between status checks in seconds (default 0.5 s)
        :param cancel_event: threading.Event object to signal user cancel (default None)
        """
        device_id = self.dev_indices[index]
        # status flag
        ctc = ct.c_int(0)
        # timeout calculation: measurement + guard
        timeout_ms = tacq_ms * 2
       # maximum loops for checking status
        max_loops = max(1, int(timeout_ms / (check_interval * 1000.0)))
        # Check picoharp measurement status
        try:
            for _ in range(max_loops):
                self.tryfunc(self.dll.PH_CTCStatus(ct.c_int(device_id), byref(ctc)), "CTCStatus")
                # CTCStatus return 0 = busy, > 0 = done, < 0 error
                if ctc.value != 0:
                    return True

                # user cancel control
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("[CTCStatus] Measurement canceled by user")
                # wait before next check
                time.sleep(check_interval)

            # measurement timeout
            raise RuntimeError(f"[CTCStatus] Timeout after {timeout_ms} ms")

        except Exception as e:
            print(f"[wait_done] Error: {e}")
            raise

    def stop(self, index=0):
        """ Stop measurement.
        :param index: device index (default 0)"""
        device_id = self.dev_indices[index]
        self.tryfunc(self.dll.PH_StopMeas(ct.c_int(device_id)), "StopMeas")

    def read_histogram(self, index=0, block=0):
        """read the measurement histogram from picoharp.
        :param index: device index (default 0)
        :param block: histogram block number (default 0)

        :returns: counts as list, overflow flag 0 as false 1 as true"""
        device_id = self.dev_indices[index]
        # create an unsigned integer array for picoharp as histogram buffer with length of HISTCHAN
        counts = (ct.c_uint * self.HISTCHAN)()
        # call DLL for retrieving the jistogram data into counts and the buffer block in picoharp is block 0
        self.tryfunc(self.dll.PH_GetHistogram(ct.c_int(device_id), counts, ct.c_int(block)), "GetHistogram")
        # flag for overflow detection
        flags = ct.c_int()
        # Check if any histogram bin is overflow
        self.tryfunc(self.dll.PH_GetFlags(ct.c_int(device_id), byref(flags)), "GetFlags")
        # Overflow flag
        overflow = (flags.value & self.FLAG_OVERFLOW) > 0
        # Cast the c-type counts array to list
        return list(counts), overflow

    def measure_histogram(self, index=0, tacq_ms=1000, block=0,
                          stop_on_overflow=True, overflow_limit=65535,
                          cancel_event=None):
        """
        measure histogram for given acquisition time in milliseconds.
        :param index: device index (default 0)
        :param tacq_ms: acquisition time in milliseconds (default 1000 ms)
        :param block: histogram block number (default 0)
        :param stop_on_overflow: whether to stop measurement on overflow (default True)
        :param overflow_limit: overflow limit (max 65535, default 65535)
        :param cancel_event: threading.Event object to signal user cancel (default None)

        :returns: dict with keys 'device_id', 'resolution_ps', 'count_rate_ch0', 'count_rate_ch1', 'tacq_ms',
                    'overflow', 'total_counts', 'counts' (list of length 65536)
        """
        device_id = self.dev_indices[index]

        # 1) overflow control
        self.set_stop_overflow(index, enable=stop_on_overflow, limit=overflow_limit)

        # 2) read resolution and count rates
        resolution_ps = self.get_resolution(index)
        cr0, cr1 = self.get_count_rates(index)

        # 3) clear histogram and start
        self.clear_hist(index, block=block)
        self.start(index, tacq_ms)

        ok = False
        # try final block to ensure stop() is called in any case (wait_done may raise)
        try:
            # 4) wait until done / timeout / overflow / cancel
            self.wait_done(index=index, tacq_ms=tacq_ms, cancel_event=cancel_event)
            ok = True
        finally:
            # 5) stop measurement in any case to ensure clean state
            try:
                self.stop(index)
            except Exception as stop_err:
                # print error
                print(f"[measure_histogram] stop() failed: {stop_err}")

        # 6) read histogram data only if measurement was successful
        counts, overflow = self.read_histogram(index, block=block)
        total = sum(counts)

        return {
            "device_id": device_id,
            "resolution_ps": resolution_ps,
            "count_rate_ch0": cr0,
            "count_rate_ch1": cr1,
            "tacq_ms": tacq_ms,
            "overflow": overflow,  # True or False
            "total_counts": total,
            "counts": counts,  # length 65536 list
        }

