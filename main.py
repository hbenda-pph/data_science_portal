import os
from collections import Counter

import pandas as pd
from flask import Flask, jsonify

from catalog.database import (
    WorksDatabase,
    build_environment_links,
    normalize_category,
    parse_list_field,
    sanitize_text,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

db = WorksDatabase()

app = Flask(__name__)


def format_timestamp(value) -> str:
    if value is None or value == "":
        return ""
    try:
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return sanitize_text(str(value))
        return ts.tz_localize(None).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return sanitize_text(str(value))


@app.route('/', methods=['GET'])
def serve_portal():
    """Entrega la página principal del portal de ciencia de datos."""
    with open(os.path.join(BASE_DIR, 'index.html'), 'r', encoding='utf-8') as f:
        return f.read()


@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint simple para monitoreo del servicio."""
    return jsonify({"status": "ok"})


@app.route('/api/catalog', methods=['GET'])
def load_catalog():
    try:
        works_df = db.fetch_all_works()
        categories_df = db.fetch_categories()

        category_names = {
            sanitize_text(row.get("category_id")): sanitize_text(row.get("category_name"))
            for _, row in categories_df.iterrows()
        } if not categories_df.empty else {}

        category_label_map = {}

        works = []
        for _, row in works_df.iterrows():
            row_dict = row.to_dict()
            category_info = normalize_category(row_dict, category_names)
            category_label_map[category_info["id"]] = category_info["name"]

            environments = build_environment_links(row_dict.get("config_json"))
            primary_url = sanitize_text(row_dict.get("work_url"))
            for env_key, env_value in environments.items():
                if not env_value["url"] and primary_url:
                    env_value["url"] = primary_url

            if not primary_url:
                for env_key in ["pro", "qua", "dev"]:
                    if environments.get(env_key, {}).get("url"):
                        primary_url = environments[env_key]["url"]
                        break

            works.append({
                "id": sanitize_text(row_dict.get("work_id")) or sanitize_text(row_dict.get("work_slug")) or "",
                "title": sanitize_text(row_dict.get("work_name")) or "Proyecto sin título",
                "summary": sanitize_text(row_dict.get("short_description")) or sanitize_text(row_dict.get("description")),
                "description": sanitize_text(row_dict.get("description")),
                "category_id": category_info["id"],
                "category_name": category_info["name"],
                "status": sanitize_text(row_dict.get("status")) or "active",
                "owner": sanitize_text(row_dict.get("owner")) or "Equipo de Data Science",
                "version": sanitize_text(row_dict.get("version")) or "",
                "last_update": format_timestamp(row_dict.get("updated_date")) or format_timestamp(row_dict.get("created_date")),
                "stack": parse_list_field(row_dict.get("stack")),
                "tags": parse_list_field(row_dict.get("tags")),
                "environments": environments,
                "primary_url": primary_url,
            })

        counter = Counter([work["category_id"] for work in works])

        categories = []
        if not categories_df.empty:
            for _, row in categories_df.iterrows():
                cat_id = sanitize_text(row.get("category_id"))
                categories.append({
                    "id": cat_id,
                    "name": sanitize_text(row.get("category_name")) or cat_id.title(),
                    "icon": sanitize_text(row.get("category_icon")),
                    "description": sanitize_text(row.get("description")),
                    "display_order": int(row.get("display_order", 0)) if pd.notna(row.get("display_order")) else 0,
                    "count": counter.get(cat_id, 0),
                })
        else:
            for cat_id, cat_name in category_names.items():
                categories.append({
                    "id": cat_id,
                    "name": cat_name or cat_id.title(),
                    "icon": "",
                    "description": "",
                    "display_order": 0,
                    "count": counter.get(cat_id, 0),
                })

        categories.sort(key=lambda item: (item.get("display_order", 0), item.get("name", "")))

        if not categories and counter:
            for cat_id in sorted(counter.keys()):
                categories.append({
                    "id": cat_id,
                    "name": category_label_map.get(cat_id, cat_id.title()),
                    "icon": "",
                    "description": "",
                    "display_order": 0,
                    "count": counter.get(cat_id, 0),
                })
            categories.sort(key=lambda item: item.get("name", ""))

        response = {
            "categories": categories,
            "works": works,
            "counts": {
                "total": len(works),
                "per_category": {key: counter[key] for key in counter}
            }
        }

        return jsonify(response)
    except Exception as error:
        print(f"ERROR /api/catalog: {error}")
        return jsonify({"error": "No se pudo cargar el catálogo", "details": str(error)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)
