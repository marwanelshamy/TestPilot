# Test Sandbox image (untrusted code boundary, ASR-1 / ADR-003).
# Containers from this image are created per run by the Runner Worker with:
#   network_mode=none, read_only rootfs, user sandbox, cap_drop=ALL, no-new-privileges,
#   CPU / memory / pids limits, tmpfs /tmp. Only /work (an anonymous volume) is writable.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt \
 && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin sandbox \
 && mkdir -p /work/tests && chown -R sandbox:sandbox /work
# /work must be a volume: Docker allows copying files into a volume of a read-only container.
VOLUME ["/work"]
WORKDIR /work
USER sandbox
CMD ["python", "-m", "pytest", "--version"]
