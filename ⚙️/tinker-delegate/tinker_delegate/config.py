"""Configuration for tinker-delegate automation."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "TINKER_"}

    # Remote Playwright browser server
    browser_ws_endpoint: str = ""
    browser_timeout: float = 180.0
    browser_poll_interval: float = 2.0
    browser_connect_timeout: float = 20.0

    # CDP browser
    cdp_url: str = "http://localhost:9222"
    cdp_timeout: float = 180.0
    cdp_poll_interval: float = 2.0
    cdp_connect_timeout: float = 20.0
    local_browser_fallback: bool = True
    local_browser_headless: bool = True
    local_browser_launch_timeout: float = 60.0

    # Email oracle
    oracle_url: str = "http://localhost:8000"
    oracle_auth_token: str = ""
    oracle_auth_key_path: str = "oracle/runtime-auth"

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

    # API key bootstrap / storage
    api_key_store_path: str = "./data/tinker_api_key.enc"
    api_key_store_key: str = ""
    dstack_key_path: str = "tinker/api_key"
    funding_receipt_store_path: str = "./data/funding_receipts.enc"
    funding_receipt_store_key: str = ""
    funding_receipt_key_path: str = "tinker/funding_receipts"
    bootstrap_signup: bool = False
    bootstrap_fail_open: bool = False
    bootstrap_oracle_timeout: float = 300.0
    bootstrap_oracle_poll_interval: float = 5.0
    allow_auth_automation_endpoint: bool = False
    debug_screenshots: bool = False
    debug_artifact_dir: str = ""
    purge_secret_debug_artifacts: bool = True
    allow_plaintext_card_endpoint: bool = False
    allow_plaintext_artifact_endpoint: bool = False
