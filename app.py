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
            "First, please clearly state the first name of the person you're looking up."
        )
        
        gather = Gather(
            input='speech',
            timeout=5,
            speech_timeout=2,
            action='/handle_first_name',
            method='POST'
        )
        gather.say(instruction_text, voice='alice', language='en-US')
        response.append(gather)
        
        # If no response, just move to next step
        response.redirect('/collect_last_name')
        
        return response
    
    def handle_first_name(self, speech_result: str, call_sid: str) -> VoiceResponse:
        """Process the first name and move to last name collection"""
        response = VoiceResponse()
        
        # Store whatever we got (even if empty)
        first_name = speech_result.strip().title() if speech_result else "Not provided"
        
        if call_sid in self.call_sessions:
            self.call_sessions[call_sid]['first_name'] = first_name
            self.call_sessions[call_sid]['current_step'] = 'collecting_last_name'
        
        logger.info(f"First name captured: '{first_name}' for call {call_sid}")
        
        # Just move to last name without confirmation
        response.redirect('/collect_last_name')
        
        return response
    
    def collect_last_name(self) -> VoiceResponse:
        """Collect the last name from the caller"""
        response = VoiceResponse()
        
        instruction_text = "Now, please state the last name."
        
        gather = Gather(
            input='speech',
            timeout=5,
            speech_timeout=2,
            action='/handle_last_name',
            method='POST'
        )
        gather.say(instruction_text, voice='alice', language='en-US')
        response.append(gather)
        
        # If no response, just move to next step
        response.redirect('/collect_date')
        
        return response
    
    def handle_last_name(self, speech_result: str, call_sid: str) -> VoiceResponse:
        """Process the last name and move to date collection"""
        response = VoiceResponse()
        
        # Store whatever we got (even if empty)
        last_name = speech_result.strip().title() if speech_result else "Not provided"
        
        if call_sid in self.call_sessions:
            self.call_sessions[call_sid]['last_name'] = last_name
            self.call_sessions[call_sid]['current_step'] = 'collecting_date'
        
        logger.info(f"Last name captured: '{last_name}' for call {call_sid}")
        
        # Just move to date without confirmation
        response.redirect('/collect_date')
        
        return response
    
    def collect_date(self) -> VoiceResponse:
        """Collect the date from the caller"""
        response = VoiceResponse()
        
        instruction_text = (
            "Now, please provide the date of birth in month, day, year format. "
            "For example, say 'January 15th, 1990'."
        )
        
        gather = Gather(
            input='speech',
            timeout=5,
            speech_timeout=2,
            action='/handle_date',
            method='POST'
        )
        gather.say(instruction_text, voice='alice', language='en-US')
        response.append(gather)
        
        # If no response, just move to confirmation
        response.redirect('/final_confirmation')
        
        return response
    
    def handle_date(self, speech_result: str, call_sid: str) -> VoiceResponse:
        """Process the date and move to confirmation"""
        response = VoiceResponse()
        
        # Store whatever we got (even if empty)
        date_input = speech_result.strip() if speech_result else "Not provided"
        
        if call_sid in self.call_sessions:
            self.call_sessions[call_sid]['date'] = date_input
            self.call_sessions[call_sid]['current_step'] = 'confirming_information'
        
        logger.info(f"Date captured: '{date_input}' for call {call_sid}")
        
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