FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
RUN useradd --create-home --uid 10001 app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app
USER app
EXPOSE 8000
# migrate -> seed demo accounts -> serve (one container, one command)
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && uvicorn --factory app.main:create_app --host 0.0.0.0 --port 8000"]
