#Dockerfile para Cloud Run (Arquitectura Flask)

#Usamos la base de Python slim para reducir el tamaño de la imagen
FROM python:3.11-slim

#Establecer directorio de trabajo
WORKDIR /app

#Instalar dependencias del sistema (necesarias para SciPy y Pandas)

#Incluimos 'musl-dev' si hay problemas con SciPy/Numpy en Alpine o Slim.
RUN apt-get update && apt-get install -y 
gcc 
&& rm -rf /var/lib/apt/lists/*

#Copiar requirements.txt e instalar dependencias Python

#Instalamos Gunicorn, Flask y las librerías de Ciencia de Datos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#Copiar el código de la aplicación (main.py e index.html)
COPY . .

#Comando para ejecutar la aplicación usando Gunicorn (servidor de producción)

#Cloud Run espera que el servicio escuche en el puerto definido por la variable de entorno $PORT

#Usamos 'main:app' donde 'main' es el nombre del archivo python y 'app' es la variable Flask.

#El puerto 8080 es el valor por defecto de $PORT en Cloud Run.

CMD exec gunicorn --bind :${PORT:-8080} --workers 1 --threads 8 --timeout 0 main:app