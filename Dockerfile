FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir requests

COPY divar_bot.py .

RUN mkdir -p /data

CMD ["python", "-u", "divar_bot.py"]
