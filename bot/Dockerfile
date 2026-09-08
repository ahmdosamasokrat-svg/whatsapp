FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir flask requests gunicorn

COPY bot.py /app/bot.py

CMD ["gunicorn", "--bind", "0.0.0.0:2002", "--workers", "2", "--timeout", "120", "bot:app"]
