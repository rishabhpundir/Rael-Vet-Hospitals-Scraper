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
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),  # Log to file
        logging.StreamHandler()  # Log to console
    ]
)

logger = logging.getLogger(__name__)


class AahaScraper:
    def __init__(self):
        self.search_url = "https://www.aaha.org/for-pet-parents/find-an-aaha-accredited-animal-hospital-near-me/"
        self.extracted_data = []
        self.hospital_names = []
        self.driver = None
        self.city = ""
        self.state = ""
        self.country = ""

    def get_driver(self):
        """Initializes or reinitializes the ChromeDriver if necessary."""
        options = uc.ChromeOptions()
        
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.88 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.88 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.88 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.88 Mobile Safari/537.36",
            "Mozilla/5.0 (iPad; CPU OS 16_5 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.88 Mobile Safari/537.36"
        ]

        # Pick a random User-Agent
        random_user_agent = random.choice(user_agents)
        proxy = None
        
        # Essential Anti-Bot Flags
        # options.add_argument("--headless=new")
        options.add_argument(f"user-agent={random_user_agent}")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-infobars")
        options.add_argument("--enable-javascript")
        options.add_argument('--disable-extensions')
        options.add_argument("--window-size=800,450")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-popup-blocking")
        # options.add_argument(f"--proxy-server={self.proxy}")
        options.add_argument("--disable-ipc-flooding-protection")
        options.add_argument("--js-flags=--max-old-space-size=1024")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-blink-features=AutomationControlled")

        if self.driver is None:
            for attempt in range(0, 3):
                try:
                    self.driver = uc.Chrome(options=options, use_subprocess=True)

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
                    logger.info(f"Current Browser version ---> {self.driver.capabilities['browserVersion']}")
                    logger.info(f"Chrome Driver's version ---> {self.driver.capabilities['chrome']['chromedriverVersion'].split(' ')[0]}")
                    break  # Exit loop on success
                except Exception as e:
                    logger.error(f"Attempt {attempt + 1}: Failed to initialize driver - {e}")
                    time.sleep(3)
            else:
                raise Exception("Failed to initialize undetected_chromedriver after multiple attempts")
            
        time.sleep(self.get_sleep_value(a=1, b=3))
        self.driver.maximize_window()
        time.sleep(self.get_sleep_value(a=1, b=3))
        self.driver.execute_script("window.focus();")
        return self.driver


    def close_driver(self):
        """Closes the driver if it is initialized."""
        if self.driver is not None:
            self.driver.quit()
            self.driver = None
            logger.info("WebDriver successfully closed.")


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


    def get_sleep_value(self, a=18, b=22):
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
            time.sleep(self.get_sleep_value(a=3, b=5))
            search_radius = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "radius"))
            )
            search_radius.clear()
            search_radius.send_keys(miles)
            
            # City field
            time.sleep(self.get_sleep_value(a=2, b=4))
            city_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "city"))
            )
            city_input.clear()
            city_input.send_keys(self.city)

            # State field
            time.sleep(self.get_sleep_value(a=3, b=5))
            state_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "stateProvince"))
            )
            state_input.clear()
            state_input.send_keys(self.state)

            # Country radio button
            time.sleep(self.get_sleep_value(a=2, b=5))
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
            
            if not refresh:
                if "Please refine your search criteria" in hospital_locator or "You are here" in hospital_locator:
                    status = "Yes!" if "You are here" in hospital_locator else "No"
                    logger.info(f"{status} results found for {self.city}, {self.state}, {self.country}")
                    return True, status
                elif "we could not verify your request" in hospital_locator:
                    logger.info(f"Couldn't search for {self.city}, {self.state}, {self.country}, retrying...")
                    return False, None
                else:
                    raise
            else:
                if "try again" in hospital_locator:
                    logger.info(f"No results found for {self.city}, {self.state}, {self.country}")
                    return ""
                return "refreshed!"
        except Exception as e:
            logger.error(f"Failed!! while searching for {self.city}, {self.state}, {self.country}")
            return False, None
        
    
    def refresh_search_results(self):
        refreshed = ""
        self.close_driver()
        time.sleep(self.get_sleep_value())
        self.driver = self.get_driver()
        while refreshed != "refreshed!":
            time.sleep(self.get_sleep_value(a=7, b=10))
            refreshed = self.open_search_page(refresh=True)
        return refreshed
            

    def process_search_results(self):
        """
        Extracts search results from the page:
        - Extracts JavaScript variable `var locations` from the page source.
        - Parses it into JSON and returns structured data.
        """
        try:
            results_soup = BeautifulSoup(self.driver.page_source, "html.parser")
            time.sleep(self.get_sleep_value(a=2, b=3))
            
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "hospitalLocatorResultsList"))
            )

            page_source = self.driver.page_source
            match = re.search(r"var locations\s*=\s*(\[[\s\S]*?\]);", page_source)
            time.sleep(self.get_sleep_value(a=1, b=2))
            if not match:
                logger.error("No location data found in page source.")
                return []

            locations_json = match.group(1)
            locations = json.loads(locations_json)
            logger.info(f"JS match found --> {locations}")
            time.sleep(self.get_sleep_value(a=1, b=2))

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

            hospital_list = results_soup.find("div", id="hospitalLocatorResultsList").find_all(class_='recno-lookup')
            for hospital in hospital_list:
                try:
                    name = hospital.text.strip()
                    self.hospital_names.append(name)
                except NoSuchElementException:
                    continue

            time.sleep(self.get_sleep_value(a=1, b=2))
            logger.info(f"Hospital Names : {self.hospital_names}")
            return True
        
        except Exception as e:
            logger.error(f"Error extracting data from search results : {e}")
            return False


    def extract_from_pages(self): 
        wait_time = 10
        
        # Extract hospitals in batch of 5
        for index, hospital_name in enumerate(self.hospital_names, start=1):
            if index % 5 == 0:
                self.refresh_search_results()
                time.sleep(self.get_sleep_value(a=3, b=5))

            logger.info(f"Extracting details for --> {hospital_name}...")
            max_retries = 3
            attempts = 0
            result = False
            while not result and attempts <= max_retries:
                try:
                    time.sleep(self.get_sleep_value())
                    WebDriverWait(self.driver, wait_time).until(
                        EC.presence_of_element_located((By.ID, "hospitalLocatorResultsList"))
                    )
                    
                    time.sleep(self.get_sleep_value(a=5, b=7))
                    name_element = WebDriverWait(self.driver, wait_time).until(
                        EC.presence_of_element_located((By.XPATH, f"//a[contains(@class, 'recno-lookup')]/strong[contains(text(), '{hospital_name.strip()}')]"))
                    )
                    
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center', inline: 'nearest'});", name_element)
                    
                    time.sleep(self.get_sleep_value(a=5, b=7))
                    self.driver.execute_script("arguments[0].click();", name_element)
                    
                    result = self.process_hospital_page(hospital_name=hospital_name)
                    
                except Exception as e:
                    logger.error(f"Error visiting hospital details page: {e}")
                    
                logger.info(f"Extraction status ---> {result}")
                time.sleep(self.get_sleep_value(a=7, b=10))
                
                if result:
                    self.driver.back()
                    WebDriverWait(self.driver, wait_time).until(
                        EC.presence_of_element_located((By.ID, "hospitalLocatorResults"))
                    )
                    time.sleep(self.get_sleep_value())
                else:
                    logger.info(f"re-trying to fetch {hospital_name} details...")
                    self.refresh_search_results()
                    
                attempts += 1
            gc.collect()
        return True


    def process_hospital_page(self, hospital_name):
        """
        Extracts additional hospital details from the individual hospital page.
        Updates the corresponding entry in extracted_data.
        """
        time.sleep(self.get_sleep_value(a=10, b=12))
        
        WebDriverWait(self.driver, 10).until(
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
 
            
    def standardize_data(self, extracted_data):
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
        self.hospital_names = []
        self.city = ""
        self.state = ""
        self.country = ""
        logger.info(f"Data successfully saved to : {file_path}")
 
        
    def process_country_df(self, df_dict: dict):
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
                logger.info("*" * 50)
                logger.info(f"{index + 1}. --> {self.city}, {self.state}")

                # Check if driver is still active
                if self.driver is None or not self.driver.session_id:
                    logger.warning("WebDriver session is invalid or closed. Restarting driver...")
                    self.close_driver()
                    self.driver = self.get_driver()
                    time.sleep(self.get_sleep_value(a=1, b=3))

                    if not self.driver:
                        logger.error("Failed to restart driver. Skipping iteration.")
                        continue
                try:
                    attempts = 0
                    max_tries = 3
                    while attempts <= max_tries and not success:
                        success, status = self.open_search_page()
                        if success and status == "Yes!":
                            success = self.process_search_results()
                            if success:
                                success = self.extract_from_pages()
                                if success:
                                    uniform_data = self.standardize_data(extracted_data=self.extracted_data)
                                    self.save_to_excel(extracted_data=uniform_data)
                                    df.at[index, "Data"] = "added"
                        else:
                            df.at[index, "Data"] = "not found"
                        attempts += 1
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
                self.close_driver()
                gc.collect()


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
            self.process_country_df(df_dict=df_dict)
            logger.info("Browser closed.")
        except Exception as e:
            logger.exception(f"Error while scraping data : \n\n{traceback.format_exc()}")
        
    
if __name__ == "__main__":
    aaha_scraper = AahaScraper()
    aaha_scraper.scraper()




