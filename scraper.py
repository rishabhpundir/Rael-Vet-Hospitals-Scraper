import time
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service

# Setup Selenium WebDriver
def setup_driver():
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    service = Service("chromedriver")  # Ensure chromedriver is in PATH or specify full path
    driver = webdriver.Chrome(service=service, options=options)
    return driver

# Function to search the directory
def search_directory(driver, search_term, search_url):
    driver.get(search_url)
    time.sleep(3)  # Allow time for page to load
    
    search_box = driver.find_element(By.NAME, "search")  # Modify based on actual field name
    search_box.clear()
    search_box.send_keys(search_term)
    search_box.send_keys(Keys.RETURN)
    time.sleep(5)  # Wait for results to load

# Function to extract business data
def extract_business_data(driver):
    soup = BeautifulSoup(driver.page_source, "html.parser")
    businesses = []
    
    for business in soup.find_all("div", class_="business-item"):  # Modify selector
        name = business.find("h2").text.strip() if business.find("h2") else "N/A"
        address = business.find("p", class_="address").text.strip() if business.find("p", class_="address") else "N/A"
        phone = business.find("span", class_="phone").text.strip() if business.find("span", class_="phone") else "N/A"
        website = business.find("a", class_="website")['href'] if business.find("a", class_="website") else "N/A"
        business_type = business.find("span", class_="category").text.strip() if business.find("span", class_="category") else "N/A"
        
        businesses.append({
            "Name": name,
            "Address": address,
            "Phone": phone,
            "Website": website,
            "Business Type": business_type
        })
    
    return businesses

# Function to save data to Excel
def save_to_excel(data, filename="business_data.xlsx"):
    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)

# Main execution
def main():
    search_url = "https://example.com/directory"  # Replace with actual URL
    search_term = "Plumbers"  # Modify as needed
    
    driver = setup_driver()
    search_directory(driver, search_term, search_url)
    business_data = extract_business_data(driver)
    driver.quit()
    
    save_to_excel(business_data)
    print(f"Scraped {len(business_data)} businesses and saved to Excel.")

if __name__ == "__main__":
    main()
