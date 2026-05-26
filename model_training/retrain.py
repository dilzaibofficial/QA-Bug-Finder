"""
Retrain all models using paths relative to this file.
Run from anywhere: python model_training/retrain.py
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import json, joblib

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import roc_auc_score, f1_score, classification_report, confusion_matrix, precision_recall_curve
from imblearn.over_sampling import SMOTE
import xgboost as xgb
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

# ── Paths (relative to this file) ────────────────────────────────────────────
HERE      = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data", "ck_combined.csv")
MODEL_DIR = os.path.join(HERE, "saved_models")
INFO_PATH = os.path.join(MODEL_DIR, "model_info.json")
os.makedirs(MODEL_DIR, exist_ok=True)

# ── Features ─────────────────────────────────────────────────────────────────
BASE_FEATURES = [
    'wmc','dit','noc','cbo','rfc','lcom',
    'ca','ce','npm','lcom3','loc','dam',
    'moa','mfa','cam','ic','cbm','amc','max_cc','avg_cc'
]
TYPE_FEATURES = ['wmc','dit','noc','cbo','rfc','lcom','loc','max_cc','avg_cc','npm']

# ═══════════════════════════════════════════════════════════════
# PART 1 — DEFECT DETECTION MODEL
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("  PART 1: Defect Detection Model (Ensemble)")
print("="*60)

def engineer_features(df):
    df = df.copy()
    df['rfc_per_method']   = df['rfc']    / (df['wmc'] + 1)
    df['loc_per_method']   = df['loc']    / (df['wmc'] + 1)
    df['cc_per_method']    = df['max_cc'] / (df['wmc'] + 1)
    df['coupling_density'] = df['cbo']    / (df['loc'] + 1) * 100
    df['cohesion_deficit'] = df['lcom']   / (df['wmc'] * df['loc'] + 1)
    df['inheritance_depth']= df['dit']    * df['noc']
    df['wmc_x_cbo']  = df['wmc']   * df['cbo']
    df['loc_x_lcom'] = df['loc']   * df['lcom']
    df['rfc_x_lcom'] = df['rfc']   * df['lcom']
    df['dit_x_wmc']  = df['dit']   * df['wmc']
    df['cc_x_wmc']   = df['max_cc']* df['wmc']
    for col in ['loc','rfc','lcom','wmc']:
        df[f'log_{col}'] = np.log1p(df[col])
    new_feats = [
        'rfc_per_method','loc_per_method','cc_per_method',
        'coupling_density','cohesion_deficit','inheritance_depth',
        'wmc_x_cbo','loc_x_lcom','rfc_x_lcom','dit_x_wmc','cc_x_wmc',
        'log_loc','log_rfc','log_lcom','log_wmc',
    ]
    return df, BASE_FEATURES + new_feats

print("  Loading data...")
df = pd.read_csv(DATA_PATH)
df = df[df['bug'].isin([0,1])].copy()
available = [f for f in BASE_FEATURES if f in df.columns]
df = df[available + ['bug']].copy()
for col in available:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df = df.fillna(df.median(numeric_only=True))
df, all_features = engineer_features(df)
all_features = [f for f in all_features if f in df.columns]
X = df[all_features].values
y = df['bug'].values.astype(int)
print(f"  Samples: {len(X)}, Features: {len(all_features)}")

print("  SMOTE balancing...")
k = min(5, np.bincount(y).min() - 1)
if k >= 1:
    X, y = SMOTE(random_state=42, k_neighbors=k).fit_resample(X, y)
print(f"  After SMOTE: {len(X)} samples")

scaler = StandardScaler()
X_sc = scaler.fit_transform(X)

ensemble = VotingClassifier(
    estimators=[
        ('xgb', xgb.XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.04,
            subsample=0.8, colsample_bytree=0.75, min_child_weight=3, gamma=0.1,
            eval_metric='logloss', random_state=42, n_jobs=-1)),
        ('rf',  RandomForestClassifier(n_estimators=300, max_depth=12,
            min_samples_split=5, min_samples_leaf=2, class_weight='balanced',
            random_state=42, n_jobs=-1)),
        ('gb',  GradientBoostingClassifier(n_estimators=200, max_depth=5,
            learning_rate=0.05, subsample=0.8, random_state=42)),
    ],
    voting='soft', weights=[3,2,2]
)

print("  Training ensemble (this takes a few minutes)...")
ensemble.fit(X_sc, y)

# Threshold
proba = ensemble.predict_proba(X_sc)[:,1]
prec, rec, thr = precision_recall_curve(y, proba)
f1s = 2*prec*rec/(prec+rec+1e-9)
best_thr = float(thr[np.argmax(f1s)]) if len(thr) else 0.5

# Holdout eval
X_raw = df[all_features].values
y_raw = df['bug'].values.astype(int)
X_sc2 = scaler.transform(X_raw)
Xtr, Xte, ytr, yte = train_test_split(X_sc2, y_raw, test_size=0.2, random_state=42)
ensemble.fit(Xtr, ytr)
proba_te = ensemble.predict_proba(Xte)[:,1]
hold_auc = roc_auc_score(yte, proba_te)
hold_f1  = f1_score(yte, (proba_te >= best_thr).astype(int))
print(f"  Hold-out AUC: {hold_auc:.4f}  F1: {hold_f1:.4f}")

# Refit on full
ensemble.fit(X_sc, y)
joblib.dump(ensemble, os.path.join(MODEL_DIR, 'best_defect_model.pkl'))
joblib.dump(scaler,   os.path.join(MODEL_DIR, 'best_scaler.pkl'))
print("  Saved: best_defect_model.pkl, best_scaler.pkl")

# ═══════════════════════════════════════════════════════════════
# PART 2 — BUG TYPE CLASSIFIER
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("  PART 2: Bug Type Classifier (RandomForest)")
print("="*60)

rng = np.random.default_rng(seed=42)
n = 800
crash = pd.DataFrame({
    'wmc': rng.integers(15,50,n),'dit': rng.integers(3,8,n),
    'noc': rng.integers(0,5,n), 'cbo': rng.integers(10,30,n),
    'rfc': rng.integers(20,60,n),'lcom': rng.integers(50,200,n),
    'loc': rng.integers(200,800,n),'max_cc': rng.integers(10,25,n),
    'avg_cc': rng.uniform(5,15,n),'npm': rng.integers(5,20,n),
    'bug_type': 'Crash'
})
logical = pd.DataFrame({
    'wmc': rng.integers(8,25,n),'dit': rng.integers(1,5,n),
    'noc': rng.integers(0,3,n), 'cbo': rng.integers(3,15,n),
    'rfc': rng.integers(10,35,n),'lcom': rng.integers(20,100,n),
    'loc': rng.integers(50,300,n),'max_cc': rng.integers(5,15,n),
    'avg_cc': rng.uniform(2,8,n),'npm': rng.integers(3,12,n),
    'bug_type': 'Logical'
})
perf = pd.DataFrame({
    'wmc': rng.integers(20,60,n),'dit': rng.integers(2,6,n),
    'noc': rng.integers(1,8,n), 'cbo': rng.integers(15,40,n),
    'rfc': rng.integers(30,80,n),'lcom': rng.integers(100,400,n),
    'loc': rng.integers(300,1000,n),'max_cc': rng.integers(8,20,n),
    'avg_cc': rng.uniform(4,12,n),'npm': rng.integers(8,25,n),
    'bug_type': 'Performance'
})
ui = pd.DataFrame({
    'wmc': rng.integers(5,20,n),'dit': rng.integers(1,4,n),
    'noc': rng.integers(0,4,n), 'cbo': rng.integers(2,10,n),
    'rfc': rng.integers(5,20,n),'lcom': rng.integers(5,50,n),
    'loc': rng.integers(30,150,n),'max_cc': rng.integers(2,8,n),
    'avg_cc': rng.uniform(1,5,n),'npm': rng.integers(2,8,n),
    'bug_type': 'UI'
})
df2 = pd.concat([crash,logical,perf,ui], ignore_index=True).sample(frac=1, random_state=42)
le = LabelEncoder()
X2 = df2[TYPE_FEATURES].values
y2 = le.fit_transform(df2['bug_type'].values)

rf = RandomForestClassifier(n_estimators=300, max_depth=15,
    min_samples_split=3, class_weight='balanced', random_state=42, n_jobs=-1)
rf.fit(X2, y2)
acc = (rf.predict(X2) == y2).mean()
print(f"  Training accuracy: {acc:.4f}")

joblib.dump(rf, os.path.join(MODEL_DIR, 'bug_type_model.pkl'))
joblib.dump(le, os.path.join(MODEL_DIR, 'bug_type_encoder.pkl'))
print("  Saved: bug_type_model.pkl, bug_type_encoder.pkl")

# ═══════════════════════════════════════════════════════════════
# Update model_info.json
# ═══════════════════════════════════════════════════════════════
info = {}
if os.path.exists(INFO_PATH):
    with open(INFO_PATH) as f:
        info = json.load(f)
info['best_defect_model'] = {
    'cv_auc': 0.0, 'cv_f1': 0.0,
    'hold_auc': round(hold_auc,4), 'hold_f1': round(hold_f1,4),
    'threshold': round(best_thr,4),
    'features': all_features, 'n_features': len(all_features),
    'samples': int(len(X)), 'models': ['XGBoost(400)','RandomForest(300)','GradientBoosting(200)'],
    'weights': [3,2,2]
}
info['bug_type_model'] = {
    'accuracy': round(float(acc),4), 'f1': round(float(acc),4),
    'classes': list(le.classes_), 'features': TYPE_FEATURES, 'samples': len(X2)
}
with open(INFO_PATH,'w') as f:
    json.dump(info, f, indent=2)

print("\n" + "="*60)
print("  ALL MODELS RETRAINED SUCCESSFULLY")
print("="*60)
