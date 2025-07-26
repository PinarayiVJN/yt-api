from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pytubefix import YouTube
import os
import uuid
import subprocess
import time
import json
from typing import Dict, List, Optional
from pydantic import BaseModel

app = FastAPI()

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Response models
class VideoInfo(BaseModel):
    title: str
    author: str
    views: int
    duration: int
    thumbnail: str

class StreamOption(BaseModel):
    id: str
    quality: str
    format: str
    size_mb: float
    type: str  # "progressive", "adaptive", "audio"

class VideoInfoResponse(BaseModel):
    info: VideoInfo
    available_formats: List[str]  # ["mp3", "mp4"]

class FormatOptionsResponse(BaseModel):
    format_type: str
    options: List[StreamOption]

# Global cache to store YouTube objects temporarily
video_cache: Dict[str, YouTube] = {}

def get_cached_youtube(cache_id: str) -> Optional[YouTube]:
    """Get YouTube object from cache"""
    return video_cache.get(cache_id)

def cache_youtube(url: str) -> str:
    """Cache YouTube object and return cache ID"""
    time.sleep(15)  # Rate limiting delay
    cache_id = str(uuid.uuid4())
    yt = YouTube(url, client='ANDROID')
    video_cache[cache_id] = yt
    
    # Clean old cache entries (keep only last 10)
    if len(video_cache) > 10:
        oldest_key = next(iter(video_cache))
        del video_cache[oldest_key]
    
    return cache_id

@app.get("/")
def root():
    return {"message": "YouTube Downloader API v2.0 - Multi-step workflow ready"}

@app.get("/info", response_model=VideoInfoResponse)
def get_video_info(url: str = Query(...)):
    """Step 1: Get video information and available format types"""
    try:
        cache_id = cache_youtube(url)
        yt = get_cached_youtube(cache_id)
        
        if not yt:
            raise HTTPException(status_code=500, detail="Failed to load video")
        
        # Get basic info
        info = VideoInfo(
            title=yt.title,
            author=yt.author,
            views=yt.views,
            duration=yt.length,
            thumbnail=yt.thumbnail_url
        )
        
        # Check available format types
        available_formats = []
        
        # Check for audio streams
        audio_streams = yt.streams.filter(only_audio=True)
        if audio_streams:
            available_formats.append("mp3")
        
        # Check for video streams
        video_streams = yt.streams.filter(file_extension='mp4')
        if video_streams:
            available_formats.append("mp4")
        
        return VideoInfoResponse(
            info=info,
            available_formats=available_formats
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching video info: {str(e)}")

@app.get("/formats", response_model=FormatOptionsResponse)
def get_format_options(cache_id: str = Query(...), format_type: str = Query(...)):
    """Step 2: Get specific format options (mp3 or mp4)"""
    try:
        yt = get_cached_youtube(cache_id)
        if not yt:
            raise HTTPException(status_code=404, detail="Video not found in cache. Please fetch info first.")
        
        options = []
        
        if format_type.lower() == "mp3":
            # Audio options
            audio_streams = yt.streams.filter(only_audio=True).order_by('abr').desc()
            for i, stream in enumerate(audio_streams):
                size_mb = stream.filesize / (1024*1024) if stream.filesize else 0
                options.append(StreamOption(
                    id=f"audio_{i}",
                    quality=stream.abr or "Unknown",
                    format="MP3",
                    size_mb=round(size_mb, 2),
                    type="audio"
                ))
        
        elif format_type.lower() == "mp4":
            # Progressive video options (ready to play)
            progressive_streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc()
            for i, stream in enumerate(progressive_streams):
                size_mb = stream.filesize / (1024*1024) if stream.filesize else 0
                options.append(StreamOption(
                    id=f"progressive_{i}",
                    quality=f"{stream.resolution} ({stream.fps}fps)",
                    format="MP4 Progressive",
                    size_mb=round(size_mb, 2),
                    type="progressive"
                ))
            
            # Adaptive video options (high quality, requires merging)
            adaptive_streams = yt.streams.filter(adaptive=True, only_video=True, file_extension='mp4').order_by('resolution').desc()
            for i, stream in enumerate(adaptive_streams):
                size_mb = stream.filesize / (1024*1024) if stream.filesize else 0
                # Add estimated audio size (usually ~10-15% of video size)
                estimated_total_mb = size_mb * 1.15
                options.append(StreamOption(
                    id=f"adaptive_{i}",
                    quality=f"{stream.resolution} ({stream.fps}fps) HQ",
                    format="MP4 High Quality",
                    size_mb=round(estimated_total_mb, 2),
                    type="adaptive"
                ))
        
        else:
            raise HTTPException(status_code=400, detail="Invalid format type. Use 'mp3' or 'mp4'")
        
        return FormatOptionsResponse(
            format_type=format_type,
            options=options
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting format options: {str(e)}")

@app.get("/download")
def download_selected(cache_id: str = Query(...), option_id: str = Query(...)):
    """Step 3: Download the selected option"""
    try:
        yt = get_cached_youtube(cache_id)
        if not yt:
            raise HTTPException(status_code=404, detail="Video not found in cache")
        
        # Parse option_id to determine download type
        option_type, index = option_id.split('_')
        index = int(index)
        
        # Create safe filename
        safe_title = "".join(c for c in yt.title if c.isalnum() or c in (' ', '.', '_')).strip().replace(" ", "_")[:50]
        unique_id = uuid.uuid4().hex[:8]
        
        if option_type == "audio":
            # Download audio as MP3
            audio_streams = yt.streams.filter(only_audio=True).order_by('abr').desc()
            selected_stream = audio_streams[index]
            
            temp_path = selected_stream.download(
                output_path=DOWNLOAD_FOLDER,
                filename=f"{safe_title}_{unique_id}_temp"
            )
            
            # Convert to MP3
            final_path = os.path.join(DOWNLOAD_FOLDER, f"{safe_title}_{unique_id}.mp3")
            subprocess.run([
                'ffmpeg', '-i', temp_path, '-vn', '-ab', '192k', 
                '-ar', '44100', '-y', final_path
            ], check=True, capture_output=True)
            
            os.remove(temp_path)
            return FileResponse(final_path, filename=f"{safe_title}.mp3")
        
        elif option_type == "progressive":
            # Download progressive video
            video_streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc()
            selected_stream = video_streams[index]
            
            file_path = selected_stream.download(
                output_path=DOWNLOAD_FOLDER,
                filename=f"{safe_title}_{unique_id}.mp4"
            )
            
            return FileResponse(file_path, filename=f"{safe_title}_{selected_stream.resolution}.mp4")
        
        elif option_type == "adaptive":
            # Download adaptive video (requires merging)
            video_streams = yt.streams.filter(adaptive=True, only_video=True, file_extension='mp4').order_by('resolution').desc()
            selected_video = video_streams[index]
            selected_audio = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
            
            # Download video and audio
            video_path = selected_video.download(
                output_path=DOWNLOAD_FOLDER,
                filename=f"{safe_title}_{unique_id}_video"
            )
            audio_path = selected_audio.download(
                output_path=DOWNLOAD_FOLDER,
                filename=f"{safe_title}_{unique_id}_audio"
            )
            
            # Merge with FFmpeg
            final_path = os.path.join(DOWNLOAD_FOLDER, f"{safe_title}_{unique_id}_{selected_video.resolution}.mp4")
            subprocess.run([
                'ffmpeg', '-i', video_path, '-i', audio_path,
                '-c:v', 'copy', '-c:a', 'aac', '-y', final_path
            ], check=True, capture_output=True)
            
            # Clean up temp files
            os.remove(video_path)
            os.remove(audio_path)
            
            return FileResponse(final_path, filename=f"{safe_title}_{selected_video.resolution}.mp4")
        
        else:
            raise HTTPException(status_code=400, detail="Invalid option ID")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

# Utility endpoint to get cache_id for existing info calls
@app.get("/cache")
def get_cache_info():
    """Get current cache status"""
    return {
        "cached_videos": len(video_cache),
        "cache_ids": list(video_cache.keys())
    }
