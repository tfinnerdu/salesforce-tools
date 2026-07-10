FROM python:3.11-slim

WORKDIR /app

# Install system deps for pyodbc
RUN apt-get update && apt-get install -y --no-install-recommends \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

ENV SCHEDULER_ENABLED=true
# Mock layer is for manual UI/demo testing only — never on in container builds.
ENV SHOW_MOCK=false

# Use -u for unbuffered stdout so hub-logs capture output immediately
CMD ["python", "-u", "app.py"]
