FROM python:3.12-slim
WORKDIR /app
COPY services/common /services/common
RUN pip install --no-cache-dir /services/common
COPY services/guardrail /app
RUN pip install --no-cache-dir .
EXPOSE 3007
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3007"]
