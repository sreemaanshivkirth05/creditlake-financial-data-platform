FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN python -m pip install --no-cache-dir . && mkdir -p /app/data && chown 50000:0 /app/data
ENV CREDITLAKE_ROOT=/app CREDITLAKE_DATA_DIR=/app/data
USER 50000:0
EXPOSE 8000
CMD ["creditlake", "serve", "--host", "0.0.0.0"]
