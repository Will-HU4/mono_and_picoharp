import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

# ---------------------------------------------------------
# 1. SET DATA DIRECTORY & EXTRACT PEAKS
# ---------------------------------------------------------
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_pattern = os.path.join(script_dir, "*.csv")

steps_m1 = []
wl_m1 = []

csv_files = glob.glob(csv_pattern)
print(f"Found {len(csv_files)} CSV files in: {script_dir}")

for f in sorted(csv_files):
    name, ext = os.path.splitext(os.path.basename(f))
    if name.isdigit():
        s = int(name)
        if 200000 <= s <= 360000:  # Step range filter for m=1 order
            df = pd.read_csv(f)
            max_idx = df['Intensity'].idxmax()
            
            # Local window around peak
            window = df.iloc[max(0, max_idx - 5):min(len(df), max_idx + 6)]
            w = window['Wavelength (nm)'].values
            I = window['Intensity'].values - window['Intensity'].min()
            
            # Sub-pixel center via weighted centroid
            peak_subpixel = np.sum(w * I) / np.sum(I) if np.sum(I) > 0 else df.loc[max_idx, 'Wavelength (nm)']
            steps_m1.append(s)
            wl_m1.append(peak_subpixel)

steps_m1 = np.array(steps_m1)
wl_m1 = np.array(wl_m1)

if len(steps_m1) == 0:
    raise ValueError(f"No matching CSV files (steps >= 310000) found in {script_dir}.")

# ---------------------------------------------------------
# 2. FIT MODELS & GENERATE FUNCTION STRINGS
# ---------------------------------------------------------
# Fit 1: Linear Model
slope_lin, intercept_lin = np.polyfit(steps_m1, wl_m1, 1)
pred_lin = slope_lin * steps_m1 + intercept_lin
res_lin = wl_m1 - pred_lin
r2_lin = 1 - (np.sum(res_lin**2) / np.sum((wl_m1 - np.mean(wl_m1))**2))
func_lin_str = f"λ(S) = {slope_lin:.8e}·S + {intercept_lin:.4f}"

# Fit 2: Quadratic Model
a, b, c = np.polyfit(steps_m1, wl_m1, 2)
pred_quad = a * steps_m1**2 + b * steps_m1 + c
res_quad = wl_m1 - pred_quad
r2_quad = 1 - (np.sum(res_quad**2) / np.sum((wl_m1 - np.mean(wl_m1))**2))
func_quad_str = f"λ(S) = {a:.4e}·S² + {b:.4e}·S + {c:.4f}"

# Fit 3: Physics Sine Model [λ = C1 * sin(C2 * S + C3)]
def grating_model(S, C1, C2, C3):
    return C1 * np.sin(C2 * S + C3)

p0 = [1200.0, 2e-6, 0.1]
popt_sine, _ = curve_fit(grating_model, steps_m1, wl_m1, p0=p0, maxfev=10000)
C1, C2, C3 = popt_sine
pred_sine = grating_model(steps_m1, *popt_sine)
res_sine = wl_m1 - pred_sine
r2_sine = 1 - (np.sum(res_sine**2) / np.sum((wl_m1 - np.mean(wl_m1))**2))
func_sine_str = f"λ(S) = {C1:.2f} · sin({C2:.4e}·S + {C3:.4f})"

# ---------------------------------------------------------
# 3. PRINT FITTED FUNCTIONS TO TERMINAL
# ---------------------------------------------------------
print("\n" + "="*70)
print("              FITTED CALIBRATION FUNCTIONS (S = Steps)")
print("="*70)
print(f"1. LINEAR FIT (R² = {r2_lin:.6f}):")
print(f"   {func_lin_str}\n")
print(f"2. QUADRATIC FIT (R² = {r2_quad:.6f}):")
print(f"   {func_quad_str}\n")
print(f"3. PHYSICS SINE FIT (R² = {r2_sine:.6f}):")
print(f"   {func_sine_str}")
print("="*70 + "\n")

# ---------------------------------------------------------
# 4. PLOTTING & SAVING RESULT
# ---------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8.5), sharex=True, gridspec_kw={'height_ratios': [3, 1]})

s_fine = np.linspace(min(steps_m1) - 5000, max(steps_m1) + 5000, 200)

# Upper panel: Fitted curves with function formulas in legend
ax1.plot(steps_m1, wl_m1, 'ko', label='Extracted Sub-pixel Peak Center', markersize=7)
ax1.plot(s_fine, slope_lin * s_fine + intercept_lin, 'r--', label=f'Linear: {func_lin_str}')
ax1.plot(s_fine, a * s_fine**2 + b * s_fine + c, 'g-', label=f'Quadratic: {func_quad_str}')
ax1.plot(s_fine, grating_model(s_fine, *popt_sine), 'b:', label=f'Sine Fit: {func_sine_str}', linewidth=2)

ax1.set_ylabel('Peak Wavelength (nm)', fontsize=12)
ax1.set_title('Monochromator Calibration Fits & Function Equations', fontsize=13, fontweight='bold')
ax1.legend(loc='upper left', fontsize=9, framealpha=0.9)
ax1.grid(True, linestyle='--', alpha=0.5)

# Lower panel: Residual errors
ax2.plot(steps_m1, res_lin, 'r--o', label='Linear Residuals')
ax2.plot(steps_m1, res_quad, 'g-s', label='Quadratic Residuals')
ax2.plot(steps_m1, res_sine, 'b:d', label='Sine Residuals')
ax2.axhline(0, color='black', linestyle='-', alpha=0.3)
ax2.set_xlabel('Motor Steps (S)', fontsize=12)
ax2.set_ylabel('Residuals (nm)', fontsize=12)
ax2.legend(loc='upper right', fontsize=9)
ax2.grid(True, linestyle='--', alpha=0.5)

plt.tight_layout()

output_img_path = os.path.join(script_dir, 'all_three_fits_result.png')
plt.savefig(output_img_path, dpi=300)
print(f"Plot saved successfully to: {output_img_path}")
plt.show()