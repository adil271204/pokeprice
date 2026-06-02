"""
Konfiguration: lädt Credentials aus .env ohne externe Abhängigkeit.
"""
import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimaler .env-Loader: KEY=VALUE, Kommentare (#) und Leerzeilen ignoriert."""
    if not path.exists():
        return
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:  # Env-Variable hat Vorrang
                os.environ[key] = value


# .env aus dem Arbeitsverzeichnis laden
_load_dotenv(Path.cwd() / ".env")


@dataclass(frozen=True)
class CardmarketConfig:
    app_token: str      # OAuth consumer key (Dedicated App)
    app_secret: str     # OAuth consumer secret
    access_token: str   # OAuth access token
    access_secret: str  # OAuth access token secret
    base_url: str       # API-Basis-URL

    @property
    def is_configured(self) -> bool:
        return all([self.app_token, self.app_secret,
                    self.access_token, self.access_secret])


@dataclass(frozen=True)
class EbayConfig:
    client_id: str
    client_secret: str
    marketplace_id: str  # z.B. "EBAY_DE"

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


@dataclass(frozen=True)
class AppConfig:
    cardmarket: CardmarketConfig
    ebay: EbayConfig
    db_path: str
    request_delay: float  # Sekunden zwischen API-Calls


def load_config() -> AppConfig:
    return AppConfig(
        cardmarket=CardmarketConfig(
            app_token=os.getenv("MKM_APP_TOKEN", ""),
            app_secret=os.getenv("MKM_APP_SECRET", ""),
            access_token=os.getenv("MKM_ACCESS_TOKEN", ""),
            access_secret=os.getenv("MKM_ACCESS_SECRET", ""),
            base_url=os.getenv("MKM_BASE_URL", "https://apiv2.cardmarket.com/ws/v2.0"),
        ),
        ebay=EbayConfig(
            client_id=os.getenv("EBAY_CLIENT_ID", ""),
            client_secret=os.getenv("EBAY_CLIENT_SECRET", ""),
            marketplace_id=os.getenv("EBAY_MARKETPLACE_ID", "EBAY_DE"),
        ),
        db_path=os.getenv("POKEPRICE_DB", "pokeprice.db"),
        request_delay=float(os.getenv("POKEPRICE_DELAY", "1.0")),
    )
