FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Pre-download the model during build (optional: comment out to download at runtime)
RUN python -c "from transformers import BlipProcessor, BlipForConditionalGeneration; \
    BlipProcessor.from_pretrained('Salesforce/blip-image-captioning-base'); \
    BlipForConditionalGeneration.from_pretrained('Salesforce/blip-image-captioning-base')"

EXPOSE 8501 8001

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
