# Custody Lookup AI 🤖📞

An intelligent voice-powered service that automates custody status inquiries through phone calls. Users can call in, provide personal information via voice, and receive real-time custody status information from the Riverside County Sheriff's database.

## 🌟 Features

- **Voice Recognition**: Powered by OpenAI Whisper for accurate speech-to-text conversion
- **Automated Phone System**: Built on Twilio for reliable call handling
- **Real-time Database Lookup**: Automatically searches Riverside County custody records
- **Natural Language Processing**: Understands and processes spoken information
- **Privacy-First Design**: No long-term data storage, immediate session cleanup
- **Error Handling**: Robust fallback mechanisms for unclear speech or system issues

## 🎯 How It Works

1. **📞 Call Reception**: User calls the service number
2. **🎤 Voice Collection**: AI agent collects first name, last name, and date of birth
3. **✅ Confirmation**: System confirms information accuracy with the caller
4. **🔍 Database Search**: Automatically queries the custody database
5. **📋 Results Delivery**: Provides custody status information back to caller

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Phone Call    │ ── │  Twilio Voice   │ ── │  Flask Server   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ OpenAI Whisper  │ ── │ Speech-to-Text  │ ── │ Session Manager │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Web Automation  │ ── │ Custody Lookup  │ ── │  Result Parser  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Twilio Account with phone number
- OpenAI API access
- HTTPS-enabled server or ngrok for development

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/custody-lookup-ai.git
cd custody-lookup-ai
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env with your API keys
```

4. **Configure environment**
```bash
# .env file
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
OPENAI_API_KEY=your_openai_api_key
FLASK_ENV=development
```

5. **Run the application**
```bash
python app.py
```

6. **Expose with ngrok (for development)**
```bash
ngrok http 5000
```

7. **Configure Twilio webhook**
- Go to Twilio Console → Phone Numbers
- Set webhook URL to: `https://your-ngrok-url.ngrok.io/incoming_call`
- Method: POST

## 📁 Project Structure

```
custody-lookup-ai/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variables template
├── .gitignore            # Git ignore rules
├── README.md             # This file
├── docs/                 # Documentation
│   ├── API.md            # API documentation
│   ├── DEPLOYMENT.md     # Deployment guide
│   └── TWILIO_SETUP.md   # Twilio configuration guide
├── src/                  # Source code
│   ├── __init__.py
│   ├── agent.py          # AI agent logic
│   ├── webhooks.py       # Twilio webhook handlers
│   ├── custody_lookup.py # Web scraping logic
│   └── utils.py          # Utility functions
├── tests/                # Test files
│   ├── test_agent.py
│   ├── test_webhooks.py
│   └── test_custody_lookup.py
└── logs/                 # Application logs
```

## 🔧 Configuration

### Twilio Setup
1. Purchase a phone number from Twilio
2. Configure voice webhook: `https://yourdomain.com/incoming_call`
3. Set HTTP method to POST
4. Optional: Configure status callback for call monitoring

### OpenAI Setup
1. Create OpenAI account
2. Generate API key
3. Ensure Whisper API access is enabled

## 📞 Usage

### Making a Call
1. **Dial** your configured Twilio number
2. **Listen** to the greeting and consent prompt
3. **Provide** requested information clearly:
   - First name
   - Last name  
   - Date of birth
4. **Confirm** information accuracy
5. **Wait** for custody status results

### Voice Commands
- Say **"yes"** or press **1** to consent
- Say **"no"** or press **2** to decline
- Speak clearly for best recognition
- Follow prompts for each information field

## 🛠️ API Reference

### Webhook Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/incoming_call` | POST | Initial call handler |
| `/handle_consent` | POST | Process user consent |
| `/collect_first_name` | POST | First name collection |
| `/handle_first_name` | POST | Process first name |
| `/collect_last_name` | POST | Last name collection |
| `/handle_last_name` | POST | Process last name |
| `/collect_date` | POST | Date collection |
| `/handle_date` | POST | Process date |
| `/handle_confirmation` | POST | Final confirmation |
| `/process_custody_lookup` | POST | Phase 2 - Database lookup |
| `/call_ended` | POST | Session cleanup |

### Session Data Structure
```json
{
  "call_sid": "CA1234567890abcdef",
  "start_time": "2025-06-06T10:30:00Z",
  "first_name": "John",
  "last_name": "Smith", 
  "date": "January 15th, 1990",
  "current_step": "ready_for_lookup"
}
```

## 🔒 Security & Privacy

- **No Data Persistence**: Personal information is immediately deleted after call completion
- **Webhook Validation**: All requests validated to ensure they come from Twilio
- **HTTPS Required**: All communications encrypted in transit
- **Rate Limiting**: Protection against abuse and DoS attacks
- **Session Isolation**: Each call maintains separate session data

## 🧪 Testing

### Unit Tests
```bash
python -m pytest tests/
```

### Manual Testing
1. **Call Flow Test**: Complete end-to-end call
2. **Speech Recognition**: Test with various accents/voices
3. **Error Handling**: Test invalid inputs and timeouts
4. **Load Testing**: Multiple concurrent calls

### Test Cases
- ✅ Clear speech recognition
- ✅ Unclear speech handling
- ✅ Timeout scenarios
- ✅ Invalid date formats
- ✅ Consent denial
- ✅ Mid-call hangups
- ✅ System errors

## 📊 Monitoring & Logging

### Application Logs
```bash
tail -f logs/custody_lookup.log
```

### Twilio Console
- Monitor call logs and errors
- Track webhook response times
- View usage statistics

### Key Metrics
- Call completion rate
- Speech recognition accuracy
- Average call duration
- Error rates by endpoint

## 🚀 Deployment

### Production Deployment Options

#### Option 1: Heroku
```bash
git push heroku main
heroku config:set TWILIO_ACCOUNT_SID=your_sid
heroku config:set TWILIO_AUTH_TOKEN=your_token
heroku config:set OPENAI_API_KEY=your_key
```

#### Option 2: AWS
- Deploy using Elastic Beanstalk
- Configure Application Load Balancer for HTTPS
- Use Parameter Store for secrets

#### Option 3: DigitalOcean
- Use App Platform for easy deployment
- Configure environment variables
- Enable automatic HTTPS

### Environment Variables
```bash
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
OPENAI_API_KEY=your_openai_api_key
FLASK_ENV=production
LOG_LEVEL=INFO
```

## 🤝 Contributing

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Development Guidelines
- Follow PEP 8 style guide
- Add unit tests for new features
- Update documentation as needed
- Test with real phone calls before submitting

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

### Common Issues

**Issue**: Webhook not receiving requests
- **Solution**: Ensure HTTPS URL is publicly accessible

**Issue**: Speech recognition errors
- **Solution**: Check microphone quality, speak clearly and slowly

**Issue**: Twilio authentication errors
- **Solution**: Verify account SID and auth token are correct

### Getting Help
- 📧 **Email**: support@yourcompany.com
- 📚 **Documentation**: [Full docs](docs/)
- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/yourusername/custody-lookup-ai/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/yourusername/custody-lookup-ai/discussions)

## 🏆 Acknowledgments

- **OpenAI** for Whisper speech recognition
- **Twilio** for voice communication platform
- **Riverside County Sheriff** for providing public custody database
- **Flask** framework for web application structure

## 🔄 Version History

- **v1.0.0** - Initial release with basic voice collection
- **v1.1.0** - Added error handling and session management
- **v1.2.0** - Improved speech recognition accuracy
- **v2.0.0** - Added custody database integration (Phase 2)

## 🛣️ Roadmap

### Phase 1 ✅
- [x] Voice call handling
- [x] Speech-to-text with Whisper
- [x] Information collection workflow
- [x] Session management

### Phase 2 🚧
- [ ] Web scraping integration
- [ ] Custody database lookup
- [ ] Result parsing and delivery
- [ ] Error handling for lookup failures

### Phase 3 🎯
- [ ] Multi-language support
- [ ] SMS result delivery option
- [ ] Multiple county database support
- [ ] Advanced analytics and reporting

---

**Built with ❤️ for automating custody status inquiries**

*For more information, visit our [documentation](docs/) or contact our support team.*