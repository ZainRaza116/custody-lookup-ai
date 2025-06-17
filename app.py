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
    
    def parse_date_of_birth(self, date_str: str) -> Optional[str]:
        """Parse various date formats into MM/DD/YYYY format required by the form"""
        if not date_str or date_str == "Not provided":
            return None
        
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
        return None
    
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
            
            # Fill Date of Birth (optional)
            if formatted_dob:
                dob_field = self.driver.find_element(By.CSS_SELECTOR, self.selectors['date_of_birth'])
                dob_field.clear()
                dob_field.send_keys(formatted_dob)
                logger.info(f"✅ Filled date of birth: {formatted_dob}")
            else:
                logger.warning(f"⚠️ Could not format date: '{date_of_birth}'")
            
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
        """Parse the search results page and extract custody information"""
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
        """Perform complete custody lookup workflow"""
        start_time = time.time()
        
        try:
            # Setup driver if not already done
            if not self.driver:
                if not self.setup_driver():
                    return {
                        'success': False,
                        'error_message': "Failed to initialize web driver",
                        'duration': time.time() - start_time
                    }
            
            # Navigate to custody page
            if not self.navigate_to_custody_page():
                return {
                    'success': False,
                    'error_message': "Failed to navigate to custody lookup page",
                    'duration': time.time() - start_time
                }
            
            # Fill the search form
            if not self.fill_search_form(first_name, last_name, date_of_birth, gender):
                return {
                    'success': False,
                    'error_message': "Failed to fill search form",
                    'duration': time.time() - start_time
                }
            
            # Submit the search
            if not self.submit_search():
                return {
                    'success': False,
                    'error_message': "Failed to submit search form",
                    'duration': time.time() - start_time
                }
            
            # Parse results
            results = self.parse_search_results()
            results['duration'] = time.time() - start_time
            results['search_params'] = {
                'first_name': first_name,
                'last_name': last_name,
                'date_of_birth': date_of_birth,
                'gender': gender
            }
            
            return results
            
        except Exception as e:
            logger.error(f"Error during custody lookup: {e}")
            return {
                'success': False,
                'error_message': f"Unexpected error during lookup: {str(e)}",
                'duration': time.time() - start_time
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
        
        return self.collect_first_name()
    
    def collect_first_name(self) -> VoiceResponse:
        """Collect the first name from the caller"""
        response = VoiceResponse()
        
        instruction_text = (
            "Great! I'll need to collect some information to search the custody database. "
            "First, please clearly state just the first name of the person you're looking up. "
            "Speak slowly and clearly. For example, say 'John' or 'Michael'."
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
            "Now, please clearly state just the last name. "
            "Speak slowly and clearly. For example, say 'Smith' or 'Johnson'."
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
        
        response.redirect('/collect_date')
        return response
    
    def collect_date(self) -> VoiceResponse:
        """Collect the date from the caller"""
        response = VoiceResponse()
        
        instruction_text = (
            "Now, please provide the date of birth. "
            "Say it clearly in month, day, year format. "
            "For example, say 'January 15th, 1990' or 'March 3rd, 1985'. "
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
        """Process the date and move to confirmation"""
        response = VoiceResponse()
        
        # Clean the date input
        date_input = self.clean_date_input(speech_result) if speech_result else "Not provided"
        
        if call_sid in self.call_sessions:
            self.call_sessions[call_sid]['date'] = date_input
            self.call_sessions[call_sid]['current_step'] = 'confirming_information'
        
        logger.info(f"Date captured: '{date_input}' for call {call_sid}")
        
        # Confirm the date if we got something useful
        if date_input != "Not provided":
            response.say(f"I heard the date as {date_input}.", voice='alice', language='en-US')
        
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
        
        # Get all the information we collected
        first_name = session.get('first_name', 'Not provided')
        last_name = session.get('last_name', 'Not provided')
        date = session.get('date', 'Not provided')
        
        confirmation_text = (
            f"Thank you. I have collected the following information: "
            f"First name: {first_name}. "
            f"Last name: {last_name}. "
            f"Date: {date}. "
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

@app.route('/collect_date', methods=['POST'])
def collect_date():
    """Collect date"""
    call_sid = request.form.get('CallSid')
    logger.info(f"Collecting date for call: {call_sid}")
    
    response = agent.collect_date()
    return str(response)

@app.route('/handle_date', methods=['POST'])
def handle_date():
    """Handle date input"""
    speech_result = request.form.get('SpeechResult', '')
    call_sid = request.form.get('CallSid')
    
    logger.info(f"Date - Call: {call_sid}, Speech: '{speech_result}'")
    
    response = agent.handle_date(speech_result, call_sid)
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
    """MODULE 3: Process custody lookup using collected information"""
    call_sid = request.form.get('CallSid')
    session = agent.get_call_session(call_sid)
    
    response = VoiceResponse()
    
    if not session:
        response.say("Sorry, I couldn't find your session information. Please call back and try again.")
        response.hangup()
        return str(response)
    
    # Get the collected information
    first_name = session.get('first_name', 'Not provided')
    last_name = session.get('last_name', 'Not provided') 
    date_of_birth = session.get('date', 'Not provided')
    
    # Validate we have at least a last name
    if not last_name or last_name == "Not provided":
        response.say("I need at least a last name to perform the search. Let me try to search with the information I have.")
    
    try:
        # Perform the custody lookup using Module 3
        logger.info(f"Starting custody lookup for call {call_sid}: {first_name} {last_name}, DOB: {date_of_birth}")
        
        # Initialize the web driver (VISIBLE mode for debugging)
        web_driver = CustodyLookupWebDriver(headless=False)
        
        # Perform the lookup
        lookup_result = web_driver.perform_custody_lookup(
            first_name=first_name,
            last_name=last_name,
            date_of_birth=date_of_birth,
            gender="M"  # Default to male
        )
        
        # Clean up the web driver
        web_driver.cleanup()
        
        # Format results for voice delivery
        voice_message = agent.format_custody_results_for_voice(lookup_result)
        
        # Deliver the results via voice
        response.say(voice_message, voice='alice', language='en-US')
        
        # Ask if they need anything else
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
        
        # Log the complete result for debugging
        logger.info(f"Custody lookup completed for call {call_sid}. Success: {lookup_result['success']}, Found: {lookup_result.get('inmates_found', 0)} records")
        
    except Exception as e:
        logger.error(f"Error during custody lookup for call {call_sid}: {e}")
        response.say("I'm sorry, there was a technical error performing the custody search. The system may be temporarily unavailable. Please try calling back in a few minutes.", voice='alice', language='en-US')
        response.hangup()
    
    finally:
        # Clean up session after lookup is complete
        agent.cleanup_session(call_sid)
    
    return str(response)

@app.route('/handle_additional_help', methods=['POST'])
def handle_additional_help():
    """Handle user response for additional help"""
    speech_result = request.form.get('SpeechResult', '')
    digits = request.form.get('Digits', '')
    call_sid = request.form.get('CallSid')
    
    response = VoiceResponse()
    
    # Check if user wants another search
    if digits == '1' or (speech_result and any(word in speech_result.lower() for word in ['yes', 'yeah', 'another', 'more', 'again'])):
        response.say("I'll help you with another custody search. Let me collect the information again.", voice='alice', language='en-US')
        
        # Reset session for new search
        if call_sid in agent.call_sessions:
            session = agent.call_sessions[call_sid]
            session['first_name'] = None
            session['last_name'] = None
            session['date'] = None
            session['current_step'] = 'collecting_first_name'
        
        response.redirect('/collect_first_name')
    else:
        response.say("Thank you for using our custody lookup service. Have a great day!", voice='alice', language='en-US')
        response.hangup()
    
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
    
    logger.info(f"Starting Flask app with Module 3 integrated on {host}:{port}")
    app.run(debug=debug, host=host, port=port)