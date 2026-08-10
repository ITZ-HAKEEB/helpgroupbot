# Manager Module - Group Management Commands

## Overview
This module has been ported from **AnnieXMusic** (Pyrogram-based) to work with **titanic-saver** (python-telegram-bot-based). All commands have been adapted to use the python-telegram-bot framework while maintaining the original functionality.

## Files Included

### 1. **actions.py** - Single User Moderation
Commands for individual user moderation:
- `/ban` - Ban a user from the group
- `/unban` - Unban a user
- `/mute` - Mute a user (remove all permissions)
- `/unmute` - Unmute a user
- `/tmute` - Temporary mute (e.g., `/tmute @user 1h`)
- `/kick` - Kick a user (ban for 2 seconds)
- `/dban` - Delete message & ban (reply only)
- `/sban` - Silent ban (no notification)
- `/kickme` - User self-kick
- `/tban` - Temporary ban (e.g., `/tban @user 1d`)

**Features:**
- Admin permission checks
- Reply, @username, or user-ID support
- Duplicate state checks (already banned/muted)
- Safe error handling

### 2. **grouphandler.py** - Group Management
Commands for managing group settings:
- `/pin` - Pin a message
- `/unpin` - Unpin a message
- `/setphoto` - Set group photo
- `/removephoto` - Remove group photo
- `/settitle` - Set group title
- `/setdescription` - Set group description

**Features:**
- Admin permission validation
- Support for replies and arguments
- View message button for pins

### 3. **id.py** - ID Information
- `/id` - Show message ID, user ID, chat ID
- Supports replies to show replied user/message ID
- Supports username lookup

### 4. **info.py** - User Information
- `/info` or `/whois` - Get detailed user information
- Shows: ID, name, username, verified status, premium status, bot status
- Profile view button

### 5. **mass_actions.py** - Mass Moderation
Owner/Admin-only mass commands with confirmation:
- `/kickall` - Kick all non-admin members
- `/banall` - Ban all non-admin members
- `/unbanall` - Unban all banned members
- `/muteall` - Mute all non-admin members
- `/unmuteall` - Unmute all members
- `/unpinall` - Unpin all messages

**Features:**
- Yes/No confirmation via inline buttons
- Progress tracking
- Error counting

### 6. **promote.py** - Admin Management
Commands for promoting/demoting admins:
- `/promote` - Promote with limited rights
- `/fullpromote` - Promote with full rights
- `/demote` - Remove admin rights
- `/tempadmin` - Temporary promotion (e.g., `/tempadmin @user 2h`)

**Features:**
- Custom title support
- Auto-demote for temp admins
- Permission presets

### 7. **purge.py** - Message Deletion
Bulk message deletion commands:
- `/purge` - Delete messages from replied to current
- `/spurge` - Silent purge (deletes command too)
- `/del` - Delete single replied message

**Features:**
- Batch deletion (100 messages at a time)
- FloodWait handling
- Confirmation message

### 8. **staff.py** - Staff Listing
- `/admins` or `/staff` - List all group admins
- `/bots` - List all bots in the group

**Features:**
- Separates owners, human admins, and bot admins
- HTML mentions
- Anonymous admin filtering

### 9. **sg.py** - Username History Checker
- `/sg` - Check username history using Sangmata bot

**Features:**
- Reply to user or provide username/ID
- Uses SangmataInfo_bot or Sangmata_beta_bot
- Shows previous usernames

**Note:** This is a simplified version since python-telegram-bot doesn't support userbots natively.

### 10. **zombie.py** - Deleted Account Cleaner
- `/zombies` - Scan and remove deleted accounts
- Supports channel ID for remote scanning

**Features:**
- Inline keyboard for actions
- Batch processing with progress updates
- Cancel support during cleanup
- FloodWait handling

## Installation

All handlers are automatically loaded when the bot starts. The Manager module has been integrated into `bot.py`:

```python
from Manager import get_manager_handlers

# In main():
for handler in get_manager_handlers():
    application.add_handler(handler)
```

## Usage

### Admin Commands
Most commands require admin privileges in the group. The bot checks for appropriate permissions before executing commands.

### Command Syntax
All commands support multiple input methods:
1. **Reply**: Reply to a user's message with the command
2. **Username**: `/ban @username [reason]`
3. **User ID**: `/ban 123456789 [reason]`

### Time Format
For temporary actions (tmute, tban, tempadmin), use:
- `s` - seconds (e.g., `30s`)
- `m` - minutes (e.g., `15m`)
- `h` - hours (e.g., `2h`)
- `d` - days (e.g., `7d`)

## Permissions Required

For the bot to use these commands effectively, it needs:
- **Ban users** - For ban/kick commands
- **Restrict members** - For mute commands
- **Delete messages** - For purge/dban commands
- **Pin messages** - For pin/unpin commands
- **Change info** - For set photo/title/description
- **Promote members** - For promote/demote commands

## Differences from Original

The following files were **NOT** ported:
- `assisuser.py` - Requires userbot (not compatible with python-telegram-bot)
- `del_msg.py` - Requires assistant userbot for delete_history
- `language.py` - Requires MongoDB and translation system
- `welcome.py` - You already have a welcome.py in the main directory

## Notes

1. **Framework Adaptation**: All Pyrogram-specific code has been converted to python-telegram-bot equivalents
2. **Error Handling**: Comprehensive try-catch blocks for API errors
3. **Permission Checks**: Admin permission validation before command execution
4. **FloodWait**: Automatic handling of Telegram rate limits
5. **Batch Processing**: Large operations processed in batches to avoid rate limits

## Testing

Before using in production:
1. Test commands in a test group
2. Verify bot has required admin permissions
3. Check that confirmation dialogs work properly
4. Test temporary actions (tmute, tban, tempadmin)

## Support

If you encounter issues:
1. Check bot permissions in the group
2. Review error logs
3. Ensure python-telegram-bot is up to date
4. Test with simpler commands first

---

**Ported by**: AI Assistant  
**Original Source**: AnnieXMusic/AnnieXMedia/plugins/Manager  
**Target**: titanic-saver bot (python-telegram-bot)
