FROM mcr.microsoft.com/playwright/python:v1.49.0-noble
WORKDIR /app
COPY services/common /services/common
RUN pip install --no-cache-dir /services/common
COPY services/browser /app
RUN pip install --no-cache-dir .
EXPOSE 3014
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3014"]
