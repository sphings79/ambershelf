FROM python:3.12-slim

# No build tools, no compilers - nothing here needs them.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY engine ./engine
COPY platforms ./platforms
COPY server ./server

# The container runs unprivileged. It cannot mount anything - that is the
# host helper's job, and the whole point of the split.
RUN useradd --uid 1000 --user-group --no-create-home ambersync \
 && mkdir -p /data /mnt/ambersync \
 && chown ambersync:ambersync /data

USER 1000:1000
EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
