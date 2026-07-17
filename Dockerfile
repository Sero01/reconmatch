FROM python:3.12-slim

# useradd before COPY so the layer cache survives source changes
RUN useradd --create-home appuser

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

USER appuser

ENV GRADIO_SERVER_NAME=0.0.0.0
# Render provides PORT; default to gradio's 7860 for local runs
CMD ["sh", "-c", "GRADIO_SERVER_PORT=${PORT:-7860} python app.py"]
