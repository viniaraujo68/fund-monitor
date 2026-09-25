from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PARQUET_DIR = DATA_DIR / "parquet"
SITE_DIR = DATA_DIR / "site"

MANAGER_CNPJ = "68622174000120"
WINDOW_START = date(2024, 9, 1)

CVM_REGISTRY_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
CVM_DAILY_URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{yyyymm}.zip"

REGISTRY_RAW_DIR = RAW_DIR / "cvm" / "registry"
DAILY_RAW_DIR = RAW_DIR / "cvm" / "daily"
REGISTRY_PARQUET = PARQUET_DIR / "registry.parquet"
DAILY_PARQUET_DIR = PARQUET_DIR / "daily"

BCB_SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados"
ANBIMA_IMA_URL = "https://www.anbima.com.br/informacoes/ima/ima-sh-down.asp"
B3_INDEX_URL = "https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/{payload}"

ANBIMA_INDICES = ("IMA-B", "IMA-B 5", "IMA-B 5+", "IRF-M", "IMA-S", "IMA-GERAL")
ANBIMA_REQUEST_PAUSE_SECONDS = 1.0
ANBIMA_RETRY_EMPTY_DAYS = 7
B3_INDEX = "IBOV"

BCB_RAW_DIR = RAW_DIR / "bcb"
ANBIMA_RAW_DIR = RAW_DIR / "anbima" / "ima"
B3_RAW_DIR = RAW_DIR / "b3"
INDICES_PARQUET = PARQUET_DIR / "indices.parquet"
IMA_PARQUET = PARQUET_DIR / "ima.parquet"
IBOVESPA_PARQUET = PARQUET_DIR / "ibovespa.parquet"
METRICS_DIR = PARQUET_DIR / "metrics"
