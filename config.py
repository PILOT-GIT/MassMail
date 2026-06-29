import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent
if load_dotenv:
    load_dotenv(BASE_DIR / ".env")


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).expanduser()
DEFAULT_DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR / 'app.db'}"


class Settings:
    # Telegram Bot
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")

    # The single Telegram user ID that is permanently the Owner (set in .env).
    # Owner cannot be demoted or removed through the bot.
    OWNER_TELEGRAM_ID: int = int(os.getenv("OWNER_TELEGRAM_ID", "123456789"))

    # Database
    DATA_DIR: Path = DATA_DIR
    DATABASE_URL: str = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    SQL_ECHO: bool = _as_bool(os.getenv("SQL_ECHO", "false"))

    # Encryption key (Fernet 32-byte url-safe base64).
    # Keep stable once Gmail accounts are linked — changing it breaks decryption.
    ENCRYPTION_KEY: str = os.getenv(
        "ENCRYPTION_KEY", "uNqG8zS-uN1kR0S5Hjg9xH9oJkL4nM2oPqRstUvwxyA="
    )

    # SMTP
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587


settings = Settings()
