"""
BuggyService - Intentionally complex Python module for AI bug detection testing.
This file has high coupling, high complexity, and low cohesion — model will flag it.
"""

import os
import re
import sys
import json
import time
import hashlib
import datetime
import threading
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from collections import defaultdict, OrderedDict
from typing import List, Dict, Optional, Tuple, Any, Union


class DataProcessor:
    """High-coupling, high-complexity class — will be flagged as Performance bug."""

    def __init__(self, db_url, cache_size, timeout, retry_count, log_level,
                 batch_size, max_workers, compression, encoding, secret_key):
        self.db_url      = db_url
        self.cache_size  = cache_size
        self.timeout     = timeout
        self.retry_count = retry_count
        self.log_level   = log_level
        self.batch_size  = batch_size
        self.max_workers = max_workers
        self.compression = compression
        self.encoding    = encoding
        self.secret_key  = secret_key
        self.cache       = {}
        self.stats       = defaultdict(int)
        self.lock        = threading.Lock()
        self.history     = []
        self.errors      = []
        self._running    = False
        self._queue      = []

    def process_all(self, records: List[Dict]) -> Dict:
        result = {}
        for i, record in enumerate(records):
            try:
                if record is None:
                    continue
                if not isinstance(record, dict):
                    self.errors.append(f"Record {i} not a dict")
                    continue
                if "id" not in record:
                    if "uuid" in record:
                        record["id"] = record["uuid"]
                    elif "key" in record:
                        record["id"] = record["key"]
                    else:
                        record["id"] = hashlib.md5(str(record).encode()).hexdigest()

                data = self._transform(record)
                if data:
                    validated = self._validate(data)
                    if validated:
                        enriched = self._enrich(validated)
                        if enriched:
                            compressed = self._compress(enriched)
                            result[record["id"]] = compressed
                            self.stats["success"] += 1
                        else:
                            self.stats["enrich_fail"] += 1
                    else:
                        self.stats["validate_fail"] += 1
                else:
                    self.stats["transform_fail"] += 1
            except Exception as e:
                self.errors.append(str(e))
                self.stats["errors"] += 1
        return result

    def _transform(self, record: Dict) -> Optional[Dict]:
        out = {}
        for k, v in record.items():
            if isinstance(v, str):
                out[k] = v.strip().lower()
            elif isinstance(v, list):
                out[k] = [str(x) for x in v if x is not None]
            elif isinstance(v, dict):
                out[k] = self._transform(v)
            elif isinstance(v, (int, float)):
                out[k] = v
            elif v is None:
                out[k] = ""
            else:
                out[k] = str(v)
        return out if out else None

    def _validate(self, data: Dict) -> Optional[Dict]:
        required = ["id", "type", "severity"]
        for field in required:
            if field not in data:
                return None
            if not data[field]:
                return None
        if data.get("severity") not in ["low", "medium", "high", "critical"]:
            data["severity"] = "medium"
        if data.get("type") not in ["crash", "logical", "performance", "ui"]:
            data["type"] = "logical"
        return data

    def _enrich(self, data: Dict) -> Dict:
        data["processed_at"]  = datetime.datetime.utcnow().isoformat()
        data["processor_ver"] = "2.1.0"
        data["checksum"]      = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        data["env"]           = os.environ.get("APP_ENV", "production")
        return data

    def _compress(self, data: Dict) -> Dict:
        if not self.compression:
            return data
        text = json.dumps(data)
        if len(text) > 1000:
            data["__compressed"] = True
            data["__size"]       = len(text)
        return data

    def run_batch(self, source_path: str) -> List[Dict]:
        results = []
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source not found: {source_path}")
        files = list(Path(source_path).glob("**/*.json"))
        for i in range(0, len(files), self.batch_size):
            chunk = files[i:i + self.batch_size]
            for f in chunk:
                try:
                    with open(f, encoding=self.encoding) as fh:
                        data = json.load(fh)
                    if isinstance(data, list):
                        out = self.process_all(data)
                    else:
                        out = self.process_all([data])
                    results.extend(out.values())
                except json.JSONDecodeError as e:
                    self.errors.append(f"JSON error in {f}: {e}")
                except PermissionError as e:
                    self.errors.append(f"Permission denied: {f}")
                except Exception as e:
                    self.errors.append(f"Unexpected error {f}: {e}")
            time.sleep(0.01)
        return results


class ReportBuilder:
    """High cyclomatic complexity — will be flagged as Logical bug."""

    STATUS_MAP   = {"open": 0, "in_progress": 1, "fixed": 2, "closed": 3, "reopened": 4}
    SEVERITY_MAP = {"low": 1, "medium": 2, "high": 3, "critical": 4}

    def __init__(self, config: Dict):
        self.config     = config
        self.filters    = config.get("filters", {})
        self.sort_by    = config.get("sort_by", "severity")
        self.max_rows   = config.get("max_rows", 1000)
        self.include_fx = config.get("include_fixes", True)
        self.format     = config.get("format", "json")

    def build(self, bugs: List[Dict], user_role: str) -> Dict:
        if not bugs:
            return {"total": 0, "bugs": [], "summary": {}}

        filtered = self._filter(bugs, user_role)
        sorted_b = self._sort(filtered)
        limited  = sorted_b[:self.max_rows]
        summary  = self._summarise(limited)
        formatted = self._format_output(limited, summary)
        return formatted

    def _filter(self, bugs: List[Dict], role: str) -> List[Dict]:
        out = []
        for b in bugs:
            if self.filters.get("severity"):
                if b.get("severity", "").lower() != self.filters["severity"].lower():
                    continue
            if self.filters.get("type"):
                if b.get("type", "").lower() != self.filters["type"].lower():
                    continue
            if self.filters.get("status"):
                if b.get("status", "").lower() != self.filters["status"].lower():
                    continue
            if self.filters.get("assigned_to"):
                if b.get("assigned_to", "").lower() != self.filters["assigned_to"].lower():
                    continue
            if role == "qa":
                if b.get("assigned_to", "").lower() not in ("qa", "tester"):
                    if b.get("severity", "").lower() not in ("critical", "high"):
                        continue
            elif role == "developer":
                if b.get("assigned_to", "").lower() not in ("developer", "dev"):
                    continue
            elif role == "analyst":
                if b.get("type", "").lower() != "performance":
                    continue
            out.append(b)
        return out

    def _sort(self, bugs: List[Dict]) -> List[Dict]:
        key = self.sort_by
        if key == "severity":
            return sorted(bugs, key=lambda b: self.SEVERITY_MAP.get(b.get("severity", "").lower(), 0), reverse=True)
        elif key == "status":
            return sorted(bugs, key=lambda b: self.STATUS_MAP.get(b.get("status", "").lower(), 0))
        elif key == "file":
            return sorted(bugs, key=lambda b: b.get("file", ""))
        elif key == "date":
            return sorted(bugs, key=lambda b: b.get("created_at", ""), reverse=True)
        else:
            return bugs

    def _summarise(self, bugs: List[Dict]) -> Dict:
        summary = {"total": len(bugs), "by_severity": {}, "by_type": {}, "by_status": {}}
        for b in bugs:
            s = b.get("severity", "unknown")
            t = b.get("type", "unknown")
            st = b.get("status", "unknown")
            summary["by_severity"][s]  = summary["by_severity"].get(s, 0) + 1
            summary["by_type"][t]      = summary["by_type"].get(t, 0) + 1
            summary["by_status"][st]   = summary["by_status"].get(st, 0) + 1
        return summary

    def _format_output(self, bugs: List[Dict], summary: Dict) -> Dict:
        if self.format == "json":
            return {"bugs": bugs, "summary": summary, "total": len(bugs)}
        elif self.format == "csv":
            rows = ["bug_id,type,severity,file,status"]
            for b in bugs:
                rows.append(f"{b.get('bug_id','')},{b.get('type','')},{b.get('severity','')},{b.get('file','')},{b.get('status','')}")
            return {"csv": "\n".join(rows), "total": len(bugs)}
        elif self.format == "html":
            rows = "".join(f"<tr><td>{b.get('bug_id','')}</td><td>{b.get('type','')}</td></tr>" for b in bugs)
            return {"html": f"<table>{rows}</table>", "total": len(bugs)}
        return {"bugs": bugs, "total": len(bugs)}


class AuthManager:
    """Handles authentication — medium complexity."""

    ROLES = ["admin", "qa", "developer", "analyst", "viewer"]

    def __init__(self, secret: str, expiry_minutes: int = 60):
        self.secret         = secret
        self.expiry_minutes = expiry_minutes
        self._sessions      = {}
        self._failed        = defaultdict(int)

    def authenticate(self, username: str, password: str) -> Optional[str]:
        if not username or not password:
            return None
        if self._failed[username] >= 5:
            return None
        token = self._generate_token(username)
        self._sessions[token] = {
            "user": username,
            "expires": datetime.datetime.utcnow() + datetime.timedelta(minutes=self.expiry_minutes)
        }
        self._failed[username] = 0
        return token

    def validate_token(self, token: str) -> Optional[str]:
        if not token or token not in self._sessions:
            return None
        session = self._sessions[token]
        if datetime.datetime.utcnow() > session["expires"]:
            del self._sessions[token]
            return None
        return session["user"]

    def _generate_token(self, username: str) -> str:
        raw = f"{username}:{self.secret}:{time.time()}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def revoke(self, token: str) -> bool:
        if token in self._sessions:
            del self._sessions[token]
            return True
        return False
