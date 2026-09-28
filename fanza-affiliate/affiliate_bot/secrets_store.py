"""Secret の保存先。値はターミナルにもログにも Git にも出さない。

- LocalEnvStore: プロジェクトの .env（パーミッション 600、.gitignore 済みを検証）
- GoogleSecretManagerStore: gcloud CLI が認証済みなら `gcloud secrets versions:add`（stdin 経由）
- VercelEnvStore: vercel CLI が認証済みなら `vercel env add`（stdin 経由）
- GitHubActionsStore: `gh` CLI があれば `gh secret set`（stdin 経由）
bootstrap はデプロイ先に応じて複数のストアへ同じ値を書く。
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

SECRET_KEYS = {
    "DMM_API_ID", "DMM_AFFILIATE_ID", "X_CONSUMER_KEY", "X_CONSUMER_SECRET", "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET", "ANTHROPIC_API_KEY", "TRACKING_SECRET", "SLACK_WEBHOOK_URL", "VERCEL_TOKEN",
}


def mask(value: str | None) -> str:
    if not value:
        return "(未設定)"
    return f"設定済み（{len(value)} 文字, 末尾 …{value[-2:]}）" if len(value) >= 8 else "設定済み"


class LocalEnvStore:
    name = "local .env"

    def __init__(self, path: Path):
        self.path = path

    def available(self) -> bool:
        return True

    def _read(self) -> list[str]:
        return self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []

    def get(self, key: str) -> str | None:
        for line in self._read():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
        return None

    def set(self, key: str, value: str) -> None:
        lines = self._read()
        esc = value.replace("\n", "")
        out, done = [], False
        for line in lines:
            if line.startswith(f"{key}="):
                out.append(f"{key}={esc}")
                done = True
            else:
                out.append(line)
        if not done:
            out.append(f"{key}={esc}")
        self.path.write_text("\n".join(out) + "\n", encoding="utf-8")
        os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
        os.environ[key] = value

    def permissions_ok(self) -> bool:
        if not self.path.exists():
            return True
        mode = stat.S_IMODE(self.path.stat().st_mode)
        return mode & 0o077 == 0

    def harden(self) -> None:
        if self.path.exists():
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)


def gitignored(repo_root: Path, rel_path: str) -> bool:
    try:
        r = subprocess.run(["git", "check-ignore", "-q", rel_path], cwd=repo_root, capture_output=True, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def tracked_secret_files(repo_root: Path) -> list[str]:
    """Git に追跡されてしまっている .env 系ファイル。"""
    try:
        r = subprocess.run(["git", "ls-files"], cwd=repo_root, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    return [f for f in r.stdout.splitlines() if re.search(r"(^|/)\.env(\.|$)", f) and not f.endswith(".example")]


def _run(cmd: list[str], input_text: str | None = None, timeout: int = 60) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, input=input_text, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return 127, "not found"
    except subprocess.SubprocessError as e:
        return 1, str(e)


class GoogleSecretManagerStore:
    name = "Google Secret Manager"

    def __init__(self, project: str | None = None):
        self.project = project or os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")

    def available(self) -> bool:
        if not shutil.which("gcloud"):
            return False
        code, out = _run(["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"])
        if code != 0 or not out:
            return False
        if not self.project:
            code, out = _run(["gcloud", "config", "get-value", "project"])
            self.project = out if code == 0 and out and out != "(unset)" else None
        return bool(self.project)

    def set(self, key: str, value: str) -> bool:
        code, _ = _run(["gcloud", "secrets", "describe", key, "--project", self.project])
        if code != 0:
            code, out = _run(["gcloud", "secrets", "create", key, "--project", self.project, "--replication-policy=automatic",
                              "--data-file=-"], input_text=value)
            return code == 0
        code, out = _run(["gcloud", "secrets", "versions", "add", key, "--project", self.project, "--data-file=-"], input_text=value)
        return code == 0


class VercelEnvStore:
    name = "Vercel Environment Variables"

    def __init__(self, project_dir: Path, token: str | None = None):
        self.project_dir = project_dir
        self.token = token or os.environ.get("VERCEL_TOKEN")

    def _cli(self) -> list[str] | None:
        if shutil.which("vercel"):
            return ["vercel"]
        if shutil.which("npx"):
            return ["npx", "--yes", "vercel"]
        return None

    def available(self) -> bool:
        cli = self._cli()
        if not cli:
            return False
        args = cli + ["whoami"] + (["--token", self.token] if self.token else [])
        code, _ = _run(args, timeout=120)
        return code == 0

    def set(self, key: str, value: str, env: str = "production") -> bool:
        cli = self._cli()
        if not cli:
            return False
        base = cli + (["--token", self.token] if self.token else []) + ["--cwd", str(self.project_dir), "--yes"]
        _run(base + ["env", "rm", key, env, "--yes"], timeout=120)
        code, _ = _run(base + ["env", "add", key, env], input_text=value, timeout=120)
        return code == 0


class GitHubActionsStore:
    name = "GitHub Actions Secrets"

    def available(self) -> bool:
        if not shutil.which("gh"):
            return False
        code, _ = _run(["gh", "auth", "status"])
        return code == 0

    def set(self, key: str, value: str) -> bool:
        code, _ = _run(["gh", "secret", "set", key], input_text=value)
        return code == 0
