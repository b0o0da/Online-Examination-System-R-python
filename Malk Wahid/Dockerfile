FROM python:3.10-slim

WORKDIR /app

COPY docker-requirements.txt .
RUN pip install --no-cache-dir -r docker-requirements.txt

COPY Mahmoud/online_exam_system/app /app

CMD python init_db.py && uvicorn main:app --host 0.0.0.0 --port 8000
