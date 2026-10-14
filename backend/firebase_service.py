"""
BuildFail-SLM: Firebase Admin SDK & Realtime Database Service
Integrates Firebase credentials securely stored in the backend/ directory.
Provides Realtime Database synchronization for:
  - Repositories catalog
  - Live Triage Issues & synthesized patches
  - Pipeline diagnostic execution logs
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger("buildfail.firebase")

# Try importing firebase_admin; log if not installed
try:
    import firebase_admin
    from firebase_admin import credentials, db
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    logger.warning("firebase-admin package is not installed. Run: pip install firebase-admin")

# Safe auto-load of .env
for _cand in [Path(".env"), Path("../.env"), Path(__file__).resolve().parent.parent / ".env"]:
    if _cand.exists():
        for _line in _cand.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip("\"' "))
        break


class FirebaseService:
    """Manages Firebase Admin SDK initialization and Realtime Database operations."""

    def __init__(self, key_filename: str = "firebase-credentials.json"):
        self.key_filename = key_filename
        self.app: Optional[Any] = None
        self.is_initialized: bool = False
        self.project_id: Optional[str] = None
        self.database_url: Optional[str] = None
        self.credentials_path: Optional[Path] = None
        self.error_message: Optional[str] = None

        self._find_and_initialize()

    def _locate_key_path(self) -> Optional[Path]:
        """Locate firebase credentials file strictly prioritizing the backend/ directory."""
        candidates = []

        # 1. Environment variable if explicitly specified
        env_key = os.getenv("FIREBASE_CREDENTIALS_PATH")
        if env_key:
            candidates.append(Path(env_key))

        # 2. backend/ directory (Current directory of this file)
        current_dir = Path(__file__).resolve().parent
        candidates.append(current_dir / self.key_filename)
        candidates.append(current_dir / "serviceAccountKey.json")

        # 3. Project root directory fallback
        root_dir = current_dir.parent
        candidates.append(root_dir / self.key_filename)
        candidates.append(root_dir / "backend" / self.key_filename)
        candidates.append(root_dir / "backend" / "serviceAccountKey.json")

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()

        return (current_dir / self.key_filename).resolve()

    def _find_and_initialize(self):
        """Initialize Firebase Admin SDK with credentials."""
        if not FIREBASE_AVAILABLE:
            self.error_message = "firebase-admin library is not installed."
            return

        target_path = self._locate_key_path()
        self.credentials_path = target_path

        if not target_path or not target_path.exists():
            self.is_initialized = False
            self.error_message = f"Credentials file not found at {target_path}. Please place your serviceAccountKey.json into the backend/ folder."
            logger.info("Firebase: " + self.error_message)
            return

        try:
            # Validate JSON content
            with open(target_path, "r", encoding="utf-8") as f:
                key_data = json.load(f)

            self.project_id = key_data.get("project_id")

            # Check if this is still an unfilled placeholder template
            if not self.project_id or "your-firebase-project" in self.project_id or "your-project-id" in self.project_id:
                self.is_initialized = False
                self.error_message = f"Credentials at {target_path} contain placeholder keys. Replace with your actual Firebase service account keys."
                logger.info("Firebase: " + self.error_message)
                return

            # Determine Realtime Database URL
            env_db_url = os.getenv("FIREBASE_DATABASE_URL")
            if env_db_url:
                self.database_url = env_db_url.strip()
            elif self.project_id:
                # Default to Asia Southeast 1 URL for fixflow-beb5b
                if "fixflow" in self.project_id:
                    self.database_url = f"https://{self.project_id}-default-rtdb.asia-southeast1.firebasedatabase.app"
                else:
                    self.database_url = f"https://{self.project_id}-default-rtdb.firebaseio.com"

            options = {}
            if self.database_url:
                options["databaseURL"] = self.database_url

            # Initialize Firebase App
            cred = credentials.Certificate(str(target_path))

            if not firebase_admin._apps:
                self.app = firebase_admin.initialize_app(cred, options)
            else:
                self.app = firebase_admin.get_app()

            self.is_initialized = True
            self.error_message = None
            logger.info(f"Firebase Admin SDK successfully initialized for project: {self.project_id} (RTDB: {self.database_url})")

        except Exception as e:
            self.is_initialized = False
            self.error_message = f"Failed to initialize Firebase: {str(e)}"
            logger.error("Firebase initialization error: " + self.error_message)

    def reinitialize(self) -> Dict[str, Any]:
        """Manually trigger a re-initialization (e.g., after user places serviceAccountKey.json)."""
        self._find_and_initialize()
        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        """Return status dictionary of Firebase configuration."""
        key_exists = bool(self.credentials_path and self.credentials_path.exists())
        key_size = self.credentials_path.stat().st_size if key_exists else 0

        return {
            "available": FIREBASE_AVAILABLE,
            "initialized": self.is_initialized,
            "project_id": self.project_id,
            "database_url": self.database_url,
            "credentials_file": self.credentials_path.name if self.credentials_path else None,
            "credentials_present": key_exists,
            "credentials_file_size_bytes": key_size,
            "error": self.error_message
        }

    def _sanitize_key(self, key: Any) -> str:
        """Firebase Realtime Database keys cannot contain: . $ # [ ] /"""
        import re
        cleaned = re.sub(r'[\.\$#\[\]/\s]', '_', str(key or "item")).strip('_')
        return cleaned or "item"

    # =========================================================================
    # REALTIME DATABASE: REPOSITORIES
    # =========================================================================
    def sync_repository(self, repo: Dict[str, Any]) -> bool:
        """Persist or update a repository in Firebase Realtime Database under /repositories/{repo_id} and /repos/{repo_id}."""
        if not self.is_initialized:
            return False

        try:
            raw_id = repo.get("id") or repo.get("name", "").lower()
            repo_id = self._sanitize_key(raw_id)
            if not repo_id:
                return False

            clean_data = json.loads(json.dumps(repo, default=str))
            # Sync to both /repositories and /repos paths in Firebase RTDB
            db.reference(f"repositories/{repo_id}").set(clean_data)
            try:
                db.reference(f"repos/{repo_id}").set(clean_data)
            except Exception:
                pass
            return True
        except Exception as e:
            logger.warning(f"Failed to sync repository to Firebase RTDB: {e}")
            return False

    def get_all_repositories(self) -> List[Dict[str, Any]]:
        """Retrieve all repositories stored in Firebase Realtime Database."""
        if not self.is_initialized:
            return []

        try:
            ref = db.reference("repositories")
            data = ref.get()
            if not data:
                # Also check /repos alias
                data = db.reference("repos").get()
            if not data:
                return []
            if isinstance(data, dict):
                return list(data.values())
            if isinstance(data, list):
                return [r for r in data if r]
            return []
        except Exception as e:
            logger.warning(f"Failed to fetch repositories from Firebase RTDB: {e}")
            return []

    # =========================================================================
    # REALTIME DATABASE: ISSUES
    # =========================================================================
    def sync_issue(self, issue: Dict[str, Any]) -> bool:
        """Persist or update a live issue in Firebase Realtime Database under /issues/{issue_id}."""
        if not self.is_initialized:
            return False

        try:
            raw_id = issue.get("id") or f"issue-{issue.get('repoId', 'unknown')}-{issue.get('number', 1)}"
            issue_id = self._sanitize_key(raw_id)
            ref = db.reference(f"issues/{issue_id}")
            clean_data = json.loads(json.dumps(issue, default=str))
            ref.set(clean_data)
            return True
        except Exception as e:
            logger.warning(f"Failed to sync issue to Firebase RTDB: {e}")
            return False

    def get_all_issues(self) -> List[Dict[str, Any]]:
        """Retrieve all issues stored in Firebase Realtime Database."""
        if not self.is_initialized:
            return []

        try:
            ref = db.reference("issues")
            data = ref.get()
            if not data:
                return []
            if isinstance(data, dict):
                return list(data.values())
            if isinstance(data, list):
                return [i for i in data if i]
            return []
        except Exception as e:
            logger.warning(f"Failed to fetch issues from Firebase RTDB: {e}")
            return []

    # =========================================================================
    # REALTIME DATABASE: PIPELINE DIAGNOSTIC RUNS
    # =========================================================================
    def log_pipeline_run(self, run_id: str, payload: Dict[str, Any]) -> bool:
        """Log full pipeline diagnosis and patch run to Firebase Realtime Database."""
        if not self.is_initialized:
            return False

        try:
            clean_run_id = self._sanitize_key(run_id)
            ref = db.reference(f"pipeline_runs/{clean_run_id}")
            clean_data = json.loads(json.dumps(payload, default=str))
            ref.set(clean_data)
            return True
        except Exception as e:
            logger.warning(f"Failed to log pipeline run to Firebase RTDB: {e}")
            return False

    def test_connection(self) -> Dict[str, Any]:
        """Perform a test ping read/write to Firebase Realtime Database."""
        if not self.is_initialized:
            return {
                "success": False,
                "message": self.error_message or "Firebase not initialized."
            }

        try:
            test_ref = db.reference("_fixflow_healthcheck")
            test_ref.set({"status": "online", "client": "FixFlow SLM Agent", "timestamp": {".sv": "timestamp"}})
            val = test_ref.get()
            return {
                "success": True,
                "message": "Firebase Realtime Database read/write verified successfully.",
                "data": val
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Firebase Realtime Database connection failed: {str(e)}"
            }

    def update_model_status(self, is_loaded: bool = True, device: str = "cuda", status: str = "online", api_url: Optional[str] = None) -> bool:
        """Update live model engine status in Firebase Realtime Database under /model_status."""
        if not self.is_initialized:
            return False
        try:
            import time
            status_data = {
                "status": status,
                "model_loaded": is_loaded,
                "device": device.upper(),
                "adapter": "krishna1707/buildfail-slm-qwen7b-adapter",
                "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
                "timestamp": int(time.time()),
                "last_active": "Live"
            }
            resolved_api_url = api_url or os.getenv("PUBLIC_API_URL") or os.getenv("NEXT_PUBLIC_API_BASE_URL")
            if resolved_api_url:
                status_data["api_url"] = resolved_api_url
            ref = db.reference("model_status")
            ref.update(status_data)
            return True
        except Exception as e:
            logger.warning(f"Failed to update model status in Firebase RTDB: {e}")
            return False


# Singleton service instance
firebase_service = FirebaseService()
