import asyncio
import logging
import os
from typing import Optional, Dict, Any
import openai
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
from flask import Flask, request, jsonify
import tempfile
from datetime import datetime
import json
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CustodyLookupAgent:
    def __init__(self, openai_api_key: str, twilio_account_sid: str, twilio_auth_token: str):
        """
        Initialize the AI agent for custody lookup calls
        """
        self.openai_client = openai.OpenAI(api_key=openai_api_key)
        self.twilio_client = Client(twilio_account_sid, twilio_auth_token)
        self.call_sessions = {} 
        
        # Error handling constants
        self.MAX_RETRIES = 3
        self.MIN_NAME_LENGTH = 2
        self.MAX_NAME_LENGTH = 50
        
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
            timeout=8,
            speech_timeout=3,
            action='/handle_consent',
            method='POST',
            num_digits=1
        )
        gather.say(greeting_text, voice='alice', language='en-US')
        response.append(gather)
        
        # If no response, ask again once
        response.say("I didn't hear a response. Let me repeat that.", voice='alice', language='en-US')
        
        gather2 = Gather(
            input='speech dtmf',
            timeout=8,
            speech_timeout=3,
            action='/handle_consent',
            method='POST',
            num_digits=1
        )
        gather2.say(greeting_text, voice='alice', language='en-US')
        response.append(gather2)
        
        # Final fallback - assume they want to continue
        response.redirect('/collect_first_name')
        
        return response
    
    def handle_consent_response(self, speech_result: str, digits: str, call_sid: str) -> VoiceResponse:
        """Handle user consent to proceed with the service"""
        response = VoiceResponse()
        
        # Check for explicit "no" - otherwise proceed
        if digits == '2' or (speech_result and any(word in speech_result.lower() for word in ['no', 'nope', 'stop', 'quit', 'end'])):
            response.say("Thank you for calling. Goodbye.", voice='alice', language='en-US')
            response.hangup()
            return response
        
        # Initialize call session and proceed
        self.call_sessions[call_sid] = {
            'start_time': datetime.now(),
            'first_name': None,
            'last_name': None,
            'date': None,
            'current_step': 'collecting_first_name',
            'retry_count': 0,
            'errors': []
        }
        
        return self.collect_first_name()
    
    def validate_name(self, name: str) -> tuple[bool, str]:
        """Validate if the provided name seems reasonable"""
        if not name or name.strip() == "":
            return False, "No name was provided"
        
        name = name.strip()
        
        # Check length
        if len(name) < self.MIN_NAME_LENGTH:
            return False, f"Name seems too short. Please provide the full name."
        
        if len(name) > self.MAX_NAME_LENGTH:
            return False, f"Name seems too long. Please provide just the first name or last name."
        
        # Check for obvious speech recognition errors
        if any(phrase in name.lower() for phrase in ['i said', 'my name is', 'the name is', 'it is', 'that is']):
            # Extract the actual name part
            for phrase in ['i said', 'my name is', 'the name is', 'it is', 'that is']:
                if phrase in name.lower():
                    name = name.lower().split(phrase, 1)[1].strip()
                    break
        
        # Remove common filler words
        name = re.sub(r'\b(um|uh|well|so|like)\b', '', name, flags=re.IGNORECASE).strip()
        
        # Check if it contains only letters, spaces, hyphens, and apostrophes
        if not re.match(r"^[a-zA-Z\s\-']+$", name):
            return False, "The name contains invalid characters. Please spell it clearly."
        
        # Check for repeated characters (speech recognition error indicator)
        if re.search(r'(.)\1{3,}', name):
            return False, "I may have misheard that. Please repeat the name clearly."
        
        return True, name.title()
    
    def collect_first_name(self, retry_count: int = 0) -> VoiceResponse:
        """Collect the first name from the caller"""
        response = VoiceResponse()
        
        if retry_count == 0:
            instruction_text = (
                "Great! I'll need to collect some information to search the custody database. "
                "First, please clearly state the first name of the person you're looking up. "
                "Speak slowly and clearly."
            )
        elif retry_count == 1:
            instruction_text = (
                "I didn't catch that clearly. Please say just the first name again, "
                "speaking slowly and clearly. For example, say 'John' or 'Mary'."
            )
        else:
            instruction_text = (
                "Let me try a different approach. Please spell out the first name, "
                "one letter at a time. For example, J-O-H-N for John."
            )
        
        gather = Gather(
            input='speech',
            timeout=10,
            speech_timeout=4,
            action='/handle_first_name',
            method='POST',
            enhanced=True
        )
        gather.say(instruction_text, voice='alice', language='en-US')
        response.append(gather)
        
        # If no response after timeout
        if retry_count < self.MAX_RETRIES:
            response.say("I didn't hear anything. Let me try again.", voice='alice', language='en-US')
            response.redirect(f'/collect_first_name?retry={retry_count + 1}')
        else:
            response.say("I'm having trouble hearing you. Let me transfer you to an operator for assistance.", voice='alice', language='en-US')
            response.redirect('/transfer_to_operator')
        
        return response
    
    def handle_first_name(self, speech_result: str, call_sid: str) -> VoiceResponse:
        """Process the first name and move to last name collection"""
        response = VoiceResponse()
        
        session = self.call_sessions.get(call_sid, {})
        retry_count = session.get('retry_count', 0)
        
        # Log the raw speech result
        logger.info(f"First name raw speech: '{speech_result}' for call {call_sid}")
        
        # Handle empty or unclear speech
        if not speech_result or speech_result.strip() == "":
            if retry_count < self.MAX_RETRIES:
                session['retry_count'] = retry_count + 1
                session['errors'].append(f"Empty speech result on attempt {retry_count + 1}")
                response.say("I didn't hear anything. Let me ask again.", voice='alice', language='en-US')
                response.redirect(f'/collect_first_name?retry={retry_count + 1}')
                return response
            else:
                response.say("I'm having trouble hearing you clearly. Let me transfer you to an operator.", voice='alice', language='en-US')
                response.redirect('/transfer_to_operator')
                return response
        
        # Validate the name
        is_valid, processed_name = self.validate_name(speech_result)
        
        if not is_valid:
            if retry_count < self.MAX_RETRIES:
                session['retry_count'] = retry_count + 1
                session['errors'].append(f"Invalid name: {processed_name}")
                response.say(f"{processed_name} Let me ask again.", voice='alice', language='en-US')
                response.redirect(f'/collect_first_name?retry={retry_count + 1}')
                return response
            else:
                response.say("Let me transfer you to an operator who can help you better.", voice='alice', language='en-US')
                response.redirect('/transfer_to_operator')
                return response
        
        # Store the validated name
        session['first_name'] = processed_name
        session['current_step'] = 'collecting_last_name'
        session['retry_count'] = 0  # Reset retry count for next field
        
        logger.info(f"First name accepted: '{processed_name}' for call {call_sid}")
        
        # Confirm the name before proceeding
        confirmation_text = f"I heard the first name as {processed_name}. Is that correct? Say yes or no."
        
        gather = Gather(
            input='speech dtmf',
            timeout=8,
            speech_timeout=3,
            action='/confirm_first_name',
            method='POST',
            num_digits=1
        )
        gather.say(confirmation_text, voice='alice', language='en-US')
        response.append(gather)
        
        # If no confirmation, proceed anyway
        response.redirect('/collect_last_name')
        
        return response
    
    def confirm_first_name(self, speech_result: str, digits: str, call_sid: str) -> VoiceResponse:
        """Handle first name confirmation"""
        response = VoiceResponse()
        
        # Check if user said no or pressed 2
        if digits == '2' or (speech_result and any(word in speech_result.lower() for word in ['no', 'nope', 'incorrect', 'wrong'])):
            response.say("Let me ask for the first name again.", voice='alice', language='en-US')
            response.redirect('/collect_first_name')
        else:
            response.say("Great! Now for the last name.", voice='alice', language='en-US')
            response.redirect('/collect_last_name')
        
        return response
    
    def collect_last_name(self, retry_count: int = 0) -> VoiceResponse:
        """Collect the last name from the caller"""
        response = VoiceResponse()
        
        if retry_count == 0:
            instruction_text = "Now, please clearly state the last name."
        elif retry_count == 1:
            instruction_text = (
                "I didn't catch that clearly. Please say the last name again, "
                "speaking slowly and clearly."
            )
        else:
            instruction_text = (
                "Please spell out the last name, one letter at a time."
            )
        
        gather = Gather(
            input='speech',
            timeout=10,
            speech_timeout=4,
            action='/handle_last_name',
            method='POST',
            enhanced=True
        )
        gather.say(instruction_text, voice='alice', language='en-US')
        response.append(gather)
        
        # If no response after timeout
        if retry_count < self.MAX_RETRIES:
            response.say("I didn't hear anything. Let me try again.", voice='alice', language='en-US')
            response.redirect(f'/collect_last_name?retry={retry_count + 1}')
        else:
            response.say("I'm having trouble hearing you. Let me transfer you to an operator for assistance.", voice='alice', language='en-US')
            response.redirect('/transfer_to_operator')
        
        return response
    
    def handle_last_name(self, speech_result: str, call_sid: str) -> VoiceResponse:
        """Process the last name and move to date collection"""
        response = VoiceResponse()
        
        session = self.call_sessions.get(call_sid, {})
        retry_count = session.get('retry_count', 0)
        
        logger.info(f"Last name raw speech: '{speech_result}' for call {call_sid}")
        
        # Handle empty or unclear speech
        if not speech_result or speech_result.strip() == "":
            if retry_count < self.MAX_RETRIES:
                session['retry_count'] = retry_count + 1
                response.say("I didn't hear anything. Let me ask again.", voice='alice', language='en-US')
                response.redirect(f'/collect_last_name?retry={retry_count + 1}')
                return response
            else:
                response.say("I'm having trouble hearing you clearly. Let me transfer you to an operator.", voice='alice', language='en-US')
                response.redirect('/transfer_to_operator')
                return response
        
        # Validate the name
        is_valid, processed_name = self.validate_name(speech_result)
        
        if not is_valid:
            if retry_count < self.MAX_RETRIES:
                session['retry_count'] = retry_count + 1
                response.say(f"{processed_name} Let me ask again.", voice='alice', language='en-US')
                response.redirect(f'/collect_last_name?retry={retry_count + 1}')
                return response
            else:
                response.say("Let me transfer you to an operator who can help you better.", voice='alice', language='en-US')
                response.redirect('/transfer_to_operator')
                return response
        
        # Store the validated name
        session['last_name'] = processed_name
        session['current_step'] = 'collecting_date'
        session['retry_count'] = 0  # Reset retry count for next field
        
        logger.info(f"Last name accepted: '{processed_name}' for call {call_sid}")
        
        # Confirm the name before proceeding
        confirmation_text = f"I heard the last name as {processed_name}. Is that correct? Say yes or no."
        
        gather = Gather(
            input='speech dtmf',
            timeout=8,
            speech_timeout=3,
            action='/confirm_last_name',
            method='POST',
            num_digits=1
        )
        gather.say(confirmation_text, voice='alice', language='en-US')
        response.append(gather)
        
        # If no confirmation, proceed anyway
        response.redirect('/collect_date')
        
        return response
    
    def confirm_last_name(self, speech_result: str, digits: str, call_sid: str) -> VoiceResponse:
        """Handle last name confirmation"""
        response = VoiceResponse()
        
        # Check if user said no or pressed 2
        if digits == '2' or (speech_result and any(word in speech_result.lower() for word in ['no', 'nope', 'incorrect', 'wrong'])):
            response.say("Let me ask for the last name again.", voice='alice', language='en-US')
            response.redirect('/collect_last_name')
        else:
            response.say("Perfect! Now I need the date of birth.", voice='alice', language='en-US')
            response.redirect('/collect_date')
        
        return response
    
    def parse_date(self, date_str: str) -> tuple[bool, str]:
        """Parse and validate date input"""
        if not date_str or date_str.strip() == "":
            return False, "No date was provided"
        
        date_str = date_str.strip().lower()
        
        # Remove common filler phrases
        for phrase in ['the date is', 'date of birth is', 'born on', 'birthday is']:
            if phrase in date_str:
                date_str = date_str.replace(phrase, '').strip()
        
        # Basic validation - look for numbers and month names
        has_numbers = bool(re.search(r'\d', date_str))
        has_month = bool(re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', date_str))
        
        if not has_numbers:
            return False, "I need to hear numbers for the date. Please include the month, day, and year."
        
        # If it seems reasonable, accept it
        if len(date_str) >= 8:  # Minimum reasonable date length
            return True, date_str.title()
        else:
            return False, "The date seems incomplete. Please provide the full date of birth including month, day, and year."
    
    def collect_date(self, retry_count: int = 0) -> VoiceResponse:
        """Collect the date from the caller"""
        response = VoiceResponse()
        
        if retry_count == 0:
            instruction_text = (
                "Now, please provide the date of birth in month, day, year format. "
                "For example, say 'January 15th, 1990' or 'March 3rd, 1985'. "
                "Speak slowly and clearly."
            )
        elif retry_count == 1:
            instruction_text = (
                "I need the date of birth more clearly. Please say the month name, "
                "then the day, then the year. For example, 'June 10th, 1980'."
            )
        else:
            instruction_text = (
                "Let me try once more. Please say the birth date very slowly: "
                "first the month name, then the day number, then the four-digit year."
            )
        
        gather = Gather(
            input='speech',
            timeout=15,
            speech_timeout=5,
            action='/handle_date',
            method='POST',
            enhanced=True
        )
        gather.say(instruction_text, voice='alice', language='en-US')
        response.append(gather)
        
        # If no response after timeout
        if retry_count < self.MAX_RETRIES:
            response.say("I didn't hear a response. Let me ask again.", voice='alice', language='en-US')
            response.redirect(f'/collect_date?retry={retry_count + 1}')
        else:
            response.say("I'm having trouble getting the date information. Let me transfer you to an operator.", voice='alice', language='en-US')
            response.redirect('/transfer_to_operator')
        
        return response
    
    def handle_date(self, speech_result: str, call_sid: str) -> VoiceResponse:
        """Process the date and move to confirmation"""
        response = VoiceResponse()
        
        session = self.call_sessions.get(call_sid, {})
        retry_count = session.get('retry_count', 0)
        
        logger.info(f"Date raw speech: '{speech_result}' for call {call_sid}")
        
        # Handle empty or unclear speech
        if not speech_result or speech_result.strip() == "":
            if retry_count < self.MAX_RETRIES:
                session['retry_count'] = retry_count + 1
                response.say("I didn't hear the date. Let me ask again.", voice='alice', language='en-US')
                response.redirect(f'/collect_date?retry={retry_count + 1}')
                return response
            else:
                response.say("I'm having trouble hearing the date. Let me transfer you to an operator.", voice='alice', language='en-US')
                response.redirect('/transfer_to_operator')
                return response
        
        # Validate the date
        is_valid, processed_date = self.parse_date(speech_result)
        
        if not is_valid:
            if retry_count < self.MAX_RETRIES:
                session['retry_count'] = retry_count + 1
                response.say(f"{processed_date} Let me ask again.", voice='alice', language='en-US')
                response.redirect(f'/collect_date?retry={retry_count + 1}')
                return response
            else:
                response.say("Let me transfer you to an operator who can help you with the date.", voice='alice', language='en-US')
                response.redirect('/transfer_to_operator')
                return response
        
        # Store the validated date
        session['date'] = processed_date
        session['current_step'] = 'confirming_information'
        
        logger.info(f"Date accepted: '{processed_date}' for call {call_sid}")
        
        # Move to final confirmation
        response.redirect('/final_confirmation')
        
        return response
    
    def final_confirmation(self, call_sid: str) -> VoiceResponse:
        """Show final confirmation of all collected information"""
        response = VoiceResponse()
        
        session = self.call_sessions.get(call_sid, {})
        
        # Get all the information we collected
        first_name = session.get('first_name', 'Not provided')
        last_name = session.get('last_name', 'Not provided')
        date = session.get('date', 'Not provided')
        
        confirmation_text = (
            f"Thank you. Let me confirm the information I collected: "
            f"First name: {first_name}. "
            f"Last name: {last_name}. "
            f"Date of birth: {date}. "
            "Is this information correct? Say yes to continue or no to start over."
        )
        
        gather = Gather(
            input='speech dtmf',
            timeout=10,
            speech_timeout=3,
            action='/handle_final_confirmation',
            method='POST',
            num_digits=1
        )
        gather.say(confirmation_text, voice='alice', language='en-US')
        response.append(gather)
        
        # If no response, proceed anyway
        response.redirect('/process_custody_lookup')
        
        return response
    
    def handle_final_confirmation(self, speech_result: str, digits: str, call_sid: str) -> VoiceResponse:
        """Handle final confirmation response"""
        response = VoiceResponse()
        
        # Check if user said no or pressed 2
        if digits == '2' or (speech_result and any(word in speech_result.lower() for word in ['no', 'nope', 'incorrect', 'wrong', 'start over'])):
            response.say("No problem. Let me start over with collecting your information.", voice='alice', language='en-US')
            # Reset session
            session = self.call_sessions.get(call_sid, {})
            session['retry_count'] = 0
            session['first_name'] = None
            session['last_name'] = None
            session['date'] = None
            session['current_step'] = 'collecting_first_name'
            response.redirect('/collect_first_name')
        else:
            response.say("Perfect! I'm now searching the Riverside County custody database. This may take a moment. Please stay on the line.", voice='alice', language='en-US')
            response.redirect('/process_custody_lookup')
        
        return response
    
    def transfer_to_operator(self) -> VoiceResponse:
        """Handle transfer to human operator"""
        response = VoiceResponse()
        
        response.say(
            "I'm transferring you to a human operator who can assist you better. "
            "Please hold while I connect you. If no operator is available, "
            "please call back during business hours.",
            voice='alice', language='en-US'
        )
        
        # In a real implementation, you would dial an operator number here
        # For now, we'll just end the call with instructions
        response.say(
            "Unfortunately, no operator is currently available. "
            "Please call back during business hours from 8 AM to 5 PM, Monday through Friday. "
            "Thank you for calling.",
            voice='alice', language='en-US'
        )
        response.hangup()
        
        return response
    
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

@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'custody-lookup-ai',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/incoming_call', methods=['POST'])
def handle_incoming_call():
    """Handle incoming call webhook"""
    call_sid = request.form.get('CallSid')
    from_number = request.form.get('From')
    logger.info(f"Incoming call: {call_sid} from {from_number}")
    
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
    retry_count = int(request.args.get('retry', 0))
    logger.info(f"Collecting first name for call: {call_sid}, retry: {retry_count}")
    
    response = agent.collect_first_name(retry_count)
    return str(response)

@app.route('/handle_first_name', methods=['POST'])
def handle_first_name():
    """Handle first name input"""
    speech_result = request.form.get('SpeechResult', '')
    call_sid = request.form.get('CallSid')
    
    logger.info(f"First name - Call: {call_sid}, Speech: '{speech_result}'")
    
    response = agent.handle_first_name(speech_result, call_sid)
    return str(response)

@app.route('/confirm_first_name', methods=['POST'])
def confirm_first_name():
    """Handle first name confirmation"""
    speech_result = request.form.get('SpeechResult', '')
    digits = request.form.get('Digits', '')
    call_sid = request.form.get('CallSid')
    
    response = agent.confirm_first_name(speech_result, digits, call_sid)
    return str(response)

@app.route('/collect_last_name', methods=['POST'])
def collect_last_name():
    """Collect last name"""
    call_sid = request.form.get('CallSid')
    retry_count = int(request.args.get('retry', 0))
    logger.info(f"Collecting last name for call: {call_sid}, retry: {retry_count}")
    
    response = agent.collect_last_name(retry_count)
    return str(response)

@app.route('/handle_last_name', methods=['POST'])
def handle_last_name():
    """Handle last name input"""
    speech_result = request.form.get('SpeechResult', '')
    call_sid = request.form.get('CallSid')
    
    logger.info(f"Last name - Call: {call_sid}, Speech: '{speech_result}'")
    
    response = agent.handle_last_name(speech_result, call_sid)
    return str(response)

@app.route('/confirm_last_name', methods=['POST'])
def confirm_last_name():
    """Handle last name confirmation"""
    speech_result = request.form.get('SpeechResult', '')
    digits = request.form.get('Digits', '')
    call_sid = request.form.get('CallSid')
    
    response = agent.confirm_last_name(speech_result, digits, call_sid)
    return str(response)

@app.route('/collect_date', methods=['POST'])
def collect_date():
    """Collect date"""
    call_sid = request.form.get('CallSid')
    retry_count = int(request.args.get('retry', 0))
    logger.info(f"Collecting date for call: {call_sid}, retry: {retry_count}")
    
    response = agent.collect_date(retry_count)
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

@app.route('/handle_final_confirmation', methods=['POST'])
def handle_final_confirmation():
    """Handle final confirmation response"""
    speech_result = request.form.get('SpeechResult', '')
    digits = request.form.get('Digits', '')
    call_sid = request.form.get('CallSid')
    
    response = agent.handle_final_confirmation(speech_result, digits, call_sid)
    return str(response)

@app.route('/transfer_to_operator', methods=['POST'])
def transfer_to_operator():
    """Transfer to human operator"""
    response = agent.transfer_to_operator()
    return str(response)

@app.route('/process_custody_lookup', methods=['POST'])
def process_custody_lookup():
    """Placeholder for Phase 2 - Custody Lookup"""
    call_sid = request.form.get('CallSid')
    session = agent.get_call_session(call_sid)
    
    response = VoiceResponse()
    
    if session:
        response.say("Phase 1 complete! All information has been collected successfully. Phase 2 implementation will continue here. Thank you for testing!")
        logger.info(f"Phase 1 complete for call {call_sid}. Session data: {session}")
    else:
        response.say("Sorry, there was an error processing your request. Please call back.")
    
    response.hangup()
    return str(response)

@app.route('/call_ended', methods=['POST'])
def call_ended():
    """Handle call completion cleanup"""
    call_sid = request.form.get('CallSid')
    agent.cleanup_session(call_sid)
    return "OK"

if __name__ == '__main__':
    port = int(os.getenv('FLASK_PORT', 5000))
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    
    logger.info(f"Starting Flask app on {host}:{port}")
    app.run(debug=debug, host=host, port=port)