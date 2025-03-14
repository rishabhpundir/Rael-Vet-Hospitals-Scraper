import time
import random
import pandas as pd
from selenium import webdriver
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from process_zipcodes import process_zip_data
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


def setup_driver():
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")  
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--start-maximized")

    driver = uc.Chrome(options=options, use_subprocess=True)  
    return driver

def get_sleep_value(a=5, b=15):
    return random.uniform(a, b)



# Open the search URL
def open_search_page(driver, search_url, city, state, country):
    driver.get(search_url)
    time.sleep(get_sleep_value())  # Allow time for the page to load
    try:
        # Scroll the search form into view
        search_container = driver.find_element(By.ID, "hospitalLocatorSearchCriteria")
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", search_container)
        time.sleep(get_sleep_value())  # Allow scrolling animation to complete

        # Fill in the city field
        city_input = driver.find_element(By.NAME, "city")
        city_input.clear()
        city_input.send_keys(city)

        # Fill in the state field
        time.sleep(get_sleep_value())
        state_input = driver.find_element(By.NAME, "stateProvince")
        state_input.clear()
        state_input.send_keys(state)

        # Select the correct country radio button
        if country == "United States":
            country_radio = driver.find_element(By.ID, "__BVID__87")  # United States radio button
        elif country == "Canada":
            country_radio = driver.find_element(By.ID, "__BVID__88")  # Canada radio button
        else:
            raise ValueError("Invalid country: must be 'United States' or 'Canada'")

        country_radio.click()
        time.sleep(get_sleep_value())

        # Click the search button
        search_button = driver.find_element(By.ID, "locator-search")
        search_button.click()
        time.sleep(get_sleep_value()) 

        try:
            no_results = driver.find_element(By.XPATH, "//p[contains(text(), 'There are no results that match your search')]")
            if no_results:
                print(f"No results found for {city}, {state}, {country}")
                return None  # Return None if no results found
            else:
                breakpoint()
        except:
            pass

        print(f"Search completed for {city}, {state}, {country}")

    except Exception as e:
        print(f"Error while searching for {city}, {state}, {country}: {e}")
        return None



# Main execution
def main():
    search_url = "https://www.aaha.org/for-pet-parents/find-an-aaha-accredited-animal-hospital-near-me/"
    us_zip_path, can_zip_path = process_zip_data()
    
    driver = setup_driver()
    us_df = pd.read_excel(us_zip_path)
    can_df = pd.read_excel(can_zip_path)

    us_df["Data"] = us_df["Data"].astype("object").fillna("")
    for index, row in us_df.iterrows():
        country = "United States"
        if row['Data'] != "":
            continue
        city, state = row["City"], row["State"]
        success = open_search_page(driver=driver, search_url=search_url, 
                         city=city, state=state, country=country)

        if success is not None:
            us_df.at[index, "Data"] = str("added")
        else:
            us_df.at[index, "Data"] = str("not found")
            
        us_df.to_excel(us_zip_path, index=False)
        time.sleep(get_sleep_value())
    
    breakpoint()
    driver.quit()
    print("Browser closed.")
    
    
if __name__ == "__main__":
    main()
