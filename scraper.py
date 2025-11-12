import requests
import pandas as pd
from bs4 import BeautifulSoup
import gspread
from datetime import datetime
import os
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

class UNGMScraper:
    def __init__(self):
        self.base_url = "https://www.ungm.org/Public/Notice"
        self.search_terms = ["office furniture", "office supplies", "office chairs"]
        self.spreadsheet_id = os.getenv('GOOGLE_SHEET_ID')
        
    def search_tenders_selenium(self):
        """
        Use Selenium to scrape UNGM (handles JavaScript)
        """
        tenders = []
        
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.get(self.base_url)
            
            # Wait for page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "tender-row"))
            )
            
            # Get page source and parse with BeautifulSoup
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Find all tender rows
            tender_rows = soup.find_all('tr')
            
            for row in tender_rows:
                cells = row.find_all('td')
                if len(cells) >= 7:
                    try:
                        title_link = cells[0].find('a')
                        if title_link:
                            tender_data = {
                                'Title': title_link.text.strip(),
                                'Deadline': cells[1].text.strip(),
                                'Published': cells[2].text.strip(),
                                'Organization': cells[3].text.strip() if len(cells) > 3 else 'N/A',
                                'Type': cells[4].text.strip() if len(cells) > 4 else 'N/A',
                                'Reference': cells[5].text.strip() if len(cells) > 5 else 'N/A',
                                'Country': cells[6].text.strip() if len(cells) > 6 else 'N/A',
                                'Status': 'Active',
                                'Difficulty': self.assess_difficulty(cells[4].text if len(cells) > 4 else ''),
                                'URL': title_link.get('href', 'N/A') if title_link else 'N/A'
                            }
                            if 'office' in tender_data['Title'].lower() or any(term in tender_data['Title'].lower() for term in self.search_terms):
                                tenders.append(tender_data)
                    except Exception as e:
                        print(f"Error parsing row: {e}")
                        continue
            
            driver.quit()
        except Exception as e:
            print(f"Selenium error: {e}")
        
        return tenders
    
    def assess_difficulty(self, tender_type):
        """
        Classify tender difficulty (Easy tenders are preferred)
        """
        easy_types = ['Request for quotation', 'Invitation to bid']
        moderate_types = ['Request for proposal']
        
        if any(easy in tender_type for easy in easy_types):
            return 'Easy'
        elif any(mod in tender_type for mod in moderate_types):
            return 'Moderate'
        return 'Complex'
    
    def filter_top_tenders(self, tenders, limit=10):
        """
        Filter and sort by difficulty (easiest first)
        """
        if not tenders:
            return []
        
        df = pd.DataFrame(tenders)
        difficulty_order = {'Easy': 1, 'Moderate': 2, 'Complex': 3}
        df['difficulty_score'] = df['Difficulty'].map(difficulty_order)
        df = df.sort_values('difficulty_score')
        return df.head(limit).to_dict('records')
    
    def update_google_sheets(self, tenders):
        """
        Update Google Sheets with new tenders
        """
        try:
            # Authenticate with Google Sheets
            gc = gspread.service_account_from_dict(json.loads(os.getenv('GOOGLE_CREDENTIALS')))
            sh = gc.open_by_key(self.spreadsheet_id)
            ws = sh.get_worksheet(0)
            
            # Clear existing data (keep headers)
            if ws.row_count > 1:
                ws.delete_rows(2, ws.row_count)
            
            # Add new data
            for idx, tender in enumerate(tenders, start=2):
                ws.append_row([
                    tender.get('Title', ''),
                    tender.get('Deadline', ''),
                    tender.get('Published', ''),
                    tender.get('Organization', ''),
                    tender.get('Type', ''),
                    tender.get('Reference', ''),
                    tender.get('Country', ''),
                    tender.get('Status', ''),
                    tender.get('Difficulty', ''),
                    tender.get('URL', '')
                ])
            
            print(f"Successfully updated {len(tenders)} tenders in Google Sheets")
            return True
        except Exception as e:
            print(f"Error updating Google Sheets: {e}")
            return False
    
    def run(self):
        """
        Main automation routine
        """
        print(f"=== UNGM Tender Scraper Started - {datetime.now()} ===")
        
        # Search for tenders using Selenium
        print("Searching for tenders...")
        tenders = self.search_tenders_selenium()
        print(f"Found {len(tenders)} office-related tenders")
        
        if not tenders:
            print("No tenders found. Exiting.")
            return
        
        # Filter top 10 easiest
        print("Filtering top 10 easiest tenders...")
        top_tenders = self.filter_top_tenders(tenders, limit=10)
        print(f"Selected {len(top_tenders)} top tenders")
        
        # Update Google Sheets
        print("Updating Google Sheets...")
        self.update_google_sheets(top_tenders)
        
        print(f"=== Completed - {datetime.now()} ===")

if __name__ == "__main__":
    scraper = UNGMScraper()
    scraper.run()
