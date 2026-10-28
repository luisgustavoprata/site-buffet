FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/buffet.db

WORKDIR /app
RUN useradd --create-home appuser && mkdir /data && chown appuser /data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s \
    CMD python -c "import os, urllib.request as u; u.urlopen('http://localhost:%s/health' % os.environ.get('PORT', '8000'))"

# A porta vem da variável PORT (o Render define a sua). --proxy-headers: o IP real do
# cliente chega pelo proxy do Render, o que importa para o limite de tentativas de login.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
