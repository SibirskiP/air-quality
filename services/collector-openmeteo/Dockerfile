FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY services/common /app/services/common
COPY services/collector-openmeteo /app/services/collector-openmeteo
COPY config /app/config
ENV PYTHONPATH=/app/services/common
CMD ["python", "services/collector-openmeteo/app/main.py"]