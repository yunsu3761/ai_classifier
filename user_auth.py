"""
User Authentication and Management for TaxoAdapt Multi-User System
Simple employee ID (사번) based authentication without passwords.

Each user gets isolated directories:
  user_data/{employee_id}/
    datasets/       - per-user datasets
    configs/        - per-user YAML configs
    save_output/    - per-user result files
    history/        - execution history log
"""
import json
import os
from pathlib import Path
from datetime import datetime


class UserManager:
    """Manages user registration, login, and per-user directories"""

    def __init__(self, user_data_dir: Path):
        self.user_data_dir = Path(user_data_dir)
        self.users_file = self.user_data_dir / "users.json"
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Create user_data directory if it doesn't exist"""
        os.makedirs(self.user_data_dir, exist_ok=True)
        if not self.users_file.exists():
            self._save_users({})

    def _load_users(self) -> dict:
        """Load users from JSON file"""
        try:
            with open(self.users_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save_users(self, users: dict):
        """Save users to JSON file"""
        with open(self.users_file, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)

    def register_or_login(self, employee_id: str, display_name: str = "") -> dict:
        """Register new user or login existing user.
        Returns user info dict."""
        employee_id = employee_id.strip()
        if not employee_id:
            raise ValueError("사번을 입력해주세요.")

        users = self._load_users()

        if employee_id in users:
            # Existing user - update last login
            users[employee_id]['last_login'] = datetime.now().isoformat()
            users[employee_id]['login_count'] = users[employee_id].get('login_count', 0) + 1
            if display_name:
                users[employee_id]['display_name'] = display_name
            self._save_users(users)
        else:
            # New user registration
            users[employee_id] = {
                'employee_id': employee_id,
                'display_name': display_name or employee_id,
                'created_at': datetime.now().isoformat(),
                'last_login': datetime.now().isoformat(),
                'login_count': 1,
            }
            self._save_users(users)

        # Create user directories
        self._create_user_dirs(employee_id)

        return users[employee_id]

    def _create_user_dirs(self, employee_id: str):
        """Create per-user directory structure"""
        user_dir = self.user_data_dir / employee_id
        for subdir in ['datasets', 'configs', 'save_output', 'history']:
            os.makedirs(user_dir / subdir, exist_ok=True)

    def get_user_dir(self, employee_id: str) -> Path:
        """Get the base directory for a user"""
        return self.user_data_dir / employee_id

    def get_user_info(self, employee_id: str) -> dict:
        """Get user information"""
        users = self._load_users()
        return users.get(employee_id, None)

    def get_all_users(self) -> dict:
        """Get all registered users"""
        return self._load_users()

    def save_execution_history(self, employee_id: str, record: dict):
        """Save an execution record to user's history"""
        history_dir = self.user_data_dir / employee_id / 'history'
        os.makedirs(history_dir, exist_ok=True)

        history_file = history_dir / 'execution_history.json'
        history = []
        if history_file.exists():
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                history = []

        record['timestamp'] = datetime.now().isoformat()
        history.append(record)

        # Keep last 100 records
        if len(history) > 100:
            history = history[-100:]

        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def get_execution_history(self, employee_id: str) -> list:
        """Get execution history for a user"""
        history_file = self.user_data_dir / employee_id / 'history' / 'execution_history.json'
        if history_file.exists():
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []
        return []
