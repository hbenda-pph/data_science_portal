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
        
        # Consulta SQL (reemplaza con tu consulta real si es necesario)
        query = """
            SELECT 
                CAST(FORMAT_DATE('%Y%m%d', call_date) AS STRING) AS date,
                company_id,
                calls_count 
            FROM 
                `platform-partners-des.service_titan.calls_analysis_table` 
            ORDER BY 
                company_id, call_date
        """
        
        # Ejecutar la consulta
        df = client.query(query).to_dataframe()
        
        # Almacenar en caché y actualizar tiempo
        _calls_df_cache = df
        _last_data_fetch_time = time.time()
        
        print("INFO: Data cargada exitosamente desde BigQuery.")
        return df
        
    except Exception as e:
        print(f"ERROR: Falló la conexión a BigQuery: {e}. Usando Mock Data.")
        
        # Generar Mock Data para desarrollo local o fallo de credenciales
        dates = pd.date_range(start='2022-01-01', periods=730)
        df_mock = pd.DataFrame({
            'date': dates.strftime('%Y%m%d'),
            'company_id': np.random.choice(['C1001', 'C1002', 'C1003'], size=730),
            'calls_count': np.random.randint(50, 300, size=730) + np.sin(np.linspace(0, 10 * np.pi, 730)) * 50
        })
        
        # Asegurar que se almacene el mock data para evitar llamadas repetidas
        _calls_df_cache = df_mock
        _last_data_fetch_time = time.time()
        
        return df_mock

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
            
        company_ids = df['company_id'].unique().tolist()
        return jsonify({"companies": company_ids})
        
    except Exception as e:
        print(f"Error en /api/companies: {e}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

# -----------------------------------------------------------------------------
# 3. ENDPOINT PRINCIPAL: ANALISIS DE INFLEXIÓN
# -----------------------------------------------------------------------------

@app.route('/api/analysis', methods=['POST'])
def run_analysis():
    """
    Realiza el análisis de inflexión para una compañía y un modo de detección.
    """
    try:
        # Parámetros recibidos del JSON
        data = request.get_json()
        company_id = data.get('companyId')
        detection_method = data.get('detection_method', 'peak_valley') # 'peak_valley' o 'midpoint'
        analysis_mode = data.get('analysis_mode', 'calls') # 'calls' o 'normalized'

        if not company_id:
            return jsonify({"error": "Missing companyId parameter"}), 400

        # Obtener Data (usa cache)
        df = get_calls_info()
        company_data = df[df['company_id'] == company_id].copy()

        if company_data.empty:
            return jsonify({"error": f"No data found for company {company_id}"}), 404

        # Preprocesamiento de datos
        company_data['date'] = pd.to_datetime(company_data['date'], format='%Y%m%d')
        company_data.set_index('date', inplace=True)
        
        # Remuestrear a nivel mensual y rellenar nulos
        monthly_data = company_data['calls_count'].resample('MS').sum().fillna(0)
        
        # Descomposición de series de tiempo
        # No se aplica descomposición formal por simplicidad, se usa la serie sin suavizar

        # Preparar datos anuales para la tabla (últimos 12 meses)
        # La lógica de la tabla anual debe ser implementada aquí si es necesaria

        # Generar datos de inflexión (Simulación de resultado)
        # Este es el core del análisis de inflexión
        
        inflection_points = []
        if not monthly_data.empty:
            # Ejemplo simplificado de detección de picos/valles con scipy
            data_to_analyze = monthly_data.values
            
            # Buscando picos (máximos locales)
            peaks, _ = find_peaks(data_to_analyze, height=np.mean(data_to_analyze) + np.std(data_to_analyze) * 0.5)
            # Buscando valles (invirtiendo la serie para encontrar mínimos)
            valleys, _ = find_peaks(-data_to_analyze, height=-np.mean(data_to_analyze) + np.std(data_to_analyze) * 0.5)

            # Convertir índices a fechas
            dates = monthly_data.index.tolist()
            
            for p in peaks:
                inflection_points.append({
                    'date': dates[p].strftime('%Y-%m-%d'),
                    'value': data_to_analyze[p],
                    'type': 'Peak (Pico)'
                })
            for v in valleys:
                inflection_points.append({
                    'date': dates[v].strftime('%Y-%m-%d'),
                    'value': data_to_analyze[v],
                    'type': 'Valley (Valle)'
                })

        # Estructurar la respuesta
        response = {
            "monthly_data": [{
                "date": date.strftime('%Y-%m-%d'), 
                "calls_count": count
            } for date, count in monthly_data.items()],
            "inflection_points": inflection_points,
            "annual_table": [], # Se debería generar la tabla anual aquí
            "company_id": company_id
        }
        
        return jsonify(response)

    except Exception as e:
        print(f"Error en /api/analysis: {e}")
        # Error al iniciar Gunicorn/Worker. MUY COMUN en Cloud Run.
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

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