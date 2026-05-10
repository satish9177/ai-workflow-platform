from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    redis_url: str
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int = 7 * 24 * 60
    encryption_key: str
    openai_api_key: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from_email: str
    app_base_url: str


settings = Settings()
