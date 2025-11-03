"""
Acceso a BigQuery para el portal de ciencia de datos (Flask).

Replica la lógica de `data_science_index/shared/database.py` sin dependencias de Streamlit.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account


class WorksDatabase:
    """Cliente ligero para consultar `settings.works_index` y `works_categories`."""

    def __init__(self, project_id: Optional[str] = None, dataset_id: str = "settings") -> None:
        self.project_id = project_id or os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.dataset_id = dataset_id

        if self.project_id:
            self.client = bigquery.Client(project=self.project_id)
        else:
            self.client = bigquery.Client()
            self.project_id = self.client.project

        self.table_index = f"{self.project_id}.{self.dataset_id}.works_index"
        self.table_categories = f"{self.project_id}.{self.dataset_id}.works_categories"

    # ------------------------------------------------------------------
    # Lecturas de catálogo
    # ------------------------------------------------------------------

    def fetch_all_works(self) -> pd.DataFrame:
        query = f"
        SELECT *
        FROM `{self.table_index}`
        WHERE status = 'active'
        ORDER BY category, created_date DESC
        "
        return self.client.query(query).to_dataframe()

    def fetch_categories(self) -> pd.DataFrame:
        query = f"
        SELECT category_id, category_name, category_icon, description, display_order
        FROM `{self.table_categories}`
        WHERE is_active = true
        ORDER BY display_order, category_name
        "
        return self.client.query(query).to_dataframe()


def sanitize_text(value: Optional[str]) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalize_category(row: dict, fallback_map: Dict[str, str]) -> Dict[str, str]:
    category_id = sanitize_text(row.get("category")) or "otros"
    return {
        "id": category_id,
        "name": sanitize_text(row.get("category_name")) or fallback_map.get(category_id, category_id.title()),
        "icon": sanitize_text(row.get("category_icon")),
        "description": sanitize_text(row.get("description")),
    }


def parse_list_field(value) -> List[str]:
    if isinstance(value, list):
        return [sanitize_text(item) for item in value if sanitize_text(item)]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            import json

            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [sanitize_text(item) for item in parsed if sanitize_text(item)]
        except Exception:
            pass
        return [sanitize_text(part) for part in text.split(',') if sanitize_text(part)]
    return []


def build_environment_links(config_json: Optional[str]) -> Dict[str, Dict[str, Optional[str]]]:
    envs = {
        "dev": {"label": "DEV", "url": None},
        "qua": {"label": "QUA", "url": None},
        "pro": {"label": "PRO", "url": None},
    }

    if not config_json:
        return envs

    try:
        import json

        config = json.loads(config_json)
        for key in envs.keys():
            url = config.get("environments", {}).get(key) if isinstance(config, dict) else None
            if isinstance(url, str) and url.strip():
                envs[key]["url"] = url.strip()
    except Exception:
        pass

    return envs

