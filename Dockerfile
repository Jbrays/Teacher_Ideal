# Usamos la imagen oficial de Python 3.12 en su versión slim (más ligera y optimizada)
FROM python:3.12-slim

# Establecemos el directorio de trabajo dentro del contenedor
WORKDIR /app

# Variables de entorno para optimizar Python en Docker
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/app/.cache/huggingface
ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache/sbert

# Instalamos dependencias del sistema operativo que podrían necesitar algunas librerías
# como PyPDF2, pdfplumber o las dependencias de machine learning.
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiamos el archivo de requerimientos primero para aprovechar la caché de Docker
COPY requirements.txt .

# PyTorch CPU evita incorporar varios GB de librerías CUDA que Cloud Run no usa.
RUN pip install --no-cache-dir torch \
      --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# El catálogo debe existir antes de generar sus vectores.
COPY backend/ ./backend/

# Hornea el modelo y los embeddings del catálogo. La primera petición no debe
# asumir el costo de descargar el modelo ni vectorizar miles de conceptos.
RUN python -c "from backend.services.taxonomy_embedder import TaxonomyEmbedder; TaxonomyEmbedder().build_embeddings()" && \
    chmod -R 777 /app/.cache

# ¡CRÍTICO! Apagar el internet a nivel de sistema para toda la librería HuggingFace
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

# Exponemos el puerto (informativo)
EXPOSE 8080

# Comando para ejecutar la aplicación con Uvicorn usando el puerto dinámico de Cloud Run
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}
