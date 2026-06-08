# Connects to a remote Archonum browser over CDP.
# No local browser download needed — we only connect out.
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cdp_example.py .

CMD ["python", "cdp_example.py"]
