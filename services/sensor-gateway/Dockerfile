FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY services/common /app/services/common
COPY services/sensor-gateway /app/services/sensor-gateway
COPY config /app/config
ENV PYTHONPATH=/app/services/common
CMD ["python", "services/sensor-gateway/app/main.py"]