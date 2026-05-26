import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Pickle compatibility shim ──────────────────────────────────────────────
# sklearn stores _loss as a C-extension; pickle may try to import it as
# top-level '_loss'. This alias fixes that across sklearn versions.
try:
    import sklearn._loss._loss as _loss_ext
    sys.modules.setdefault('_loss', _loss_ext)
except Exception:
    pass
try:
    import sklearn._loss.loss as _loss_loss
    sys.modules.setdefault('sklearn._loss.loss', _loss_loss)
except Exception:
    pass
"""
BugPredictor — Unified inference class (v2)
Uses: best_defect_model (Ensemble, AUC ~90%) + bug_type_model (RF, Acc 99%)
Accepts: dict of metrics  OR  source code file path  OR  ZIP path
"""

import numpy as np
import pandas as pd
import joblib, json, os, random
from pathlib import Path

MODEL_DIR = os.path.join(os.path.dirname(__file__), "saved_models")

# ─── Templates ───────────────────────────────────────────────────────────────
REASON_TEMPLATES = {
    "Crash": [
        "High coupling (CBO={cbo}) with {rfc} method calls increases null-reference risk.",
        "Excessive dependencies (CBO={cbo}) suggest missing null-guard checks.",
        "Deep call chain (RFC={rfc}) with high coupling causes NullPointerException or ArrayIndexOutOfBounds.",
    ],
    "Logical": [
        "Cyclomatic complexity (max_cc={max_cc}) indicates complex branching — wrong condition likely introduced.",
        "Low cohesion (LCOM={lcom}) with {wmc} weighted methods causes scattered logic and incorrect results.",
        "High avg complexity ({avg_cc} per method) across {wmc} methods makes edge-case handling error-prone.",
    ],
    "Performance": [
        "Large class (LOC={loc}) with deep inheritance (DIT={dit}) degrades runtime performance.",
        "High NOC={noc} with {loc} lines creates a heavy-weight class prone to slowdowns.",
        "Excessive LOC={loc} and inheritance depth (DIT={dit}) result in performance bottleneck.",
    ],
    "UI": [
        "Small UI component (LOC={loc}) with CBO={cbo} dependencies has rendering inconsistency.",
        "Low-complexity view class may have CSS/layout misalignment due to incomplete state handling.",
        "UI component with RFC={rfc} calls shows potential display issue under specific user interaction.",
    ],
}

FIX_TEMPLATES = {
    "Crash": [
        "Add null-checks before every object access. Reduce CBO={cbo} via Dependency Injection or facade pattern.",
        "Validate all method parameters. Break the class (CBO={cbo}) into smaller, loosely coupled units.",
        "Wrap high-risk method chains in try-catch. Reduce RFC={rfc} by extracting helper utilities.",
    ],
    "Logical": [
        "Refactor methods with CC > {max_cc} into smaller single-responsibility functions. Add unit tests per branch.",
        "Group related methods to increase cohesion. Review all conditional paths in the {wmc} weighted methods.",
        "Simplify avg_cc={avg_cc} by extracting strategy patterns. Add boundary-value test cases.",
    ],
    "Performance": [
        "Extract sub-classes from large class (LOC={loc}). Prefer composition over deep inheritance (DIT={dit}).",
        "Profile to find hot-spots. Consider caching or lazy-loading to reduce runtime overhead.",
        "Reduce DIT={dit} by flattening hierarchy. Split large class (LOC={loc}) using Single Responsibility.",
    ],
    "UI": [
        "Review CSS flex/grid properties. Test on multiple screen sizes and browser viewports.",
        "Add explicit state handling for all UI interactions. Check alignment and spacing in the component tree.",
        "Validate rendering with mock data covering empty, error, and loaded states.",
    ],
}

RESPONSIBILITY = {"Crash": "Developer", "Logical": "Developer",
                  "Performance": "Analyst", "UI": "QA"}

BASE_FEATURES = [
    'wmc', 'dit', 'noc', 'cbo', 'rfc', 'lcom',
    'ca', 'ce', 'npm', 'lcom3', 'loc', 'dam',
    'moa', 'mfa', 'cam', 'ic', 'cbm', 'amc',
    'max_cc', 'avg_cc'
]
TYPE_FEATURES = ['wmc', 'dit', 'noc', 'cbo', 'rfc', 'lcom',
                 'loc', 'max_cc', 'avg_cc', 'npm']


# ─── Feature engineering (must match step5) ──────────────────────────────────
def _engineer(m: dict) -> np.ndarray:
    df = pd.DataFrame([m])
    for col in BASE_FEATURES:
        if col not in df:
            df[col] = 0
    df['rfc_per_method']    = df['rfc']    / (df['wmc'] + 1)
    df['loc_per_method']    = df['loc']    / (df['wmc'] + 1)
    df['cc_per_method']     = df['max_cc'] / (df['wmc'] + 1)
    df['coupling_density']  = df['cbo']    / (df['loc'] + 1) * 100
    df['cohesion_deficit']  = df['lcom']   / (df['wmc'] * df['loc'] + 1)
    df['inheritance_depth'] = df['dit']    * df['noc']
    df['wmc_x_cbo']   = df['wmc']  * df['cbo']
    df['loc_x_lcom']  = df['loc']  * df['lcom']
    df['rfc_x_lcom']  = df['rfc']  * df['lcom']
    df['dit_x_wmc']   = df['dit']  * df['wmc']
    df['cc_x_wmc']    = df['max_cc'] * df['wmc']
    import numpy as np
    for col in ['loc', 'rfc', 'lcom', 'wmc']:
        df[f'log_{col}'] = np.log1p(df[col])
    return df


class BugPredictor:
    def __init__(self, model_dir: str = MODEL_DIR):
        self.model_dir = model_dir
        self._load_models()

    def _load_models(self):
        def _p(n): return os.path.join(self.model_dir, n)

        # Prefer improved ensemble model; fall back to step-2 model
        if os.path.exists(_p('best_defect_model.pkl')):
            self.defect_model  = joblib.load(_p('best_defect_model.pkl'))
            self.defect_scaler = joblib.load(_p('best_scaler.pkl'))
            self._use_eng      = True
            print("OK BugPredictor — using IMPROVED ensemble model")
        else:
            self.defect_model  = joblib.load(_p('ck_defect_model.pkl'))
            self.defect_scaler = joblib.load(_p('ck_scaler.pkl'))
            self._use_eng      = False
            print("OK BugPredictor — using base XGBoost model")

        self.type_model   = joblib.load(_p('bug_type_model.pkl'))
        self.type_encoder = joblib.load(_p('bug_type_encoder.pkl'))

        with open(_p('model_info.json'))     as f: info = json.load(f)
        with open(_p('severity_rules.json')) as f: sev  = json.load(f)

        self.severity_rules = {tuple(k.split('|')): v for k, v in sev.items()}

        # Threshold (improved model stores it; else use 0.5)
        bm = info.get('best_defect_model', {})
        self.threshold      = bm.get('threshold', 0.5)
        self._all_features  = bm.get('features', BASE_FEATURES)
        print(f"   Threshold   : {self.threshold}")
        print(f"   Features    : {len(self._all_features)}")

    # ── core helpers ──────────────────────────────────────────────────────────
    def _defect_prob(self, metrics: dict) -> float:
        if self._use_eng:
            df  = _engineer(metrics)
            cols = [c for c in self._all_features if c in df.columns]
            X   = df[cols].values
        else:
            X = np.array([[metrics.get(f, 0) for f in BASE_FEATURES]])
        X_sc = self.defect_scaler.transform(X)
        return float(self.defect_model.predict_proba(X_sc)[0][1])

    def _bug_type(self, metrics: dict):
        X   = np.array([[metrics.get(f, 0) for f in TYPE_FEATURES]])
        enc = self.type_model.predict(X)[0]
        proba = float(self.type_model.predict_proba(X)[0].max())
        return self.type_encoder.inverse_transform([enc])[0], proba

    def _severity(self, bug_type: str, prob: float) -> str:
        level = 'high' if prob >= 0.72 else ('medium' if prob >= 0.50 else 'low')
        return self.severity_rules.get((bug_type, level), 'Medium')

    def _line_est(self, metrics: dict, prob: float, seed: int) -> int:
        loc = max(int(metrics.get('loc', 100)), 10)
        line = int(loc * prob * random.Random(seed).uniform(0.1, 0.85))
        return max(1, min(line, loc))

    def _text(self, tpl: dict, bug_type: str, metrics: dict, seed: int) -> str:
        tmpl = random.Random(seed).choice(tpl[bug_type])
        safe = {k: round(v, 1) if isinstance(v, float) else v for k, v in metrics.items()}
        try:
            return tmpl.format(**safe)
        except KeyError:
            return tmpl

    # ── public: predict from metrics dict ─────────────────────────────────────
    def predict(self, metrics: dict, file_name: str = "Unknown.java",
                bug_id: int = 1) -> dict | None:
        """
        Input : CK metrics dict
        Output: bug report row dict, or None if file is clean
        """
        prob = self._defect_prob(metrics)
        if prob < self.threshold:
            return None

        bug_type, type_conf = self._bug_type(metrics)
        severity = self._severity(bug_type, prob)
        line_num = self._line_est(metrics, prob, seed=bug_id)
        reason   = self._text(REASON_TEMPLATES, bug_type, metrics, seed=bug_id)
        fix      = self._text(FIX_TEMPLATES,    bug_type, metrics, seed=bug_id + 100)

        return {
            "bug_id"            : f"BUG-{str(bug_id).zfill(3)}",
            "type"              : bug_type,
            "severity"          : severity,
            "file"              : file_name,
            "line_number"       : line_num,
            "description"       : f"{bug_type} bug detected with {prob*100:.1f}% confidence",
            "ai_reason"         : reason,
            "suggested_fix"     : fix,
            "assigned_to"       : RESPONSIBILITY[bug_type],
            "status"            : "Open",
            "defect_probability": round(prob, 4),
            "type_confidence"   : round(type_conf, 4),
        }

    # ── public: analyze a source code file ────────────────────────────────────
    def analyze_file(self, file_path: str, bug_id_start: int = 1) -> list:
        """
        Input : path to a .java/.py/.js/.log/.txt file
        Output: list of bug report dicts
        """
        from code_metric_extractor import extract_metrics_from_file, EXCEPTION_BUG_MAP

        info     = extract_metrics_from_file(file_path)
        fname    = Path(file_path).name
        results  = []
        bug_id   = bug_id_start

        if info['is_log']:
            # Log file — return exception-based bugs directly
            for bug in info['log_bugs']:
                results.append({
                    "bug_id"            : f"BUG-{str(bug_id).zfill(3)}",
                    "type"              : bug['bug_type'],
                    "severity"          : bug['severity'],
                    "file"              : fname,
                    "line_number"       : bug['line_number'],
                    "description"       : f"{bug['exception']} detected in log",
                    "ai_reason"         : f"Exception '{bug['exception']}' found: {bug['raw_line']}",
                    "suggested_fix"     : f"Investigate and handle {bug['exception']} at line {bug['line_number']}",
                    "assigned_to"       : RESPONSIBILITY.get(bug['bug_type'], 'Developer'),
                    "status"            : "Open",
                    "defect_probability": 0.95,
                    "type_confidence"   : 1.0,
                })
                bug_id += 1
        else:
            # Source code — run ML models
            result = self.predict(info['metrics'], fname, bug_id)
            if result:
                results.append(result)

        return results

    # ── public: analyze a ZIP file ────────────────────────────────────────────
    def analyze_zip(self, zip_path: str) -> list:
        """
        Input : path to uploaded .zip file
        Output: list of all bug report dicts found in all files
        """
        from code_metric_extractor import extract_metrics_from_zip

        file_records = extract_metrics_from_zip(zip_path)
        all_bugs     = []
        bug_id       = 1

        for rec in file_records:
            fname = rec['file']

            if rec['is_log']:
                for bug in rec['log_bugs']:
                    all_bugs.append({
                        "bug_id"            : f"BUG-{str(bug_id).zfill(3)}",
                        "type"              : bug['bug_type'],
                        "severity"          : bug['severity'],
                        "file"              : fname,
                        "line_number"       : bug['line_number'],
                        "description"       : f"{bug['exception']} in {fname}",
                        "ai_reason"         : bug['raw_line'],
                        "suggested_fix"     : f"Handle {bug['exception']} properly",
                        "assigned_to"       : RESPONSIBILITY.get(bug['bug_type'], 'Developer'),
                        "status"            : "Open",
                        "defect_probability": 0.95,
                        "type_confidence"   : 1.0,
                    })
                    bug_id += 1
            else:
                result = self.predict(rec['metrics'], fname, bug_id)
                if result:
                    all_bugs.append(result)
                    bug_id += 1

        return all_bugs
