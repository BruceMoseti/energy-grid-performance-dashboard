"""Application settings and the balancing authorities GridPulse tracks."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Keys are EIA "respondent" codes, which is what the EIA API and our own
# ?region= query parameter expect. Values are the display names people know.
REGIONS: dict[str, str] = {
    "PJM": "PJM Interconnection",
    "MISO": "Midcontinent ISO",
    "ERCO": "ERCOT",
    "CISO": "California ISO",
    "NYIS": "New York ISO",
    "ISNE": "ISO New England",
}

# EIA region-data series types mapped onto our grid_load columns.
#   D  = demand, DF = day-ahead demand forecast,
#   NG = net generation, TI = total interchange.
EIA_TYPE_TO_COLUMN: dict[str, str] = {
    "D": "actual_demand_mw",
    "DF": "forecast_demand_mw",
    "NG": "net_generation_mw",
    "TI": "interchange_mw",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://gridpulse:gridpulse@localhost:5432/gridpulse"

    eia_api_key: str = ""
    eia_base_url: str = "https://api.eia.gov/v2/electricity/rto/region-data/data/"

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
