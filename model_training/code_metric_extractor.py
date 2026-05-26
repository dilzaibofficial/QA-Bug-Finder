import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
"""
Code Metric Extractor
Reads uploaded source code files and computes CK-style metrics.
Supports: .java  .py  .js  .ts  .cpp  .c  .cs
          .zip (extracts and analyzes all source files inside)
          .log  .txt (error pattern analysis)

Output: dict of CK metrics compatible with trained models
"""

import re
import os
import ast
import zipfile
import math
from pathlib import Path


# ─── Supported source extensions ─────────────────────────────────────────────
SOURCE_EXTS  = {'.java', '.py', '.js', '.ts', '.cpp', '.c', '.cs', '.php', '.rb'}
LOG_EXTS     = {'.log', '.txt'}


# ═══════════════════════════════════════════════════════════════════════════════
#  JAVA metric extractor (regex-based — no Java compiler needed)
# ═══════════════════════════════════════════════════════════════════════════════
def extract_java_metrics(code: str, filename: str = "Unknown.java") -> dict:
    code_no_comments = re.sub(r'//[^\n]*', '', code)
    code_no_comments = re.sub(r'/\*[\s\S]*?\*/', '', code_no_comments)

    lines = [l for l in code_no_comments.split('\n') if l.strip()]
    loc   = len(lines)

    # WMC — method declarations
    method_pat = re.compile(
        r'(public|private|protected|static|final|synchronized|\s)+'
        r'[\w<>\[\]]+\s+(\w+)\s*\([^)]*\)\s*(throws\s+[\w,\s]+)?\s*\{'
    )
    methods = method_pat.findall(code_no_comments)
    wmc = max(1, len(methods))

    # NPM — public methods
    npm = len(re.findall(r'\bpublic\s+[\w<>\[\]]+\s+\w+\s*\(', code_no_comments))

    # DIT — inheritance depth (count extends keyword)
    extends_count = len(re.findall(r'\bextends\b', code))
    dit = extends_count + 1

    # NOC — number of children / implements
    noc = len(re.findall(r'\bimplements\b', code))

    # CBO — coupling (import statements = external dependencies)
    imports = re.findall(r'^\s*import\s+([\w.]+);', code, re.MULTILINE)
    cbo = len(set(imports))

    # CE / CA
    ce = cbo
    ca = max(0, cbo // 3)

    # RFC — unique method calls (methodName followed by '(')
    calls = re.findall(r'\b(\w+)\s*\(', code_no_comments)
    rfc   = len(set(calls))

    # Private fields for LCOM
    fields = re.findall(r'\b(private|protected)\s+[\w<>\[\]]+\s+(\w+)\s*[;=]', code)
    n_fields = len(fields)

    # LCOM — approximation: fields unused across methods → lack of cohesion
    lcom = max(0, (n_fields * wmc) - (n_fields * 2))
    lcom = min(lcom, 300)

    # Cyclomatic complexity — count decision keywords
    decisions = len(re.findall(
        r'\b(if|else\s+if|while|for|do|case|catch|&&|\|\||\?)\b', code_no_comments
    ))
    max_cc = decisions + 1
    avg_cc = round(max(1.0, decisions / wmc), 2)

    # MOA — measure of aggregation (field types that are classes, not primitives)
    primitives = {'int', 'long', 'double', 'float', 'boolean', 'byte', 'char', 'short', 'void'}
    field_types = re.findall(r'\b(?:private|protected|public)\s+([\w<>]+)\s+\w+\s*;', code)
    moa = sum(1 for t in field_types if t not in primitives)

    # DAM — data access metric
    dam = round(npm / max(1, wmc), 3)

    # MFA — measure of functional abstraction
    mfa = round(extends_count / max(1, wmc), 3)

    # CAM — cohesion among methods
    cam = round(npm / max(1, loc) * 10, 3)

    # IC, CBM
    ic  = extends_count
    cbm = max(0, cbo // 4)

    # AMC — average method complexity
    amc = round(loc / wmc, 2)

    # LCOM3
    lcom3 = min(1.0, round(lcom / max(1, wmc * n_fields + 1), 3))

    return {
        'wmc': wmc, 'dit': dit, 'noc': noc, 'cbo': cbo, 'rfc': rfc,
        'lcom': lcom, 'ca': ca, 'ce': ce, 'npm': npm, 'lcom3': lcom3,
        'loc': loc, 'dam': dam, 'moa': moa, 'mfa': mfa, 'cam': cam,
        'ic': ic, 'cbm': cbm, 'amc': amc, 'max_cc': max_cc, 'avg_cc': avg_cc,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  PYTHON metric extractor (uses ast module — very accurate)
# ═══════════════════════════════════════════════════════════════════════════════
def extract_python_metrics(code: str, filename: str = "Unknown.py") -> dict:
    loc = len([l for l in code.split('\n') if l.strip() and not l.strip().startswith('#')])

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return _fallback_metrics(loc, filename)

    # Count classes
    classes    = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    functions  = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    n_classes  = max(1, len(classes))

    wmc = len(functions)
    npm = len([f for f in functions if not f.name.startswith('_')])

    # Imports → CBO
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or '')
    cbo = len(set(imports))
    ce  = cbo
    ca  = max(0, cbo // 3)

    # DIT — count base classes
    bases = sum(len(c.bases) for c in classes)
    dit   = bases + 1
    noc   = max(0, n_classes - 1)

    # RFC — unique function calls
    calls = [n.func.attr if isinstance(n.func, ast.Attribute) else
             (n.func.id if isinstance(n.func, ast.Name) else '')
             for n in ast.walk(tree) if isinstance(n, ast.Call)
             if hasattr(n, 'func')]
    rfc = len(set(c for c in calls if c))

    # Cyclomatic complexity
    decisions = sum(1 for n in ast.walk(tree)
                    if isinstance(n, (ast.If, ast.While, ast.For,
                                      ast.ExceptHandler, ast.With,
                                      ast.BoolOp, ast.comprehension)))
    max_cc = decisions + 1
    avg_cc = round(max(1.0, decisions / max(1, wmc)), 2)

    # Fields / attributes
    assigns = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)]
    n_fields = len(assigns)
    lcom   = max(0, (n_fields * wmc) // 2 - wmc)
    lcom3  = min(1.0, round(lcom / max(1, wmc * max(1, n_fields)), 3))

    dam  = round(npm / max(1, wmc), 3)
    mfa  = round(bases / max(1, wmc), 3)
    cam  = round(npm / max(1, loc) * 10, 3)
    moa  = noc
    ic   = bases
    cbm  = max(0, cbo // 4)
    amc  = round(loc / max(1, wmc), 2)

    return {
        'wmc': wmc, 'dit': dit, 'noc': noc, 'cbo': cbo, 'rfc': rfc,
        'lcom': lcom, 'ca': ca, 'ce': ce, 'npm': npm, 'lcom3': lcom3,
        'loc': loc, 'dam': dam, 'moa': moa, 'mfa': mfa, 'cam': cam,
        'ic': ic, 'cbm': cbm, 'amc': amc, 'max_cc': max_cc, 'avg_cc': avg_cc,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  JavaScript / TypeScript metric extractor (regex-based)
# ═══════════════════════════════════════════════════════════════════════════════
def extract_js_metrics(code: str, filename: str = "Unknown.js") -> dict:
    code_clean = re.sub(r'//[^\n]*', '', code)
    code_clean = re.sub(r'/\*[\s\S]*?\*/', '', code_clean)

    loc = len([l for l in code_clean.split('\n') if l.strip()])

    # Functions: function x() / const x = () => / x: function
    func_pats = [
        r'\bfunction\s+\w+\s*\(',
        r'\bconst\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>',
        r'\blet\s+\w+\s*=\s*function',
        r'^\s*\w+\s*\([^)]*\)\s*\{',
    ]
    wmc = sum(len(re.findall(p, code_clean, re.MULTILINE)) for p in func_pats)
    wmc = max(1, wmc)

    npm = len(re.findall(r'\bexport\b', code_clean))

    imports = re.findall(r"(?:import|require)\s*\(?['\"]([^'\"]+)['\"]", code)
    cbo = len(set(imports))
    ce, ca = cbo, max(0, cbo // 3)

    classes = re.findall(r'\bclass\s+\w+', code)
    extends = re.findall(r'\bextends\s+\w+', code)
    dit = len(extends) + 1
    noc = max(0, len(classes) - 1)

    calls = re.findall(r'\b(\w+)\s*\(', code_clean)
    rfc   = len(set(calls))

    decisions = len(re.findall(
        r'\b(if|else\s+if|while|for|switch|case|catch|&&|\|\||\?)\b', code_clean
    ))
    max_cc = decisions + 1
    avg_cc = round(max(1.0, decisions / wmc), 2)

    lcom  = max(0, (cbo * wmc) // 3)
    lcom3 = min(1.0, round(lcom / max(1, wmc * 10), 3))
    dam   = round(npm / max(1, wmc), 3)
    mfa   = round(len(extends) / max(1, wmc), 3)
    cam   = round(npm / max(1, loc) * 10, 3)
    moa   = noc
    ic, cbm = len(extends), max(0, cbo // 4)
    amc   = round(loc / wmc, 2)

    return {
        'wmc': wmc, 'dit': dit, 'noc': noc, 'cbo': cbo, 'rfc': rfc,
        'lcom': lcom, 'ca': ca, 'ce': ce, 'npm': npm, 'lcom3': lcom3,
        'loc': loc, 'dam': dam, 'moa': moa, 'mfa': mfa, 'cam': cam,
        'ic': ic, 'cbm': cbm, 'amc': amc, 'max_cc': max_cc, 'avg_cc': avg_cc,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  LOG / TXT — error pattern detector
# ═══════════════════════════════════════════════════════════════════════════════
EXCEPTION_BUG_MAP = {
    # Crash patterns
    'NullPointerException'           : ('Crash',       'Critical'),
    'ArrayIndexOutOfBoundsException' : ('Crash',       'Critical'),
    'StackOverflowError'             : ('Crash',       'Critical'),
    'OutOfMemoryError'               : ('Crash',       'Critical'),
    'StringIndexOutOfBoundsException': ('Crash',       'High'),
    'IndexOutOfBoundsException'      : ('Crash',       'High'),
    'ClassCastException'             : ('Crash',       'High'),
    'NoSuchElementException'         : ('Crash',       'High'),
    # Logical patterns
    'AssertionError'                 : ('Logical',     'High'),
    'ArithmeticException'            : ('Logical',     'High'),
    'IllegalArgumentException'       : ('Logical',     'Medium'),
    'IllegalStateException'          : ('Logical',     'Medium'),
    'NumberFormatException'          : ('Logical',     'Medium'),
    'ConcurrentModificationException': ('Logical',     'High'),
    'UnsupportedOperationException'  : ('Logical',     'Medium'),
    # Performance
    'TimeoutException'               : ('Performance', 'High'),
    'SQLException'                   : ('Performance', 'High'),
    'ConnectionException'            : ('Performance', 'High'),
    # Generic
    'ERROR'                          : ('Logical',     'Medium'),
    'FATAL'                          : ('Crash',       'Critical'),
    'EXCEPTION'                      : ('Logical',     'Medium'),
    'WARN'                           : ('Logical',     'Low'),
}

def extract_log_bugs(content: str, filename: str) -> list:
    """Parse log/txt file and return list of found bugs (no ML needed)."""
    bugs = []
    lines = content.split('\n')
    seen  = set()

    for i, line in enumerate(lines, start=1):
        for pattern, (btype, severity) in EXCEPTION_BUG_MAP.items():
            if pattern.lower() in line.lower() and pattern not in seen:
                seen.add(pattern)
                # Try to extract a class/method name from the line
                cls_match = re.search(r'at\s+([\w.]+)\.\w+\(', line)
                location  = cls_match.group(1).split('.')[-1] if cls_match else filename

                bugs.append({
                    'file'       : filename,
                    'line_number': i,
                    'raw_line'   : line.strip()[:120],
                    'exception'  : pattern,
                    'bug_type'   : btype,
                    'severity'   : severity,
                })
                break
    return bugs


# ═══════════════════════════════════════════════════════════════════════════════
#  Fallback metrics (when parsing fails)
# ═══════════════════════════════════════════════════════════════════════════════
def _fallback_metrics(loc: int = 100, filename: str = '') -> dict:
    wmc = max(1, loc // 20)
    return {
        'wmc': wmc, 'dit': 1, 'noc': 0, 'cbo': 3, 'rfc': wmc * 2,
        'lcom': 10, 'ca': 1, 'ce': 3, 'npm': max(1, wmc // 2),
        'lcom3': 0.1, 'loc': loc, 'dam': 0.5, 'moa': 0, 'mfa': 0.1,
        'cam': 0.3, 'ic': 0, 'cbm': 1, 'amc': max(1, loc // wmc),
        'max_cc': max(1, wmc // 2), 'avg_cc': 1.5,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  Main extractor function — call this from the pipeline
# ═══════════════════════════════════════════════════════════════════════════════
def extract_metrics_from_file(file_path: str) -> dict:
    """
    Read one source file and return its CK metrics.
    Returns: {'metrics': {...}, 'is_log': bool, 'log_bugs': [...]}
    """
    path = Path(file_path)
    ext  = path.suffix.lower()

    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            code = f.read()
    except Exception as e:
        return {'metrics': _fallback_metrics(filename=path.name),
                'is_log': False, 'log_bugs': [], 'error': str(e)}

    if ext == '.java':
        m = extract_java_metrics(code, path.name)
        return {'metrics': m, 'is_log': False, 'log_bugs': []}

    elif ext == '.py':
        m = extract_python_metrics(code, path.name)
        return {'metrics': m, 'is_log': False, 'log_bugs': []}

    elif ext in {'.js', '.ts'}:
        m = extract_js_metrics(code, path.name)
        return {'metrics': m, 'is_log': False, 'log_bugs': []}

    elif ext in {'.cpp', '.c', '.cs', '.php', '.rb'}:
        # Generic C-style extraction
        m = extract_java_metrics(code, path.name)   # reuse Java regex (compatible)
        return {'metrics': m, 'is_log': False, 'log_bugs': []}

    elif ext in {'.log', '.txt'}:
        bugs = extract_log_bugs(code, path.name)
        loc  = len(code.split('\n'))
        return {'metrics': _fallback_metrics(loc, path.name),
                'is_log': True, 'log_bugs': bugs}

    else:
        loc = len(code.split('\n'))
        return {'metrics': _fallback_metrics(loc, path.name),
                'is_log': False, 'log_bugs': []}


def extract_metrics_from_zip(zip_path: str, extract_to: str = None) -> list:
    """
    Extract ZIP and return metrics for every source file inside.
    Returns: list of {'file': name, 'metrics': {...}, 'is_log': bool, 'log_bugs': [...]}
    """
    if extract_to is None:
        extract_to = zip_path.replace('.zip', '_unzipped')
    os.makedirs(extract_to, exist_ok=True)

    results = []
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_to)

    for root, _, files in os.walk(extract_to):
        for fname in files:
            fpath = os.path.join(root, fname)
            ext   = Path(fname).suffix.lower()
            if ext in SOURCE_EXTS | LOG_EXTS:
                info = extract_metrics_from_file(fpath)
                info['file'] = fname
                results.append(info)

    return results


# ─── Quick self-test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    sample_java = '''
import java.util.List;
import java.util.ArrayList;
import org.springframework.beans.factory.annotation.Autowired;

public class UserService extends BaseService implements IUserService {
    private UserRepository userRepo;
    private EmailService emailService;
    private int maxRetries;

    public User findById(Long id) {
        if (id == null) {
            throw new IllegalArgumentException("id cannot be null");
        }
        return userRepo.findById(id).orElse(null);
    }

    public List<User> findAll() {
        List<User> users = new ArrayList<>();
        for (User u : userRepo.findAll()) {
            if (u.isActive() && u.getRole() != null) {
                users.add(u);
            }
        }
        return users;
    }

    public void saveUser(User user) {
        try {
            userRepo.save(user);
            emailService.sendWelcome(user.getEmail());
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
'''

    print("=== Java Metrics ===")
    m = extract_java_metrics(sample_java, "UserService.java")
    print(json.dumps(m, indent=2))

    sample_py = '''
import os
import re
from typing import List

class DataProcessor:
    def __init__(self, config):
        self.config = config
        self.data = []

    def load(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        with open(path) as f:
            self.data = f.readlines()
        return True

    def process(self) -> List[str]:
        result = []
        for line in self.data:
            if line.strip() and not line.startswith("#"):
                result.append(line.upper())
        return result
'''

    print("\n=== Python Metrics ===")
    m = extract_python_metrics(sample_py, "data_processor.py")
    print(json.dumps(m, indent=2))

    sample_log = """
2026-01-15 10:23:45 ERROR NullPointerException at com.example.UserService.findById(UserService.java:45)
2026-01-15 10:23:46 FATAL StackOverflowError at com.example.RecursiveCalc.compute(RecursiveCalc.java:12)
2026-01-15 10:24:00 WARN  IllegalArgumentException: value out of range at com.example.Validator.check
2026-01-15 10:25:00 INFO  Service started successfully
"""
    print("\n=== Log Bugs ===")
    bugs = extract_log_bugs(sample_log, "app.log")
    for b in bugs:
        print(b)
