import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv('BOT_API')
    ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
    WEBAPP_URL = os.getenv('WEBAPP_URL', 'https://tgreward.shop/tiktok.php')
    PORT = int(os.getenv('PORT', '5000'))
    
    @classmethod
    def validate(cls):
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_API environment variable is required")
        if not cls.ADMIN_ID:
            raise ValueError("ADMIN_ID environment variable is required")
