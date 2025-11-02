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
import warnings
import time

# Ocultar advertencias de Pandas/Numpy
warnings.filterwarnings('ignore')

# Inicialización de Flask
app = Flask(__name__)

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
    sin credenciales activas de BQ, o si no se está en un entorno GCloud.
    """
    global _calls_df_cache
    global _last_data_fetch_time

    # Comprobación de caché
    current_time = time.time()
    if _calls_df_cache is not None and (current_time - _last_data_fetch_time) < CACHE_EXPIRY_SECONDS:
        print("INFO: Data retrieved from in-memory cache.")
        return _calls_df_cache

    try:
        # Intento de conexión a BigQuery (asumiendo credenciales de GCloud)
        client = bigquery.Client()
        
        # Define tu consulta SQL real aquí
        QUERY = """
            SELECT 
                company_id, 
                company_name, 
                EXTRACT(YEAR FROM call_date) AS year,
                EXTRACT(MONTH FROM call_date) AS month,
                COUNT(call_id) AS calls
            FROM 
                `your_gcp_project.your_dataset.your_calls_table`
            GROUP BY 1, 2, 3, 4
            ORDER BY 1, 3, 4
        """
        
        calls_df = client.query(QUERY).to_dataframe()
        print("INFO: Data retrieved successfully from BigQuery.")
        
    except Exception as e:
        print(f"WARNING: BigQuery failed ({e}). Loading mock data for demo.")
        
        # === MOCK DATA FOR DEMO PURPOSES ===
        num_companies = 5
        years = np.arange(2020, 2025)
        months = np.arange(1, 13)
        data = []
        for i in range(1, num_companies + 1):
            company_id = i * 100
            company_name = f"Company {i} Analysis Group"
            for year in years:
                for month in months:
                    # Simulación de datos con estacionalidad
                    base_calls = np.random.randint(500, 2000)
                    seasonal_factor = 1 + np.sin(2 * np.pi * (month - 3) / 12) * 0.4 
                    calls = int(base_calls * seasonal_factor * (1 + i * 0.1) * (1 + np.random.rand() * 0.1))
                    
                    data.append({
                        'company_id': company_id,
                        'company_name': company_name,
                        'year': year,
                        'month': month,
                        'calls': calls
                    })
        calls_df = pd.DataFrame(data)
        # ===================================
        
    # Actualizar caché
    _calls_df_cache = calls_df
    _last_data_fetch_time = current_time
    
    return _calls_df_cache

# =============================================================================
# 2. FUNCIONES DE ANÁLISIS (Reutilizadas de Streamlit)
# =============================================================================

def calculate_monthly_percentages(calls_df, company_id):
    """Calcula el porcentaje de llamadas por mes para una compañía específica."""
    company_data = calls_df[calls_df['company_id'] == company_id].copy()
    
    if company_data.empty:
        return None, None, None
    
    monthly_totals = company_data.groupby('month')['calls'].sum()
    monthly_calls = np.zeros(12)
    for month, calls in monthly_totals.items():
        monthly_calls[month - 1] = calls
    
    total_calls = np.sum(monthly_calls)
    monthly_percentages = (monthly_calls / total_calls) * 100 if total_calls > 0 else np.zeros(12)
    
    return monthly_calls, monthly_percentages, total_calls

def detect_peaks_valleys_quartiles(calls):
    """Detecta picos y valles usando el método estricto de cuartiles."""
    sorted_indices = np.argsort(calls)
    # Los dos valores más bajos son valles, los dos más altos son picos
    valleys = sorted_indices[:2]
    peaks = sorted_indices[-2:]
    return peaks, valleys

def analyze_inflection_points(calls_df, company_id, detection_method):
    """Ejecuta el análisis de puntos de inflexión y prepara los resultados."""
    
    monthly_calls, monthly_percentages, total_calls = calculate_monthly_percentages(calls_df, company_id)
    
    if monthly_percentages is None:
        return None, None, None, None
    
    months_indices = np.arange(0, 12)
    calls = monthly_percentages
    peaks = []
    valleys = []

    # Implementación de las lógicas de detección
    if detection_method == "Original (find_peaks)":
        peaks, _ = find_peaks(calls, height=np.mean(calls), distance=2)
        valleys, _ = find_peaks(-calls, height=-np.mean(calls), distance=2)

    elif detection_method == "Mathematical Strict":
        peaks, valleys = detect_peaks_valleys_quartiles(calls)

    elif detection_method == "Hybrid (3-4 months)":
        # Combina una distancia mínima para evitar ruido
        peaks, _ = find_peaks(calls, height=np.mean(calls), distance=3)
        valleys, _ = find_peaks(-calls, height=-np.mean(calls), distance=3)
        
    # Prepara el formato de salida para el frontend (de base 0 a base 1)
    peak_months = (months_indices[peaks] + 1).tolist()
    valley_months = (months_indices[valleys] + 1).tolist()
    
    # Datos de la curva
    curve_data = [{'month': int(m + 1), 'percentage': round(p, 2)} 
                  for m, p in zip(months_indices, calls)]
    
    return curve_data, peak_months, valley_months, total_calls

def calculate_annual_data(calls_df, company_id, mode="percentages"):
    """Calcula datos mensuales por año para la tabla resumen."""
    company_data = calls_df[calls_df['company_id'] == company_id].copy()
    
    if company_data.empty:
        return None
    
    yearly_monthly = company_data.groupby(['year', 'month'])['calls'].sum().reset_index()
    years = sorted(yearly_monthly['year'].unique())
    months = range(1, 13)
    annual_table = {}
    
    for year in years:
        year_data = yearly_monthly[yearly_monthly['year'] == year]
        year_total = year_data['calls'].sum()
        year_row = {}
        
        for month in months:
            month_data = year_data[year_data['month'] == month]
            month_calls = month_data['calls'].iloc[0] if not month_data.empty else 0
            
            if mode == "percentages" and year_total > 0:
                value = round((month_calls / year_total) * 100, 2)
            else:  # absolute o total_calls es 0
                value = int(month_calls)
                
            year_row[str(month)] = value
        
        annual_table[str(year)] = year_row
    
    return annual_table

# =============================================================================
# 3. ENDPOINTS DE LA API
# =============================================================================

@app.route('/api/companies', methods=['GET'])
def get_companies():
    """Endpoint para obtener la lista de compañías disponibles."""
    df_calls = get_calls_info()
    if df_calls.empty:
        return jsonify({"companies": []}), 200
        
    companies = df_calls[['company_id', 'company_name']].drop_duplicates()
    
    # Convierte a lista de diccionarios para JSON
    company_list = companies.to_dict('records')
    
    return jsonify({"companies": company_list})


@app.route('/api/inflection-analysis', methods=['POST'])
def run_analysis():
    """Endpoint principal para ejecutar el análisis y devolver resultados."""
    try:
        data = request.get_json()
        company_id = data.get('company_id', None)
        detection_method = data.get('detection_method', 'Hybrid (3-4 months)')
        analysis_mode = data.get('analysis_mode', 'percentages')
        
        if company_id is None:
            return jsonify({"error": "company_id is required"}), 400

        # 1. Obtener la data base (usa caché si es posible)
        df_calls = get_calls_info()

        # 2. Ejecutar el análisis de estacionalidad y puntos de inflexión
        curve_data, peaks, valleys, total_calls = analyze_inflection_points(
            df_calls, company_id, detection_method
        )
        
        # 3. Calcular la tabla de datos anuales
        annual_table = calculate_annual_data(df_calls, company_id, analysis_mode)

        if curve_data is None:
            return jsonify({"error": f"No data found for company {company_id}"}), 404

        # 4. Compilar la respuesta final
        response = {
            "company_id": company_id,
            "total_calls": int(total_calls),
            "curve_data": curve_data,      # Datos (mes, porcentaje) para Plotly
            "peak_months": peaks,          # Meses (1-12) donde están los picos
            "valley_months": valleys,      # Meses (1-12) donde están los valles
            "annual_table": annual_table   # Datos para la tabla HTML
        }

        return jsonify(response)

    except Exception as e:
        print(f"ERROR en la API: {e}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

# 4. SERVIR ARCHIVOS ESTATICOS

@app.route('/', methods=['GET'])
def serve_index():
    """Sirve el archivo HTML principal."""
    # En Cloud Run, este archivo debe estar disponible en la misma ruta 
    # donde se ejecuta el servidor.
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
                <p>El servidor Flask está activo, pero el archivo <code>index.html</code> no se encontró en el directorio <code>static</code>.</p>
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
    # app.run(host='0.0.0.0', port=port, debug=True) 
    
    # Para Cloud Run, se recomienda usar Gunicorn, pero para este test, Flask es suficiente:
    app.run(host='0.0.0.0', port=port)
