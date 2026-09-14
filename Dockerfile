FROM python:3.12-alpine

WORKDIR /app
COPY . .

EXPOSE 8765
ENTRYPOINT ["python3", "tools/local_library_server.py"]
CMD ["--public", "--port", "8765"]
