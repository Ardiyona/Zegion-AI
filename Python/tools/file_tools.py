import os


def list_files(path="."):

    files = []

    for root, dirs, filenames in os.walk(path):

        for filename in filenames:

            full_path = os.path.join(root, filename)

            files.append(full_path)

    return "\n".join(files)

def search_in_files(keyword, path="."):

    import os

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