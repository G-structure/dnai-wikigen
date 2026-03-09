from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration — all values come from environment variables."""

    # Neko Chrome CDP endpoint
    cdp_url: str = "http://172.31.0.3:9222"

    # API server
    host: str = "0.0.0.0"
    port: int = 8000

    # Output directory for screenshots, scraped data, etc.
    data_dir: str = "/data"

    # dstack TEE mode (true when running on Phala Cloud)
    dstack_enabled: bool = False
    dstack_socket: str = "/var/run/dstack.sock"

    model_config = {"env_prefix": ""}  # no prefix — CDP_URL, APP_HOST, etc.


settings = Settings()
