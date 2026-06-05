# Usamos la imagen oficial de Python 3.12 en su versión slim (más ligera y optimizada)
FROM python:3.12-slim

# Establecemos el directorio de trabajo dentro del contenedor
WORKDIR /app

# Variables de entorno para optimizar Python en Docker
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/app/.cache/huggingface

# Instalamos dependencias del sistema operativo que podrían necesitar algunas librerías
# como PyPDF2, pdfplumber o las dependencias de machine learning.
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiamos el archivo de requerimientos primero para aprovechar la caché de Docker
COPY requirements.txt .

# Instalamos las dependencias de Python (incluyendo el modelo de Spacy)
RUN pip install --no-cache-dir -r requirements.txt

# Pre-descargamos el modelo SBERT para que quede "horneado" en la imagen de Docker
# Esto evita descargar 2.2 GB en cada inicio del contenedor, previniendo fallos en Cloud Run
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"

# Copiamos todo el código fuente del backend al contenedor
COPY backend/ ./backend/

# Exponemos el puerto (informativo)
EXPOSE 8080

# Comando para ejecutar la aplicación con Uvicorn usando el puerto dinámico de Cloud Run
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}
