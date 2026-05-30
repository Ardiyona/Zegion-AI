import os
import subprocess


def list_files(path="."):
    """Daftar semua file dalam direktori (rekursif)."""
    files = []

    for root, dirs, filenames in os.walk(path):
        for filename in filenames:
            full_path = os.path.join(root, filename)
            files.append(full_path)

    return "\n".join(files)


def search_in_files(keyword, path="."):
    """Cari file yang mengandung keyword tertentu."""
    results = []

    for root, dirs, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    if keyword.lower() in content.lower():
                        results.append(filepath)
            except:
                pass

    if results:
        return "\n".join(results)

    return "Tidak ditemukan"


def read_file(path):
    """Baca isi file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error: {str(e)}"


def write_file(path, content):
    """Tulis konten ke file."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Berhasil menulis ke {path}"
    except Exception as e:
        return f"Error: {str(e)}"


def execute_python(path):
    """Jalankan file Python dan return hasilnya."""
    try:
        result = subprocess.run(
            ["py", path],
            capture_output=True,
            text=True,
            timeout=10
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
