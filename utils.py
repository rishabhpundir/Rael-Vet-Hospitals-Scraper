import os
import sys


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def find_input_xlsx_files(root_folder):
    """
    Scan a folder and its subfolders for files ending with 'input.xlsx'.
    
    Args:
        root_folder (str): Path to the folder to scan.
    
    Returns:
        list: Paths of all files ending with 'input.xlsx'.
    """
    input_xlsx_files = []
    
    for root, dirs, files in os.walk(root_folder):
        for file in files:
            if file.endswith("input.xlsx"):
                full_path = os.path.join(root, file)
                input_xlsx_files.append(full_path)
    
    return input_xlsx_files

# Main execution
def get_input_files():
    input_folder = os.path.join(BASE_DIR, 'input')
    os.makedirs(input_folder, exist_ok=True)
    file_paths = find_input_xlsx_files(root_folder=input_folder)

    if file_paths:
        print("City/State data files found and loaded!!")
        print(f"Found files: {file_paths}")
    else:
        print("No files found in 'input' folder, ending with 'input.xlsx'. Exiting.")
        sys.exit(1)
    
    return file_paths
