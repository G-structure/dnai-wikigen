"""Configuration for tinker-delegate automation."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "TINKER_"}

    # CDP browser
    cdp_url: str = "http://localhost:9222"

    # Email oracle
    oracle_url: str = "http://localhost:8000"

    # Tinker auth
    tinker_console_url: str = "https://tinker-console.thinkingmachines.ai"

    # Account details (auto-fetched from oracle if not set)
    email: str = ""
    first_name: str = "Tinker"
    last_name: str = "Delegate"

    # Timing
    otp_poll_interval: float = 3.0  # seconds between OTP polls
    otp_poll_timeout: float = 120.0  # max seconds to wait for OTP
    otp_max_age: int = 300  # max age of OTP email in seconds
