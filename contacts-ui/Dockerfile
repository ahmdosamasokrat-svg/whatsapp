FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir flask requests gunicorn

COPY app.py /app/app.py

CMD ["gunicorn", "--bind", "0.0.0.0:2001", "--workers", "2", "--timeout", "120", "app:app"]
