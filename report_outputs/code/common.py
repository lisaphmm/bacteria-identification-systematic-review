"""Shared paths and plot style for the report scripts."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TABLES = os.path.join(ROOT, "report_outputs", "tables")
FIGS = os.path.join(ROOT, "report_outputs", "figures")
os.makedirs(TABLES, exist_ok=True)
os.makedirs(FIGS, exist_ok=True)

# Okabe-Ito colour-blind-safe palette, assigned in a fixed order
C = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73", "vermillion": "#D55E00",
     "sky": "#56B4E9", "purple": "#CC79A7", "yellow": "#F0E442", "grey": "#7F7F7F", "black": "#222222"}
INK, MUTED, GRID = "#222222", "#6B6B6B", "#E3E3E3"

def style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
        "xtick.color": INK, "ytick.color": INK, "text.color": INK, "axes.spines.top": False,
        "axes.spines.right": False, "axes.grid": False, "figure.dpi": 150, "savefig.dpi": 300,
        "savefig.bbox": "tight", "figure.facecolor": "white", "axes.facecolor": "white",
    })

def save(fig, name):
    p = os.path.join(FIGS, name)
    fig.savefig(p)
    plt.close(fig)
    print("saved", p)
