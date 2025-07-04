import re
import os
import gc
import time
import json
import random
import logging
import platform
import traceback
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from utils import get_input_files
from selenium_stealth import stealth
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC


# input/output files Config
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROXY_PATH = os.path.join(BASE_DIR, os.path.join('proxy', 'auth.zip'))
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
        self.random_sites = ["https://1mb.club/", "http://bettermotherfuckingwebsite.com/", 
                             "https://t0.vc/", "https://motherfuckingwebsite.com/"]
        self.extracted_data = []
        self.hospital_names = []
        self.driver = None
        self.city = ""
        self.state = ""
        self.country = ""
        self.headless = False


    def is_raspberry_pi(self):
        try:
            machine = os.uname().machine
            return machine.startswith("arm") or machine.startswith("aarch64")
        except AttributeError:
            return False


    def get_driver(self):
        """Initializes the WebDriver using the official ChromiumDriver."""
        if self.driver is None:
            for attempt in range(3):
                try:
                    options = webdriver.ChromeOptions()
                    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
                    "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
                    if self.is_raspberry_pi():
                        # Use Chromium on Raspberry Pi
                        user_agent ="Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 " \
                        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                        chromium_path = "/usr/bin/chromium-browser"
                        chromedriver_path = "/usr/bin/chromedriver"
                        options.binary_location = chromium_path
                        logger.info("Running on Raspberry Pi (ARM). Using Chromium.")
                        service = Service(chromedriver_path)
                    else:
                        # Use Chrome on non-ARM systems
                        logger.info("Running on non-ARM system. Using Chrome.")
                        service = Service()  # Uses default chromedriver in PATH

                    # --- Anti-Bot & Performance Settings ---
                    if self.headless:
                        options.add_argument("--headless=new")

                    # options.add_extension(f"{PROXY_PATH}")
                    options.add_argument("--disable-infobars")
                    options.add_argument(f"user-agent={user_agent}")
                    options.add_argument("--disable-dev-shm-usage")
                    options.add_argument("--force-major-version-to-minor")
                    options.add_argument("--enable-features=UserAgentClientHint")
                    options.add_argument("--disable-blink-features=AutomationControlled")
                    

                    # --- Initialize WebDriver ---
                    self.driver = webdriver.Chrome(service=service, options=options)
                    self.driver.set_page_load_timeout(180)
                    self.driver.execute_cdp_cmd("Network.enable", {})
                    
                    # --- Stealth & WebDriver Evasion ---
                    self.driver.execute_cdp_cmd(
                        "Page.addScriptToEvaluateOnNewDocument",
                        {
                            "source": r"""
                                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                                Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                                Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
                            """
                        }
                    )

                    logger.info(f"User Agent: {user_agent}")
                    if not self.headless:
                        logger.info("Adding stealth settings...")
                        languages = ["en-US", "en"]
                        vendor = "WebKit" if platform.system() != "Linux" else "WebKit"
                        platform_ = "Win32" if platform.system() != "Linux" else "Linux x86_64"
                        webgl_vendor = "WebKit" if platform.system() != "Linux" else "WebKit"
                        renderer = "WebKit WebGL" if platform.system() != "Linux" else  "WebKit WebGL"
                        
                        logger.info(f"Vendor: {vendor} Platform: {platform_} WebGL: {webgl_vendor} Renderer: {renderer}")
                        stealth(
                            self.driver,
                            languages=languages,
                            vendor=vendor,
                            platform=platform_,
                            webgl_vendor=webgl_vendor,
                            renderer=renderer,
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

        return self.driver


    def close_driver(self):
        """Closes the driver if it is initialized."""
        if self.driver is not None:
            self.driver.quit()
            self.driver = None
            logger.info("WebDriver successfully closed.")


    def mouse_moves(self):
        """
        Simulate human-like mouse movements and add random key presses.
        """
        # Only attempt these 'human-like' actions if not headless
        if not self.headless:
            actions = ActionChains(self.driver)
            
            # Random small move offset
            a = random.randint(10, 30)
            b = random.randint(10, 30)
            c = random.randint(80, 95)

            # 1) Random offset move
            actions.move_by_offset(a, b).perform()
            time.sleep(self.get_sleep_value(a=0.5, b=0.7))

            # 2) Scroll down
            self.driver.execute_script(f"window.scrollBy(0, {c});")
            time.sleep(self.get_sleep_value(a=0.5, b=0.7))

            # 3) Scroll up
            self.driver.execute_script(f"window.scrollBy(0, -{c});")
            time.sleep(self.get_sleep_value(a=0.5, b=0.7))

            # 4) Move to <body> element
            element = self.driver.find_element(By.TAG_NAME, "body")
            actions.move_to_element(element).perform()
            time.sleep(self.get_sleep_value(a=0.5, b=0.7))

            # 5) Random key presses to look more "human"
            possible_keys = [Keys.ARROW_DOWN, Keys.ARROW_UP, 
                             Keys.ARROW_LEFT, Keys.ARROW_RIGHT]
            
            # We'll do up to 3 random key presses:
            for _ in range(random.randint(1, 3)):
                key_to_press = random.choice(possible_keys)
                actions.send_keys(key_to_press).perform()
                time.sleep(self.get_sleep_value(a=0.2, b=0.5))

        # A small pause at the end, whether headless or not
        time.sleep(self.get_sleep_value(a=1, b=1.5))


    def visit_random_sites(self):
        if not self.headless:
            time.sleep(self.get_sleep_value(a=1, b=2))
            self.driver.maximize_window()
            self.driver.execute_script("window.focus();")

        time.sleep(self.get_sleep_value(a=1, b=1.5))
        random.shuffle(self.random_sites)
        for site in self.random_sites[:2]:
            self.driver.get(site)
            time.sleep(self.get_sleep_value(a=1, b=1.5))


    def get_sleep_value(self, a=16, b=20):
        return random.uniform(a, b)


    def open_search_page(self, refresh=False, miles="20"):
        """
        Runs queries on the website, fills in search and gets results.
        If the WebDriver crashes, it automatically restarts.
        """
        logger.info(f"Searching for: {self.city}, {self.state}, {self.country}...")

        try:
            self.driver.get(self.search_url)

            # Get search page
            time.sleep(self.get_sleep_value(a=5, b=8))
            search_container = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "hospitalLocatorSearchCriteria"))
            )
            self.mouse_moves()  
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", search_container)

            # Set Search radius
            time.sleep(self.get_sleep_value(a=1, b=2))
            search_radius = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "radius"))
            )
            search_radius.clear()
            search_radius.send_keys(miles)

            # City field
            time.sleep(self.get_sleep_value(a=1, b=2))
            city_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "city"))
            )
            city_input.clear()
            city_input.send_keys(self.city)

            # State field
            self.mouse_moves()
            time.sleep(self.get_sleep_value(a=2, b=3))
            state_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "stateProvince"))
            )
            state_input.clear()
            state_input.send_keys(self.state)

            # Country radio button
            self.mouse_moves()
            time.sleep(self.get_sleep_value(a=1, b=2))
            country_radio_id = "__BVID__87" if self.country == "United States" else "__BVID__88"
            country_radio = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, country_radio_id))
            )
            self.driver.execute_script("arguments[0].click();", country_radio)

            # Submit from by clicking "Search" button
            time.sleep(self.get_sleep_value(a=1, b=2))
            search_button = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "locator-search"))
            )
            self.driver.execute_script("arguments[0].click();", search_button)

            # check search results page
            time.sleep(self.get_sleep_value(a=8, b=12))
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
            logger.error(f"Failed!! while searching for {self.city}, {self.state}, {self.country} : \n {e}")
            return False, None

        
    def refresh_search_results(self):
        refreshed = ""
        self.close_driver()
        time.sleep(self.get_sleep_value())
        self.driver = self.get_driver()
        max_attempts = 3
        attempts = 0
        while refreshed != "refreshed!" and attempts <= max_attempts:
            time.sleep(self.get_sleep_value(a=7, b=10))
            refreshed = self.open_search_page(refresh=True)
            attempts += 1
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

            json_data = match.group(1)
            locations = json.loads(json_data)
            json_saved = self.save_locations_json_data(json_data=json_data)
            logger.info(f"{json_saved}")
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
            logger.info(f"Facility Names : ")
            logger.info("=" * 20)
            for index, hospital_value in enumerate(self.hospital_names, start=1):
                logger.info(f"{index}. {hospital_value}")
            return True
        
        except Exception as e:
            logger.error(f"Error extracting data from search results : {e}")
            return False


    def extract_from_pages(self): 
        wait_time = 10
        
        # Extract hospitals in batch of 5
        for index, hospital_name in enumerate(self.hospital_names, start=1):
            logger.info('-' * 30)
            logger.info(f"{index}. Extracting details for --> {hospital_name}...")
            max_retries = 3
            attempts = 0
            result = False
            while not result and attempts <= max_retries:
                try:
                    time.sleep(self.get_sleep_value(a=4, b=5))
                    WebDriverWait(self.driver, wait_time).until(
                        EC.presence_of_element_located((By.ID, "hospitalLocatorResultsList"))
                    )
                    
                    time.sleep(self.get_sleep_value(a=3, b=4))
                    name_element = WebDriverWait(self.driver, wait_time).until(
                        EC.presence_of_element_located(
                            (By.XPATH, f"""//a[contains(@class, "recno-lookup")]/strong[contains(text(), "{hospital_name.strip()}")]""")
                        )
                    )
                    self.mouse_moves()
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center', inline: 'nearest'});", name_element)
                    
                    time.sleep(self.get_sleep_value(a=2, b=3))
                    self.driver.execute_script("arguments[0].click();", name_element)
                    
                    result = self.process_hospital_page(hospital_name=hospital_name)
                    
                except Exception as e:
                    logger.error(f"Error visiting hospital details page: {e}")
                    
                logger.info(f"Extraction status ---> {result}")
                time.sleep(self.get_sleep_value(a=3, b=5))
                
                if result:
                    self.driver.back()
                    WebDriverWait(self.driver, wait_time).until(
                        EC.presence_of_element_located((By.ID, "hospitalLocatorResults"))
                    )
                    time.sleep(self.get_sleep_value(a=3, b=5))
                else:
                    logger.info(f"Refreshing search results... to continue with -->  {hospital_name}")
                    self.refresh_search_results()
                    time.sleep(self.get_sleep_value(a=2, b=3))
                    
                attempts += 1
            gc.collect()
        return True


    def process_hospital_page(self, hospital_name):
        """
        Extracts additional hospital details from the individual hospital page.
        Updates the corresponding entry in extracted_data.
        """
        time.sleep(self.get_sleep_value(a=3, b=5))
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


    def save_locations_json_data(self, json_data):
        """
        To save the initial location data from search results page into a JSON file.
        """
        # Ensure the directory exists
        date_stamp = datetime.now().strftime('%Y%m%d')
        file_path = os.path.join(os.path.join(OUTPUT_FOLDER, 'json'), f"locations_json_{date_stamp}.json")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Load existing data if file exists or start with an empty dictionary
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    existing_data = json.load(file)
            except (json.JSONDecodeError, IOError):
                existing_data = {}
        else:
            existing_data = {}

        # Ensure json_data is properly formatted
        if isinstance(json_data, str):
            try:
                json_data = json.loads(json_data)
            except json.JSONDecodeError:
                pass

        # Save the updated data back to the file
        key = f'{self.city}_{self.state}'
        existing_data[key] = json_data
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(existing_data, file, indent=4)
        
        return f"Success! Locations JSON data saved to --> {file_path}"


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
            city_backup_path = os.path.join(zip_folder, f'{country}_Backup.xlsx')
            for index, row in df.iterrows():
                df.to_excel(city_backup_path, index=False)
                success = False
                self.country = country
                self.city, self.state = row["City"], row["State"]

                if str(row['Data']).strip() in ("added", "not found"):
                    continue

                time.sleep(self.get_sleep_value(a=1, b=3))
                logger.info("*" * 50)
                logger.info(f"{index + 1}. --> {self.city}, {self.state}")

                # Check if driver is still active
                if self.driver is None or not self.driver.session_id:
                    logger.warning("Web driver is not initialised. Restarting it...")
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
                        time.sleep(self.get_sleep_value(a=8, b=10))
                        self.visit_random_sites()
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


    def scraper(self, headless):
        """
        initialises the scraper by reading processed input files from zipcodes.
        """
        self.headless = headless
        try:
            file_paths = get_input_files()
            with pd.ExcelFile(file_paths[0], engine="openpyxl") as xls:
                sheets_dict = pd.read_excel(xls, sheet_name=None)

            df_dict = {k:df.fillna("") for k, df in sheets_dict.items()}
            self.process_country_df(df_dict=df_dict)
            logger.info("Browser closed.")
        except Exception as e:
            logger.exception(f"Error while scraping data : \n\n{traceback.format_exc()}")
        
    
if __name__ == "__main__":
    headless = False
    aaha_scraper = AahaScraper()
    aaha_scraper.scraper(headless=headless)



