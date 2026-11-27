FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY worker ./worker
# Runs as root ONLY to talk to the Docker socket (risk R-009). It never executes user code:
# every test runs in a separate, locked-down Test Sandbox container.
CMD ["python", "-m", "worker.main"]
