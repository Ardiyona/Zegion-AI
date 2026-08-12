import os
import subprocess
from pathlib import Path


SANDBOX_ROOT = Path(os.getenv("FILE_OPS_ROOT", Path(__file__).resolve().parents[2])).resolve()


def _safe_path(path=".", *, must_exist=False):
    """Resolve path di dalam sandbox project saja."""
    base = Path(path).expanduser()
    target = (SANDBOX_ROOT / base).resolve() if not base.is_absolute() else base.resolve()

    check_target = target if target.exists() else target.parent
    if must_exist and not target.exists():
        raise FileNotFoundError(path)
    if os.path.commonpath([str(SANDBOX_ROOT), str(check_target)]) != str(SANDBOX_ROOT):
        raise PermissionError(f"Path di luar sandbox: {path}")
    return target


def _display(path):
    try:
        return str(path.relative_to(SANDBOX_ROOT))
    except ValueError:
        return str(path)


def list_files(path="."):
    """Daftar semua file dalam direktori (rekursif)."""
    try:
        root_path = _safe_path(path, must_exist=True)
        if not root_path.is_dir():
            return "Error: path bukan direktori"

        files = []
        for root, dirs, filenames in os.walk(root_path):
            dirs[:] = [d for d in dirs if _safe_path(Path(root) / d).is_dir()]
            for filename in filenames:
                full_path = _safe_path(Path(root) / filename)
                files.append(_display(full_path))

        return "\n".join(files)
    except Exception as e:
        return f"Error: {str(e)}"


def search_in_files(keyword, path="."):
    """Cari file yang mengandung keyword tertentu."""
    try:
        root_path = _safe_path(path, must_exist=True)
        if not root_path.is_dir():
            return "Error: path bukan direktori"

        results = []
        for root, dirs, filenames in os.walk(root_path):
            dirs[:] = [d for d in dirs if _safe_path(Path(root) / d).is_dir()]
            for filename in filenames:
                filepath = _safe_path(Path(root) / filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                        if keyword.lower() in content.lower():
                            results.append(_display(filepath))
                except Exception:
                    pass

        if results:
            return "\n".join(results)

        return "Tidak ditemukan"
    except Exception as e:
        return f"Error: {str(e)}"


def read_file(path):
    """Baca isi file."""
    try:
        safe_path = _safe_path(path, must_exist=True)
        if not safe_path.is_file():
            return "Error: path bukan file"
        with open(safe_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error: {str(e)}"


def write_file(path, content):
    """Tulis konten ke file."""
    try:
        safe_path = _safe_path(path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Berhasil menulis ke {_display(safe_path)}"
    except Exception as e:
        return f"Error: {str(e)}"


def execute_python(path):
    """Jalankan file Python dan return hasilnya."""
    try:
        safe_path = _safe_path(path, must_exist=True)
        if not safe_path.is_file() or safe_path.suffix != ".py":
            return "Error: path bukan file Python"

        result = subprocess.run(
            ["py", str(safe_path)],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=SANDBOX_ROOT,
        )

        if result.returncode == 0:
            return f"""
STATUS: SUCCESS

OUTPUT:
{result.stdout}
"""
        else:
            return f"""
STATUS: ERROR

ERROR:
{result.stderr}
"""

    except Exception as e:
        return f"""
STATUS: ERROR

ERROR:
{str(e)}
"""
