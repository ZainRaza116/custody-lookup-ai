import asyncio
import logging
from typing import Optional, Dict, Any
import openai
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
from flask import Flask, request, jsonify
import tempfile
import os
from datetime import datetime
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CustodyLookupAgent:
    def __init__(self, openai_api_key: str, twilio_account_sid: str, twilio_auth_token: str):
        """
        Initialize the AI agent for custody lookup calls
        
        Args:
            openai_api_key: OpenAI API key for Whisper
            twilio_account_sid: Twilio account SID
            twilio_auth_token: Twilio authentication token
        """
        self.openai_client = openai.OpenAI(api_key=openai_api_key)
        self.twilio_client = Client(twilio_account_sid, twilio_auth_token)
        self.call_sessions = {}  # Store call session data
        
    def create_greeting_response(self) -> VoiceResponse:
        """
        Create the initial greeting when call is received
        
        Returns:
            VoiceResponse: Twilio voice response with greeting
        """
        response = VoiceResponse()
        
        greeting_text = (
            "Hello, you've reached the automated custody status lookup service. "
            "I can help you check custody information using the Riverside County database. "
            "Please note that this call may be recorded for quality purposes. "
            "To continue, please say 'yes' or press 1. To end this call, say 'no' or hang up."
        )
        
        gather = Gather(
            input='speech dtmf',
            timeout=10,
            speech_timeout=3,
            action='/handle_consent',
            method='POST'
        )
        gather.say(greeting_text, voice='alice', language='en-US')
        response.append(gather)
        
        # Fallback if no input received
        response.say("I didn't receive your response. Please call back when you're ready. Goodbye.")
        response.hangup()
        
        return response
    
    def handle_consent_response(self, speech_result: str, digits: str, call_sid: str) -> VoiceResponse:
        """
        Handle user consent to proceed with the service
        
        Args:
            speech_result: Speech recognition result
            digits: DTMF digits pressed
            call_sid: Unique call identifier
            
        Returns:
            VoiceResponse: Next step in conversation
        """
        response = VoiceResponse()
        
        # Check for consent
        consent_given = False
        if digits == '1' or (speech_result and any(word in speech_result.lower() for word in ['yes', 'yeah', 'okay', 'ok', 'sure'])):
            consent_given = True
        elif digits == '2' or (speech_result and any(word in speech_result.lower() for word in ['no', 'nope', 'stop'])):
            consent_given = False
        
        if consent_given:
            # Initialize call session
            self.call_sessions[call_sid] = {
                'start_time': datetime.now(),
                'first_name': None,
                'last_name': None,
                'date': None,
                'current_step': 'collecting_first_name'
            }
            
            return self.collect_first_name()
        else:
            response.say("Thank you for calling. Goodbye.")
            response.hangup()
            return response
    
    def collect_first_name(self) -> VoiceResponse:
        """
        Collect the first name from the caller
        
        Returns:
            VoiceResponse: Prompt for first name
        """
        response = VoiceResponse()
        
        instruction_text = (
            "Great! I'll need to collect some information to search the custody database. "
            "First, please clearly state the first name of the person you're looking up. "
            "Please speak slowly and clearly."
        )
        
        gather = Gather(
            input='speech',
            timeout=10,
            speech_timeout=3,
            action='/handle_first_name',
            method='POST'
        )
        gather.say(instruction_text, voice='alice', language='en-US')
        response.append(gather)
        
        # Fallback
        response.say("I didn't catch that. Let me transfer you to try again.")
        response.redirect('/collect_first_name')
        
        return response
    
    def handle_first_name(self, speech_result: str, call_sid: str) -> VoiceResponse:
        """
        Process the first name and move to last name collection
        
        Args:
            speech_result: Recognized speech containing first name
            call_sid: Call session identifier
            
        Returns:
            VoiceResponse: Confirmation and next step
        """
        response = VoiceResponse()
        
        if not speech_result or len(speech_result.strip()) < 2:
            response.say("I didn't catch the first name clearly. Let me ask again.")
            response.redirect('/collect_first_name')
            return response
        
        # Clean and store first name
        first_name = speech_result.strip().title()
        
        if call_sid in self.call_sessions:
            self.call_sessions[call_sid]['first_name'] = first_name
            self.call_sessions[call_sid]['current_step'] = 'collecting_last_name'
        
        # Confirm and move to last name
        confirmation_text = f"I heard the first name as {first_name}. Now, please state the last name."
        
        gather = Gather(
            input='speech',
            timeout=10,
            speech_timeout=3,
            action='/handle_last_name',
            method='POST'
        )
        gather.say(confirmation_text, voice='alice', language='en-US')
        response.append(gather)
        
        return response
    
    def handle_last_name(self, speech_result: str, call_sid: str) -> VoiceResponse:
        """
        Process the last name and move to date collection
        
        Args:
            speech_result: Recognized speech containing last name
            call_sid: Call session identifier
            
        Returns:
            VoiceResponse: Confirmation and next step
        """
        response = VoiceResponse()
        
        if not speech_result or len(speech_result.strip()) < 2:
            response.say("I didn't catch the last name clearly. Let me ask again.")
            response.redirect('/collect_last_name')
            return response
        
        # Clean and store last name
        last_name = speech_result.strip().title()
        
        if call_sid in self.call_sessions:
            self.call_sessions[call_sid]['last_name'] = last_name
            self.call_sessions[call_sid]['current_step'] = 'collecting_date'
        
        # Confirm and move to date
        confirmation_text = (
            f"I heard the last name as {last_name}. "
            "Now, please provide the date of birth in month, day, year format. "
            "For example, say 'January 15th, 1990' or 'March 3rd, 1985'."
        )
        
        gather = Gather(
            input='speech',
            timeout=15,
            speech_timeout=4,
            action='/handle_date',
            method='POST'
        )
        gather.say(confirmation_text, voice='alice', language='en-US')
        response.append(gather)
        
        return response
    
    def handle_date(self, speech_result: str, call_sid: str) -> VoiceResponse:
        """
        Process the date and confirm all information
        
        Args:
            speech_result: Recognized speech containing date
            call_sid: Call session identifier
            
        Returns:
            VoiceResponse: Final confirmation
        """
        response = VoiceResponse()
        
        if not speech_result:
            response.say("I didn't catch the date. Let me ask again.")
            response.redirect('/collect_date')
            return response
        
        # Store date (you'll need to implement date parsing)
        date_input = speech_result.strip()
        
        if call_sid in self.call_sessions:
            self.call_sessions[call_sid]['date'] = date_input
            self.call_sessions[call_sid]['current_step'] = 'confirming_information'
            
            session = self.call_sessions[call_sid]
            
            # Final confirmation
            confirmation_text = (
                f"Let me confirm the information. "
                f"First name: {session['first_name']}. "
                f"Last name: {session['last_name']}. "
                f"Date: {session['date']}. "
                "Is this information correct? Please say 'yes' to proceed or 'no' to start over."
            )
            
            gather = Gather(
                input='speech dtmf',
                timeout=10,
                speech_timeout=3,
                action='/handle_confirmation',
                method='POST'
            )
            gather.say(confirmation_text, voice='alice', language='en-US')
            response.append(gather)
        
        return response
    
    def handle_confirmation(self, speech_result: str, digits: str, call_sid: str) -> VoiceResponse:
        """
        Handle final confirmation and proceed to lookup
        
        Args:
            speech_result: Speech recognition result
            digits: DTMF digits pressed
            call_sid: Call session identifier
            
        Returns:
            VoiceResponse: Processing message or restart
        """
        response = VoiceResponse()
        
        # Check confirmation
        confirmed = False
        if digits == '1' or (speech_result and any(word in speech_result.lower() for word in ['yes', 'yeah', 'correct', 'right'])):
            confirmed = True
        
        if confirmed and call_sid in self.call_sessions:
            # Mark as ready for Phase 2 processing
            self.call_sessions[call_sid]['current_step'] = 'ready_for_lookup'
            
            processing_text = (
                "Thank you. I'm now searching the Riverside County custody database. "
                "This may take a moment. Please stay on the line."
            )
            
            response.say(processing_text, voice='alice', language='en-US')
            
            # Redirect to Phase 2 (custody lookup)
            response.redirect('/process_custody_lookup')
            
        else:
            response.say("Let's start over with the information collection.")
            response.redirect('/collect_first_name')
        
        return response
    
    async def transcribe_audio(self, audio_file_path: str) -> Optional[str]:
        """
        Transcribe audio using OpenAI Whisper
        
        Args:
            audio_file_path: Path to audio file
            
        Returns:
            Transcribed text or None if failed
        """
        try:
            with open(audio_file_path, 'rb') as audio_file:
                transcript = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            return transcript.strip()
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return None
    
    def get_call_session(self, call_sid: str) -> Optional[Dict[str, Any]]:
        """
        Get call session data
        
        Args:
            call_sid: Call session identifier
            
        Returns:
            Session data or None
        """
        return self.call_sessions.get(call_sid)
    
    def cleanup_session(self, call_sid: str):
        """
        Clean up call session data
        
        Args:
            call_sid: Call session identifier
        """
        if call_sid in self.call_sessions:
            del self.call_sessions[call_sid]
            logger.info(f"Cleaned up session for call {call_sid}")

# Flask application for handling Twilio webhooks
app = Flask(__name__)

# Initialize the agent (you'll need to provide your API keys)
agent = CustodyLookupAgent(
    openai_api_key="your_openai_api_key",
    twilio_account_sid="your_twilio_account_sid",
    twilio_auth_token="your_twilio_auth_token"
)

@app.route('/incoming_call', methods=['POST'])
def handle_incoming_call():
    """Handle incoming call webhook"""
    call_sid = request.form.get('CallSid')
    logger.info(f"Incoming call: {call_sid}")
    
    response = agent.create_greeting_response()
    return str(response)

@app.route('/handle_consent', methods=['POST'])
def handle_consent():
    """Handle consent response"""
    speech_result = request.form.get('SpeechResult', '')
    digits = request.form.get('Digits', '')
    call_sid = request.form.get('CallSid')
    
    response = agent.handle_consent_response(speech_result, digits, call_sid)
    return str(response)

@app.route('/collect_first_name', methods=['POST'])
def collect_first_name():
    """Collect first name"""
    response = agent.collect_first_name()
    return str(response)

@app.route('/handle_first_name', methods=['POST'])
def handle_first_name():
    """Handle first name input"""
    speech_result = request.form.get('SpeechResult', '')
    call_sid = request.form.get('CallSid')
    
    response = agent.handle_first_name(speech_result, call_sid)
    return str(response)

@app.route('/collect_last_name', methods=['POST'])
def collect_last_name():
    """Redirect to collect last name"""
    call_sid = request.form.get('CallSid')
    session = agent.get_call_session(call_sid)
    
    if session and session['first_name']:
        response = VoiceResponse()
        response.say(f"Please state the last name for {session['first_name']}.")
        
        gather = Gather(
            input='speech',
            timeout=10,
            speech_timeout=3,
            action='/handle_last_name',
            method='POST'
        )
        response.append(gather)
        return str(response)
    else:
        return str(agent.collect_first_name())

@app.route('/handle_last_name', methods=['POST'])
def handle_last_name():
    """Handle last name input"""
    speech_result = request.form.get('SpeechResult', '')
    call_sid = request.form.get('CallSid')
    
    response = agent.handle_last_name(speech_result, call_sid)
    return str(response)

@app.route('/collect_date', methods=['POST'])
def collect_date():
    """Redirect to collect date"""
    call_sid = request.form.get('CallSid')
    session = agent.get_call_session(call_sid)
    
    if session and session['last_name']:
        response = VoiceResponse()
        response.say("Please provide the date of birth in month, day, year format.")
        
        gather = Gather(
            input='speech',
            timeout=15,
            speech_timeout=4,
            action='/handle_date',
            method='POST'
        )
        response.append(gather)
        return str(response)
    else:
        return str(agent.collect_first_name())

@app.route('/handle_date', methods=['POST'])
def handle_date():
    """Handle date input"""
    speech_result = request.form.get('SpeechResult', '')
    call_sid = request.form.get('CallSid')
    
    response = agent.handle_date(speech_result, call_sid)
    return str(response)

@app.route('/handle_confirmation', methods=['POST'])
def handle_confirmation():
    """Handle final confirmation"""
    speech_result = request.form.get('SpeechResult', '')
    digits = request.form.get('Digits', '')
    call_sid = request.form.get('CallSid')
    
    response = agent.handle_confirmation(speech_result, digits, call_sid)
    return str(response)

@app.route('/process_custody_lookup', methods=['POST'])
def process_custody_lookup():
    """Placeholder for Phase 2 - Custody Lookup"""
    call_sid = request.form.get('CallSid')
    session = agent.get_call_session(call_sid)
    
    response = VoiceResponse()
    
    if session:
        # This is where Phase 2 will be implemented
        response.say("Processing your request. Phase 2 implementation will continue here.")
        logger.info(f"Ready for custody lookup: {session}")
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
    app.run(debug=True, port=5000)