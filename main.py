import os

import pandas as pd
from flask import Flask, jsonify


from catalog.database import (
    WorksDatabase,
    build_environment_links,
    normalize_category,
    parse_list_field,
    sanitize_text,
)


def format_timestamp(value: str) -> str:
    if not value:
        return ""
    try:
        if isinstance(value, str):
            ts = pd.to_datetime(value, errors="coerce")
        else:
            ts = pd.to_datetime(value)
        if pd.isna(ts):
            return sanitize_text(str(value))
        return ts.tz_localize(None).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return sanitize_text(str(value))


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db = WorksDatabase()


app = Flask(__name__, static_folder=BASE_DIR)


@app.route('/', methods=['GET'])
def serve_portal():
    """Entrega la página principal del portal de ciencia de datos."""
    return app.send_static_file('index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint simple para monitoreo del servicio."""
    return jsonify({"status": "ok"})


@app.route('/api/apps', methods=['GET'])
def list_apps():
    try:
        works_df = db.fetch_all_works()
        categories_df = db.fetch_categories()

        category_map = {
            sanitize_text(row.get("category_id")): sanitize_text(row.get("category_name"))
            for _, row in categories_df.iterrows()
        } if not categories_df.empty else {}

        apps = []
        for _, row in works_df.iterrows():
            category_info = normalize_category(row, category_map)
            envs = build_environment_links(row.get("config_json"))
            for key in envs:
                if envs[key]["url"] is None and sanitize_text(row.get("work_url")):
                    envs[key]["url"] = sanitize_text(row.get("work_url"))

            apps.append({
                "id": sanitize_text(row.get("work_id")) or sanitize_text(row.get("work_slug")) or "",
                "title": sanitize_text(row.get("work_name")) or "Proyecto sin título",
                "summary": sanitize_text(row.get("short_description")) or sanitize_text(row.get("description")),
                "description": sanitize_text(row.get("description")),
                "category": category_info["name"],
                "category_id": category_info["id"],
                "status": sanitize_text(row.get("status")) or "active",
                "owner": sanitize_text(row.get("owner")) or "Equipo de Data Science",
                "version": sanitize_text(row.get("version")) or "",
                "last_update": format_timestamp(row.get("updated_date")) or format_timestamp(row.get("created_date")),
                "stack": parse_list_field(row.get("stack")),
                "tags": parse_list_field(row.get("tags")),
                "environments": envs,
                "primary_url": sanitize_text(row.get("work_url")),
            })

        apps.sort(key=lambda item: (item.get("category", ""), item.get("title", "")))

        return jsonify({
            "apps": apps,
            "count": len(apps)
        })
    except Exception as error:
        print(f"ERROR /api/apps: {error}")
        return jsonify({"error": "No fue posible cargar el catálogo", "details": str(error)}), 500


@app.route('/api/categories', methods=['GET'])
def list_categories():
    try:
        categories_df = db.fetch_categories()
        if categories_df.empty:
            return jsonify({"categories": []})

        categories = []
        for _, row in categories_df.iterrows():
            categories.append({
                "id": sanitize_text(row.get("category_id")),
                "name": sanitize_text(row.get("category_name")),
                "icon": sanitize_text(row.get("category_icon")),
                "description": sanitize_text(row.get("description")),
                "display_order": int(row.get("display_order", 0)) if pd.notna(row.get("display_order")) else 0,
            })

        categories.sort(key=lambda c: (c.get("display_order", 0), c.get("name", "")))
        return jsonify({"categories": categories})
    except Exception as error:
        print(f"ERROR /api/categories: {error}")
        return jsonify({"error": "No fue posible cargar las categorías", "details": str(error)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)
