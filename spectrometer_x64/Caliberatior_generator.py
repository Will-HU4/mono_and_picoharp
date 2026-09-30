import pyvisa
import triax_320
from spectrometer_function import generate_step_to_wavelength_mapping

# 1. Initialize Monochromator
rm = pyvisa.ResourceManager()
mono = triax_320.Triax320(resource_manager=rm)
mono.connect_device()

# 2. Define sequence of motor steps to scan (e.g., 0 to 50,000 steps with 5,000 step size)
scan_steps = list(range(0, 55000, 5000))

# 3. Execute calibration & generate mapping.json
generate_step_to_wavelength_mapping(mono_instance=mono, steps_to_scan=scan_steps)

# 4. Cleanup
mono.close_device()