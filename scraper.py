import time
import random
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from process_zipcodes import process_zip_data
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

import undetected_chromedriver as uc

def setup_driver():
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")  
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # options.add_argument("--start-maximized")

    driver = uc.Chrome(options=options, use_subprocess=True)  
    return driver

driver = setup_driver()

# Setup Selenium WebDriver
# def setup_driver():
#     options = Options()
#     options.add_argument("--disable-blink-features=AutomationControlled")  # Prevent detection as a bot
#     options.add_argument("--no-sandbox")  # Bypass OS security model (useful for Linux)
#     options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource issues
#     options.add_argument("--start-maximized")  # Open Chrome in maximized mode
#     # options.add_argument("--headless")  # Uncomment to run Chrome in headless mode

#     # Initialize WebDriver
#     chromedriver_path = r"C:\Program Files\Google\Chrome\Application\chromedriver.exe"
#     service = Service(chromedriver_path)
#     driver = webdriver.Chrome(service=service, options=options)
#     return driver

def get_sleep_value(a: int, b: int) -> int:
    return random.randint(a, b)



# Open the search URL
def open_search_page(driver, search_url, city, state, country):
    driver.get(search_url)
    time.sleep(get_sleep_value(a=7, b=10))  # Allow time for the page to load
    try:
        # Scroll the search form into view
        search_container = driver.find_element(By.ID, "hospitalLocatorSearchCriteria")
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", search_container)
        time.sleep(get_sleep_value(a=2, b=4))  # Allow scrolling animation to complete

        # Fill in the city field
        city_input = driver.find_element(By.NAME, "city")
        city_input.clear()
        city_input.send_keys(city)

        # Fill in the state field
        time.sleep(get_sleep_value(a=1, b=2))
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
        time.sleep(get_sleep_value(a=3, b=7))

        # Click the search button
        search_button = driver.find_element(By.ID, "locator-search")
        search_button.click()
        time.sleep(get_sleep_value(a=3, b=7)) 

        print(f"Search completed for {city}, {state}, {country}")
        breakpoint()

    except Exception as e:
        print(f"Error while searching for {city}, {state}, {country}: {e}")




# Main execution
def main():
    search_url = "https://www.aaha.org/for-pet-parents/find-an-aaha-accredited-animal-hospital-near-me/"
    us_zip_path, can_zip_path = process_zip_data()
    
    driver = setup_driver()
    us_df = pd.read_excel(us_zip_path)
    can_df = pd.read_excel(can_zip_path)

    for _, row in us_df.iterrows():
        country = "United States"
        if row['Data'] == 'added':
            continue
        city, state = row["City"], row["State"]
        open_search_page(driver=driver, search_url=search_url, 
                         city=city, state=state, country=country)
        row["Data"] = "added"
        time.sleep(get_sleep_value(a=3, b=6)) 
    
    # Keep browser open for debugging
    input("Press Enter to close the browser...")
    driver.quit()
    print("Browser closed.")
    
    
if __name__ == "__main__":
    main()
