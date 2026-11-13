"""BassBlend: automatic multi-sub tuning for the miniDSP 2x4HD."""
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def version() -> str:
    """The VERSION file written by an update or image build, else git, else 'dev'."""
    f = _ROOT / "VERSION"
    try:
        if f.is_file():
            return f.read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        pass
    return _git_version()


@lru_cache(maxsize=1)
def _git_version() -> str:
    try:
        import subprocess
        r = subprocess.run(["git", "-C", str(_ROOT), "describe", "--tags", "--always", "--dirty"],
                           capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "dev"
