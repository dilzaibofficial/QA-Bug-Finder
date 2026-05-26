# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

"""
STEP 1 - Data Loading & Preparation
Loads:
  - dataset.zip   → 37 CSV files (CK metrics from Apache projects)
  - dataset1.zip  → 13 ARFF files (NASA defect datasets)
Saves cleaned CSVs to: model_training/data/
"""

import pandas as pd
import numpy as np
import os
import glob
from scipy.io import arff
import warnings
warnings.filterwarnings('ignore')

# ─── Paths ───────────────────────────────────────────────────────────────────
CK_FOLDER   = r"d:\Zainab FYP\dataset_extracted\datasets-software defect prediction"
NASA_FOLDER = r"d:\Zainab FYP\dataset1_extracted"
OUT_FOLDER  = r"d:\Zainab FYP\model_training\data"

# CK metric column names in dataset.zip
CK_FEATURES = [
    'wmc', 'dit', 'noc', 'cbo', 'rfc', 'lcom',
    'ca', 'ce', 'npm', 'lcom3', 'loc', 'dam',
    'moa', 'mfa', 'cam', 'ic', 'cbm', 'amc',
    'max_cc', 'avg_cc'
]


# ─── Loader: CK Metrics (dataset.zip) ────────────────────────────────────────
def load_ck_datasets():
    print("\n[CK Metrics] Loading CSV files...")
    all_dfs = []
    csv_files = glob.glob(os.path.join(CK_FOLDER, "*.csv"))

    for path in csv_files:
        try:
            df = pd.read_csv(path)
            df.columns = [c.strip().lower() for c in df.columns]
            df['source_file'] = os.path.basename(path).replace('.csv', '')
            all_dfs.append(df)
            bugs = int(df['bug'].sum()) if 'bug' in df.columns else -1
            print(f"  OK {os.path.basename(path):35s}  rows={len(df):4d}  bugs={bugs}")
        except Exception as e:
            print(f"  ERR {os.path.basename(path)} - {e}")

    combined = pd.concat(all_dfs, ignore_index=True)
    print(f"\n  Total rows    : {len(combined)}")
    print(f"  Bug count     : {int(combined['bug'].sum())}")
    print(f"  Bug rate      : {combined['bug'].mean()*100:.1f}%")
    return combined


# ─── Loader: NASA ARFF (dataset1.zip) ────────────────────────────────────────
def load_nasa_datasets():
    print("\n[NASA Datasets] Loading ARFF files...")
    all_dfs = []
    arff_files = glob.glob(os.path.join(NASA_FOLDER, "*.arff"))

    for path in arff_files:
        try:
            raw, meta = arff.loadarff(path)
            df = pd.DataFrame(raw)

            # Decode byte-string columns
            for col in df.select_dtypes(['object']).columns:
                df[col] = df[col].apply(
                    lambda x: x.decode('utf-8') if isinstance(x, bytes) else x
                )

            df.columns = [c.strip().lower() for c in df.columns]
            df['source_file'] = os.path.basename(path).replace('.arff', '')

            # Normalize target column name → 'bug'
            if 'defects' in df.columns:
                df['bug'] = df['defects'].map(
                    {'true': 1, 'false': 0, 'TRUE': 1, 'FALSE': 0,
                     'yes': 1, 'no': 0}
                ).fillna(0).astype(int)
            elif 'label' in df.columns:
                df['bug'] = pd.to_numeric(df['label'], errors='coerce').fillna(0).astype(int)

            all_dfs.append(df)
            bugs = int(df['bug'].sum()) if 'bug' in df.columns else -1
            print(f"  OK {os.path.basename(path):15s}  rows={len(df):5d}  bugs={bugs}")

        except Exception as e:
            print(f"  ERR {os.path.basename(path)} - {e}")

    combined = pd.concat(all_dfs, ignore_index=True)
    print(f"\n  Total rows    : {len(combined)}")
    print(f"  Bug count     : {int(combined['bug'].sum())}")
    print(f"  Bug rate      : {combined['bug'].mean()*100:.1f}%")
    return combined


# ─── Clean & validate ────────────────────────────────────────────────────────
def clean_dataset(df, features, label='bug'):
    available = [f for f in features if f in df.columns]
    missing   = [f for f in features if f not in df.columns]
    if missing:
        print(f"  [warn] Missing columns (will be skipped): {missing}")

    keep = available + [label, 'source_file']
    df = df[[c for c in keep if c in df.columns]].copy()

    # Convert to numeric
    for col in available:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df[label] = pd.to_numeric(df[label], errors='coerce')
    df = df.dropna(subset=[label])
    df[label] = df[label].astype(int)

    # Fill remaining NaN with column median
    df[available] = df[available].fillna(df[available].median())

    # Clip extreme outliers (3-sigma per column)
    for col in available:
        lo = df[col].mean() - 3 * df[col].std()
        hi = df[col].mean() + 3 * df[col].std()
        df[col] = df[col].clip(lo, hi)

    return df, available


# ─── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  STEP 1 — DATA LOADING")
    print("=" * 60)

    os.makedirs(OUT_FOLDER, exist_ok=True)

    # ── CK datasets ──
    ck_raw = load_ck_datasets()
    ck_clean, ck_used_features = clean_dataset(ck_raw, CK_FEATURES)
    ck_out = os.path.join(OUT_FOLDER, "ck_combined.csv")
    ck_clean.to_csv(ck_out, index=False)
    print(f"\n  Saved → {ck_out}")
    print(f"  Features used: {ck_used_features}")
    print(f"  Final shape  : {ck_clean.shape}")

    # ── NASA datasets ──
    nasa_raw  = load_nasa_datasets()
    # NASA has Halstead + McCabe features; keep all numeric columns
    nasa_numeric = nasa_raw.select_dtypes(include=[np.number]).columns.tolist()
    nasa_feats   = [c for c in nasa_numeric if c != 'bug']
    nasa_clean, nasa_used = clean_dataset(nasa_raw, nasa_feats)
    nasa_out = os.path.join(OUT_FOLDER, "nasa_combined.csv")
    nasa_clean.to_csv(nasa_out, index=False)
    print(f"\n  Saved → {nasa_out}")
    print(f"  Features used ({len(nasa_used)}): {nasa_used}")
    print(f"  Final shape  : {nasa_clean.shape}")

    print("\n" + "=" * 60)
    print("  STEP 1 COMPLETE")
    print("=" * 60)
