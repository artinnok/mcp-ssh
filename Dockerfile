FROM python:3.12-slim

ENV MCP_PORT=8000 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install "mcp[cli]" paramiko

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

COPY app.py /app/app.py
COPY agent /app/agent
COPY scripts /app/scripts
RUN chmod +x /app/scripts/*.sh

EXPOSE ${MCP_PORT}
ENTRYPOINT ["/app/entrypoint.sh"]
