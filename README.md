# Hockey RSVP Bot

A Discord bot that automatically tracks RSVPs for hockey games by parsing an iCal feed and creating polls in your Discord server.

## Features

- 📅 Fetches games from your team's iCal feed
- 🤖 Automatically creates polls 7 days before each game
- ✅ Players can RSVP with Yes/No/Maybe reactions
- 💾 Stores RSVP data in a local SQLite database
- 📊 Updates poll counts in real-time

## Setup Instructions

### 1. Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name (e.g., "Hockey RSVP Bot")
3. Go to the "Bot" section in the left sidebar
4. Click "Add Bot"
5. Under "Privileged Gateway Intents", enable:
   - Message Content Intent
   - Server Members Intent (optional, for better username handling)
6. Click "Reset Token" and copy your bot token (you'll need this later)

### 2. Invite Bot to Your Server

1. In the Discord Developer Portal, go to "OAuth2" → "URL Generator"
2. Select the following scopes:
   - `bot`
3. Select the following bot permissions:
   - Read Messages/View Channels
   - Send Messages
   - Embed Links
   - Add Reactions
   - Read Message History
   - Use External Emojis
4. Copy the generated URL and open it in your browser
5. Select your Discord server and authorize the bot

### 3. Get Your Discord Channel ID

1. In Discord, enable Developer Mode:
   - User Settings → Advanced → Developer Mode (toggle on)
2. Right-click on the channel where you want polls posted
3. Click "Copy Channel ID"

### 4. Install and Configure

1. Clone or download this repository to your Fedora server

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```

4. Edit `.env` with your configuration:
   ```
   DISCORD_BOT_TOKEN=your_bot_token_here
   CHANNEL_ID=your_channel_id_here
   ICAL_URL=your_ical_feed_url
   TIMEZONE=America/Toronto
   ```

### 5. Run the Bot

```bash
python bot.py
```

The bot will:
- Connect to Discord
- Check daily at midnight for games 7 days away
- Automatically create polls for upcoming games
- Track RSVPs as users react to polls

## Usage

### Automatic Polls

The bot automatically checks once per day for games happening in exactly 7 days and creates polls.

### Manual Commands

- `!testpoll` - Create a test poll for the next upcoming game (admin only)
- `!checkgames` - Manually trigger the daily game check (admin only)

### RSVP Instructions for Players

1. When a poll appears, react with:
   - ✅ for Yes (attending)
   - ❌ for No (not attending)
   - ❓ for Maybe (uncertain)

2. Your response will be tracked automatically
3. You can change your response by clicking a different reaction
4. The poll will update in real-time with current counts

## Running as a Service (Fedora)

To keep the bot running in the background:

1. Create a systemd service file:
   ```bash
   sudo nano /etc/systemd/system/hockey-rsvp-bot.service
   ```

2. Add the following content (adjust paths as needed):
   ```ini
   [Unit]
   Description=Hockey RSVP Discord Bot
   After=network.target

   [Service]
   Type=simple
   User=your_username
   WorkingDirectory=/path/to/hockey-rsvp-bot
   ExecStart=/usr/bin/python3 /path/to/hockey-rsvp-bot/bot.py
   Restart=on-failure
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable hockey-rsvp-bot
   sudo systemctl start hockey-rsvp-bot
   ```

4. Check status:
   ```bash
   sudo systemctl status hockey-rsvp-bot
   ```

## File Structure

```
hockey-rsvp-bot/
├── bot.py              # Main Discord bot
├── ical_parser.py      # iCal feed parser
├── database.py         # SQLite database handler
├── requirements.txt    # Python dependencies
├── .env               # Configuration (create from .env.example)
├── .env.example       # Configuration template
├── hockey_rsvp.db     # SQLite database (created automatically)
└── README.md          # This file
```

## Future Enhancements

- Google Calendar integration to update event descriptions with RSVP data
- Web dashboard to view RSVP history
- Notifications/reminders for players who haven't responded
- Export RSVP data to CSV
- Multi-team support

## Troubleshooting

**Bot doesn't respond:**
- Check that the bot is online in Discord (green status)
- Verify the bot has proper permissions in your channel
- Check logs: `sudo journalctl -u hockey-rsvp-bot -f`

**Polls not created automatically:**
- The bot checks once daily at midnight (server time)
- Verify your timezone is set correctly in `.env`
- Manually trigger with `!checkgames` to test

**iCal feed issues:**
- Verify the ICAL_URL is correct
- Check that the URL is accessible from your server
- Test parsing with `!testpoll`

## License

MIT License - Feel free to modify and distribute as needed.
