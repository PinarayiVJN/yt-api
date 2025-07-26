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
    yt = YouTube(url, client='ANDROID')
    # Create a safe filename from the title and a unique ID
    # This removes characters that are problematic in filenames
    safe_title = "".join(c for c in yt.title if c.isalnum() or c in (' ', '.', '_')).strip().replace(" ", "_")
    video_id = uuid.uuid4().hex # Generates a random, unique 32-character string
    filename = f"{safe_title}_{video_id}" # Combines safe title and unique ID

    if format == 'mp3':
        # Select the best quality audio stream
        audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
        # Download the audio stream (it often comes as an .mp4 container for audio)
        audio_path = audio_stream.download(output_path=DOWNLOAD_FOLDER, filename=filename + ".mp4")

        mp3_path = os.path.join(DOWNLOAD_FOLDER, filename + ".mp3")
        # Use ffmpeg to convert the downloaded audio (MP4 container) to MP3
        # '-i': input file
        # '-vn': no video (only audio)
        # '-ab 192k': audio bitrate (quality)
        # '-ar 44100': audio sample rate
        # '-y': overwrite output file if it exists
        # 'check=True': raises an error if the ffmpeg command fails
        subprocess.run(['ffmpeg', '-i', audio_path, '-vn', '-ab', '192k', '-ar', '44100', '-y', mp3_path], check=True)
        os.remove(audio_path) # Delete the temporary MP4 audio file
        return mp3_path # Return the path to the newly created MP3 file

    else: # Default format is 'mp4'
        # Select the best quality progressive MP4 stream (contains both audio and video)
        stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
        # Download the progressive MP4 stream
        return stream.download(output_path=DOWNLOAD_FOLDER, filename=filename + ".mp4")

@app.get("/") # This defines an API endpoint for the root URL "/"
def root():
    # When someone accesses your base URL, they'll see this message
    return {"message": "YouTube Downloader API is running"}

@app.get("/download") # This defines the main API endpoint for downloads
# 'url' is a required query parameter (e.g., ?url=...)
# 'format' is an optional query parameter that defaults to "mp4"
def download(url: str = Query(...), format: str = Query("mp4")):
    try:
        # Call the download function with the provided URL and format
        file_path = download_youtube_video(url, format)
        # Return the downloaded file as a web response
        # 'filename' ensures the downloaded file has a proper name in the user's browser
        return FileResponse(file_path, filename=os.path.basename(file_path))
    except Exception as e:
        # If any error occurs during the process, return a 500 status code and the error message
        return JSONResponse(status_code=500, content={"error": str(e)})
