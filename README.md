# 🤖 Telegram Group Help Bot

A powerful, feature-rich Telegram bot for group management with AI capabilities, translation services, and MongoDB integration.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-blue.svg)](https://core.telegram.org/bots)
[![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-green.svg)](https://www.mongodb.com/atlas)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ Features

### 🛡️ Group Management
- **Admin Tools** - Promote, demote, manage permissions
- **Moderation** - Warn, mute, ban users
- **Welcome Messages** - Customizable welcome with media and buttons
- **Auto-Delete** - Automatic message deletion
- **Clean Service** - Auto-delete service messages
- **Bot Protection** - Prevent unauthorized bot additions
- **Link Spam Protection** - Block unwanted links
- **Forward Protection** - Block forwarded messages
- **Content Blocking** - Block specific text and media
- **Custom Filters** - Auto-response triggers

### 🤖 AI Features (NEW!)
- **ChatGPT Integration** - AI-powered conversations
- **Auto-Reply Chatbot** - No commands needed in private chat!
- **Multi-turn Context** - Remembers last 10 messages
- **Smart Responses** - Powered by GPT-4
- **Private Chat** - Just message the bot directly
- **Group Mentions** - Mention bot to ask questions

### 🌐 Translation (NEW!)
- **40+ Languages** - Support for major world languages
- **Auto-Detection** - Automatic source language detection
- **Interactive Menu** - Easy language selection
- **Fast Translation** - Powered by Deep Translate API

### 💾 Database
- **MongoDB Atlas** - Cloud-based persistent storage
- **8 Collections** - Organized data structure
- **Auto-Indexes** - Optimized queries
- **Migration Tool** - Easy JSON to MongoDB transfer
- **Auto-Backup** - MongoDB Atlas backups

---

## 🚀 Quick Start

### 1. Clone Repository
```bash
git clone https://github.com/nishkarshk212/titanic-saver.git
cd titanic-saver
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
cp .env.example .env
nano .env
```

Add your credentials:
```env
BOT_TOKEN=your_bot_token
LOG_CHANNEL_ID=your_log_channel
OWNER_ID=your_user_id
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/?appName=GROUPHELP
```

### 4. Test MongoDB Connection
```bash
python test_mongodb.py
```

### 5. Migrate Data (if upgrading)
```bash
python migrate_to_mongodb.py
```

### 6. Run Bot
```bash
python bot.py
```

---

## 📋 Available Commands

### General Commands
| Command | Description |
|---------|-------------|
| `/start` | Start the bot |
| `/help` | Show help menu |
| `/id` | Get user/chat ID |
| `/info` | User information |
| `/settings` | Group settings |

### AI Commands 🤖
| Command | Description |
|---------|-------------|
| (just message) | Auto-reply in private chat |
| `/ai <message>` | Chat with AI |
| `/gpt <message>` | Chat with AI (alias) |
| `/clearchat` | Clear AI history |

### Translation Commands 🌐
| Command | Description |
|---------|-------------|
| `/translate <lang> <text>` | Translate text |
| `/tr <lang> <text>` | Short command |
| `/tl <text>` | Language menu |
| `/langs` | List languages |

### Admin Commands
| Command | Description |
|---------|-------------|
| `/promote` | Promote user |
| `/demote` | Demote user |
| `/warn` | Warn user |
| `/mute` | Mute user |
| `/ban` | Ban user |
| `/unban` | Unban user |

---

## 🏗️ Architecture

### File Structure
```
├── bot.py                      # Main bot file
├── config.py                   # Configuration
├── database.py                 # MongoDB connection
├── ai_chat.py                  # ChatGPT integration
├── translator.py               # Translation service
├── user_manager_mongo.py       # User management
├── settings_manager_mongo.py   # Settings management
├── moderation_manager_mongo.py # Moderation data
├── filters_manager_mongo.py    # Custom filters
├── block_content_manager_mongo.py # Blocked content
├── admin.py                    # Admin tools
├── moderation.py               # Moderation
├── welcome.py                  # Welcome messages
├── filter.py                   # Auto-filters
├── settings.py                 # Settings menu
├── help.py                     # Help system
├── clean_service.py            # Service cleaner
├── auto_delete.py              # Auto-delete
├── bot_protection.py           # Bot protection
├── link_spam.py                # Link spam protection
├── forward_protection.py       # Forward protection
├── block_content.py            # Content blocking
├── anonymous_admin.py          # Anonymous admin support
├── font.py                     # Text formatting
├── user_manager.py             # Legacy user manager
├── settings_manager.py         # Legacy settings manager
├── moderation_manager.py       # Legacy moderation manager
├── filters_manager.py          # Legacy filters manager
├── block_content_manager.py    # Legacy block manager
├── migrate_to_mongodb.py       # Migration script
├── test_mongodb.py             # Test suite
├── requirements.txt            # Dependencies
├── .env                        # Environment variables
├── .env.example                # Environment template
└── .gitignore                  # Git ignore rules
```

### Database Collections
- `users` - User data and statistics
- `chat_settings` - Group configurations
- `warns` - User warnings
- `muters` - Users with mute permissions
- `voice_chat_managers` - Voice chat managers
- `banned_channels` - Banned channels
- `blocked_content` - Blocked text/media
- `filters` - Custom auto-response filters

---

## 🔧 Configuration

### Required Environment Variables
```env
# Telegram Bot
BOT_TOKEN=your_bot_token_here
LOG_CHANNEL_ID=your_log_channel_id
OWNER_ID=your_telegram_user_id

# MongoDB
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/?appName=GROUPHELP
```

### Optional Configuration
```env
# RapidAPI (if not using hardcoded keys)
RAPIDAPI_KEY=your_rapidapi_key
```

---

## 📚 Documentation

### Guides
- [🤖 AI & Translation Guide](AI_TRANSLATION_GUIDE.md) - Complete AI and translation features
- [🚀 Deployment Guide](DEPLOYMENT_GUIDE.md) - Server setup and deployment
- [💾 MongoDB Setup](MONGODB_SETUP.md) - Database configuration
- [⚡ Quick Start](QUICK_START.md) - Get started quickly
- [📊 Integration Summary](MONGODB_INTEGRATION_SUMMARY.md) - Technical details

### API Integration
- **ChatGPT**: RapidAPI (ChatGPT-42)
- **Translation**: RapidAPI (Deep Translate)
- **Database**: MongoDB Atlas

---

## 🛠️ Development

### Running Tests
```bash
# Test MongoDB connection
python test_mongodb.py

# Test bot manually
python bot.py
```

### Code Structure
- **Handler Groups**: Organized by priority (0-9)
- **Manager Pattern**: Separate files for data operations
- **MongoDB Integration**: Async-ready with proper error handling
- **API Integration**: HTTP client with retry logic

### Adding New Features
1. Create new module file
2. Implement handler functions
3. Add to bot.py handler registration
4. Update documentation

---

## 🚀 Deployment

### Quick Deploy
```bash
# 1. Clone repo
git clone https://github.com/nishkarshk212/titanic-saver.git

# 2. Setup
cd titanic-saver
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
nano .env

# 4. Run
python bot.py
```

### Production Deployment
See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for:
- Systemd service setup
- Auto-start configuration
- Log rotation
- Monitoring
- Security hardening

---

## 📊 Monitoring

### Check Bot Status
```bash
# Systemd
sudo systemctl status telegram-bot.service

# Logs
sudo journalctl -u telegram-bot.service -f

# Process
ps aux | grep bot.py
```

### Database Monitoring
- MongoDB Atlas Dashboard
- Collection sizes
- Query performance
- Index usage

### API Monitoring
- RapidAPI Dashboard
- Request counts
- Rate limits
- Error rates

---

## 🔒 Security

### Best Practices
- ✅ Never commit `.env` file
- ✅ Use strong bot tokens
- ✅ Restrict MongoDB IP access
- ✅ Monitor API usage
- ✅ Regular dependency updates
- ✅ Use HTTPS for webhooks
- ✅ Implement rate limiting

### API Keys Security
```bash
# Secure .env file
chmod 600 .env

# Add to .gitignore (already done)
echo ".env" >> .gitignore
```

---

## 🐛 Troubleshooting

### Common Issues

**Bot won't start:**
```bash
# Check logs
python bot.py 2>&1 | tee bot.log

# Verify .env
cat .env

# Test MongoDB
python test_mongodb.py
```

**MongoDB connection failed:**
1. Check MONGODB_URI
2. Whitelist IP in MongoDB Atlas
3. Test with `python test_mongodb.py`
4. Check SSL certificates

**API errors:**
1. Verify RapidAPI key
2. Check quota usage
3. Test API on RapidAPI dashboard
4. Review error logs

### Getting Help
1. Check documentation files
2. Review bot logs
3. Test individual components
4. Check API dashboards

---

## 📈 Performance

### Optimizations
- MongoDB indexes for fast queries
- Connection pooling
- Message handler groups
- Efficient data structures
- Caching where applicable

### Scaling
- MongoDB Atlas auto-scaling
- Multiple bot instances (with caution)
- Redis caching (future)
- Message queue (future)

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create feature branch
3. Make changes
4. Test thoroughly
5. Submit pull request

---

## 📄 License

This project is licensed under the MIT License.

---

## 🙏 Credits

- **Python Telegram Bot** - Bot framework
- **MongoDB Atlas** - Database hosting
- **RapidAPI** - API marketplace
- **ChatGPT-42** - AI service
- **Deep Translate** - Translation service

---

## 📞 Support

For issues and questions:
1. Check documentation
2. Review troubleshooting guide
3. Check bot logs
4. Verify API dashboards

---

## 🎯 Roadmap

### Completed ✅
- [x] MongoDB integration
- [x] AI Chat (ChatGPT)
- [x] Translation service
- [x] Migration tools
- [x] Documentation
- [x] Deployment guide

### Planned 🚧
- [ ] Web dashboard
- [ ] Analytics
- [ ] Multi-language support
- [ ] Image generation
- [ ] Voice translation
- [ ] Advanced AI features
- [ ] Custom plugins
- [ ] Webhook support

---

**Made with ❤️ for Telegram group admins**

[⭐ Star this repo](https://github.com/nishkarshk212/titanic-saver) if you find it useful!
# Doraemon-Help
