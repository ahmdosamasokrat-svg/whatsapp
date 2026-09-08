FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend and frontend source
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY data/flows_export.json /app/data/flows_export.json

# Setup environment
ENV PYTHONPATH=/app/backend
ENV DB_PATH=/app/data/bot.db

EXPOSE 2004

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "2004"]
