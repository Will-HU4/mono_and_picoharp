# calib.py
import json, numpy as np, pandas as pd, matplotlib.pyplot as plt
from pathlib import Path
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
# --------------------------------------------
def normalise(v):
    return (v - v.min()) / (v.max() - v.min())

def find_mapping(step, power, wl_spec, cnt_spec,
                 a_range=(0.05,0.07,0.00025),
                 b_range=(0,200,1)):
    # Find the best linear mapping from monochromator steps to spectrometer wavelengths.
    p_norm = normalise(power)
    best = {'a':None,'b':None,'r':-np.inf}
    a_vals = np.arange(*a_range)    # start, stop, step
    b_vals = np.arange(*b_range)
    # do a grid search over a and b
    for a in a_vals:
        wl = a*step
        for b in b_vals:
            wl_mono = wl + b
            if wl_mono.min()<wl_spec.min() or wl_mono.max()>wl_spec.max():
                continue
            spec_interp = np.interp(wl_mono, wl_spec, cnt_spec)
            r, _ = pearsonr(p_norm, normalise(spec_interp))
            if r > best['r']:
                best.update(a=a,b=b,r=r)

    a_best, b_best = best['a'], best['b']
    wl_mono = a_best * step + b_best
    spec_interp_norm = normalise(np.interp(wl_mono, wl_spec, cnt_spec))
    # Plot the results
    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.plot(wl_mono, p_norm, label="Mono (mapped)")
    ax1.plot(wl_mono, spec_interp_norm, label="USB reference", alpha=0.8)

    ax1.set_title(f"λ = {a_best:.5f}·step + {b_best:.2f}   (Pearson r = {best['r']:.3f})")
    ax1.set_xlabel("Wavelength / nm")
    ax1.set_ylabel("Normalised intensity")
    ax1.grid(True)
    ax1.legend()

    # Add secondary x-axis showing step
    def nm_to_step(wl):
        return (wl - b_best) / a_best

    def step_to_nm(s):
        return a_best * s + b_best

    ax2 = ax1.secondary_xaxis('top', functions=(nm_to_step, step_to_nm))
    ax2.set_xlabel("Monochromator step")

    plt.tight_layout()
    png_path = Path("mono_vs_spec_overlay.png")
    plt.savefig(png_path, dpi=300)
    plt.show()
    return best['a'], best['b'], best['r']

def save_mapping(a, b, score, outfile="mapping.json"):
    """ Save the mapping parameters to a JSON file.
    """
    meta = {
        "a": float(a),
        "b": float(b),
        "score": float(score)
    }

    Path(outfile).write_text(json.dumps(meta, indent=2))
    print(f"mapping saved → {outfile}")
# --------------------------------------------
if __name__ == "__main__":

    mono_csv = "spectrum_trimmed_step_=11000.csv"
    spec_csv = "Spectrum_700nm_lambda_below.csv"

    step, power = load_mono_csv(mono_csv)
    wl_spec, cnt_spec= load_spec_csv(spec_csv)

    a,b,score = find_mapping(step, power, wl_spec, cnt_spec)
    print(f"best  a={a:.5f}, b={b:.1f},  r={score:.3f}")
    save_mapping(a,b,score)
