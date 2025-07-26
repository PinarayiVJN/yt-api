from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from pytubefix import YouTube
import os
import uuid
import subprocess

app = FastAPI()

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def download_youtube_video(url: str, format: str = 'mp4') -> str:
    yt = YouTube(url)
    safe_title = "".join(c for c in yt.title if c.isalnum() or c in (' ', '.', '_')).strip().replace(" ", "_")
    video_id = uuid.uuid4().hex
    filename = f"{safe_title}_{video_id}"

    if format == 'mp3':
        audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
        audio_path = audio_stream.download(output_path=DOWNLOAD_FOLDER, filename=filename + ".mp4")

        mp3_path = os.path.join(DOWNLOAD_FOLDER, filename + ".mp3")
        subprocess.run(['ffmpeg', '-i', audio_path, '-vn', '-ab', '192k', '-ar', '44100', '-y', mp3_path], check=True)
        os.remove(audio_path)
        return mp3_path

    else:
        stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
        return stream.download(output_path=DOWNLOAD_FOLDER, filename=filename + ".mp4")

@app.get("/")
def root():
    return {"message": "YouTube Downloader API is running"}

@app.get("/download")
def download(url: str = Query(...), format: str = Query("mp4")):
    try:
        file_path = download_youtube_video(url, format)
        return FileResponse(file_path, filename=os.path.basename(file_path))
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
