import re
import time
import json
import random
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from process_zipcodes import process_zip_data
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException


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

def open_search_page(driver, search_url, city, state, country):
    """
    Runs queries on the website.
    """
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
            country_radio = driver.find_element(By.ID, "__BVID__87")
        elif country == "Canada":
            country_radio = driver.find_element(By.ID, "__BVID__88")
        else:
            raise ValueError("Invalid country: must be 'United States' or 'Canada'")

        country_radio.click()
        time.sleep(get_sleep_value())

        # Click the search button
        search_button = driver.find_element(By.ID, "locator-search")
        search_button.click()
        time.sleep(get_sleep_value()) 

        try:
            driver.find_element(By.XPATH, "//p[contains(text(), 'There are no results that match your search')]")
            print(f"No results found for {city}, {state}, {country}")
        except NoSuchElementException:
            print(f"Results found for {city}, {state}, {country}, proceeding...")
            hospital_results = process_search_results(driver) # Continue processing results
            return hospital_results

        print(f"Search completed for {city}, {state}, {country}")
    except Exception as e:
        print(f"Error while searching for {city}, {state}, {country}: {e}")
        return None


def process_search_results(driver):
    """
    Extracts search results from the page:
    - Parses hospital locations from the JavaScript variable.
    - Extracts URLs from the search results list.
    - Clicks each hospital, extract more data, and returns.
    """

    extracted_data = []

    # Step 1: Extract hospital data/locations from JavaScript (inside <script>)
    try:
        script_tag = driver.find_element(By.XPATH, "//script[contains(text(), 'var locations')]").get_attribute("innerHTML")
        match = re.search(r"var locations = (\[.*?\]);", script_tag, re.DOTALL)
        if not match:
            print("No location data found in script.")
            return []

        locations_json = match.group(1)
        locations = json.loads(locations_json)

        for loc in locations:
            if "Your Location" in loc.get("name", "N/A"):
                continue
            extracted_data.append({
                "Name": loc.get("name", "N/A"),
                "Address": loc.get("address", "N/A"),
                "Phone": loc.get("phone", "N/A"),
                "Latitude": loc.get("lat", "N/A"),
                "Longitude": loc.get("lng", "N/A"),
                "Distance": loc.get("distance", "N/A"),
                "Practice": loc.get("icon", "N/A"),
                "URL": "N/A"
            })
    except Exception as e:
        print("Error extracting hospital locations:", e)

    # Step 2: Extract URLs from `hospitalLocatorResultsList` and merge with extracted_data
    try:
        hospital_list = driver.find_elements(By.CSS_SELECTOR, "#hospitalLocatorResultsList .col-lg-4.col-md-6.mb-5")
        for hospital in hospital_list:
            try:
                name_element = hospital.find_element(By.CSS_SELECTOR, "a.recno-lookup")
                name = name_element.text.strip()
                hospital_url = name_element.get_attribute("href")

                for entry in extracted_data:
                    if entry["Name"] == name:
                        entry["URL"] = hospital_url
                        break
            except NoSuchElementException:
                continue
    except Exception as e:
        print("Error extracting hospital details:", e)

    # Step 3: Click each hospital link, extract details, then go back
    for hospital in hospital_list:
        try:
            name_element = hospital.find_element(By.CSS_SELECTOR, "a.recno-lookup")
            name_element.click()
            time.sleep(get_sleep_value())
            extracted_data = process_hospital_details(driver, extracted_data)
            breakpoint()
            time.sleep(get_sleep_value())
        except Exception as e:
            print(f"Error visiting hospital details page: {e}")
    return extracted_data




def process_hospital_details(driver, extracted_data):
    """
    Extracts additional hospital details from the individual hospital page.
    Updates the corresponding entry in extracted_data.
    """
    try:
        # Get the hospital name from the details page
        hospital_name_element = driver.find_element(By.CSS_SELECTOR, "h2.hldp_hospital_name")
        hospital_name = hospital_name_element.text.strip()

        # Find the correct hospital entry in extracted_data
        for entry in extracted_data:
            if entry["Name"] == hospital_name:
                hospital_entry = entry
                break
        else:
            print(f"Hospital '{hospital_name}' not found in extracted_data.")
            return extracted_data

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Step 1: Extract from hospitalLocatorDetailsAboveMap
        above_map = soup.find("div", id="hospitalLocatorDetailsAboveMap")
        contact_card_body = above_map.find_all('div', class_='card-body')[-1] if above_map else None
        if not contact_card_body:
            print("No 'hospitalLocatorDetailsAboveMap' section found.")
        else:
            try:
                website_element = contact_card_body.find('a', href=True, string=lambda x: x and ':' in x)
                hospital_entry["Website"] = website_element["href"].strip() if website_element else "N/A"
            except AttributeError:
                hospital_entry["Website"] = "N/A"
            try:
                phone_element = contact_card_body.find('div', string=lambda x: x and 'Phone' in x)
                hospital_entry["Phone"] = phone_element.text.strip().split(":")[-1].strip() if phone_element else "N/A"
            except AttributeError:
                hospital_entry["Phone"] = "N/A"
            try:
                email_element = contact_card_body.find('a', href=lambda href: href and "mailto:" in href)
                hospital_entry["Email"] = email_element["href"].replace("mailto:", "").strip() if email_element else "N/A"
            except AttributeError:
                hospital_entry["Email"] = "N/A"
            try:
                social_links = contact_card_body.select("ul.socials1-items a")
                hospital_entry["Social Media"] = [link["href"].strip() for link in social_links] if social_links else "N/A"
            except AttributeError:
                hospital_entry["Social Media"] = "N/A"

        # Step 2: Extract from HospitalLocatorDetailsBelowMap
        below_map = soup.find("div", id="HospitalLocatorDetailsBelowMap")
        if not below_map:
            print("No 'HospitalLocatorDetailsBelowMap' section found.")
        else:
            below_cards = below_map.find_all(class_="card")
            for card in below_cards:
                try:
                    title_element = card.find(class_="card-header")
                    title = title_element.text.strip() if title_element else "N/A"
                    if title in ('Veterinarians', 'Species Treated'):
                        ul_element = card.find_next("ul")
                        hospital_entry[title] = [li.text.strip() for li in ul_element.find_all("li")] if ul_element else []
                    elif title == 'Hospital Hours':
                        hours_table = card.find("table")
                        if hours_table:
                            hospital_entry[title] = {
                                row.find_all("td")[0].text.strip(): row.find_all("td")[1].text.strip()
                                for row in hours_table.find_all("tr")
                            }
                        else:
                            hospital_entry[title] = {}
                    elif title == "Mission":
                        mission_text = card.find_next("p")
                        hospital_entry[title] = mission_text.text.strip() if mission_text else "N/A"
                except AttributeError:
                    continue
        print(f"Extracted additional details for {hospital_name}")
        driver.back()
        return extracted_data
    except Exception as e:
        print(f"Error processing hospital details page: {e}")


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
            
        # us_df.to_excel(us_zip_path, index=False)
        time.sleep(get_sleep_value())
    
    breakpoint()
    driver.quit()
    print("Browser closed.")
    
    
if __name__ == "__main__":
    main()
