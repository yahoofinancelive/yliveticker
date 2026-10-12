FROM python:3.12-slim

WORKDIR /app
COPY setup.py README.md LICENSE ./
COPY yliveticker ./yliveticker
RUN pip install --no-cache-dir ".[influxdb]" && useradd --uid 10001 --create-home collector
COPY examples/tsdb_example.py ./examples/tsdb_example.py

USER collector
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "examples/tsdb_example.py"]
