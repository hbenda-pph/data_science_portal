📊 API de Análisis de Puntos de Inflexión (Python/Flask/BigQuery)

Este repositorio contiene el código fuente para una API de backend desarrollada en Flask, diseñada para analizar patrones de estacionalidad y detectar puntos de inflexión (picos y valles) en el volumen de llamadas históricas de diferentes compañías, extrayendo datos de Google BigQuery.

La API sirve como backend para una aplicación de frontend (el archivo index.html) que consume los datos procesados para visualización.

⚙️ Estructura del Proyecto

main.py: El script principal de Flask que define los endpoints de la API, maneja la lógica de caché, se conecta a BigQuery y realiza los cálculos analíticos (pandas, numpy, scipy).

index.html: El frontend (HTML/Tailwind/Plotly.js) para interactuar con la API.

requirements.txt: Lista todas las dependencias de Python necesarias.

.gitignore: Archivo de configuración para ignorar carpetas y archivos temporales/sensibles.

🚀 Configuración y Ejecución

Sigue estos pasos para configurar y ejecutar el proyecto en Google Cloud Shell o en un entorno Linux similar:

1. Clonar el Repositorio

git clone [https://www.youtube.com/watch?v=44ziZ12rJwU](https://www.youtube.com/watch?v=44ziZ12rJwU)
cd [nombre-del-repositorio]


2. Crear y Activar un Entorno Virtual

Es fundamental aislar las dependencias del proyecto.

python3 -m venv venv
source venv/bin/activate


3. Instalar Dependencias

Instala todas las librerías necesarias listadas en requirements.txt.

pip install -r requirements.txt


4. Autenticación de Google Cloud y BigQuery (Cloud Shell Simplificado)

NOTA IMPORTANTE: Si estás ejecutando en Google Cloud Shell, ya estás automáticamente autenticado con las credenciales de tu usuario. No se requiere ningún comando adicional como gcloud auth application-default login para que BigQuery funcione.

5. Ejecutar el Servidor Flask

Puedes ejecutar el servidor Flask en modo de desarrollo:

export FLASK_APP=main.py
export FLASK_ENV=development
flask run --host=0.0.0.0 --port=8080


El servidor estará disponible en http://localhost:8080. Recuerda que en Cloud Shell puedes usar la función "Web Preview" (Vista previa web) para acceder a este puerto.

📌 Endpoints de la API

Método

Endpoint

Descripción

GET

/api/companies

Retorna la lista de todas las compañías disponibles (company_id, company_name).

POST

/api/inflection-analysis

Retorna el análisis completo (datos de la curva de estacionalidad, puntos de inflexión y tabla anual) para un company_id dado.