FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 RUFF_CACHE_DIR=/tmp/ruff-cache
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --system hub
COPY . .
USER hub
CMD ["sh", "-ec", "python manage.py migrate --noinput && exec gunicorn hub.wsgi:application --bind 0.0.0.0:8000"]
