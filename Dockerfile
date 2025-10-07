FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

RUN useradd -r -s /bin/false botuser && \
    mkdir -p /app/data && \
    chown -R botuser:botuser /app
USER botuser

VOLUME ["/app/data"]

CMD ["python", "bot.py"]