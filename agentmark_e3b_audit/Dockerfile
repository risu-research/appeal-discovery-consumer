FROM python:3.12-slim
RUN pip install --no-cache-dir paho-mqtt==2.1.0
WORKDIR /app
COPY agentmark_e3b_lab /app/core
COPY agentmark_e3b_audit /app/audit
ENV PYTHONPATH=/app/core:/app/core/e3_mqtt/app:/app/audit
