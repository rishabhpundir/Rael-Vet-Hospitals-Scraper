import re
import os
import time
import json
import psutil
import signal
import random
import logging
import platform
import traceback
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium_stealth import stealth
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from process_zipcodes import process_zip_data
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException, NoSuchElementException


# input/output files Config
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_FOLDER = os.path.join(BASE_DIR, 'logs')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'output')
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(LOGS_FOLDER, exist_ok=True)

timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = os.path.join(LOGS_FOLDER, f"scraper_log_{timestamp_str}.log")
COLUMNS = (
    "Name", "Address", "Phone", "Latitude", "Longitude", 
    "Distance", "Practice", "Website", "Email", "Social Media", 
    "Veterinarians", "Species Treated", "Hospital Hours", "Mission"
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Capture all levels of logs
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),  # Log to file
        logging.StreamHandler()  # Log to console
    ]
)

logger = logging.getLogger(__name__)


class AahaScraper:
    def setup_driver(self, retries=3):
        """Sets up an undetected ChromeDriver with improved stability and cleanup."""
        options = uc.ChromeOptions()

        # Essential Anti-Bot Flags
        # options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-ipc-flooding-protection")

        # Clean up old Chrome processes before launching a new one
        self.cleanup_chrome_processes()

        # Retry mechanism for driver initialization
        for attempt in range(retries):
            try:
                driver = uc.Chrome(options=options, use_subprocess=True)  

                # Remove "webdriver" flag
                driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
                })

                # Stealth mode
                stealth(driver,
                    languages=["en-US", "en"],
                    vendor="Google Inc.",
                    platform="Win64",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True,
                )

                logger.info("WebDriver successfully initialized.")
                return driver  # Success, return driver
                
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Failed to initialize driver - {e}")
                time.sleep(3)  # Wait before retrying

        raise Exception("Failed to initialize undetected_chromedriver after multiple attempts")


    def cleanup_chrome_processes(self):
        """Kills lingering Chrome processes to prevent memory leaks, cross-platform."""
        try:
            for process in psutil.process_iter(attrs=["pid", "name"]):
                if process.info["name"] and "chrome" in process.info["name"].lower():
                    if platform.system() == "Windows":
                        process.terminate()  # Windows-safe termination
                    else:
                        os.kill(process.info["pid"], signal.SIGTERM)  # Unix-based termination
                    logger.info(f"Terminated lingering Chrome process: PID {process.info['pid']}")
        except Exception as e:
            logger.warning(f"Error while cleaning up Chrome processes: {e}")


    def get_sleep_value(self, a=10, b=15):
        return random.uniform(a, b)


    def open_search_page(self, driver, search_url, city, state, country, max_retries=3):
        """
        Runs queries on the website, fills in search and gets results.
        If the WebDriver crashes, it automatically restarts.
        """
        logger.info(f"Searching for: {city}, {state}, {country}...")
        try:
            driver.get(search_url)
            time.sleep(self.get_sleep_value())
            search_container = driver.find_element(By.ID, "hospitalLocatorSearchCriteria")
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", search_container)
            time.sleep(self.get_sleep_value(a=5, b=8))

            # Set search radius
            city_input = driver.find_element(By.NAME, "radius")
            city_input.clear()
            city_input.send_keys("20")
            
            # Fill in the city field
            time.sleep(self.get_sleep_value(a=5, b=8))
            city_input = driver.find_element(By.NAME, "city")
            city_input.clear()
            city_input.send_keys(city)

            # Fill in the state field
            time.sleep(self.get_sleep_value(a=5, b=8))
            state_input = driver.find_element(By.NAME, "stateProvince")
            state_input.clear()
            state_input.send_keys(state)

            # Select the correct country radio button
            country_radio_id = "__BVID__87" if country == "United States" else "__BVID__88"
            country_radio = driver.find_element(By.ID, country_radio_id)
            country_radio.click()
            time.sleep(self.get_sleep_value(a=6, b=8))

            # Click the search button
            search_button = driver.find_element(By.ID, "locator-search")
            search_button.click()
            time.sleep(self.get_sleep_value(a=12, b=15))
            results_soup = BeautifulSoup(driver.page_source, "html.parser")
            list_exists = results_soup.find(id="hospitalLocatorResultsList") is not None
            if list_exists:
                logger.info(f"Results found for {city}, {state}, {country}, proceeding...")
                hospital_results = self.process_search_results(driver, results_soup)
                return hospital_results
            else:
                logger.info(f"No results found for {city}, {state}, {country}")
                return None
        except Exception as e:
            logger.error(f"Failed to search for {city}, {state}, {country}")
            return None
            

    def process_search_results(self, driver, results_soup):
        """
        Extracts search results from the page:
        - Extracts JavaScript variable `var locations` from the page source.
        - Parses it into JSON and returns structured data.
        """
        extracted_data = []
        time.sleep(self.get_sleep_value(a=12, b=15))
        try:
            # Ensure the page is fully loaded
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "hospitalLocatorResultsList")))
            page_source = driver.page_source
            match = re.search(r"var locations\s*=\s*(\[[\s\S]*?\]);", page_source)
            if not match:
                logger.error("No location data found in page source.")
                return []

            locations_json = match.group(1)
            locations = json.loads(locations_json)
            logger.info(f"JS match found --> {locations}")

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
                })
        except Exception as e:
            logger.error("Error extracting hospital locations:", e)

        # Step 2: Extract hospital names & URLs from `hospitalLocatorResultsList` and merge with extracted_data
        try:
            hospital_names = []
            hospital_list = results_soup.find("div", id="hospitalLocatorResultsList").find_all(class_='recno-lookup')
            for hospital in hospital_list:
                try:
                    name = hospital.text.strip()
                    hospital_names.append(name)
                except NoSuchElementException:
                    continue
        except Exception as e:
            logger.error("Error extracting hospital details:", e)

        # Step 3: Click each hospital link, extract details, then go back
        logger.info(f"Hospital Names : {hospital_names}")
        for hospital_name in hospital_names:
            logger.info(f"Extracting details for -> {hospital_name}...")
            try:
                time.sleep(self.get_sleep_value())
                search_container = driver.find_element(By.ID, "hospitalLocatorResultsList")
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", search_container)
                time.sleep(self.get_sleep_value(a=4, b=7))
                name_element = driver.find_element(By.XPATH, f"//a[@class='recno-lookup']//strong[text()='{hospital_name}']")
                name_element.click()
                time.sleep(self.get_sleep_value(a=4, b=7))
                extracted_data, driver = self.process_hospital_details(driver, extracted_data)
                
            except Exception as e:
                logger.error(f"Error visiting hospital details page: {e}")
        return extracted_data


    def process_hospital_details(self, driver, extracted_data):
        """
        Extracts additional hospital details from the individual hospital page.
        Updates the corresponding entry in extracted_data.
        """
        time.sleep(self.get_sleep_value(a=15, b=17))
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, "hldp_hospital_name")))
        try:
            # Get the hospital name from the details page
            hospital_name_element = driver.find_element(By.CLASS_NAME, "hldp_hospital_name")
            hospital_name = hospital_name_element.text.strip()

            # Find the correct hospital entry in extracted_data\
            for entry in extracted_data:
                if entry["Name"] == hospital_name:
                    hospital_entry = entry
                    break
            else:
                logger.error(f"Hospital '{hospital_name}' not found in extracted_data.")
                return extracted_data, driver

            soup = BeautifulSoup(driver.page_source, "html.parser")

            # Step 1: Extract from hospitalLocatorDetailsAboveMap
            above_map = soup.find("div", id="hospitalLocatorDetailsAboveMap")
            contact_card_body = above_map.find_all('div', class_='card-body')[-1] if above_map else None
            if not contact_card_body:
                logger.error("No 'hospitalLocatorDetailsAboveMap' section found.")
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
                    hospital_entry["Social Media"] = {link.text.strip(): link["href"].strip() for link in social_links} if social_links else {}
                except AttributeError:
                    hospital_entry["Social Media"] = {}

            # Step 2: Extract from HospitalLocatorDetailsBelowMap
            below_map = soup.find("div", id="HospitalLocatorDetailsBelowMap")
            if not below_map:
                logger.error("No 'HospitalLocatorDetailsBelowMap' section found.")
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
                                    row.find_all("td")[0].text.strip(): row.find_all("td")[1].text.strip() for row in hours_table.find_all("tr")
                                }
                            else:
                                hospital_entry[title] = {}
                        elif title == "Mission":
                            mission_text = card.find_next("p")
                            hospital_entry[title] = mission_text.text.strip() if mission_text else "N/A"
                    except AttributeError:
                        continue
            logger.info(f"Extracted additional details for -> {hospital_name}")
            time.sleep(self.get_sleep_value(a=2, b=4))
            driver.back()
            return extracted_data, driver
        except Exception as e:
            logger.error(f"Error processing hospital details page: {e}")
 
            
    def standardize_extracted_data(self, extracted_data):
        """
        Ensures all dictionaries in extracted_data have the same keys.
        Missing keys are added using the predefined COLUMNS tuple.
        """
        for entry in extracted_data:
            for key in COLUMNS:
                if key not in entry:
                    if key in ["Veterinarians", "Species Treated", "Social Media"]:
                        entry[key] = []
                    elif key == "Hospital Hours":
                        entry[key] = {}
                    else:
                        entry[key] = "N/A"
        return extracted_data


    def save_to_excel(self, extracted_data, filename="hospital_data"):
        """
        Saves extracted_data (list of dicts) into an Excel file.
        Converts lists and dictionaries into readable string formats.
        """
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(OUTPUT_FOLDER, f"{filename}_{timestamp_str}.xlsx")
        df = pd.DataFrame(extracted_data)
        for col in df.columns:
            df[col] = df[col].apply(lambda x: "; ".join(x) if isinstance(x, list) else str(x) if isinstance(x, dict) else x)
        df.to_excel(file_path, index=False)
        logger.info(f"Data successfully saved to : {file_path}")
 
        
    def process_country_df(self, search_url: str, df_dict: dict):
        """
        Iterates over the country's city/state dataframes and runs the scraper.
        Restarts the driver if it crashes or closes unexpectedly.
        """
        driver = self.setup_driver()
        for country, df_list in df_dict.items():
            df = df_list[0]
            df_path = df_list[1]

            for index, row in df.iterrows():
                time.sleep(self.get_sleep_value(a=1, b=3))
                driver.maximize_window()
                time.sleep(self.get_sleep_value(a=1, b=3))
                driver.execute_script("window.focus();")
                success = False
                if row['Data'].strip() in ("added", "not found"):
                    continue
                city, state = row["City"], row["State"]
                logger.info("*" * 50)
                logger.info(f"{index}. --> {city}, {state}")

                # Check if driver is still active
                if driver is None or not driver.session_id:
                    logger.warning("WebDriver session is invalid or closed. Restarting driver...")
                    if driver is not None:
                        driver.quit()
                    driver = self.setup_driver()
                    time.sleep(self.get_sleep_value(a=1, b=3))
                    driver.maximize_window()
                    time.sleep(self.get_sleep_value(a=1, b=3))
                    driver.execute_script("window.focus();")
                    if not driver:
                        logger.error("Failed to restart driver. Skipping iteration.")
                        continue
                try:
                    extracted_data = self.open_search_page(driver, search_url, city, state, country)
                    if extracted_data:
                        uniform_data = self.standardize_extracted_data(extracted_data)
                        self.save_to_excel(uniform_data, filename=f"{city}_{state}")
                        df.at[index, "Data"] = "added"
                    else:
                        df.at[index, "Data"] = "not found"
                    success = True
                except KeyboardInterrupt:
                    logger.warning("Script interrupted manually. Skipping save operation.")
                    raise
                except Exception as e:
                    logger.error(f"Error while processing {city}, {state}: {e}")
                    df.at[index, "Data"] = "error"
                finally:
                    if success or df.at[index, "Data"] in ("not found", "error"):
                        df.to_excel(df_path, index=False)
                        time.sleep(3)

        # Ensure driver is closed after the loop ends
        if driver:
            driver.quit()


    def scraper(self):
        """
        initialises the scraper by reading processed input files from zipcodes.
        """
        try:
            search_url = "https://www.aaha.org/for-pet-parents/find-an-aaha-accredited-animal-hospital-near-me/"
            us_zip_path, can_zip_path = process_zip_data()
            us_df = pd.read_excel(us_zip_path)
            can_df = pd.read_excel(can_zip_path)
            us_df["Data"] = us_df["Data"].astype("object").fillna("")
            can_df["Data"] = us_df["Data"].astype("object").fillna("")
            df_dict = {"United States": [us_df, us_zip_path], "Canada": [can_df, can_zip_path]}
            self.process_country_df(search_url=search_url, df_dict=df_dict)
            logger.info("Browser closed.")
        except Exception as e:
            logger.exception(f"Error while scraping data : \n\n{traceback.format_exc()}")
        
    
if __name__ == "__main__":
    aaha_scraper = AahaScraper()
    aaha_scraper.scraper()




