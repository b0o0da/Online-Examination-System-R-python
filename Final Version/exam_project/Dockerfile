FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create logs directory
RUN mkdir -p logs

# Expose port
EXPOSE 8000

# Init DB and start server
CMD ["sh", "-c", "python init_db.py && python create_admin.py && uvicorn main:app --host 0.0.0.0 --port 8000"]
