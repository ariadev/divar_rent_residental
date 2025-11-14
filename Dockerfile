FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir requests python-dotenv "python-telegram-bot[job-queue]"

COPY divar_bot.py .

RUN mkdir -p /data

CMD ["python", "-u", "divar_bot.py"]
