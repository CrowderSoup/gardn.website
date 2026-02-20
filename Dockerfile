FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock /app/
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

COPY . /app

ENTRYPOINT ["./docker/entrypoint.sh"]
CMD ["sh", "-c", "uv run gunicorn gardn.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]
