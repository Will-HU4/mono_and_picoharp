# calib.py
import json, numpy as np, pandas as pd, matplotlib.pyplot as plt
from pathlib import Path
from scipy.optimize import curve_fit
from scipy.stats import pearsonr   # for correlation coefficient

# --------------------------------------------
def load_mono_csv(path):
    """ Load a CSV file containing monochromator data.
    """
    df = pd.read_csv(path)
    num_cols = [c for c in df.columns if c.replace('.', '', 1).isdigit()]
    steps = np.array(num_cols,  dtype=float)
    power = df.iloc[0, df.columns.get_indexer(num_cols)].astype(float).values
    return steps, power

def load_spec_csv(path):
    # skip header, assume two columns: λ, counts
    pairs = []
    with open(path) as f:
        for ln in f:
            tok = ln.strip().split(',')
            if len(tok)==2:
                try: pairs.append([float(tok[0]), float(tok[1])])
                except ValueError: pass
    arr = np.asarray(pairs)
    return arr[:,0], arr[:,1]       # λ, counts

def normalise(v):
    return (v - v.min()) / (v.max() - v.min())

# --------------------------------------------
# Sine Model Definition
# --------------------------------------------
def sine_model(S, C1, C2, C3):
    """ Physics-based sine grating dispersion model """
    return C1 * np.sin(C2 * S + C3)

def find_mapping_sine(step, power, wl_spec, cnt_spec, p0=[1662.46, 1.3634e-6, -0.00465]):
    """
    Finds the best Sine mapping parameters (C1, C2, C3) matching monochromator power
    to the reference spectrometer wavelength spectrum.
    """
    p_norm = normalise(power)
    best = {'C1': None, 'C2': None, 'C3': None, 'r': -np.inf}

    # Define optimization objective function using Pearson correlation over interpolated spectrum
    def loss_func(params):
        c1, c2, c3 = params
        wl_mono = sine_model(step, c1, c2, c3)
        if wl_mono.min() < wl_spec.min() or wl_mono.max() > wl_spec.max():
            return 1e6  # Penalty out of spectrum bounds
        spec_interp = np.interp(wl_mono, wl_spec, cnt_spec)
        r, _ = pearsonr(p_norm, normalise(spec_interp))
        return -r if not np.isnan(r) else 1e6

    # Run optimizer starting from initial guess p0
    from scipy.optimize import minimize
    res = minimize(loss_func, p0, method='Nelder-Mead')
    
    C1_best, C2_best, C3_best = res.x
    wl_mono = sine_model(step, C1_best, C2_best, C3_best)
    spec_interp_norm = normalise(np.interp(wl_mono, wl_spec, cnt_spec))
    r_best, _ = pearsonr(p_norm, spec_interp_norm)

    # Plot the results
    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.plot(wl_mono, p_norm, label="Mono (mapped)")
    ax1.plot(wl_mono, spec_interp_norm, label="USB reference", alpha=0.8)

    ax1.set_title(f"λ = {C1_best:.2f}·sin({C2_best:.4e}·step + {C3_best:.4f})   (Pearson r = {r_best:.3f})")
    ax1.set_xlabel("Wavelength / nm")
    ax1.set_ylabel("Normalised intensity")
    ax1.grid(True)
    ax1.legend()

    # Add secondary x-axis using non-linear transformation
    def nm_to_step(wl):
        return (np.arcsin(wl / C1_best) - C3_best) / C2_best

    def step_to_nm(s):
        return C1_best * np.sin(C2_best * s + C3_best)

    ax2 = ax1.secondary_xaxis('top', functions=(nm_to_step, step_to_nm))
    ax2.set_xlabel("Monochromator step")

    plt.tight_layout()
    png_path = Path("mono_vs_spec_overlay.png")
    plt.savefig(png_path, dpi=300)
    plt.show()

    return C1_best, C2_best, C3_best, r_best

def save_mapping_sine(C1, C2, C3, score, outfile="mapping.json"):
    """ Save Sine model parameters to JSON format compatible with UI loaders.
    """
    meta = {
        "model": "sine",
        "C1": float(C1),
        "C2": float(C2),
        "C3": float(C3),
        "score": float(score)
    }

    Path(outfile).write_text(json.dumps(meta, indent=2))
    print(f"Sine mapping saved → {outfile}")

# --------------------------------------------
if __name__ == "__main__":

    mono_csv = "spectrum_trimmed_step_=11000.csv"
    spec_csv = "Spectrum_700nm_lambda_below.csv"

    step, power = load_mono_csv(mono_csv)
    wl_spec, cnt_spec = load_spec_csv(spec_csv)

    C1, C2, C3, score = find_mapping_sine(step, power, wl_spec, cnt_spec)
    print(f"best Sine params: C1={C1:.4f}, C2={C2:.8e}, C3={C3:.6f}, r={score:.3f}")
    save_mapping_sine(C1, C2, C3, score)