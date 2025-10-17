FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Copy files
COPY requirements.txt /app/requirements.txt
COPY main.py /app/main.py
COPY db.py /app/db.py
COPY setup_db.py /app/setup_db.py
COPY import_jsonl.py /app/import_jsonl.py
COPY .env /app/.env
COPY templates/index.html /app/templates/index.html

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 8000

# Run the app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]