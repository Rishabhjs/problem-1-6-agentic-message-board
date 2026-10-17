FROM python:3.12-slim
WORKDIR /app
COPY src/ /app/src/
ENV BOARD_DB=/data/board.db PORT=8000
VOLUME /data
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"
CMD ["python","src/main.py","serve","--simulate"]
