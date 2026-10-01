FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python run.py backfill --days 35
EXPOSE 8000
CMD ["uvicorn", "airpulse.api:app", "--host", "0.0.0.0", "--port", "8000"]
