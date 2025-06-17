import os
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables securely
load_dotenv()

def make_test_call():
    """Make a test call to verify the custody lookup system"""
    
    # Get credentials from environment variables
    account_sid = 'ACfca506577596fcae1c5a38e9475b12c2'
    auth_token = '8cc079c027506ec5e755e1015169eb58'
    
    if not account_sid or not auth_token:
        print("❌ Error: Twilio credentials not found in environment variables")
        print("Please set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in your .env file")
        return
    
    try:
        client = Client(account_sid, auth_token)
        
        # Make the call to test your custody lookup system
        print("📞 Initiating test call...")
        
        call = client.calls.create(
            to='+923048685416',  # Your Pakistani number
            from_='+12293606141',  # Your Twilio US number
            url='https://efad-182-181-248-252.ngrok-free.app/incoming_call',  # Your webhook URL
            method='POST'
        )
        
        print(f"✅ Call SID: {call.sid}")
        print("📱 Call initiated! You should receive a call shortly.")
        print("🎤 You'll hear your custody lookup greeting message.")
        print("\n📋 Test Instructions:")
        print("1. Answer the call")
        print("2. Say 'yes' to continue")
        print("3. Provide a first name (e.g., 'John')")
        print("4. Provide a last name (e.g., 'Smith')")
        print("5. Provide a date of birth (e.g., 'January 15, 1990')")
        print("6. Wait for the system to search and provide results")
        
    except Exception as e:
        print(f"❌ Error making call: {e}")
        
        # Common error troubleshooting
        if "authenticate" in str(e).lower():
            print("\n🔧 Authentication Error:")
            print("- Check your TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN")
            print("- Make sure they're correctly set in your .env file")
        elif "permissions" in str(e).lower():
            print("\n🔧 Permissions Error:")
            print("- Check if your Twilio account has calling permissions")
            print("- Verify your account has sufficient credits")
        elif "number" in str(e).lower():
            print("\n🔧 Phone Number Error:")
            print("- Verify your Twilio phone number is active: +12293606141")
            print("- Check if the destination number +923048685416 is valid")

if __name__ == "__main__":
    make_test_call()