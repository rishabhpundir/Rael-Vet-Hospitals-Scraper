import re
import os
import gc
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
from selenium_stealth import stealth
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from process_zipcodes import process_zip_data
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support import expected_conditions as EC


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
    def __init__(self):
        """Sets up an undetected ChromeDriver with improved stability and cleanup."""
        self.options = uc.ChromeOptions()
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.88 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.88 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.88 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.88 Mobile Safari/537.36",
            "Mozilla/5.0 (iPad; CPU OS 16_5 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.88 Mobile Safari/537.36"
        ]

        # Pick a random User-Agent
        self.random_user_agent = random.choice(self.user_agents)
        
        # Essential Anti-Bot Flags
        # self.options.add_argument("--headless=new")
        self.options.add_argument(f"user-agent={self.random_user_agent}")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-gpu")
        self.options.add_argument("--start-maximized")
        self.options.add_argument("--disable-infobars")
        self.options.add_argument("--enable-javascript")
        self.options.add_argument('--disable-extensions')
        self.options.add_argument("--disable-notifications")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--disable-popup-blocking")
        self.options.add_argument("--disable-ipc-flooding-protection")
        self.options.add_argument("--js-flags=--max-old-space-size=1024")
        self.options.add_argument("--disable-background-timer-throttling")
        self.options.add_argument("--disable-blink-features=AutomationControlled")

        # Clean up old Chrome processes before launching a new one
        # self.cleanup_chrome_processes()

        # Retry mechanism for driver initialization
        for attempt in range(0, 3):
            try:
                self.driver = uc.Chrome(options=self.options, use_subprocess=True)

                # Remove "webdriver" flag
                self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
                })

                # Apply stealth settings
                stealth(self.driver,
                    languages=["en-US", "en"],
                    vendor="Google Inc." if platform.system() != "Darwin" else "Apple Computer, Inc.",
                    platform="Win64" if platform.system() != "Darwin" else "MacIntel",
                    webgl_vendor="Intel Inc." if platform.system() != "Darwin" else "Apple Inc.",
                    renderer="Intel Iris OpenGL Engine" if platform.system() != "Darwin" else "Apple M1",
                    fix_hairline=True,
                )

                logger.info("WebDriver successfully initialized.")
                self.extracted_data = []
                self.search_url = "https://www.aaha.org/for-pet-parents/find-an-aaha-accredited-animal-hospital-near-me/"
                self.city = ""
                self.state = ""
                self.country = ""

                logger.info(f"Current Browser version ---> {self.driver.capabilities['browserVersion']}")
                logger.info(f"Chrome Driver's version ---> {self.driver.capabilities['chrome']['chromedriverVersion'].split(' ')[0]}")
                break  # Exit loop on success
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Failed to initialize driver - {e}")
                time.sleep(3)
        else:
            raise Exception("Failed to initialize undetected_chromedriver after multiple attempts")


    def cleanup_chrome_processes(self):
        """Kills lingering Chrome processes to prevent memory leaks, cross-platform."""
        try:
            for process in psutil.process_iter(attrs=["pid", "name"]):
                if process.info["name"] and "chrome" in process.info["name"].lower():
                    if platform.system() == "Windows":
                        process.terminate()
                    else:
                        os.kill(process.info["pid"], signal.SIGTERM) 
                    logger.info(f"Terminated lingering Chrome process: PID {process.info['pid']}")
        except Exception as e:
            logger.warning(f"Error while cleaning up Chrome processes: {e}")


    def get_sleep_value(self, a=18, b=21):
        return random.uniform(a, b)


    def open_search_page(self, refresh=False, miles="20"):
        """
        Runs queries on the website, fills in search and gets results.
        If the WebDriver crashes, it automatically restarts.
        """
        logger.info(f"Searching for: {self.city}, {self.state}, {self.country}...")
        try:
            self.driver.get(self.search_url)
            time.sleep(self.get_sleep_value(a=8, b=10))
            search_container = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "hospitalLocatorSearchCriteria"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", search_container)

            # Search radius
            time.sleep(self.get_sleep_value(a=8, b=10))
            search_radius = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "radius"))
            )
            search_radius.clear()
            search_radius.send_keys(miles)
            
            # City field
            time.sleep(self.get_sleep_value(a=8, b=10))
            city_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "city"))
            )
            city_input.clear()
            city_input.send_keys(self.city)

            # State field
            time.sleep(self.get_sleep_value(a=8, b=10))
            state_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "stateProvince"))
            )
            state_input.clear()
            state_input.send_keys(self.state)

            # Country radio button
            time.sleep(self.get_sleep_value(a=8, b=10))
            country_radio_id = "__BVID__87" if self.country == "United States" else "__BVID__88"
            country_radio = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, country_radio_id))
            )
            country_radio.click()

            # Click Search
            time.sleep(self.get_sleep_value(a=8, b=11))
            search_button = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "locator-search"))
            )
            search_button.click()

            time.sleep(self.get_sleep_value())
            hospital_locator = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "hospital-locator"))
            ).text.strip()
            
            if "try again" in hospital_locator:
                logger.info(f"No results found for {self.city}, {self.state}, {self.country}")
                return None
            elif "You are here" in hospital_locator:
                results_soup = BeautifulSoup(self.driver.page_source, "html.parser")
                logger.info(f"Results found for {self.city}, {self.state}, {self.country}, proceeding...")
                if not refresh:
                    hospital_results = self.process_search_results(results_soup)
                    return hospital_results
                else:
                    return "refreshed!"
            else:
                raise
        except Exception as e:
            logger.error(f"Failed searching for {self.city}, {self.state}, {self.country}")
            return None
            

    def process_search_results(self, results_soup):
        """
        Extracts search results from the page:
        - Extracts JavaScript variable `var locations` from the page source.
        - Parses it into JSON and returns structured data.
        """
        try:
            # Ensure the page is fully loaded
            hospital_locator_results_list = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "hospitalLocatorResultsList"))
            )
            page_source = self.driver.page_source
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
                self.extracted_data.append({
                    "Name": loc.get("name", "N/A").strip(),
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
        wait_time = 20
        for index, hospital_name in enumerate(hospital_names, start=1):
            if index % 4 == 0 and wait_time <= 45:
                wait_time += 4
                logger.info(f"Wait time increased to --> {wait_time}")
                
            extracted = False
            logger.info(f"Extracting details for --> {hospital_name}...")
            max_retries = 3
            attempts = 0
            result = False
            while not result and attempts <= max_retries:
                try:
                    time.sleep(self.get_sleep_value())
                    hospital_locator_results_list = WebDriverWait(self.driver, wait_time).until(
                        EC.presence_of_element_located((By.ID, "hospitalLocatorResultsList"))
                    )
                    
                    time.sleep(self.get_sleep_value())
                    name_element = WebDriverWait(self.driver, wait_time).until(
                        EC.presence_of_element_located((By.XPATH, f"//a[contains(@class, 'recno-lookup')]/strong[contains(text(), '{hospital_name.strip()}')]"))
                    )
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center', inline: 'nearest'});", name_element)
                    time.sleep(self.get_sleep_value())
                    self.driver.execute_script("arguments[0].click();", name_element)
                    result = self.process_hospital_details(hospital_name=hospital_name)
                except Exception as e:
                    logger.error(f"Error visiting hospital details page: {e}")
                    
                logger.info(f"Extraction status ---> {result}")
                time.sleep(self.get_sleep_value())
                if result:
                    self.driver.back()
                    WebDriverWait(self.driver, wait_time).until(
                        EC.presence_of_element_located((By.ID, "hospitalLocatorResults"))
                    )
                    time.sleep(self.get_sleep_value())
                else:
                    logger.info(f"re-trying to fetch {hospital_name} details...")
                    if attempts == 0:
                        self.driver.quit()
                        time.sleep(self.get_sleep_value(a=45, b=60))
                        self.driver = uc.Chrome(options=self.options, use_subprocess=True)
                    refresh_att = 3
                    current_att = 0
                    refreshed = "Search not refreshed yet!"
                    while refreshed != "refreshed!" and current_att <= refresh_att:
                        time.sleep(self.get_sleep_value(a=30, b=60))
                        refreshed = self.open_search_page(refresh=True)
                        logger.info(refreshed)
                        current_att += 1
                attempts += 1
                gc.collect()
        return self.extracted_data


    def process_hospital_details(self, hospital_name):
        """
        Extracts additional hospital details from the individual hospital page.
        Updates the corresponding entry in extracted_data.
        """
        time.sleep(self.get_sleep_value(a=20, b=25))
        WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.ID, "hospitalLocatorDetailsAboveMap"))
        )
        try:
            # Find the correct hospital entry in extracted_data
            hospital_entry = None
            for entry in self.extracted_data:
                if entry["Name"].strip() == hospital_name.strip():
                    hospital_entry = entry
                    break
            if not hospital_entry:
                raise Exception(f"Hospital '{hospital_name}' not found in extracted_data.")

            hospital_details_soup = BeautifulSoup(self.driver.page_source, "html.parser")

            # Step 1: Extract from hospitalLocatorDetailsAboveMap
            above_map = hospital_details_soup.find("div", id="hospitalLocatorDetailsAboveMap")
            contact_card_body = above_map.find_all('div', class_='card-body')[-1] if above_map else None
            if not contact_card_body:
                raise Exception("No 'hospitalLocatorDetailsAboveMap' section found.")
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
            below_map = hospital_details_soup.find("div", id="HospitalLocatorDetailsBelowMap")
            if not below_map:
                raise Exception("No 'HospitalLocatorDetailsBelowMap' section found.")
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
            return True
        except Exception as e:
            logger.error(f"Error processing hospital details page: {e}")
        return False
 
            
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


    def save_to_excel(self, extracted_data):
        """
        Saves extracted_data (list of dicts) into an Excel file.
        Converts lists and dictionaries into readable string formats.
        """
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(OUTPUT_FOLDER, f"{self.city}_{self.state}_{timestamp_str}.xlsx")
        df = pd.DataFrame(extracted_data)
        for col in df.columns:
            df[col] = df[col].apply(lambda x: "; ".join(x) if isinstance(x, list) else str(x) if isinstance(x, dict) else x)
        df.insert(0, 'State', self.state)
        df.insert(1, 'City', self.city.title())
        df.to_excel(file_path, index=False)
        self.extracted_data = []
        self.city = ""
        self.state = ""
        self.country = ""
        logger.info(f"Data successfully saved to : {file_path}")
 
        
    def process_country_df(self, search_url: str, df_dict: dict):
        """
        Iterates over the country's city/state dataframes and runs the scraper.
        Restarts the driver if it crashes or closes unexpectedly.
        """
        for country, df_list in df_dict.items():
            df = df_list[0]
            df_path = df_list[1]
            zip_folder = os.path.join(BASE_DIR, 'zipcodes')
            us_city_backup_path = os.path.join(zip_folder, f'{country}_Processed_Backup.xlsx')
            for index, row in df.iterrows():
                df.to_excel(us_city_backup_path, index=False)
                success = False
                self.country = country
                self.city, self.state = row["City"], row["State"]
                if row['Data'].strip() in ("added", "not found"):
                    continue
                time.sleep(self.get_sleep_value(a=1, b=3))
                self.driver.maximize_window()
                time.sleep(self.get_sleep_value(a=1, b=3))
                self.driver.execute_script("window.focus();")
                logger.info("*" * 50)
                logger.info(f"{index + 1}. --> {self.city}, {self.state}")

                # Check if driver is still active
                if self.driver is None or not self.driver.session_id:
                    logger.warning("WebDriver session is invalid or closed. Restarting driver...")
                    if self.driver is not None:
                        self.driver.quit()
                    self.driver = uc.Chrome(options=self.options, use_subprocess=True)  
                    time.sleep(self.get_sleep_value(a=1, b=3))
                    self.driver.maximize_window()
                    time.sleep(self.get_sleep_value(a=1, b=3))
                    self.driver.execute_script("window.focus();")
                    if not self.driver:
                        logger.error("Failed to restart driver. Skipping iteration.")
                        continue
                try:
                    extracted_data = self.open_search_page()
                    if extracted_data:
                        uniform_data = self.standardize_extracted_data(extracted_data=extracted_data)
                        self.save_to_excel(extracted_data=uniform_data)
                        df.at[index, "Data"] = "added"
                    else:
                        df.at[index, "Data"] = "not found"
                    success = True
                except KeyboardInterrupt:
                    logger.warning("Script interrupted manually. Skipping save operation.")
                    raise
                except Exception as e:
                    logger.error(f"Error while processing {self.city}, {self.state}: {e}")
                    df.at[index, "Data"] = "error"
                finally:
                    if success or df.at[index, "Data"] in ("not found", "error"):
                        df.to_excel(df_path, index=False)
                        time.sleep(3)
                gc.collect()
            gc.collect()

        # Ensure driver is closed after the loop ends
        if self.driver:
            self.driver.quit()


    def scraper(self):
        """
        initialises the scraper by reading processed input files from zipcodes.
        """
        try:
            us_zip_path, can_zip_path = process_zip_data()
            us_df = pd.read_excel(us_zip_path)
            can_df = pd.read_excel(can_zip_path)
            us_df["Data"] = us_df["Data"].astype("object").fillna("")
            can_df["Data"] = us_df["Data"].astype("object").fillna("")
            df_dict = {"United States": [us_df, us_zip_path], "Canada": [can_df, can_zip_path]}
            self.process_country_df(search_url=self.search_url, df_dict=df_dict)
            logger.info("Browser closed.")
        except Exception as e:
            logger.exception(f"Error while scraping data : \n\n{traceback.format_exc()}")
        
    
if __name__ == "__main__":
    aaha_scraper = AahaScraper()
    aaha_scraper.scraper()




