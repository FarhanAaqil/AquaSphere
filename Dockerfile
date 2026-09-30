FROM python:3.12-slim

# Prevent Python from writing pyc files and buffer output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Pre-install CPU-only PyTorch to keep image lightweight (~180MB vs ~2.5GB CUDA)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies (torch is already satisfied by CPU wheel)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code, trained model, scaler, and dashboard HTML
COPY . .

# Expose default port (Render will route via $PORT)
EXPOSE 8000

# Launch uvicorn bound to 0.0.0.0 and Render's $PORT
CMD ["sh", "-c", "uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
