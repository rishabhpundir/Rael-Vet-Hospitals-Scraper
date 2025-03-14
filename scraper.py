import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from process_zipcodes import process_zip_data
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


# Setup Selenium WebDriver
def setup_driver():
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")  # Prevent detection as a bot
    options.add_argument("--no-sandbox")  # Bypass OS security model (useful for Linux)
    options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource issues
    options.add_argument("--start-maximized")  # Open Chrome in maximized mode
    # options.add_argument("--headless")  # Uncomment to run Chrome in headless mode

    # Initialize WebDriver
    chromedriver_path = r"C:\Program Files\Google\Chrome\Application\chromedriver.exe"
    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=options)
    return driver

# Open the search URL
def open_search_page(driver, search_url):
    driver.get(search_url)
    time.sleep(10)
    print("Page loaded successfully.")

# Main execution
def main():
    search_url = "https://www.aaha.org/for-pet-parents/find-an-aaha-accredited-animal-hospital-near-me/"
    us_zip_path, can_zip_path = process_zip_data()
    breakpoint()
    
    driver = setup_driver()
    open_search_page(driver, search_url)
    
    # Keep browser open for debugging
    input("Press Enter to close the browser...")
    driver.quit()
    print("Browser closed.")
    
    
if __name__ == "__main__":
    main()
