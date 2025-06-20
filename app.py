import asyncio
import logging
import os
import re
import time
from typing import Optional, Dict, Any
from datetime import datetime
import json
from dotenv import load_dotenv

import openai
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
from flask import Flask, request, jsonify

# Selenium imports for Module 3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CustodyLookupWebDriver:
    def __init__(self, headless: bool = False, wait_timeout: int = 10):
        """Initialize the web driver for custody lookup"""
        self.headless = headless
        self.wait_timeout = wait_timeout
        self.driver = None
        self.wait = None
        
        # Target URL for custody lookup
        self.custody_url = "https://jimspub.riversidesheriff.org/"
        
        # CSS selectors for form elements
        self.selectors = {
            'last_name': 'input[name="lastName"]',
            'first_name': 'input[name="firstName"]', 
            'date_of_birth': 'input[name="dob"]',
            'gender': 'select[name="sex"]',
            'search_button': 'input[type="submit"][value="Search"]'
        }
    
    def setup_driver(self) -> bool:
        """Set up and configure the Chrome WebDriver"""
        try:
            chrome_options = Options()
            
            if self.headless:
                chrome_options.add_argument('--headless')
            
            # Additional options for stability
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            # Initialize driver
            self.driver = webdriver.Chrome(options=chrome_options)
            self.wait = WebDriverWait(self.driver, self.wait_timeout)
            
            logger.info("WebDriver initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            return False
    
    def validate_and_format_date(self, date_input: str) -> tuple:
        """
        Validate and format date input to MM/DD/YYYY format
        Returns tuple: (formatted_date, is_valid)
        """
        if not date_input or date_input == "Not provided":
            return None, False
        
        # Clean the input
        date_input = date_input.strip().replace('-', '/').replace('.', '/')
        
        # Common date patterns to match
        patterns = [
            # MM/DD/YYYY or M/D/YYYY
            r'^(\d{1,2})/(\d{1,2})/(\d{4})$',
            # MM-DD-YYYY or M-D-YYYY
            r'^(\d{1,2})-(\d{1,2})-(\d{4})$',
            # YYYY/MM/DD
            r'^(\d{4})/(\d{1,2})/(\d{1,2})$',
            # YYYY-MM-DD
            r'^(\d{4})-(\d{1,2})-(\d{1,2})$'
        ]
        
        for i, pattern in enumerate(patterns):
            match = re.match(pattern, date_input)
            if match:
                if i < 2:  # MM/DD/YYYY format
                    month, day, year = match.groups()
                else:  # YYYY/MM/DD format
                    year, month, day = match.groups()
                
                try:
                    # Validate the date
                    datetime(int(year), int(month), int(day))
                    
                    # Format to MM/DD/YYYY
                    formatted_date = f"{int(month):02d}/{int(day):02d}/{year}"
                    return formatted_date, True
                    
                except ValueError:
                    continue
        
        return None, False
    
    def parse_spoken_date(self, spoken_date: str) -> str:
        """
        Convert spoken date to MM/DD/YYYY format
        Enhanced to handle formats like "October 16 1988"
        """
        if not spoken_date:
            return ""
        
        spoken_date = spoken_date.lower().strip()
        logger.info(f"Parsing spoken date: '{spoken_date}'")
        
        # Month name mappings
        months = {
            'january': '01', 'jan': '01',
            'february': '02', 'feb': '02',
            'march': '03', 'mar': '03',
            'april': '04', 'apr': '04',
            'may': '05',
            'june': '06', 'jun': '06',
            'july': '07', 'jul': '07',
            'august': '08', 'aug': '08',
            'september': '09', 'sep': '09', 'sept': '09',
            'october': '10', 'oct': '10',
            'november': '11', 'nov': '11',
            'december': '12', 'dec': '12'
        }
        
        # Convert number words to digits
        number_words = {
            'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
            'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
            'ten': '10', 'eleven': '11', 'twelve': '12', 'thirteen': '13',
            'fourteen': '14', 'fifteen': '15', 'sixteen': '16', 'seventeen': '17',
            'eighteen': '18', 'nineteen': '19', 'twenty': '20', 'thirty': '30'
        }
        
        # Clean up the input
        spoken_date = spoken_date.replace(',', ' ').replace('.', ' ')
        spoken_date = re.sub(r'\s+', ' ', spoken_date).strip()
        
        # Replace number words with digits
        for word, digit in number_words.items():
            spoken_date = re.sub(r'\b' + word + r'\b', digit, spoken_date)
        
        # Handle twenty-something and thirty-something numbers
        spoken_date = re.sub(r'twenty[\s-]?(\w+)', lambda m: '2' + number_words.get(m.group(1), m.group(1)), spoken_date)
        spoken_date = re.sub(r'thirty[\s-]?(\w+)', lambda m: '3' + number_words.get(m.group(1), m.group(1)), spoken_date)
        
        # Look for month names and extract components
        found_month = None
        for month_name, month_num in months.items():
            if month_name in spoken_date:
                found_month = month_num
                # Remove the month name to make number extraction easier
                spoken_date = spoken_date.replace(month_name, ' ')
                break
        
        # Extract all numbers from the remaining text
        numbers = re.findall(r'\d+', spoken_date)
        
        logger.info(f"Found month: {found_month}, Numbers: {numbers}")
        
        # Pattern 1: Month name with day and year (e.g., "October 16 1988")
        if found_month and len(numbers) >= 2:
            try:
                day = int(numbers[0])
                year = int(numbers[1])
                
                # Handle 2-digit years
                if year < 100:
                    year = year + 1900 if year > 50 else year + 2000
                
                # Validate ranges
                if 1 <= day <= 31 and 1900 <= year <= 2025:
                    result = f"{found_month}/{day:02d}/{year}"
                    logger.info(f"✅ Parsed as: {result}")
                    return result
            except ValueError:
                pass
        
        # Pattern 2: MM/DD/YYYY or similar with slashes/dashes
        if len(numbers) >= 3:
            try:
                month, day, year = int(numbers[0]), int(numbers[1]), int(numbers[2])
                
                # Handle 2-digit years
                if year < 100:
                    year = year + 1900 if year > 50 else year + 2000
                
                # Validate ranges
                if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2025:
                    result = f"{month:02d}/{day:02d}/{year}"
                    logger.info(f"✅ Parsed as: {result}")
                    return result
            except ValueError:
                pass
        
        # Pattern 3: Just numbers without month name
        if not found_month and len(numbers) >= 3:
            try:
                # Assume MM DD YYYY format
                month, day, year = int(numbers[0]), int(numbers[1]), int(numbers[2])
                
                # Handle 2-digit years
                if year < 100:
                    year = year + 1900 if year > 50 else year + 2000
                
                if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2025:
                    result = f"{month:02d}/{day:02d}/{year}"
                    logger.info(f"✅ Parsed as: {result}")
                    return result
            except ValueError:
                pass
        
        logger.warning(f"❌ Could not parse date: '{spoken_date}'")
        return ""
    
    def parse_date_of_birth(self, date_str: str) -> Optional[str]:
        """Parse various date formats into MM/DD/YYYY format required by the form"""
        if not date_str or date_str == "Not provided":
            return None
        
        # First try to parse spoken date
        date_str = self.parse_spoken_date(date_str)
        
        # Then validate and format
        formatted_date, is_valid = self.validate_and_format_date(date_str)
        
        if is_valid:
            return formatted_date
        
        # If basic validation fails, try the original parsing logic
        date_str = date_str.strip().lower()
        
        # Remove common words
        for word in ['born', 'on', 'the', 'of']:
            date_str = date_str.replace(word, ' ')
        
        # Clean up extra spaces
        date_str = ' '.join(date_str.split())
        
        # Month name mappings
        months = {
            'january': '01', 'jan': '01',
            'february': '02', 'feb': '02',
            'march': '03', 'mar': '03',
            'april': '04', 'apr': '04',
            'may': '05',
            'june': '06', 'jun': '06',
            'july': '07', 'jul': '07',
            'august': '08', 'aug': '08',
            'september': '09', 'sep': '09', 'sept': '09',
            'october': '10', 'oct': '10',
            'november': '11', 'nov': '11',
            'december': '12', 'dec': '12'
        }
        
        # Try to extract numbers for year, month, day
        numbers = re.findall(r'\d+', date_str)
        
        # Look for month names
        found_month = None
        for month_name, month_num in months.items():
            if month_name in date_str:
                found_month = month_num
                break
        
        # Pattern 1: Month Name Day, Year (e.g., "January 15, 1990")
        if found_month and len(numbers) >= 2:
            try:
                day = int(numbers[0])
                year = int(numbers[1]) if len(numbers[1]) == 4 else int(numbers[1]) + 1900 if int(numbers[1]) > 50 else int(numbers[1]) + 2000
                
                if 1 <= day <= 31 and 1900 <= year <= 2025:
                    return f"{found_month}/{day:02d}/{year}"
            except ValueError:
                pass
        
        # Pattern 2: MM/DD/YYYY or M/D/YYYY
        if len(numbers) >= 3:
            try:
                month, day, year = int(numbers[0]), int(numbers[1]), int(numbers[2])
                
                # Handle 2-digit years
                if year < 100:
                    year = year + 1900 if year > 50 else year + 2000
                
                if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2025:
                    return f"{month:02d}/{day:02d}/{year}"
            except ValueError:
                pass
        
        logger.warning(f"Could not parse date: {date_str}")
        return ""  # Return empty string instead of None for form compatibility
    
    def navigate_to_custody_page(self) -> bool:
        """Navigate to the custody lookup page"""
        try:
            logger.info(f"Navigating to {self.custody_url}")
            self.driver.get(self.custody_url)
            
            # Wait for the page to load and check for the search form
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, self.selectors['last_name'])))
            
            logger.info("Successfully navigated to custody lookup page")
            return True
            
        except TimeoutException:
            logger.error("Timeout waiting for custody lookup page to load")
            return False
        except WebDriverException as e:
            logger.error(f"Error navigating to custody page: {e}")
            return False
    
    def fill_search_form(self, first_name: str, last_name: str, date_of_birth: str, gender: str = "M") -> bool:
        """Fill the custody search form with provided information"""
        try:
            # Parse and format date of birth
            formatted_dob = self.parse_date_of_birth(date_of_birth) if date_of_birth else ""
            
            # Log what we're filling
            logger.info(f"Filling form with: First='{first_name}', Last='{last_name}', DOB='{date_of_birth}' -> '{formatted_dob}', Gender='{gender}'")
            
            # Fill Last Name (mandatory field)
            if last_name and last_name != "Not provided":
                last_name_field = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, self.selectors['last_name'])))
                last_name_field.clear()
                last_name_field.send_keys(last_name.strip().title())
                logger.info(f"✅ Filled last name: {last_name}")
            else:
                logger.error("❌ Last name is required but not provided")
                return False
            
            # Fill First Name (optional)
            if first_name and first_name != "Not provided":
                first_name_field = self.driver.find_element(By.CSS_SELECTOR, self.selectors['first_name'])
                first_name_field.clear()
                first_name_field.send_keys(first_name.strip().title())
                logger.info(f"✅ Filled first name: {first_name}")
            
            # Fill Date of Birth (optional) - handle None case
            if formatted_dob and formatted_dob != "":
                dob_field = self.driver.find_element(By.CSS_SELECTOR, self.selectors['date_of_birth'])
                dob_field.clear()
                dob_field.send_keys(formatted_dob)
                logger.info(f"✅ Filled date of birth: {formatted_dob}")
            else:
                logger.warning(f"⚠️ Skipping date field - could not format: '{date_of_birth}'")
            
            # Select Gender
            if gender in ["M", "F", ""]:
                gender_select = Select(self.driver.find_element(By.CSS_SELECTOR, self.selectors['gender']))
                gender_select.select_by_value(gender)
                logger.info(f"✅ Selected gender: {gender if gender else 'Any'}")
            
            # Add a small delay to see the filled form
            time.sleep(2)
            
            logger.info("✅ Form filled successfully")
            return True
            
        except TimeoutException:
            logger.error("❌ Timeout waiting for form elements")
            return False
        except NoSuchElementException as e:
            logger.error(f"❌ Form element not found: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Error filling form: {e}")
            return False
    
    def submit_search_and_process_results(self) -> Dict[str, Any]:
        """MODULE 4: Submit search and process results from table"""
        try:
            # Click the search button
            search_button = self.driver.find_element(By.CSS_SELECTOR, self.selectors['search_button'])
            search_button.click()
            
            # Wait for page to load
            time.sleep(3)
            
            # Check for results table
            return self.check_and_process_table()
            
        except Exception as e:
            logger.error(f"Error during search submission: {e}")
            return {
                'success': False,
                'error_message': "Sorry, there was an error processing your request. Please try again later.",
                'inmates_found': 0,
                'inmates': []
            }
    
    def check_and_process_table(self) -> Dict[str, Any]:
        """Check for results table and process the information"""
        try:
            # Wait longer for potential table to load
            WebDriverWait(self.driver, 15).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            # Give extra time for dynamic content
            time.sleep(5)
            
            # Look for common table selectors
            table_selectors = [
                'table',
                '.results-table',
                '#results-table',
                'table[class*="result"]',
                'table[id*="result"]',
                '.custody-results',
                '#custody-results',
                'table[class*="data"]',
                'table[id*="data"]'
            ]
            
            table_found = False
            table_data = []
            
            logger.info("Searching for result tables...")
            
            for selector in table_selectors:
                try:
                    tables = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    logger.info(f"Found {len(tables)} tables with selector '{selector}'")
                    
                    for i, table in enumerate(tables):
                        # Check if table has content (rows with data)
                        rows = table.find_elements(By.TAG_NAME, 'tr')
                        logger.info(f"Table {i+1}: {len(rows)} rows found")
                        
                        if len(rows) > 1:  # More than just header row
                            table_found = True
                            table_data = self.extract_table_data(table)
                            logger.info(f"✅ Table data extracted: {len(table_data)} records")
                            break
                    
                    if table_found:
                        break
                        
                except NoSuchElementException:
                    continue
            
            # If no structured table found, try to find any results text
            if not table_found:
                logger.info("No structured table found, checking for any results text...")
                page_text = self.driver.page_source.lower()
                
                # Check for "no results" messages
                if any(phrase in page_text for phrase in ['no records found', 'no results', 'no inmates found', 'no matches']):
                    logger.info("Found 'no results' message")
                    return {
                        'success': True,
                        'inmates_found': 0,
                        'inmates': [],
                        'voice_message': "Sorry, no results found for the provided information."
                    }
                
                # Look for any data that might be results
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                
                # Look for divs or other elements that might contain results
                potential_results = soup.find_all(['div', 'span', 'p'], string=re.compile(r'booking|inmate|custody|arrest', re.I))
                
                if potential_results:
                    logger.info(f"Found {len(potential_results)} potential result elements")
                    # Create a simple result from found text
                    result_text = ' '.join([elem.get_text(strip=True) for elem in potential_results[:3]])  # First 3 elements
                    if result_text:
                        return {
                            'success': True,
                            'inmates_found': 1,
                            'inmates': [{'info': result_text}],
                            'voice_message': f"I found custody information: {result_text}"
                        }
            
            if table_found and table_data:
                return {
                    'success': True,
                    'inmates_found': len(table_data),
                    'inmates': table_data,
                    'voice_message': self.format_table_data_for_voice(table_data)
                }
            else:
                logger.info("No results found in any format")
                return {
                    'success': True,
                    'inmates_found': 0,
                    'inmates': [],
                    'voice_message': "Sorry, no results found for the provided information."
                }
                
        except TimeoutException:
            logger.warning("Timeout waiting for page to load completely")
            return {
                'success': True,
                'inmates_found': 0,
                'inmates': [],
                'voice_message': "Sorry, no results found for the provided information."
            }
        except Exception as e:
            logger.error(f"Error checking for table: {e}")
            return {
                'success': False,
                'error_message': "Sorry, there was an error retrieving the information. Please try again later.",
                'inmates_found': 0,
                'inmates': []
            }
    
    def extract_table_data(self, table) -> list:
        """Extract relevant data from the custody results table"""
        data = []
        
        try:
            rows = table.find_elements(By.TAG_NAME, 'tr')
            logger.info(f"Processing table with {len(rows)} total rows")
            
            # Get headers
            headers = []
            if rows:
                header_cells = rows[0].find_elements(By.TAG_NAME, 'th')
                if not header_cells:  # Try td if no th
                    header_cells = rows[0].find_elements(By.TAG_NAME, 'td')
                
                headers = [cell.text.strip() for cell in header_cells if cell.text.strip()]
                logger.info(f"Found headers: {headers}")
            
            # Get data rows
            data_row_count = 0
            for i, row in enumerate(rows[1:], 1):  # Skip header row
                cells = row.find_elements(By.TAG_NAME, 'td')
                if cells:
                    row_data = {}
                    cell_values = []
                    
                    for j, cell in enumerate(cells):
                        cell_text = cell.text.strip()
                        if cell_text:  # Only add non-empty cells
                            header = headers[j] if j < len(headers) else f"Column_{j+1}"
                            row_data[header] = cell_text
                            cell_values.append(cell_text)
                    
                    logger.info(f"Row {i} data: {cell_values}")
                    
                    # Only add rows that have meaningful data (not just empty or header-like content)
                    if any(row_data.values()) and len([v for v in row_data.values() if v]) > 1:
                        data.append(row_data)
                        data_row_count += 1
                        logger.info(f"✅ Added data row {data_row_count}: {row_data}")
                    else:
                        logger.info(f"⚠️ Skipped empty/invalid row {i}")
            
            logger.info(f"Final extraction result: {len(data)} valid data rows")
            
        except Exception as e:
            logger.error(f"Error extracting table data: {e}")
        
        return data
    
    def format_table_data_for_voice(self, table_data: list) -> str:
        """Convert table data to spoken information"""
        if not table_data:
            return "Sorry, no custody information was found."
        
        try:
            # Start with confirmation
            if len(table_data) == 1:
                voice_message = "I found one custody record. Here are the details: "
            else:
                voice_message = f"I found {len(table_data)} custody records. Here are the details: "
            
            for i, record in enumerate(table_data):
                if len(table_data) > 1:
                    voice_message += f"Record {i+1}: "
                
                # Log what we're processing
                logger.info(f"Processing record {i+1}: {record}")
                
                # Check if this looks like actual custody data
                record_text = ' '.join(str(v) for v in record.values() if v)
                
                # If the record seems to contain custody-related keywords, process it
                if any(keyword.lower() in record_text.lower() for keyword in ['booking', 'inmate', 'custody', 'arrest', 'charge', 'bond', 'jail', 'detention']):
                    # Prioritize important fields
                    priority_fields = [
                        'Name', 'Full Name', 'Inmate Name', 'Subject Name',
                        'Booking Number', 'Booking ID', 'ID',
                        'Status', 'Custody Status', 'Current Status',
                        'Booking Date', 'Arrest Date', 'Date Booked',
                        'Charges', 'Charge', 'Offense',
                        'Bond', 'Bail', 'Bond Amount',
                        'Location', 'Facility', 'Housing Location',
                        'Release Date', 'Scheduled Release'
                    ]
                    
                    # Speak priority fields first
                    spoken_fields = set()
                    for field_name in priority_fields:
                        for key, value in record.items():
                            if field_name.lower() in key.lower() and value and key not in spoken_fields:
                                clean_value = self.clean_value_for_speech(value)
                                if clean_value:
                                    voice_message += f"{key}: {clean_value}. "
                                    spoken_fields.add(key)
                                break
                    
                    # Speak remaining fields
                    for key, value in record.items():
                        if key not in spoken_fields and value:
                            clean_value = self.clean_value_for_speech(value)
                            if clean_value:
                                voice_message += f"{key}: {clean_value}. "
                else:
                    # If it doesn't look like custody data, it might be a "no results" table
                    logger.info(f"Record doesn't contain custody keywords: {record_text}")
                    if any(phrase in record_text.lower() for phrase in ['no records', 'no results', 'not found', 'no matches']):
                        return "Sorry, no results found for the provided information."
                    else:
                        # Just read whatever data we have
                        voice_message += f"Information found: {record_text}. "
            
            return voice_message if voice_message.strip().endswith('.') else voice_message.strip() + "."
            
        except Exception as e:
            logger.error(f"Error formatting table data for voice: {e}")
            return "I found some information but had trouble reading it clearly. Please try again later."
    
    def clean_value_for_speech(self, value: str) -> str:
        """Clean and format values for better speech synthesis"""
        if not value or value.strip() == '':
            return None
        
        value = value.strip()
        
        # Remove excessive whitespace
        value = re.sub(r'\s+', ' ', value)
        
        # Format dates for better speech
        date_pattern = r'(\d{1,2})/(\d{1,2})/(\d{4})'
        value = re.sub(date_pattern, r'\1 slash \2 slash \3', value)
        
        # Format times
        time_pattern = r'(\d{1,2}):(\d{2})'
        value = re.sub(time_pattern, r'\1 \2', value)
        
        # Handle currency
        if value.startswith('$'):
            value = value.replace('$', 'dollar ')
        
        return value
    
    def submit_search(self) -> bool:
        """Submit the search form"""
        try:
            search_button = self.driver.find_element(By.CSS_SELECTOR, self.selectors['search_button'])
            search_button.click()
            
            # Wait a moment for the search to process
            time.sleep(3)
            
            logger.info("Search form submitted successfully")
            return True
            
        except NoSuchElementException:
            logger.error("Search button not found")
            return False
        except Exception as e:
            logger.error(f"Error submitting form: {e}")
            return False
    
    def parse_search_results(self) -> Dict[str, Any]:
        """Parse the search results page and extract custody information (LEGACY METHOD)"""
        try:
            # Wait for results to load
            time.sleep(3)
            
            # Get page source and parse with BeautifulSoup
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            results = {
                'success': False,
                'inmates_found': 0,
                'inmates': [],
                'error_message': None
            }
            
            # Look for "No records found" message
            if "no records found" in page_source.lower() or "no inmates found" in page_source.lower():
                results['success'] = True
                results['error_message'] = "No custody records found for the provided information"
                logger.info("No custody records found")
                return results
            
            # Look for inmate data tables
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        cell_texts = [cell.get_text(strip=True) for cell in cells]
                        
                        # Look for data that looks like inmate information
                        if any(keyword in ' '.join(cell_texts).lower() for keyword in ['booking', 'name', 'charge', 'bond']):
                            inmate_data = {}
                            
                            # Simple parsing - extract all text as a record
                            inmate_data['info'] = ' | '.join(cell_texts)
                            
                            if inmate_data['info'] and len(inmate_data['info'].strip()) > 10:
                                results['inmates'].append(inmate_data)
            
            results['inmates_found'] = len(results['inmates'])
            results['success'] = True
            
            logger.info(f"Found {results['inmates_found']} custody record(s)")
            return results
            
        except Exception as e:
            logger.error(f"Error parsing search results: {e}")
            return {
                'success': False,
                'inmates_found': 0,
                'inmates': [],
                'error_message': f"Error parsing results: {str(e)}"
            }
    
    def perform_custody_lookup(self, first_name: str, last_name: str, date_of_birth: str, gender: str = "M") -> Dict[str, Any]:
        """Perform complete custody lookup workflow with Module 4 integration"""
        start_time = time.time()
        
        try:
            # Setup driver if not already done
            if not self.driver:
                if not self.setup_driver():
                    return {
                        'success': False,
                        'error_message': "Failed to initialize web driver",
                        'duration': time.time() - start_time,
                        'inmates_found': 0,
                        'inmates': []
                    }
            
            # Navigate to custody page
            if not self.navigate_to_custody_page():
                return {
                    'success': False,
                    'error_message': "Failed to navigate to custody lookup page",
                    'duration': time.time() - start_time,
                    'inmates_found': 0,
                    'inmates': []
                }
            
            # Fill the search form
            if not self.fill_search_form(first_name, last_name, date_of_birth, gender):
                return {
                    'success': False,
                    'error_message': "Failed to fill search form",
                    'duration': time.time() - start_time,
                    'inmates_found': 0,
                    'inmates': []
                }
            
            # Submit and process results using Module 4
            results = self.submit_search_and_process_results()
            results['duration'] = time.time() - start_time
            results['search_params'] = {
                'first_name': first_name,
                'last_name': last_name,
                'date_of_birth': date_of_birth,
                'gender': gender
            }
            
            # Important: Don't cleanup here - let the calling function handle it
            # This prevents premature browser closure
            
            return results
            
        except Exception as e:
            logger.error(f"Error during custody lookup: {e}")
            return {
                'success': False,
                'error_message': f"Unexpected error during lookup: {str(e)}",
                'duration': time.time() - start_time,
                'inmates_found': 0,
                'inmates': []
            }
    
    def cleanup(self):
        """Clean up driver resources"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("WebDriver closed successfully")
            except Exception as e:
                logger.error(f"Error closing WebDriver: {e}")
            finally:
                self.driver = None
                self.wait = None

class CustodyLookupAgent:
    def __init__(self, openai_api_key: str, twilio_account_sid: str, twilio_auth_token: str):
        """Initialize the AI agent for custody lookup calls"""
        self.openai_client = openai.OpenAI(api_key=openai_api_key)
        self.twilio_client = Client(twilio_account_sid, twilio_auth_token)
        self.call_sessions = {}
        self.date_validation_attempts = {}  # Track date validation attempts per call
        
    def create_greeting_response(self) -> VoiceResponse:
        response = VoiceResponse()
        
        greeting_text = (
            "Hello, you've reached the automated custody status lookup service. "
            "I can help you check custody information using the Riverside County database. "
            "Please note that this call may be recorded for quality purposes. "
            "To continue, please say 'yes' or press 1. To end this call, say 'no' or hang up."
        )
        
        gather = Gather(
            input='speech dtmf',
            timeout=5,
            speech_timeout=2,
            action='/handle_consent',
            method='POST'
        )
        gather.say(greeting_text, voice='alice', language='en-US')
        response.append(gather)
        
        # If no response, just proceed anyway
        response.redirect('/collect_first_name')
        
        return response
    
    def handle_consent_response(self, speech_result: str, digits: str, call_sid: str) -> VoiceResponse:
        """Handle user consent to proceed with the service"""
        response = VoiceResponse()
        
        # Check for explicit "no" - otherwise proceed
        if digits == '2' or (speech_result and any(word in speech_result.lower() for word in ['no', 'nope', 'stop'])):
            response.say("Thank you for calling. Goodbye.")
            response.hangup()
            return response
        
        # Initialize call session and proceed
        self.call_sessions[call_sid] = {
            'start_time': datetime.now(),
            'first_name': None,
            'last_name': None,
            'date': None,
            'current_step': 'collecting_first_name'
        }
        
        # Initialize date validation attempts counter
        self.date_validation_attempts[call_sid] = 0
        
        return self.collect_first_name()
    
    def collect_first_name(self) -> VoiceResponse:
        """Collect the first name from the caller"""
        response = VoiceResponse()
        
        instruction_text = (
            "Great! I'll need to collect some information to search the custody database. "
            "First, please clearly state the first name of the person you're looking up."
        )
        
        gather = Gather(
            input='speech',
            timeout=8,
            speech_timeout=4,
            action='/handle_first_name',
            method='POST',
            enhanced=True
        )
        gather.say(instruction_text, voice='alice', language='en-US')
        response.append(gather)
        
        # If no response, just move to next step
        response.redirect('/collect_last_name')
        
        return response
    
    def handle_first_name(self, speech_result: str, call_sid: str) -> VoiceResponse:
        """Process the first name and move to last name collection"""
        response = VoiceResponse()
        
        # Clean and validate the first name
        first_name = self.clean_name_input(speech_result) if speech_result else "Not provided"
        
        if call_sid in self.call_sessions:
            self.call_sessions[call_sid]['first_name'] = first_name
            self.call_sessions[call_sid]['current_step'] = 'collecting_last_name'
        
        logger.info(f"First name captured: '{first_name}' for call {call_sid}")
        
        # Confirm the name
        if first_name != "Not provided" and len(first_name) > 1:
            response.say(f"I heard the first name as {first_name}.", voice='alice', language='en-US')
        
        response.redirect('/collect_last_name')
        return response
    
    def collect_last_name(self) -> VoiceResponse:
        """Collect the last name from the caller"""
        response = VoiceResponse()
        
        instruction_text = (
            "Now, please clearly state the last name."
        )
        
        gather = Gather(
            input='speech',
            timeout=8,
            speech_timeout=4,
            action='/handle_last_name',
            method='POST',
            enhanced=True
        )
        gather.say(instruction_text, voice='alice', language='en-US')
        response.append(gather)
        
        # If no response, just move to next step
        response.redirect('/collect_date')
        
        return response
    
    def handle_last_name(self, speech_result: str, call_sid: str) -> VoiceResponse:
        """Process the last name and move to date collection"""
        response = VoiceResponse()
        
        # Clean and validate the last name
        last_name = self.clean_name_input(speech_result) if speech_result else "Not provided"
        
        if call_sid in self.call_sessions:
            self.call_sessions[call_sid]['last_name'] = last_name
            self.call_sessions[call_sid]['current_step'] = 'collecting_date'
        
        logger.info(f"Last name captured: '{last_name}' for call {call_sid}")
        
        # Confirm the name
        if last_name != "Not provided" and len(last_name) > 1:
            response.say(f"I heard the last name as {last_name}.", voice='alice', language='en-US')
        
        # Re-enable date collection
        response.redirect('/collect_date')
        return response
    
    def collect_date(self) -> VoiceResponse:
        """Collect the date from the caller with improved validation"""
        response = VoiceResponse()
        
        instruction_text = (
            "Now, please provide the date of birth. "
            "You can say it like 'October 16, 1988' or 'ten twenty five nineteen eighty'. "
            "Speak slowly and clearly."
        )
        
        gather = Gather(
            input='speech',
            timeout=10,
            speech_timeout=5,
            action='/handle_date',
            method='POST',
            enhanced=True
        )
        gather.say(instruction_text, voice='alice', language='en-US')
        response.append(gather)
        
        # If no response, just move to confirmation
        response.redirect('/final_confirmation')
        
        return response
    
    def handle_date(self, speech_result: str, call_sid: str) -> VoiceResponse:
        """Process the date with enhanced validation and retry logic"""
        response = VoiceResponse()
        
        # Initialize attempts counter if not exists
        if call_sid not in self.date_validation_attempts:
            self.date_validation_attempts[call_sid] = 0
        
        # Clean the date input
        date_input = self.clean_date_input(speech_result) if speech_result else "Not provided"
        logger.info(f"Date input received: '{date_input}' for call {call_sid}")
        
        # Create a temporary web driver instance for date validation
        temp_driver = CustodyLookupWebDriver(headless=True)
        
        # Try to parse and validate the date
        parsed_date = temp_driver.parse_spoken_date(date_input) if date_input != "Not provided" else ""
        formatted_date, is_valid = temp_driver.validate_and_format_date(parsed_date) if parsed_date else (None, False)
        
        temp_driver.cleanup()
        
        logger.info(f"Parsed date: '{parsed_date}', Formatted: '{formatted_date}', Valid: {is_valid}")
        
        if is_valid and formatted_date:
            # Date is valid, confirm with user
            confirmation_text = f"I heard the date as {formatted_date}. Is this correct? Please say yes or no."
            
            gather = Gather(
                input='speech',
                timeout=8,
                speech_timeout=3,
                action='/confirm_date',
                method='POST'
            )
            gather.say(confirmation_text, voice='alice', language='en-US')
            response.append(gather)
            
            # Store the formatted date temporarily
            if call_sid in self.call_sessions:
                self.call_sessions[call_sid]['temp_date'] = formatted_date
            
            # Default to proceeding if no response
            response.redirect('/final_confirmation')
            
        else:
            # Date is invalid, check attempts
            self.date_validation_attempts[call_sid] += 1
            
            if self.date_validation_attempts[call_sid] < 3:
                retry_text = (
                    "I didn't understand the date format. Please speak the date clearly. "
                    "For example, say 'October 16, 1988' or 'ten twenty five nineteen eighty'."
                )
                
                gather = Gather(
                    input='speech',
                    timeout=10,
                    speech_timeout=5,
                    action='/handle_date',
                    method='POST',
                    enhanced=True
                )
                gather.say(retry_text, voice='alice', language='en-US')
                response.append(gather)
                
                # If no response, proceed without date
                response.redirect('/final_confirmation')
            else:
                # Max attempts reached
                response.say("I'm having trouble understanding the date format. I'll proceed with the search using the name information only.", voice='alice', language='en-US')
                
                if call_sid in self.call_sessions:
                    self.call_sessions[call_sid]['date'] = "Not provided"
                
                response.redirect('/final_confirmation')
        
        logger.info(f"Date processing - Call: {call_sid}, Input: '{date_input}', Valid: {is_valid}, Attempts: {self.date_validation_attempts.get(call_sid, 0)}")
        
        return response
    
    def confirm_date(self, speech_result: str, call_sid: str) -> VoiceResponse:
        """Handle date confirmation from user"""
        response = VoiceResponse()
        
        session = self.call_sessions.get(call_sid, {})
        temp_date = session.get('temp_date', 'Not provided')
        
        # Check user's confirmation
        if speech_result and any(word in speech_result.lower() for word in ['yes', 'correct', 'right', 'yeah', 'yep']):
            # User confirmed the date
            if call_sid in self.call_sessions:
                self.call_sessions[call_sid]['date'] = temp_date
                self.call_sessions[call_sid]['current_step'] = 'confirming_information'
            
            logger.info(f"Date confirmed: '{temp_date}' for call {call_sid}")
            response.redirect('/final_confirmation')
            
        elif speech_result and any(word in speech_result.lower() for word in ['no', 'wrong', 'incorrect', 'nope']):
            # User rejected the date, try again if attempts allow
            self.date_validation_attempts[call_sid] += 1
            
            if self.date_validation_attempts[call_sid] < 3:
                response.redirect('/collect_date')
            else:
                response.say("I'll proceed with the search using the name information only.", voice='alice', language='en-US')
                if call_sid in self.call_sessions:
                    self.call_sessions[call_sid]['date'] = "Not provided"
                response.redirect('/final_confirmation')
        else:
            # Unclear response, assume yes
            if call_sid in self.call_sessions:
                self.call_sessions[call_sid]['date'] = temp_date
            response.redirect('/final_confirmation')
        
        return response

    # RE-ENABLED - Date collection methods
        """Collect the date from the caller with improved validation"""
        response = VoiceResponse()
        
        instruction_text = (
            "Now, please provide the date of birth in MM/DD/YYYY format. "
            "For example, say 'ten twenty five nineteen eighty' for 10/25/1980. "
            "Or you can say 'October 25th, 1980'. Speak slowly and clearly."
        )
        
        gather = Gather(
            input='speech',
            timeout=10,
            speech_timeout=5,
            action='/handle_date',
            method='POST',
            enhanced=True
        )
        gather.say(instruction_text, voice='alice', language='en-US')
        response.append(gather)
        
        # If no response, just move to confirmation
        response.redirect('/final_confirmation')
        
        return response
    
    def handle_date(self, speech_result: str, call_sid: str) -> VoiceResponse:
        """Process the date with enhanced validation and retry logic"""
        response = VoiceResponse()
        
        # Initialize attempts counter if not exists
        if call_sid not in self.date_validation_attempts:
            self.date_validation_attempts[call_sid] = 0
        
        # Clean the date input
        date_input = self.clean_date_input(speech_result) if speech_result else "Not provided"
        
        # Create a temporary web driver instance for date validation
        temp_driver = CustodyLookupWebDriver(headless=True)
        
        # Try to parse and validate the date
        parsed_date = temp_driver.parse_spoken_date(date_input) if date_input != "Not provided" else ""
        formatted_date, is_valid = temp_driver.validate_and_format_date(parsed_date) if parsed_date else (None, False)
        
        temp_driver.cleanup()
        
        if is_valid and formatted_date:
            # Date is valid, confirm with user
            confirmation_text = f"I heard the date as {formatted_date}. Is this correct? Please say yes or no."
            
            gather = Gather(
                input='speech',
                timeout=8,
                speech_timeout=3,
                action='/confirm_date',
                method='POST'
            )
            gather.say(confirmation_text, voice='alice', language='en-US')
            response.append(gather)
            
            # Store the formatted date temporarily
            if call_sid in self.call_sessions:
                self.call_sessions[call_sid]['temp_date'] = formatted_date
            
            # Default to proceeding if no response
            response.redirect('/final_confirmation')
            
        else:
            # Date is invalid, check attempts
            self.date_validation_attempts[call_sid] += 1
            
            if self.date_validation_attempts[call_sid] < 3:
                retry_text = (
                    "I didn't understand the date format. Please speak the date clearly in MM/DD/YYYY format. "
                    "For example, say 'ten twenty five nineteen eighty' for 10/25/1980."
                )
                
                gather = Gather(
                    input='speech',
                    timeout=10,
                    speech_timeout=5,
                    action='/handle_date',
                    method='POST',
                    enhanced=True
                )
                gather.say(retry_text, voice='alice', language='en-US')
                response.append(gather)
                
                # If no response, proceed without date
                response.redirect('/final_confirmation')
            else:
                # Max attempts reached
                response.say("I'm having trouble understanding the date format. I'll proceed with the search using the name information only.", voice='alice', language='en-US')
                
                if call_sid in self.call_sessions:
                    self.call_sessions[call_sid]['date'] = "Not provided"
                
                response.redirect('/final_confirmation')
        
        logger.info(f"Date processing - Call: {call_sid}, Input: '{date_input}', Valid: {is_valid}, Attempts: {self.date_validation_attempts.get(call_sid, 0)}")
        
        return response
    
    def confirm_date(self, speech_result: str, call_sid: str) -> VoiceResponse:
        """Handle date confirmation from user"""
        response = VoiceResponse()
        
        session = self.call_sessions.get(call_sid, {})
        temp_date = session.get('temp_date', 'Not provided')
        
        # Check user's confirmation
        if speech_result and any(word in speech_result.lower() for word in ['yes', 'correct', 'right', 'yeah', 'yep']):
            # User confirmed the date
            if call_sid in self.call_sessions:
                self.call_sessions[call_sid]['date'] = temp_date
                self.call_sessions[call_sid]['current_step'] = 'confirming_information'
            
            logger.info(f"Date confirmed: '{temp_date}' for call {call_sid}")
            response.redirect('/final_confirmation')
            
        elif speech_result and any(word in speech_result.lower() for word in ['no', 'wrong', 'incorrect', 'nope']):
            # User rejected the date, try again if attempts allow
            self.date_validation_attempts[call_sid] += 1
            
            if self.date_validation_attempts[call_sid] < 3:
                response.redirect('/collect_date')
            else:
                response.say("I'll proceed with the search using the name information only.", voice='alice', language='en-US')
                if call_sid in self.call_sessions:
                    self.call_sessions[call_sid]['date'] = "Not provided"
                response.redirect('/final_confirmation')
        else:
            # Unclear response, assume yes
            if call_sid in self.call_sessions:
                self.call_sessions[call_sid]['date'] = temp_date
            response.redirect('/final_confirmation')
        
        return response

    def clean_name_input(self, name_input: str) -> str:
        """Clean and validate name input from voice recognition"""
        if not name_input:
            return "Not provided"
        
        # Remove common speech recognition artifacts
        name = name_input.strip()
        
        # Remove common filler words and phrases
        filler_words = ['um', 'uh', 'well', 'so', 'like', 'you know', 'i said', 'the name is', 'it is']
        for filler in filler_words:
            name = re.sub(r'\b' + re.escape(filler) + r'\b', '', name, flags=re.IGNORECASE)
        
        # Clean up extra spaces and punctuation
        name = re.sub(r'[^\w\s\'-]', '', name)  # Keep only letters, spaces, hyphens, apostrophes
        name = ' '.join(name.split())  # Normalize spaces
        
        # If it's too short or too long, it's probably wrong
        if len(name) < 2 or len(name) > 25:
            return "Not provided"
        
        return name.title()
    
    def clean_date_input(self, date_input: str) -> str:
        """Clean and validate date input from voice recognition"""
        if not date_input:
            return "Not provided"
        
        # Remove common filler words
        date_str = date_input.strip().lower()
        filler_words = ['um', 'uh', 'well', 'the date is', 'born on', 'birthday is']
        for filler in filler_words:
            date_str = re.sub(r'\b' + re.escape(filler) + r'\b', '', date_str, flags=re.IGNORECASE)
        
        # Clean up and normalize
        date_str = ' '.join(date_str.split())
        
        return date_str if date_str else "Not provided"
    
    def final_confirmation(self, call_sid: str) -> VoiceResponse:
        """Show final confirmation of all collected information"""
        response = VoiceResponse()
        
        session = self.call_sessions.get(call_sid, {})
        
        # Get all the information we collected (including date now)
        first_name = session.get('first_name', 'Not provided')
        last_name = session.get('last_name', 'Not provided')
        date = session.get('date', 'Not provided')
        
        if date != 'Not provided':
            confirmation_text = (
                f"Thank you. I have collected the following information: "
                f"First name: {first_name}. "
                f"Last name: {last_name}. "
                f"Date of birth: {date}. "
                "I'm now searching the Riverside County custody database. "
                "This may take a moment. Please stay on the line."
            )
        else:
            confirmation_text = (
                f"Thank you. I have collected the following information: "
                f"First name: {first_name}. "
                f"Last name: {last_name}. "
                "I'm now searching the Riverside County custody database. "
                "This may take a moment. Please stay on the line."
            )
        
        response.say(confirmation_text, voice='alice', language='en-US')
        
        # Redirect to Phase 2 (custody lookup)
        response.redirect('/process_custody_lookup')
        
        return response
    
    def format_custody_results_for_voice(self, lookup_result: Dict[str, Any]) -> str:
        """Format custody lookup results for voice delivery"""
        if not lookup_result['success']:
            return f"I'm sorry, there was an error performing the custody lookup: {lookup_result.get('error_message', 'Unknown error')}"
        
        # Check if we have a pre-formatted voice message from Module 4
        if 'voice_message' in lookup_result:
            return lookup_result['voice_message']
        
        inmates_found = lookup_result.get('inmates_found', 0)
        
        if inmates_found == 0:
            return "I searched the Riverside County custody database and did not find any current custody records for the provided information."
        
        elif inmates_found == 1:
            inmate = lookup_result['inmates'][0]
            message = f"I found one custody record with the following information: {inmate.get('info', 'Details not available')}"
            return message
        
        else:
            message = f"I found {inmates_found} custody records matching your search. "
            for i, inmate in enumerate(lookup_result['inmates'][:2], 1):  # Limit to first 2 for voice
                message += f"Record {i}: {inmate.get('info', 'Details not available')}. "
            
            if inmates_found > 2:
                message += f"And {inmates_found - 2} additional records found."
            
            return message
    
    def get_call_session(self, call_sid: str) -> Optional[Dict[str, Any]]:
        """Get call session data"""
        return self.call_sessions.get(call_sid)
    
    def cleanup_session(self, call_sid: str):
        """Clean up call session data"""
        if call_sid in self.call_sessions:
            del self.call_sessions[call_sid]
            logger.info(f"Cleaned up session for call {call_sid}")
        
        if call_sid in self.date_validation_attempts:
            del self.date_validation_attempts[call_sid]

# Flask application for handling Twilio webhooks
app = Flask(__name__)

# Initialize the agent with environment variables
try:
    agent = CustodyLookupAgent(
        openai_api_key=os.getenv('OPENAI_API_KEY'),
        twilio_account_sid=os.getenv('TWILIO_ACCOUNT_SID'),
        twilio_auth_token=os.getenv('TWILIO_AUTH_TOKEN')
    )
    logger.info("Agent initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize agent: {e}")
    raise

@app.route('/', methods=['GET', 'POST'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'custody-lookup-ai',
        'timestamp': datetime.now().isoformat(),
        'method': request.method
    })

# Add this debug route after the health_check route
@app.route('/debug', methods=['GET', 'POST'])
def debug_endpoint():
    """Debug endpoint to see what's being sent"""
    return jsonify({
        'method': request.method,
        'url': request.url,
        'headers': dict(request.headers),
        'form_data': dict(request.form),
        'args': dict(request.args)
    })

@app.route('/incoming_call', methods=['POST'])
def handle_incoming_call():
    """Handle incoming call webhook"""
    # Debug: Log all incoming data
    logger.info(f"Incoming webhook data: {dict(request.form)}")
    logger.info(f"Headers: {dict(request.headers)}")
    
    call_sid = request.form.get('CallSid')
    from_number = request.form.get('From')
    to_number = request.form.get('To')
    call_status = request.form.get('CallStatus')
    
    logger.info(f"Incoming call: {call_sid} from {from_number} to {to_number}, status: {call_status}")
    
    # If no CallSid, this might not be a real Twilio request
    if not call_sid:
        logger.warning("No CallSid found - this might not be a real Twilio webhook")
        return "No CallSid provided", 400
    
    response = agent.create_greeting_response()
    return str(response)

@app.route('/handle_consent', methods=['POST'])
def handle_consent():
    """Handle consent response"""
    speech_result = request.form.get('SpeechResult', '')
    digits = request.form.get('Digits', '')
    call_sid = request.form.get('CallSid')
    
    logger.info(f"Consent response - Call: {call_sid}, Speech: {speech_result}, Digits: {digits}")
    
    response = agent.handle_consent_response(speech_result, digits, call_sid)
    return str(response)

@app.route('/collect_first_name', methods=['POST'])
def collect_first_name():
    """Collect first name"""
    call_sid = request.form.get('CallSid')
    logger.info(f"Collecting first name for call: {call_sid}")
    
    response = agent.collect_first_name()
    return str(response)

@app.route('/handle_first_name', methods=['POST'])
def handle_first_name():
    """Handle first name input"""
    speech_result = request.form.get('SpeechResult', '')
    call_sid = request.form.get('CallSid')
    
    logger.info(f"First name - Call: {call_sid}, Speech: '{speech_result}'")
    
    response = agent.handle_first_name(speech_result, call_sid)
    return str(response)

@app.route('/collect_last_name', methods=['POST'])
def collect_last_name():
    """Collect last name"""
    call_sid = request.form.get('CallSid')
    logger.info(f"Collecting last name for call: {call_sid}")
    
    response = agent.collect_last_name()
    return str(response)

@app.route('/handle_last_name', methods=['POST'])
def handle_last_name():
    """Handle last name input"""
    speech_result = request.form.get('SpeechResult', '')
    call_sid = request.form.get('CallSid')
    
    logger.info(f"Last name - Call: {call_sid}, Speech: '{speech_result}'")
    
    response = agent.handle_last_name(speech_result, call_sid)
    return str(response)

# RE-ENABLED - Date collection routes
@app.route('/collect_date', methods=['POST'])
def collect_date():
    """Collect date"""
    call_sid = request.form.get('CallSid')
    logger.info(f"Collecting date for call: {call_sid}")
    
    response = agent.collect_date()
    return str(response)

@app.route('/handle_date', methods=['POST'])
def handle_date():
    """Handle date input with validation"""
    speech_result = request.form.get('SpeechResult', '')
    call_sid = request.form.get('CallSid')
    
    logger.info(f"Date - Call: {call_sid}, Speech: '{speech_result}'")
    
    response = agent.handle_date(speech_result, call_sid)
    return str(response)

@app.route('/confirm_date', methods=['POST'])
def confirm_date():
    """Handle date confirmation"""
    speech_result = request.form.get('SpeechResult', '')
    call_sid = request.form.get('CallSid')
    
    logger.info(f"Date confirmation - Call: {call_sid}, Speech: '{speech_result}'")
    
    response = agent.confirm_date(speech_result, call_sid)
    return str(response)

@app.route('/final_confirmation', methods=['POST'])
def final_confirmation():
    """Show final confirmation"""
    call_sid = request.form.get('CallSid')
    
    logger.info(f"Final confirmation for call: {call_sid}")
    
    response = agent.final_confirmation(call_sid)
    return str(response)

@app.route('/process_custody_lookup', methods=['POST'])
def process_custody_lookup():
    """Start custody lookup with immediate response to avoid timeout"""
    call_sid = request.form.get('CallSid')
    session = agent.get_call_session(call_sid)
    
    response = VoiceResponse()
    
    try:
        logger.info(f"=== Starting process_custody_lookup for call {call_sid} ===")
        
        if not session:
            logger.error(f"No session found for call {call_sid}")
            response.say("Sorry, I couldn't find your session information. Please call back and try again.")
            response.hangup()
            return str(response)
        
        # Get the collected information (no date collection now)
        first_name = session.get('first_name', 'Not provided')
        last_name = session.get('last_name', 'Not provided') 
        
        logger.info(f"Session data: first_name='{first_name}', last_name='{last_name}'")
        
        # Validate we have at least a last name
        if not last_name or last_name == "Not provided":
            logger.error(f"No last name provided for call {call_sid}")
            response.say("I need at least a last name to perform the search. Please call back with the required information.")
            response.hangup()
            return str(response)
        
        # Store search params in session for background processing
        if call_sid in agent.call_sessions:
            agent.call_sessions[call_sid]['search_params'] = {
                'first_name': first_name,
                'last_name': last_name,
                'date_of_birth': date_of_birth
            }
        
        logger.info(f"Search params: {first_name} {last_name}, DOB: {date_of_birth}")
        
        # Immediately respond to avoid timeout
        logger.info("Returning immediate response to avoid timeout")
        response.say("I'm searching the database now. Please hold while I look up the custody information. This will take a moment.", voice='alice', language='en-US')
        
        # Redirect to a polling endpoint that will check if search is complete
        response.redirect('/check_search_status')
        
        # Start the background search in a separate thread
        import threading
        search_thread = threading.Thread(
            target=perform_background_search,
            args=(call_sid, first_name, last_name, date_of_birth)
        )
        search_thread.daemon = True
        search_thread.start()
        
        logger.info("Started background search thread")
        
    except Exception as e:
        logger.error(f"ERROR in process_custody_lookup for call {call_sid}: {str(e)}", exc_info=True)
        response.say("I'm sorry, there was a technical error. Please try calling back.", voice='alice', language='en-US')
        response.hangup()
        agent.cleanup_session(call_sid)
    
    logger.info(f"Returning immediate TwiML response: {str(response)}")
    return str(response)

def perform_background_search(call_sid: str, first_name: str, last_name: str, date_of_birth: str = 'Not provided'):
    """Perform the actual custody lookup in background"""
    web_driver = None
    
    try:
        logger.info(f"=== Background search started for call {call_sid}: {first_name} {last_name}, DOB: {date_of_birth} ===")
        
        # Initialize the web driver
        web_driver = CustodyLookupWebDriver(headless=True)  # Use headless for background
        
        # Perform the lookup
        lookup_result = web_driver.perform_custody_lookup(
            first_name=first_name,
            last_name=last_name,
            date_of_birth=date_of_birth,
            gender="M"
        )
        
        logger.info(f"Background search completed: {lookup_result}")
        
        # Store results in session
        if call_sid in agent.call_sessions:
            agent.call_sessions[call_sid]['search_completed'] = True
            agent.call_sessions[call_sid]['search_results'] = lookup_result
            
            # Generate voice message
            if lookup_result.get('success') and lookup_result.get('inmates_found', 0) > 0:
                voice_message = agent.format_custody_results_for_voice(lookup_result)
            else:
                if 'voice_message' in lookup_result:
                    voice_message = lookup_result['voice_message']
                else:
                    voice_message = "Sorry, no results found for the provided information."
            
            agent.call_sessions[call_sid]['voice_message'] = voice_message
            logger.info(f"Stored results in session for call {call_sid}")
        
    except Exception as e:
        logger.error(f"Error in background search for call {call_sid}: {e}", exc_info=True)
        
        # Store error in session
        if call_sid in agent.call_sessions:
            agent.call_sessions[call_sid]['search_completed'] = True
            agent.call_sessions[call_sid]['search_error'] = True
            agent.call_sessions[call_sid]['voice_message'] = "Sorry, there was an error performing the search. Please try again."
    
    finally:
        if web_driver:
            web_driver.cleanup()
            logger.info("Background search: WebDriver cleaned up")

@app.route('/check_search_status', methods=['POST'])
def check_search_status():
    """Check if background search is complete and deliver results"""
    call_sid = request.form.get('CallSid')
    session = agent.get_call_session(call_sid)
    
    response = VoiceResponse()
    
    try:
        logger.info(f"=== Checking search status for call {call_sid} ===")
        
        if not session:
            response.say("Sorry, I lost track of your search. Please call back.")
            response.hangup()
            return str(response)
        
        # Check if search is completed
        if session.get('search_completed', False):
            logger.info("Search completed, delivering results")
            
            # Get the voice message
            voice_message = session.get('voice_message', 'Sorry, no results found.')
            
            # Deliver results
            response.say(voice_message, voice='alice', language='en-US')
            
            # Ask for another search
            gather = Gather(
                input='speech dtmf',
                timeout=8,
                speech_timeout=3,
                action='/handle_additional_help',
                method='POST',
                num_digits=1
            )
            gather.say("Would you like another search? Say yes or press 1 for yes, or say no or press 2 to end the call.", voice='alice', language='en-US')
            response.append(gather)
            
            # Default to ending call
            response.say("Thank you for using our service. Goodbye.", voice='alice', language='en-US')
            response.hangup()
            
        else:
            logger.info("Search still in progress, asking user to wait")
            # Search still in progress
            response.say("I'm still searching the database. Please hold on a moment longer.", voice='alice', language='en-US')
            response.pause(length=3)
            response.redirect('/check_search_status')
        
    except Exception as e:
        logger.error(f"Error checking search status: {e}", exc_info=True)
        response.say("Sorry, there was an error. Please try calling back.", voice='alice', language='en-US')
        response.hangup()
        agent.cleanup_session(call_sid)
    
    logger.info(f"Returning search status response: {str(response)}")
    return str(response)

@app.route('/handle_repeat_request', methods=['POST'])
def handle_repeat_request():
    """Handle user request to repeat information"""
    call_sid = request.form.get('CallSid')
    speech_result = request.form.get('SpeechResult', '')
    digits = request.form.get('Digits', '')
    
    logger.info(f"=== handle_repeat_request for call {call_sid} ===")
    logger.info(f"Speech: '{speech_result}', Digits: '{digits}'")
    
    response = VoiceResponse()
    
    try:
        session = agent.get_call_session(call_sid)
        
        # Check if user wants to repeat
        if digits == '1' or (speech_result and any(word in speech_result.lower() for word in ['yes', 'yeah', 'repeat'])):
            logger.info("User requested repeat")
            if session and 'last_voice_message' in session:
                logger.info("Playing stored voice message")
                response.say(session['last_voice_message'], voice='alice', language='en-US')
            else:
                logger.warning("No stored voice message found")
                response.say("I'm sorry, I don't have the information to repeat. Let me help you with something else.", voice='alice', language='en-US')
        else:
            logger.info("User did not request repeat")
        
        # Continue to additional help
        response.redirect('/ask_additional_help')
        
    except Exception as e:
        logger.error(f"Error in handle_repeat_request: {e}", exc_info=True)
        response.say("I'm sorry, there was an error. Let me help you with something else.", voice='alice', language='en-US')
        response.redirect('/ask_additional_help')
    
    logger.info(f"Returning repeat response: {str(response)}")
    return str(response)

@app.route('/ask_additional_help', methods=['POST'])
def ask_additional_help():
    """Ask if user needs additional help"""
    call_sid = request.form.get('CallSid')
    
    logger.info(f"=== ask_additional_help for call {call_sid} ===")
    
    response = VoiceResponse()
    
    try:
        gather = Gather(
            input='speech dtmf',
            timeout=8,
            speech_timeout=3,
            action='/handle_additional_help',
            method='POST',
            num_digits=1
        )
        gather.say("Is there anything else I can help you with today? Say yes or press 1 for another search, or say no or press 2 to end the call.", voice='alice', language='en-US')
        response.append(gather)
        
        # Default to ending call if no response
        response.say("Thank you for using our custody lookup service. Goodbye.", voice='alice', language='en-US')
        response.hangup()
        
        # Clean up session
        agent.cleanup_session(call_sid)
        
    except Exception as e:
        logger.error(f"Error in ask_additional_help: {e}", exc_info=True)
        response.say("Thank you for calling. Goodbye.", voice='alice', language='en-US')
        response.hangup()
        agent.cleanup_session(call_sid)
    
    logger.info(f"Returning additional help response: {str(response)}")
    return str(response)

@app.route('/handle_additional_help', methods=['POST'])
def handle_additional_help():
    """Handle user response for additional help - simplified version"""
    call_sid = request.form.get('CallSid')
    speech_result = request.form.get('SpeechResult', '')
    digits = request.form.get('Digits', '')
    
    logger.info(f"=== handle_additional_help for call {call_sid} ===")
    logger.info(f"Speech: '{speech_result}', Digits: '{digits}'")
    
    response = VoiceResponse()
    
    try:
        # Check if user wants another search
        if digits == '1' or (speech_result and any(word in speech_result.lower() for word in ['yes', 'yeah', 'another', 'more', 'again'])):
            logger.info("User requested another search")
            response.say("Starting a new search.", voice='alice', language='en-US')
            
            # Reset session for new search
            if call_sid in agent.call_sessions:
                session = agent.call_sessions[call_sid]
                session['first_name'] = None
                session['last_name'] = None
                session['current_step'] = 'collecting_first_name'
                # Clear any stored voice message
                if 'last_voice_message' in session:
                    del session['last_voice_message']
                logger.info("Reset session for new search")
            
            response.redirect('/collect_first_name')
        else:
            logger.info("User wants to end call")
            response.say("Thank you for calling. Goodbye.", voice='alice', language='en-US')
            response.hangup()
    
    except Exception as e:
        logger.error(f"Error in handle_additional_help: {e}", exc_info=True)
        response.say("Goodbye.", voice='alice', language='en-US')
        response.hangup()
    
    finally:
        # Always clean up session when we're done
        if not any(word in speech_result.lower() for word in ['yes', 'yeah', 'another', 'more', 'again']) and digits != '1':
            agent.cleanup_session(call_sid)
    
    logger.info(f"Returning additional help response: {str(response)}")
    return str(response)

# Test endpoint for custody lookup functionality (for development/debugging)
@app.route('/test_custody_lookup', methods=['GET', 'POST'])
def test_custody_lookup():
    """Test endpoint for custody lookup functionality"""
    if request.method == 'GET':
        return """
        <html>
        <head>
            <title>Test Custody Lookup</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                input, select { margin: 5px; padding: 8px; }
                input[type="submit"] { background-color: #4CAF50; color: white; padding: 10px 20px; border: none; cursor: pointer; }
            </style>
        </head>
        <body>
            <h2>Test Custody Lookup System</h2>
            <form method="post">
                <p><label>First Name:</label><br><input type="text" name="first_name" placeholder="John"></p>
                <p><label>Last Name:</label><br><input type="text" name="last_name" placeholder="Doe" required></p>
                <p><label>Date of Birth:</label><br><input type="text" name="date_of_birth" placeholder="January 15, 1990 or 01/15/1990"></p>
                <p><label>Gender:</label><br>
                    <select name="gender">
                        <option value="M">Male</option>
                        <option value="F">Female</option>
                        <option value="">Any</option>
                    </select>
                </p>
                <p><input type="submit" value="Search Custody Database"></p>
            </form>
        </body>
        </html>
        """
    
    # Process test search
    first_name = request.form.get('first_name', '')
    last_name = request.form.get('last_name', '')
    date_of_birth = request.form.get('date_of_birth', '')
    gender = request.form.get('gender', 'M')
    
    if not last_name:
        return jsonify({'error': 'Last name is required'})
    
    try:
        # Initialize the web driver
        web_driver = CustodyLookupWebDriver(headless=True)
        
        # Perform the lookup
        result = web_driver.perform_custody_lookup(
            first_name=first_name,
            last_name=last_name,
            date_of_birth=date_of_birth,
            gender=gender
        )
        
        # Clean up
        web_driver.cleanup()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'Test failed: {str(e)}'})

@app.route('/call_ended', methods=['POST'])
def call_ended():
    """Handle call completion cleanup"""
    call_sid = request.form.get('CallSid')
    agent.cleanup_session(call_sid)
    return "OK"

# Health check endpoint for monitoring
@app.route('/health', methods=['GET'])
def health_detailed():
    """Detailed health check endpoint"""
    try:
        # Test web driver setup
        test_driver = CustodyLookupWebDriver(headless=True)
        driver_status = test_driver.setup_driver()
        test_driver.cleanup()
        
        return jsonify({
            'status': 'healthy',
            'service': 'custody-lookup-ai-complete',
            'timestamp': datetime.now().isoformat(),
            'components': {
                'flask': 'ok',
                'twilio': 'ok' if agent.twilio_client else 'error',
                'openai': 'ok' if agent.openai_client else 'error',
                'selenium_webdriver': 'ok' if driver_status else 'error'
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('FLASK_PORT', 5000))
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    
    logger.info(f"Starting Flask app with Module 3 & 4 integrated on {host}:{port}")
    app.run(debug=debug, host=host, port=port)