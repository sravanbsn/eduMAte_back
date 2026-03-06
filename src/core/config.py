from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SkillSwarm SocraticBridge API"
    VERSION: str = "1.0.0"

    # Security Configuration
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ADAPTA_CHROME_EXTENSION_API_KEY: str = "default-adapta-dev-key"
    WEBHOOK_SECRET_KEY: str = "secure-secret-for-internal-webhooks"

    # Blockchain (Web3) Configuration
    WEB3_RPC_URL: str = "https://sepolia.infura.io/v3/YOUR-INFURA-API-KEY"
    MASTER_WALLET_PRIVATE_KEY: str = (
        "0000000000000000000000000000000000000000000000000000000000000000"  # Replace in production!
    )
    MASTERY_TOKEN_CONTRACT_ADDRESS: str = "0xYourDeployedContractAddress"

    # PostgreSQL Configuration (Defaulting to localhost for dev)
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "skillswarm_db"

    # Neo4j Configuration
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
