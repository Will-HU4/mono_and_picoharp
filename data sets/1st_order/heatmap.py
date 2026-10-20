import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# 1. Gather all CSV files and sort them by integer motor step value
csv_files = glob.glob("*.csv")
# Filter and sort files that are named numerically (e.g., 310000.csv)
steps = sorted([int(os.path.splitext(f)[0]) for f in csv_files if os.path.splitext(f)[0].isdigit()])

# 2. Extract common wavelength values from the first file
first_df = pd.read_csv(f"{steps[0]}.csv")
wavelengths = first_df['Wavelength (nm)'].values

# 3. Stack intensity arrays into a 2D matrix (Rows = Motor Steps, Columns = Wavelengths)
intensity_matrix = []
for step in steps:
    df = pd.read_csv(f"{step}.csv")
    intensity_matrix.append(df['Intensity'].values)

intensity_matrix = np.array(intensity_matrix)

# 4. Construct DataFrame for Heatmap
df_heatmap = pd.DataFrame(
    intensity_matrix, 
    index=steps, 
    columns=np.round(wavelengths, 1)
)

# 5. Plot Heatmap
plt.figure(figsize=(12, 6))
sns.heatmap(
    df_heatmap, 
    cmap='viridis', 
    cbar_kws={'label': 'Intensity (a.u.)'}
)

plt.title('Monochromator Calibration Heatmap')
plt.xlabel('Wavelength (nm)')
plt.ylabel('Motor Steps')
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

plt.figure(figsize=(12, 7))

# Plot each step's spectrum offset vertically
offset_step = 2000  # Adjust offset height as needed
for i, step in enumerate(steps):
    plt.plot(wavelengths, intensity_matrix[i] + i * offset_step, label=f'Step {step}')

plt.title('Stacked Spectral Waterfall Plot')
plt.xlabel('Wavelength (nm)')
plt.ylabel('Intensity + Offset')
plt.grid(True, linestyle='--', alpha=0.5)
plt.tight_layout()
plt.show()

# Find the wavelength corresponding to maximum intensity per step
peak_wavelengths = [wavelengths[np.argmax(row)] for row in intensity_matrix]

plt.figure(figsize=(12, 6))
plt.imshow(
    intensity_matrix,
    aspect='auto',
    origin='lower',
    extent=[wavelengths.min(), wavelengths.max(), steps[0], steps[-1]],
    cmap='magma'
)

# Overlay the peak track line
plt.plot(peak_wavelengths, steps, 'cyan', linestyle='--', marker='o', label='Tracked Peak Position')

plt.colorbar(label='Intensity')
plt.title('Calibration Matrix with Peak Path')
plt.xlabel('Wavelength (nm)')
plt.ylabel('Motor Steps')
plt.legend()
plt.tight_layout()
plt.show()

import matplotlib.pyplot as plt
from matplotlib.colors import PowerNorm

plt.figure(figsize=(12, 6))
plt.imshow(
    intensity_matrix,
    aspect='auto',
    origin='lower',
    extent=[wavelengths.min(), wavelengths.max(), steps[0], steps[-1]],
    cmap='inferno',               # 'inferno' or 'turbo' provide high peak contrast
    norm=PowerNorm(gamma=0.3)     # Suppresses noise floor & pops signal peaks
)

plt.colorbar(label='Intensity (Power Scaled)')
plt.title('Monochromator Step vs. Wavelength (Power Scaled)')
plt.xlabel('Wavelength (nm)')
plt.ylabel('Motor Steps')
plt.tight_layout()
plt.show()