FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 RUFF_CACHE_DIR=/tmp/ruff-cache
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --system hub && install -d -m 0700 -o hub /tmp/hub-mail /var/lib/knowledge-hub/documents
COPY . .
USER hub
CMD ["sh", "-ec", "python manage.py migrate --noinput && python manage.py createcachetable && exec gunicorn hub.wsgi:application --bind 0.0.0.0:8000"]
