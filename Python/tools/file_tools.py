import os


def list_files(path="."):

    files = []

    for root, dirs, filenames in os.walk(path):

        for filename in filenames:

            full_path = os.path.join(root, filename)

            files.append(full_path)

    return "\n".join(files)

def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error: {str(e)}"

def write_file(path, content):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Berhasil menulis ke {path}"

    except Exception as e:
        return f"Error: {str(e)}"