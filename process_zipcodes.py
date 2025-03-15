import os
import pandas as pd


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# Function to save data to Excel
def save_to_excel(data, filename):
    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)
    print(f"Success! file saved : {filename}")

# Function to read zip code data
def read_zipcode_data(file_path):
    df = pd.read_csv(file_path, dtype=str)
    return df

# Function to normalize zip code data
def normalize_zip_data(us_zip_df, can_zip_df):
    us_zip_df = us_zip_df[["City", "State"]].drop_duplicates().sort_values(by=["State", "City"]).reset_index(drop=True)
    can_zip_df = can_zip_df[["CITY", "PROVINCE_ABBR"]].rename(columns={"CITY": "City", "PROVINCE_ABBR": "State"}).drop_duplicates().sort_values(by=["State", "City"]).reset_index(drop=True)
    
    us_zip_df["Data"] = ""
    can_zip_df["Data"] = ""
    
    return us_zip_df, can_zip_df

# Main execution
def process_zip_data():
    zip_folder = os.path.join(BASE_DIR, 'zipcodes')
    us_zip_csv_path = os.path.join(zip_folder, 'USZIPCodes202503.csv')
    can_zip_csv_path = os.path.join(zip_folder, 'CanadianPostalCodes202403.csv')
    us_zip_processed_path = os.path.join(zip_folder, 'USZIPCodes202503_Processed.xlsx')
    can_zip_processed_path = os.path.join(zip_folder, 'CanadianPostalCodes202403_Processed.xlsx')
    
    if not os.path.exists(us_zip_processed_path) or not os.path.exists(can_zip_processed_path):
        us_zip_df = read_zipcode_data(us_zip_csv_path)
        can_zip_df = read_zipcode_data(can_zip_csv_path)
        us_zip_df, can_zip_df = normalize_zip_data(us_zip_df, can_zip_df)
        save_to_excel(us_zip_df, us_zip_processed_path)
        save_to_excel(can_zip_df, can_zip_processed_path)
        print("City/State data files processed!!")
    else:
        print("City/State data files loaded!!")
    
    return us_zip_processed_path, can_zip_processed_path
    

