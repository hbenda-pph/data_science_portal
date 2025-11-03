# -*- coding: utf-8 -*-
# =============================================================================
# FLASK SERVER & BIGQUERY API - ANALISIS DE PUNTOS DE INFLEXIÓN
# Este script levanta un servidor Flask que actúa como backend en Cloud Run.
# Procesa datos de BigQuery y devuelve JSON para el frontend HTML/JS.
# =============================================================================

from flask import Flask, jsonify, request
import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from google.cloud import bigquery
import google.auth
import warnings
import time
import os # Importar os para la ruta de la aplicación

# Ocultar advertencias de Pandas/Numpy
warnings.filterwarnings('ignore')

# Inicialización de Flask
# CRUCIAL: Indicamos a Flask que busque archivos estáticos (como index.html) 
# en el directorio actual (os.path.dirname(os.path.abspath(__file__))), 
# que es /app dentro del contenedor.
# ESTA CORRECCIÓN SOLUCIONA EL ERROR 503 EN CLOUD RUN
app = Flask(__name__, static_folder=os.path.dirname(os.path.abspath(__file__)))


# --- Caching global para la data de BigQuery ---
# En un entorno real, usarías un sistema de caché externo (Redis) o Cloud Storage
_calls_df_cache = None
_last_data_fetch_time = 0
CACHE_EXPIRY_SECONDS = 3600  # 1 hora de caché

# =============================================================================
# 1. FUNCIONES DE BIGQUERY Y MOCK DATA
# =============================================================================

def get_calls_info():
    """
    Extrae información consolidada de llamadas desde BigQuery.
    Usa caching simple para evitar llamadas repetidas a la DB.
    
    NOTA: Se usa MOCK DATA si la caché está vacía, para permitir la ejecución local 
    sin credenciales activas de BQ, o si no se está en un entorno Cloud Run/Compute Engine.
    """
    global _calls_df_cache, _last_data_fetch_time
    
    # Check if data is cached and not expired
    if _calls_df_cache is not None and (time.time() - _last_data_fetch_time) < CACHE_EXPIRY_SECONDS:
        return _calls_df_cache
    
    try:
        # Intenta usar las credenciales de Cloud Run/Compute Engine
        client = bigquery.Client()

        # Registrar información básica de credenciales para debugging
        try:
            default_credentials, default_project = google.auth.default()
            service_account_email = getattr(default_credentials, 'service_account_email', 'unknown')
            print(f"INFO: BigQuery client initialized. client.project={client.project}, default_project={default_project}, service_account={service_account_email}")
        except Exception as cred_info_error:
            print(f"WARN: No se pudo obtener información de credenciales: {cred_info_error}")
        
        # Consulta SQL tomada del dashboard original (Streamlit)
        query = """
           SELECT c.company_id AS company_id
                , c.company_name AS company_name
                , COUNT(DISTINCT cl.campaign_id) AS campaigns
                , COUNT(cl.lead_call_customer_id) AS customers
                , cl.location_state AS state
                , EXTRACT(YEAR FROM DATE(cl.lead_call_created_on)) AS year
                , EXTRACT(MONTH FROM DATE(cl.lead_call_created_on)) AS month
                , COUNT(cl.lead_call_id) AS calls
             FROM `pph-central.analytical.vw_consolidated_call_inbound_location` cl
             JOIN `pph-central.settings.companies` c
               ON cl.company_id = c.company_id
            WHERE DATE(cl.lead_call_created_on) < DATE('2025-10-01')
              AND EXTRACT(YEAR FROM DATE(cl.lead_call_created_on)) >= 2015
            GROUP BY c.company_id,
                     c.company_name,
                     cl.location_state,
                     EXTRACT(YEAR FROM DATE(cl.lead_call_created_on)),
                     EXTRACT(MONTH FROM DATE(cl.lead_call_created_on))
            ORDER BY c.company_id,
                     cl.location_state,
                     EXTRACT(YEAR FROM DATE(cl.lead_call_created_on)),
                     EXTRACT(MONTH FROM DATE(cl.lead_call_created_on))
        """
        
        # Ejecutar la consulta
        df = client.query(query).to_dataframe()
        
        # Almacenar en caché y actualizar tiempo
        _calls_df_cache = df
        _last_data_fetch_time = time.time()
        
        print("INFO: Data cargada exitosamente desde BigQuery.")
        return df
        
    except Exception as e:
        print(f"ERROR: Falló la conexión a BigQuery: {e}")
        raise


def normalize_detection_method(method):
    if not method:
        return "Hybrid (3-4 months)"
    method = method.strip()
    if method in ("Hybrid (3-4 months)", "Mathematical Strict", "Original (find_peaks)"):
        return method
    mapping = {
        "hybrid": "Hybrid (3-4 months)",
        "hybrid (3-4 months)": "Hybrid (3-4 months)",
        "mathematical strict": "Mathematical Strict",
        "strict": "Mathematical Strict",
        "original": "Original (find_peaks)",
        "original (find_peaks)": "Original (find_peaks)",
        "find_peaks": "Original (find_peaks)"
    }
    return mapping.get(method.lower(), "Hybrid (3-4 months)")


def normalize_analysis_mode(mode):
    if not mode:
        return "percentages"
    key = mode.strip().lower()
    if key in ("percentages", "percentage", "percent", "porcentajes"):
        return "percentages"
    if key in ("absolute", "absoluto", "absolute numbers"):
        return "absolute"
    return "percentages"


def prepare_company_dataframe(calls_df, company_id):
    company_id_str = str(company_id)
    company_df = calls_df[calls_df['company_id'].astype(str) == company_id_str].copy()
    if company_df.empty:
        raise KeyError(f"No data found for company {company_id_str}")
    required_columns = {'year', 'month', 'calls'}
    if not required_columns.issubset(company_df.columns):
        raise ValueError("Dataset incompleto para el análisis de inflexión.")
    company_df['year'] = company_df['year'].astype(int)
    company_df['month'] = company_df['month'].astype(int)
    company_df['calls'] = company_df['calls'].astype(float)
    return company_df, company_id_str


def calculate_monthly_metrics(company_df):
    monthly_totals = company_df.groupby('month')['calls'].sum()
    months = list(range(1, 13))
    monthly_calls = np.array([float(monthly_totals.get(month, 0.0)) for month in months], dtype=float)
    total_calls = float(monthly_calls.sum())
    if total_calls > 0:
        monthly_percentages = (monthly_calls / total_calls) * 100.0
    else:
        monthly_percentages = np.zeros(12, dtype=float)
    return months, monthly_calls, monthly_percentages, total_calls


def detect_peaks_valleys_quartiles(calls):
    calls_array = np.array(calls, dtype=float)
    if calls_array.size == 0:
        return np.array([], dtype=int), np.array([], dtype=int)
    sorted_indices = np.argsort(calls_array)
    valleys = np.sort(sorted_indices[:2])
    peaks = np.sort(sorted_indices[-2:])
    return peaks.astype(int), valleys.astype(int)


def detect_inflection_points(monthly_percentages, method):
    method_normalized = normalize_detection_method(method)
    percentages = np.array(monthly_percentages, dtype=float)
    if percentages.size == 0:
        return np.array([], dtype=int), np.array([], dtype=int)
    average = np.mean(percentages)
    if method_normalized == "Original (find_peaks)":
        peaks, _ = find_peaks(percentages, height=average, distance=2)
        valleys, _ = find_peaks(-percentages, height=-average, distance=2)
    elif method_normalized == "Mathematical Strict":
        peaks, valleys = detect_peaks_valleys_quartiles(percentages)
    else:
        peaks, _ = find_peaks(percentages, height=average, distance=3)
        valleys, _ = find_peaks(-percentages, height=-average, distance=3)
    return np.array(peaks, dtype=int), np.array(valleys, dtype=int)


def calculate_annual_data(company_df, mode):
    if company_df.empty:
        return None
    yearly_monthly = (
        company_df.groupby(['year', 'month'])['calls']
        .sum()
        .reset_index()
    )
    if yearly_monthly.empty:
        return None
    years = sorted(yearly_monthly['year'].unique())
    months = list(range(1, 13))
    annual_table = pd.DataFrame(0.0, index=years, columns=months)
    for year in years:
        year_data = yearly_monthly[yearly_monthly['year'] == year]
        year_total = year_data['calls'].sum()
        for month in months:
            month_calls = year_data.loc[year_data['month'] == month, 'calls']
            value = float(month_calls.iloc[0]) if not month_calls.empty else 0.0
            if mode == 'percentages':
                value = (value / year_total * 100.0) if year_total > 0 else 0.0
            annual_table.at[year, month] = value
    return annual_table


def format_annual_table(annual_df, mode):
    if annual_df is None or annual_df.empty:
        return {}
    table = {}
    for year in annual_df.index:
        row = {}
        for month in annual_df.columns:
            value = float(annual_df.loc[year, month])
            if mode == 'percentages':
                value = round(value, 2)
            else:
                value = int(round(value))
            row[str(int(month))] = value
        table[str(int(year))] = row
    return table


def build_curve_data(months, monthly_calls, monthly_percentages):
    curve = []
    for idx, month in enumerate(months):
        curve.append({
            "month": int(month),
            "percentage": round(float(monthly_percentages[idx]), 4),
            "calls": float(monthly_calls[idx])
        })
    return curve


def build_analysis_payload(calls_df, company_id, detection_method, analysis_mode):
    detection_method = normalize_detection_method(detection_method)
    analysis_mode = normalize_analysis_mode(analysis_mode)
    company_df, company_id_str = prepare_company_dataframe(calls_df, company_id)
    company_name = (
        company_df['company_name'].dropna().iloc[0]
        if 'company_name' in company_df.columns and not company_df['company_name'].dropna().empty
        else company_id_str
    )
    months, monthly_calls, monthly_percentages, total_calls = calculate_monthly_metrics(company_df)
    peaks, valleys = detect_inflection_points(monthly_percentages, detection_method)
    peak_months = sorted({int(months[idx]) for idx in peaks})
    valley_months = sorted({int(months[idx]) for idx in valleys})
    curve_data = build_curve_data(months, monthly_calls, monthly_percentages)
    annual_df = calculate_annual_data(company_df, analysis_mode)
    annual_table = format_annual_table(annual_df, analysis_mode)

    summary = {}
    if 'campaigns' in company_df.columns:
        summary['campaigns'] = int(company_df['campaigns'].max())
    if 'customers' in company_df.columns:
        summary['customers'] = int(company_df['customers'].sum())
    if 'state' in company_df.columns:
        states = sorted({str(state) for state in company_df['state'].dropna().unique()})
        if states:
            summary['states'] = states

    response = {
        "company_id": company_id_str,
        "company_name": company_name,
        "detection_method": detection_method,
        "analysis_mode": analysis_mode,
        "total_calls": int(round(total_calls)),
        "curve_data": curve_data,
        "peak_months": peak_months,
        "valley_months": valley_months,
        "annual_table": annual_table,
        "monthly_call_breakdown": {
            "months": [int(m) for m in months],
            "calls": [int(round(val)) for val in monthly_calls],
            "percentages": [round(float(val), 4) for val in monthly_percentages]
        },
        "year_range": [
            int(company_df['year'].min()),
            int(company_df['year'].max())
        ]
    }

    if summary:
        response['summary'] = summary

    return response

# -----------------------------------------------------------------------------
# 2. ENDPOINT PARA LISTAR COMPAÑIAS (PARA EL SELECTOR DE FRONTEND)
# -----------------------------------------------------------------------------

@app.route('/api/companies', methods=['GET'])
def get_companies():
    """Devuelve la lista de IDs de compañía disponibles."""
    try:
        df = get_calls_info()
        # Si el DataFrame está vacío o es Mock, devolvemos un error
        if df.empty:
            return jsonify({"error": "No data available"}), 500
            
        if 'company_name' in df.columns:
            companies_df = (
                df[['company_id', 'company_name']]
                .drop_duplicates()
                .sort_values(by='company_name')
            )
        else:
            company_ids = sorted(df['company_id'].unique().tolist())
            companies_df = pd.DataFrame({
                'company_id': company_ids,
                'company_name': company_ids
            })

        companies = companies_df.to_dict(orient='records')
        return jsonify({"companies": companies})
        
    except Exception as e:
        print(f"Error en /api/companies: {e}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

# -----------------------------------------------------------------------------
# 3. ENDPOINT PRINCIPAL: ANALISIS DE INFLEXIÓN
# -----------------------------------------------------------------------------

def _handle_inflection_analysis_request():
    try:
        payload = request.get_json() or {}
        company_id = payload.get('company_id')
        if company_id in (None, '', []):
            company_id = payload.get('companyId')
        if company_id in (None, '', []):
            return jsonify({"error": "Missing company_id parameter"}), 400

        detection_method = normalize_detection_method(payload.get('detection_method'))
        analysis_mode = normalize_analysis_mode(payload.get('analysis_mode'))

        df = get_calls_info()
        result = build_analysis_payload(df, company_id, detection_method, analysis_mode)
        return jsonify(result)

    except KeyError as missing_error:
        return jsonify({
            "error": "No data found for the requested company",
            "details": str(missing_error)
        }), 404
    except ValueError as validation_error:
        return jsonify({
            "error": str(validation_error)
        }), 400
    except Exception as e:
        print(f"Error en análisis de inflexión: {e}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@app.route('/api/analysis', methods=['POST'])
def run_analysis():
    """Compatibilidad con versiones anteriores."""
    return _handle_inflection_analysis_request()


@app.route('/api/inflection-analysis', methods=['POST'])
def run_inflection_analysis():
    """Endpoint principal usado por el portal actual."""
    return _handle_inflection_analysis_request()

# 4. SERVIR ARCHIVOS ESTATICOS

@app.route('/', methods=['GET'])
def serve_index():
    """Sirve el archivo HTML principal."""
    # Como la carpeta estática se configuró en la inicialización (static_folder=os.path.dirname...)
    # Flask puede encontrar 'index.html' directamente en el directorio /app.
    try:
        # Esto sirve el archivo HTML que actúa como frontend
        return app.send_static_file('index.html')
    except Exception as e:
        # En caso de que se ejecute localmente sin configurar la carpeta static
        return f"""
        <html>
            <head><title>Cloud Run Portal</title></head>
            <body style="font-family: sans-serif; padding: 20px;">
                <h1>Backend Flask Funcionando</h1>
                <p>El servidor Flask está activo, pero el archivo <code>index.html</code> no se encontró en la ruta de archivos estáticos configurada.</p>
                <p>Asegúrate de que tu frontend (index.html) esté en la ubicación correcta para ser servido.</p>
                <p>Error: {e}</p>
            </body>
        </html>
        """

if __name__ == '__main__':
    # Usar el puerto de Cloud Run (o 8080 si se ejecuta localmente)
    import os
    port = int(os.environ.get('PORT', 8080))
    # Para desarrollo local:
    # app.run(debug=True, host='0.0.0.0', port=port)
    print(f"Flask en modo local, puerto: {port}")
    
