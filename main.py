from typing import Optional
import subprocess
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import json
import re 
import asyncio
import os
from datetime import datetime
from prometheus_client import Gauge, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client import start_http_server
from starlette.responses import Response


app = FastAPI()

with open("config.json") as f:
    config = json.load(f)
gstreamer_path = config.get("gstreamer_path")
file_path_orig = config.get("file_path")

# Переменные для хранения состояния, URL и процесса потока
rtsp_url: Optional[str] = None
stream_status: str = "Stopped"
error_message: Optional[str] = None
process: Optional[subprocess.Popen] = None
monitoring_active: bool = False  # Флаг для управления мониторингом

# Регулярное выражение для проверки RTSP URL
rtsp_pattern = r"^rtsp:\/\/(\d{1,3}\.){3}\d{1,3}(:\d{1,5})?(\/\S*)?$"

# Функция валидации RTSP URL
def validate_rtsp_url(url: str) -> bool:
    return bool(re.match(rtsp_pattern, url))

async def monitor_process():
    global stream_status, process, error_message
    while True:
        await asyncio.sleep(1)
        if process: 
            if process.poll() is not None:
                code = process.returncode
                if code != 0:
                    output, error = process.communicate()
                    error_message = error
                    stream_status = "Something wrong with programms"
                else:
                    stream_status = "Stopped"
                    process = None
                    error_message = None
            else:
                stream_status = "Running"
                error_message = None



class StreamData(BaseModel):
    url: str

# Маршрут для отображения HTML-страницы с интерфейсом
@app.get("/", response_class=HTMLResponse)
async def home():
    try:
        with open("static/index.html") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content, status_code=200)
    except FileNotFoundError:
        return HTMLResponse(content="index.html not found", status_code=404)

@app.post("/start")
async def start_stream(data: StreamData):
    global rtsp_url, stream_status, process, error_message, monitoring_active, monitoring_task, file_path_orig
    
    # Проверка валидности RTSP URL
    if not validate_rtsp_url(data.url):
        error_message = "Invalid RTSP URL. Please enter a correct RTSP URL"
        raise HTTPException(status_code=400, detail="Invalid RTSP URL. Please enter a correct RTSP URL.")


    if stream_status == "Running":
        error_message = "Stream already running."
        raise HTTPException(status_code=400, detail="Stream already running.")

    rtsp_url = data.url
    stream_status = "Preparing"
    error_message = None

    file_path = file_path_orig + "/" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".mkv"
    command = [
        gstreamer_path,
        "rtspsrc", f'location="{rtsp_url}"',
        "protocols=tcp", 
        "latency=200",
        "drop-on-latency=true",
        "!", "queue",
        "!", "rtph264depay",
        "!", "h264parse",
        "!", "tee", "name=t", "t.",
        "!", "queue",
        "!", "matroskamux",
        "!", "filesink", f'location={file_path}', 't.',
        "!", "avdec_h264",
        "!", "autovideosink"
    ]

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        monitoring_active = True  # Включаем мониторинг
        # Запускаем фоновые задачи для мониторинга
        asyncio.create_task(monitor_process())
        monitoring_task = asyncio.create_task(monitor_process())
    except Exception as e:
        stream_status = "Error something wrong with start"
        error_message = str(e)
        rtsp_url = None
        raise HTTPException(status_code=500, detail=f"Failed to start stream: {e}")
    return {"status": stream_status, "rtsp_url": rtsp_url}

@app.post("/stop")
async def stop_stream():
    global rtsp_url, stream_status, process, error_message, monitoring_active, monitoring_task

    if stream_status == "Stopped":
        error_messag = 'Stream already stopped'
        raise HTTPException(status_code=400, detail="Stream already stopped.")
    
    # Остановить мониторинг
    monitoring_active = False
    if monitoring_task:
        monitoring_task.cancel()  # Отменяем задачу мониторинга
        try:
            await monitoring_task  # Ждем, пока задача завершится
        except asyncio.CancelledError:
            pass  # Игнорируем исключение отмены

    if process:
        process.terminate()
        process.wait()  # дождаться завершения
        process = None

    stream_status = "Stopped"
    rtsp_url = None
    error_message = None

    return {"status": "Stream stopped"}

@app.get("/status")
async def get_status():
    global stream_status, error_message, rtsp_url
    return {"status": stream_status, "rtsp_url": rtsp_url if rtsp_url else "No stream","error_message": error_message}

# Создаем метрику типа Gauge для статуса пайплайна
pipeline_status = Gauge("pipeline_status", "Status of the pipeline", ['status', 'error'])

# Функция для обновления статуса пайплайна (для примера - случайное значение)
def update_pipeline_status():
    global stream_status, error_message
    if error_message:
        pipeline_status.labels(status = stream_status, error = error_message).set(-1)
    elif (stream_status == 'Running'):
        pipeline_status.labels(status = stream_status, error= "None").set(1)
    elif (stream_status == 'Stopped'):
        pipeline_status.labels(status = stream_status, error= "None").set(0)
        

@app.get("/metrics")
async def metrics():
    # Обновляем статус пайплайна перед выдачей метрик
    update_pipeline_status()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Подключение статических файлов
app.mount("/static", StaticFiles(directory="static"), name="static")
