# Mass Mailer Bot

A Telegram bot for managing Gmail-based bulk mail operations. It lets authorized users:

- connect Gmail accounts using Gmail App Passwords
- create target email lists from manual input or CSV uploads
- launch bulk sending operations with configurable delays
- track operation progress and results
- manage access roles for other users

## Features

- Telegram-based UI with inline buttons and menus
- Role-based authorization (owner, admin, user, unauthorized)
- Gmail SMTP validation before saving accounts
- CSV import for Gmail accounts and target emails
- Background operation execution with progress updates
- SQLite by default, with optional PostgreSQL support via SQLAlchemy

## Project structure

- [main.py](main.py) – application entry point
- [config.py](config.py) – environment and settings loading
- [database.py](database.py) – async SQLAlchemy engine and session factory
- [models.py](models.py) – database models
- [gmail_service.py](gmail_service.py) – SMTP email delivery helpers
- [scheduler.py](scheduler.py) – background execution of mail operations
- [bot/](bot/) – aiogram handlers, middleware, keyboards, and state definitions

## Requirements

- Python 3.10+
- A Telegram Bot token from BotFather
- Gmail accounts with 2-Step Verification enabled
- Gmail App Passwords for each sender account

## Environment variables

Create a file named .env in the project root with the following variables:

```env
BOT_TOKEN=your_telegram_bot_token
OWNER_TELEGRAM_ID=your_telegram_user_id
ENCRYPTION_KEY=your_32_byte_fernet_key
DATABASE_URL=sqlite+aiosqlite:///app.db
SQL_ECHO=false
DATA_DIR=.
```

### Notes

- OWNER_TELEGRAM_ID must be your Telegram user ID. This account becomes the owner automatically.
- ENCRYPTION_KEY should be a valid Fernet key. Example:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- If you do not set DATABASE_URL, the bot uses a local SQLite database at app.db.

## Local setup

1. Clone the repository:

```bash
git clone <your-repo-url>
cd MassMailer_new
```

2. Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create your .env file as described above.

5. Start the bot:

```bash
python main.py
```

The bot will:
- create the database tables automatically
- start the Telegram polling loop
- begin listening for commands and inline menu actions

## Bot usage workflow

1. Start the bot in Telegram.
2. The owner account is auto-authorized on first contact.
3. Use the menu to:
   - add Gmail sender accounts
   - create target email lists
   - launch an operation
4. For each Gmail account, use a 16-character Gmail App Password rather than your normal password.
5. During an operation, the bot sends one email per target for each selected sender, with randomized delays between sends.

## Gmail account setup

To use Gmail accounts with this bot:

1. Enable 2-Step Verification on the Google account.
2. Create an App Password from Google Account Security.
3. In the bot, add the Gmail address and the App Password.
4. The bot validates the SMTP credentials before saving the account.

> Using app passwords is strongly recommended. Do not share your regular Gmail password with the bot.

## Deployment options

### Option 1: VPS / Linux server

A common production setup is:

- Ubuntu or Debian server
- Python 3.10+
- systemd service
- nginx optional, only if you want a web-facing reverse proxy

Example systemd service:

```ini
[Unit]
Description=Mass Mailer Bot
After=network.target

[Service]
User=your-user
WorkingDirectory=/path/to/MassMailer_new
Environment=PATH=/path/to/MassMailer_new/venv/bin
ExecStart=/path/to/MassMailer_new/venv/bin/python /path/to/MassMailer_new/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Save it as /etc/systemd/system/massmailer.service and enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable massmailer
sudo systemctl start massmailer
sudo systemctl status massmailer
```

### Option 2: Docker (optional)

A Docker deployment can be added later if you want containerized hosting. The current code is standard Python and can be containerized with a simple Dockerfile.

## Database notes

- By default, the bot uses SQLite and stores data in app.db.
- To use PostgreSQL, set DATABASE_URL to a PostgreSQL connection string such as:

```env
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

The database schema is created automatically when the bot starts.

## Security recommendations

- Keep your .env file private and never commit it.
- Use strong random values for ENCRYPTION_KEY.
- Restrict Telegram bot access to trusted users.
- Avoid storing plain Gmail passwords in your repository or logs.
- Use a dedicated service account or deployment user on servers.

## Troubleshooting

### Bot does not start

- Confirm BOT_TOKEN is valid.
- Check that the Python dependencies installed successfully.
- Review the console logs for import or configuration issues.

### Gmail accounts fail to verify

- Make sure 2-Step Verification is enabled.
- Use a valid 16-character App Password.
- Confirm the Gmail account can access SMTP on port 587.

### Operation sends fail

- Check SMTP authentication errors in the logs.
- Ensure the selected Gmail account still has a valid app password.
- Review the operation status in the bot and the database if needed.

## License

This project is provided as-is for educational and operational use. Add your own license if you intend to distribute it.
