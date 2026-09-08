FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir flask gunicorn

COPY app.py /app/app.py

CMD ["gunicorn", "--bind", "0.0.0.0:2003", "--workers", "2", "--timeout", "120", "app:app"]
