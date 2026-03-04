FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY services/common /app/services/common
COPY services/processor /app/services/processor
COPY config /app/config
ENV PYTHONPATH=/app/services/common
CMD ["python", "services/processor/app/main.py"]