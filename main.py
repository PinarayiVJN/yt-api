from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pytubefix import YouTube
import os
import uuid
import subprocess
import re
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
    cache_id: str
    info: VideoInfo
    available_formats: List[str]

class FormatOptionsResponse(BaseModel):
    format_type: str
    options: List[StreamOption]

# Global cache to store YouTube objects temporarily
video_cache: Dict[str, YouTube] = {}

def process_youtube_url(url):
    """Simple URL processing - exactly like Google Colab"""
    url = url.split('?feature=shared')[0]

    if url.startswith("https://youtube.com") or url.startswith("http://youtube.com"):
        return url

    # Extract video ID
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/v\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})',
        r'([a-zA-Z0-9_-]{11})'
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            new_url = f"https://www.youtube.com/watch?v={video_id}"
            return new_url

    return url

def get_cached_youtube(cache_id: str) -> Optional[YouTube]:
    """Get YouTube object from cache"""
    return video_cache.get(cache_id)

def cache_youtube(url: str) -> str:
    """Cache YouTube object - NO DELAYS, NO CLIENT SPECIFICATION"""
    # Process URL exactly like Google Colab
    processed_url = process_youtube_url(url)
    
    # Create YouTube object exactly like Google Colab (no client, no delays)
    yt = YouTube(processed_url)
    
    # Force load streams to test connection
    streams = yt.streams
    
    cache_id = str(uuid.uuid4())
    video_cache[cache_id] = yt
    
    # Clean old cache entries (keep only last 10)
    if len(video_cache) > 10:
        oldest_key = next(iter(video_cache))
        del video_cache[oldest_key]
    
    return cache_id

def merge_video_audio(video_path, audio_path, output_path):
    """Merge video and audio using FFmpeg - exactly like Google Colab"""
    try:
        merge_command = [
            'ffmpeg',
            '-i', video_path,
            '-i', audio_path,
            '-c:v', 'copy',  # Copy video without re-encoding
            '-c:a', 'aac',   # Convert audio to AAC
            '-y',            # Overwrite output file
            output_path
        ]

        result = subprocess.run(merge_command, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg merge failed: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr}")
        return False

@app.get("/")
def root():
    return {"message": "YouTube Downloader API v3.0 - Google Colab Logic Implementation"}

@app.get("/info", response_model=VideoInfoResponse)
def get_video_info(url: str = Query(...)):
    """Step 1: Get video information using Google Colab logic"""
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
            cache_id=cache_id,
            info=info,
            available_formats=available_formats
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching video info: {str(e)}")

@app.get("/formats", response_model=FormatOptionsResponse)
def get_format_options(cache_id: str = Query(...), format_type: str = Query(...)):
    """Step 2: Get specific format options using Google Colab logic"""
    try:
        yt = get_cached_youtube(cache_id)
        if not yt:
            raise HTTPException(status_code=404, detail="Video not found in cache. Please fetch info first.")
        
        options = []
        
        if format_type.lower() == "mp3":
            # Audio options - exactly like Google Colab
            audio_streams = yt.streams.filter(only_audio=True).order_by('abr').desc()
            for i, stream in enumerate(audio_streams):
                size_mb = stream.filesize / (1024*1024) if stream.filesize else 0
                options.append(StreamOption(
                    id=f"audio_{i}",
                    quality=stream.abr or "Unknown",
                    format=f"{stream.mime_type}",
                    size_mb=round(size_mb, 2),
                    type="audio"
                ))
        
        elif format_type.lower() == "mp4":
            # Progressive video options (ready to play) - exactly like Google Colab
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
            
            # Adaptive video options (high quality, requires merging) - exactly like Google Colab
            adaptive_streams = yt.streams.filter(adaptive=True, only_video=True, file_extension='mp4').order_by('resolution').desc()
            for i, stream in enumerate(adaptive_streams):
                size_mb = stream.filesize / (1024*1024) if stream.filesize else 0
                # Add estimated audio size
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
    """Step 3: Download using Google Colab logic"""
    try:
        yt = get_cached_youtube(cache_id)
        if not yt:
            raise HTTPException(status_code=404, detail="Video not found in cache")
        
        # Parse option_id
        option_type, index = option_id.split('_')
        index = int(index)
        
        # Create safe filename - exactly like Google Colab
        safe_title = "".join(c for c in yt.title if c.isalnum() or c in (' ', '.', '_', '-')).strip()
        safe_title = safe_title.replace(' ', '_')[:50]
        unique_id = uuid.uuid4().hex[:8]
        
        if option_type == "audio":
            # Download audio - exactly like Google Colab
            audio_streams = yt.streams.filter(only_audio=True).order_by('abr').desc()
            selected_stream = audio_streams[index]
            
            file_path = selected_stream.download(output_path=DOWNLOAD_FOLDER)
            
            # Rename to .mp3 - exactly like Google Colab
            base, ext = os.path.splitext(file_path)
            new_file_path = base + ".mp3"
            os.rename(file_path, new_file_path)
            
            return FileResponse(new_file_path, filename=f"{safe_title}.mp3")
        
        elif option_type == "progressive":
            # Download progressive video - exactly like Google Colab
            video_streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc()
            selected_stream = video_streams[index]
            
            file_path = selected_stream.download(output_path=DOWNLOAD_FOLDER)
            
            return FileResponse(file_path, filename=f"{safe_title}_{selected_stream.resolution}.mp4")
        
        elif option_type == "adaptive":
            # Download adaptive video - exactly like Google Colab
            video_streams = yt.streams.filter(adaptive=True, only_video=True, file_extension='mp4').order_by('resolution').desc()
            selected_video_stream = video_streams[index]
            
            # Get best audio stream
            audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
            if not audio_stream:
                raise HTTPException(status_code=500, detail="No audio stream found for merging")
            
            # Download video and audio with temp prefixes - exactly like Google Colab
            video_path = selected_video_stream.download(
                output_path=DOWNLOAD_FOLDER,
                filename_prefix="temp_video_"
            )
            audio_path = audio_stream.download(
                output_path=DOWNLOAD_FOLDER,
                filename_prefix="temp_audio_"
            )
            
            # Create output filename - exactly like Google Colab
            output_filename = f"{safe_title}_{selected_video_stream.resolution}.mp4"
            output_path = os.path.join(DOWNLOAD_FOLDER, output_filename)
            
            # Merge with FFmpeg - exactly like Google Colab
            if merge_video_audio(video_path, audio_path, output_path):
                # Clean up temporary files - exactly like Google Colab
                os.remove(video_path)
                os.remove(audio_path)
                
                return FileResponse(output_path, filename=f"{safe_title}_{selected_video_stream.resolution}.mp4")
            else:
                raise HTTPException(status_code=500, detail="FFmpeg merge failed")
        
        else:
            raise HTTPException(status_code=400, detail="Invalid option ID")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

@app.get("/cache")
def get_cache_info():
    """Get current cache status"""
    return {
        "cached_videos": len(video_cache),
        "cache_ids": list(video_cache.keys())
    }
