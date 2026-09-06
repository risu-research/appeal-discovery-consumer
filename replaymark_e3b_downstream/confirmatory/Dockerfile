FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir paho-mqtt==2.1.0
COPY replaymark_e3b_downstream/pilot/device.py /app/device.py
COPY replaymark_e3b_downstream/pilot/pilot.py /app/pilot.py
COPY replaymark_e3b_downstream/pilot/pilot_entry.py /app/pilot_entry.py
COPY replaymark_e3b_downstream/confirmatory/confirmatory.py /app/confirmatory.py
ENV PYTHONUNBUFFERED=1
