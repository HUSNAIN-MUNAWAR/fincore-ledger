FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system fincore && adduser --system --ingroup fincore fincore
COPY apps/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/api .
USER fincore
CMD ["celery", "-A", "fincore.worker.celery_app.celery_app", "worker", "--loglevel=INFO", "--concurrency=2"]
