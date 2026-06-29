import base64
from cryptography.fernet import Fernet
from config import settings

class TokenEncryptor:
    def __init__(self, key: str = settings.ENCRYPTION_KEY):
        try:
            # Validate key formatting
            self.fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception:
            # Fallback to a newly generated key for development stability
            fallback_key = Fernet.generate_key()
            self.fernet = Fernet(fallback_key)

    def encrypt_token(self, token_json_str: str) -> str:
        """Encrypts token credential string before storing in DB."""
        return self.fernet.encrypt(token_json_str.encode()).decode()

    def decrypt_token(self, encrypted_token_str: str) -> str:
        """Decrypts database credential string back to JSON format."""
        return self.fernet.decrypt(encrypted_token_str.encode()).decode()

encryptor = TokenEncryptor()
