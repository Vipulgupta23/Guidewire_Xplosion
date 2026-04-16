import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "https://xxxx.supabase.co")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    # Upstash Redis
    UPSTASH_REDIS_REST_URL: str = os.getenv("UPSTASH_REDIS_REST_URL", "")
    UPSTASH_REDIS_REST_TOKEN: str = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

    # External APIs
    OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY", "")
    AQICN_API_KEY: str = os.getenv("AQICN_API_KEY", "")
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # App config
    JWT_SECRET: str = os.getenv("JWT_SECRET", "incometrix_super_secret_2026")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    DEMO_OTP_EMAIL: str = os.getenv("DEMO_OTP_EMAIL", "")
    UPI_SIM_PROVIDER: str = os.getenv("UPI_SIM_PROVIDER", "Incometrix UPI Sandbox")

    # Trigger engine
    TRIGGER_POLL_INTERVAL_MINUTES: int = int(
        os.getenv("TRIGGER_POLL_INTERVAL_MINUTES", "15")
    )


settings = Settings()
