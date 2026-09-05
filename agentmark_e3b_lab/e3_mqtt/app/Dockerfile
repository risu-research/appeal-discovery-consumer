FROM python:3.13-slim
WORKDIR /app
COPY e3_mqtt/app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY e3_mqtt/app/device.py e3_mqtt/app/experiment.py e3_mqtt/app/ladder.py /app/
COPY agentmark /app/agentmark
ENV PYTHONUNBUFFERED=1
