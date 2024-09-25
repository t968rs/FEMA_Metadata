import os


def get_file_names(folder_path: str, ext: str = None) -> list:
    """
    This function will return a list of files in a folder with a specific extension
    """
    namelist = set()

    for file in os.listdir(folder_path):
        name = None
        if ext:
            if file.endswith(ext):
                if "." in file:
                    name = file.split(".")[0]
                else:
                    name = file
        else:
            if "." in file:
                name = file.split(".")[0]
            else:
                name = file
        if name:
            if name not in namelist:
                namelist.add(name)

    return list(namelist)

