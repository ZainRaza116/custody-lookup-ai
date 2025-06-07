from twilio.rest import Client

# Twilio credentials
account_sid = 'ACfca506577596fcae1c5a38e9475b12c2'
auth_token = '8cc079c027506ec5e755e1015169eb58'
client = Client(account_sid, auth_token)

# Make the call to test your custody lookup system
call = client.calls.create(
    to='+923048685416',  # Your Pakistani number
    from_='+12293606141',  # Your Twilio US number
    url='https://d485-139-135-59-36.ngrok-free.app/incoming_call',  # Your webhook URL
    method='POST'
)

print(f"Call SID: {call.sid}")
print("Call initiated! You should receive a call shortly.")
print("You'll hear your custody lookup greeting message.")