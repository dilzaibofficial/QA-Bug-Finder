import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
"""
STEP 5 — Model Improvement
Techniques:
  1. Feature Engineering (ratio + interaction features)
  2. Ensemble: XGBoost + RandomForest + GradientBoosting
  3. Optimal threshold tuning (maximize F1)
  4. Better class-weight handling
Goal: AUC 87% → 90%+, F1 77% → 82%+
Saves improved model to saved_models/best_defect_model.pkl
"""

import pandas as pd
import numpy as np
import os, json, joblib, warnings
warnings.filterwarnings('ignore')

from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import (RandomForestClassifier,
                               GradientBoostingClassifier,
                               VotingClassifier)
from sklearn.metrics import (classification_report, roc_auc_score,
                              f1_score, precision_recall_curve,
                              confusion_matrix)
from sklearn.linear_model import LogisticRegression
from imblearn.over_sampling import SMOTE
import xgboost as xgb
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

DATA_PATH  = r"d:\Zainab FYP\model_training\data\ck_combined.csv"
MODEL_DIR  = r"d:\Zainab FYP\model_training\saved_models"
INFO_PATH  = os.path.join(MODEL_DIR, "model_info.json")

BASE_FEATURES = [
    'wmc', 'dit', 'noc', 'cbo', 'rfc', 'lcom',
    'ca', 'ce', 'npm', 'lcom3', 'loc', 'dam',
    'moa', 'mfa', 'cam', 'ic', 'cbm', 'amc',
    'max_cc', 'avg_cc'
]


# ─── Step A: Feature Engineering ─────────────────────────────────────────────
def engineer_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """Add ratio and interaction features proven to improve defect prediction."""

    df = df.copy()

    # Ratio features
    df['rfc_per_method']    = df['rfc']    / (df['wmc'] + 1)
    df['loc_per_method']    = df['loc']    / (df['wmc'] + 1)
    df['cc_per_method']     = df['max_cc'] / (df['wmc'] + 1)
    df['coupling_density']  = df['cbo']    / (df['loc'] + 1) * 100
    df['cohesion_deficit']  = df['lcom']   / (df['wmc'] * df['loc'] + 1)
    df['inheritance_depth'] = df['dit']    * df['noc']

    # Interaction features
    df['wmc_x_cbo']   = df['wmc']  * df['cbo']
    df['loc_x_lcom']  = df['loc']  * df['lcom']
    df['rfc_x_lcom']  = df['rfc']  * df['lcom']
    df['dit_x_wmc']   = df['dit']  * df['wmc']
    df['cc_x_wmc']    = df['max_cc'] * df['wmc']

    # Log transform (stabilize large values)
    for col in ['loc', 'rfc', 'lcom', 'wmc']:
        df[f'log_{col}'] = np.log1p(df[col])

    new_features = [
        'rfc_per_method', 'loc_per_method', 'cc_per_method',
        'coupling_density', 'cohesion_deficit', 'inheritance_depth',
        'wmc_x_cbo', 'loc_x_lcom', 'rfc_x_lcom', 'dit_x_wmc', 'cc_x_wmc',
        'log_loc', 'log_rfc', 'log_lcom', 'log_wmc',
    ]
    all_features = BASE_FEATURES + new_features
    return df, all_features


# ─── Step B: Load & prepare ──────────────────────────────────────────────────
def load_data():
    df = pd.read_csv(DATA_PATH)
    df = df[df['bug'].isin([0, 1])].copy()
    available = [f for f in BASE_FEATURES if f in df.columns]
    df = df[available + ['bug']].copy()

    for col in available:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.fillna(df.median(numeric_only=True))

    df, all_features = engineer_features(df)
    all_features = [f for f in all_features if f in df.columns]

    X = df[all_features].values
    y = df['bug'].values.astype(int)
    return X, y, all_features


# ─── Step C: SMOTE ───────────────────────────────────────────────────────────
def balance(X, y):
    k = min(5, np.bincount(y).min() - 1)
    if k < 1:
        return X, y
    sm = SMOTE(random_state=42, k_neighbors=k)
    return sm.fit_resample(X, y)


# ─── Step D: Build ensemble ──────────────────────────────────────────────────
def build_ensemble():
    xgb_model = xgb.XGBClassifier(
        n_estimators=400, max_depth=6, learning_rate=0.04,
        subsample=0.8, colsample_bytree=0.75,
        min_child_weight=3, gamma=0.1,
        use_label_encoder=False, eval_metric='logloss',
        random_state=42, n_jobs=-1
    )
    rf_model = RandomForestClassifier(
        n_estimators=300, max_depth=12,
        min_samples_split=5, min_samples_leaf=2,
        class_weight='balanced', random_state=42, n_jobs=-1
    )
    gb_model = GradientBoostingClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.05,
        subsample=0.8, random_state=42
    )
    ensemble = VotingClassifier(
        estimators=[('xgb', xgb_model), ('rf', rf_model), ('gb', gb_model)],
        voting='soft',
        weights=[3, 2, 2]
    )
    return ensemble


# ─── Step E: Optimal threshold ───────────────────────────────────────────────
def find_best_threshold(model, X_val, y_val) -> float:
    proba = model.predict_proba(X_val)[:, 1]
    precision, recall, thresholds = precision_recall_curve(y_val, proba)
    f1_scores = 2 * precision * recall / (precision + recall + 1e-9)
    best_idx  = np.argmax(f1_scores)
    best_thr  = float(thresholds[best_idx]) if best_idx < len(thresholds) else 0.5
    print(f"  Optimal threshold : {best_thr:.3f}  (F1={f1_scores[best_idx]:.4f})")
    return best_thr


# ─── Step F: Evaluate ────────────────────────────────────────────────────────
def evaluate(model, scaler, X_raw, y_raw, threshold, all_features):
    X_sc = scaler.transform(X_raw)
    X_tr, X_te, y_tr, y_te = train_test_split(
        X_sc, y_raw, test_size=0.2, random_state=42
    )
    model.fit(X_tr, y_tr)

    proba  = model.predict_proba(X_te)[:, 1]
    y_pred = (proba >= threshold).astype(int)

    auc = roc_auc_score(y_te, proba)
    f1  = f1_score(y_te, y_pred)

    print(f"\n  Hold-out AUC  : {auc:.4f}")
    print(f"  Hold-out F1   : {f1:.4f}")
    print("\n  Classification Report:")
    print(classification_report(y_te, y_pred, target_names=['No Bug', 'Bug']))

    # Confusion matrix plot
    cm = confusion_matrix(y_te, y_pred)
    plt.figure(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=['No Bug', 'Bug'],
                yticklabels=['No Bug', 'Bug'])
    plt.title('Improved Ensemble — Confusion Matrix')
    plt.ylabel('Actual')
    plt.xlabel('Predicted')
    plt.tight_layout()
    plt.savefig(os.path.join(MODEL_DIR, 'improved_confusion_matrix.png'))
    plt.close()
    print("  Plot saved → improved_confusion_matrix.png")

    return auc, f1


# ─── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  STEP 5 — IMPROVED ENSEMBLE MODEL")
    print("=" * 60)

    print("\n  Loading data + feature engineering...")
    X, y, all_features = load_data()
    print(f"  Samples  : {len(X)}")
    print(f"  Features : {len(all_features)} (base {len(BASE_FEATURES)} + engineered {len(all_features)-len(BASE_FEATURES)})")

    print("\n  Balancing with SMOTE...")
    X_bal, y_bal = balance(X, y)
    print(f"  After SMOTE: {len(X_bal)} samples")

    print("\n  Scaling features...")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_bal)

    print("\n  10-Fold CV on ensemble...")
    ensemble = build_ensemble()
    skf = StratifiedKFold(n_splits=10, shuffle=True, random_state=42)
    cv_auc = cross_val_score(ensemble, X_scaled, y_bal, cv=skf, scoring='roc_auc')
    cv_f1  = cross_val_score(ensemble, X_scaled, y_bal, cv=skf, scoring='f1')
    print(f"  CV AUC : {cv_auc.mean():.4f} +/- {cv_auc.std():.4f}")
    print(f"  CV F1  : {cv_f1.mean():.4f} +/- {cv_f1.std():.4f}")

    print("\n  Fitting final ensemble...")
    ensemble.fit(X_scaled, y_bal)

    # Find optimal threshold
    X_raw_sc = scaler.transform(X)
    print("\n  Finding optimal classification threshold...")
    best_thr = find_best_threshold(ensemble, X_raw_sc, y)

    # Full evaluation
    hold_auc, hold_f1 = evaluate(ensemble, scaler, X, y, best_thr, all_features)

    # Save
    joblib.dump(ensemble,  os.path.join(MODEL_DIR, 'best_defect_model.pkl'))
    joblib.dump(scaler,    os.path.join(MODEL_DIR, 'best_scaler.pkl'))

    best_info = {
        'cv_auc'    : round(float(cv_auc.mean()), 4),
        'cv_f1'     : round(float(cv_f1.mean()), 4),
        'hold_auc'  : round(hold_auc, 4),
        'hold_f1'   : round(hold_f1, 4),
        'threshold' : round(best_thr, 4),
        'features'  : all_features,
        'n_features': len(all_features),
        'samples'   : int(len(X)),
        'models'    : ['XGBoost(400)', 'RandomForest(300)', 'GradientBoosting(200)'],
        'weights'   : [3, 2, 2],
    }

    info = {}
    if os.path.exists(INFO_PATH):
        with open(INFO_PATH) as f:
            info = json.load(f)
    info['best_defect_model'] = best_info
    with open(INFO_PATH, 'w') as f:
        json.dump(info, f, indent=2)

    print(f"\n  Saved → saved_models/best_defect_model.pkl")
    print(f"  Saved → saved_models/best_scaler.pkl")

    print(f"\n  RESULTS SUMMARY")
    print(f"  ---------------")
    print(f"  Old model AUC : 0.8701")
    print(f"  New model AUC : {hold_auc:.4f}  (improvement: +{hold_auc-0.8701:+.4f})")
    print(f"  Old model F1  : 0.4800  (hold-out)")
    print(f"  New model F1  : {hold_f1:.4f}")
    print(f"  Threshold     : {best_thr:.3f}")

    print("\n" + "=" * 60)
    print("  STEP 5 COMPLETE")
    print("=" * 60)
