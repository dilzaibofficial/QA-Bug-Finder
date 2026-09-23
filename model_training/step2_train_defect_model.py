import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
"""
STEP 2 — Train Defect Prediction Model
Dataset : ck_combined.csv (CK metrics from dataset.zip)
Model   : XGBoost + SMOTE (handles class imbalance)
Output  : saved_models/ck_defect_model.pkl
          saved_models/ck_scaler.pkl
          saved_models/model_info.json
"""

import pandas as pd
import numpy as np
import os
import json
import joblib
import warnings
warnings.filterwarnings('ignore')

from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (classification_report, roc_auc_score,
                              confusion_matrix, accuracy_score)
from imblearn.over_sampling import SMOTE
import xgboost as xgb
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

# ─── Paths ───────────────────────────────────────────────────────────────────
DATA_PATH   = r"d:\Zainab FYP\model_training\data\ck_combined.csv"
MODEL_DIR   = r"d:\Zainab FYP\model_training\saved_models"
INFO_PATH   = os.path.join(MODEL_DIR, "model_info.json")

CK_FEATURES = [
    'wmc', 'dit', 'noc', 'cbo', 'rfc', 'lcom',
    'ca', 'ce', 'npm', 'lcom3', 'loc', 'dam',
    'moa', 'mfa', 'cam', 'ic', 'cbm', 'amc',
    'max_cc', 'avg_cc'
]


# ─── Load Data ───────────────────────────────────────────────────────────────
def load_data():
    df = pd.read_csv(DATA_PATH)
    available = [f for f in CK_FEATURES if f in df.columns]
    print(f"  Features available : {len(available)}/{len(CK_FEATURES)}")
    print(f"  Total samples      : {len(df)}")
    print(f"  Bug samples        : {int(df['bug'].sum())} ({df['bug'].mean()*100:.1f}%)")
    # Keep only binary labels (0 or 1)
    df = df[df['bug'].isin([0, 1])].copy()
    print(f"  After binary filter: {len(df)} rows")
    X = df[available].values
    y = df['bug'].values.astype(int)
    return X, y, available


# ─── Apply SMOTE ─────────────────────────────────────────────────────────────
def apply_smote(X, y):
    print(f"\n  [SMOTE] Before: {len(X)} samples  ({y.sum()} bugs)")
    min_class_count = min(np.bincount(y))
    k = min(5, min_class_count - 1)
    if k < 1:
        print(f"  [SMOTE] Skipped — minority class too small ({min_class_count} samples)")
        return X, y
    sm = SMOTE(random_state=42, k_neighbors=k)
    X_res, y_res = sm.fit_resample(X, y)
    print(f"  [SMOTE] After : {len(X_res)} samples  ({y_res.sum()} bugs)")
    return X_res, y_res


# ─── Train XGBoost ───────────────────────────────────────────────────────────
def train_model(X, y, features):
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        gamma=0.1,
        use_label_encoder=False,
        eval_metric='logloss',
        random_state=42,
        n_jobs=-1
    )

    # 10-fold cross validation
    print("\n  Running 10-Fold Cross Validation...")
    skf = StratifiedKFold(n_splits=10, shuffle=True, random_state=42)
    cv_auc = cross_val_score(model, X_scaled, y, cv=skf, scoring='roc_auc')
    cv_acc = cross_val_score(model, X_scaled, y, cv=skf, scoring='accuracy')
    cv_f1  = cross_val_score(model, X_scaled, y, cv=skf, scoring='f1')

    print(f"  AUC      : {cv_auc.mean():.4f}  ± {cv_auc.std():.4f}")
    print(f"  Accuracy : {cv_acc.mean():.4f}  ± {cv_acc.std():.4f}")
    print(f"  F1 Score : {cv_f1.mean():.4f}  ± {cv_f1.std():.4f}")

    # Final fit on all data
    model.fit(X_scaled, y)

    # Feature importance
    importance = pd.DataFrame({
        'feature'   : features,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)

    print("\n  Top 10 Important Features:")
    print(importance.head(10).to_string(index=False))

    return model, scaler, {
        'auc'     : round(float(cv_auc.mean()), 4),
        'accuracy': round(float(cv_acc.mean()), 4),
        'f1'      : round(float(cv_f1.mean()), 4),
        'features': features,
        'samples' : int(len(X)),
        'bug_rate': round(float(y.mean()), 4)
    }


# ─── Plot confusion matrix ────────────────────────────────────────────────────
def plot_results(model, scaler, X, y, features):
    X_sc = scaler.transform(X)
    X_tr, X_te, y_tr, y_te = train_test_split(
        X_sc, y, test_size=0.2, random_state=42
    )
    model.fit(X_tr, y_tr)
    y_pred = model.predict(X_te)

    print("\n  Classification Report (hold-out 20%):")
    print(classification_report(y_te, y_pred, target_names=['No Bug', 'Bug']))

    # Confusion matrix
    cm = confusion_matrix(y_te, y_pred)
    plt.figure(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=['No Bug', 'Bug'],
                yticklabels=['No Bug', 'Bug'])
    plt.title('Defect Model — Confusion Matrix')
    plt.ylabel('Actual')
    plt.xlabel('Predicted')
    plt.tight_layout()
    plt.savefig(os.path.join(MODEL_DIR, 'defect_confusion_matrix.png'))
    plt.close()
    print(f"  Plot saved → saved_models/defect_confusion_matrix.png")

    # Feature importance plot
    imp = pd.DataFrame({'feature': features,
                        'importance': model.feature_importances_})\
            .sort_values('importance')
    plt.figure(figsize=(8, 6))
    plt.barh(imp['feature'], imp['importance'], color='steelblue')
    plt.title('XGBoost — Feature Importance')
    plt.xlabel('Importance')
    plt.tight_layout()
    plt.savefig(os.path.join(MODEL_DIR, 'feature_importance.png'))
    plt.close()
    print(f"  Plot saved → saved_models/feature_importance.png")


# ─── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  STEP 2 — DEFECT PREDICTION MODEL")
    print("=" * 60)

    os.makedirs(MODEL_DIR, exist_ok=True)

    # Load
    X_raw, y_raw, features = load_data()

    # SMOTE
    X_bal, y_bal = apply_smote(X_raw, y_raw)

    # Train
    print("\n  Training XGBoost...")
    model, scaler, metrics = train_model(X_bal, y_bal, features)

    # Plots
    plot_results(model, scaler, X_raw, y_raw, features)

    # Save model + scaler
    joblib.dump(model,  os.path.join(MODEL_DIR, 'ck_defect_model.pkl'))
    joblib.dump(scaler, os.path.join(MODEL_DIR, 'ck_scaler.pkl'))
    print(f"\n  Model  saved → saved_models/ck_defect_model.pkl")
    print(f"  Scaler saved → saved_models/ck_scaler.pkl")

    # Save / update model_info.json
    info = {}
    if os.path.exists(INFO_PATH):
        with open(INFO_PATH) as f:
            info = json.load(f)
    info['ck_defect_model'] = metrics
    with open(INFO_PATH, 'w') as f:
        json.dump(info, f, indent=2)

    print(f"\n  model_info.json updated")
    print(f"\n  Final AUC      : {metrics['auc']}")
    print(f"  Final Accuracy : {metrics['accuracy']}")
    print(f"  Final F1       : {metrics['f1']}")

    print("\n" + "=" * 60)
    print("  STEP 2 COMPLETE")
    print("=" * 60)
