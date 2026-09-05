import subprocess
import sys
from pathlib import Path

sys.path.append(str(Path("backend").resolve()))
from backend.tools.video_gen import _get_ffmpeg_path

ffmpeg_exe = _get_ffmpeg_path()
if not ffmpeg_exe:
    print("FFMPEG NOT FOUND")
    sys.exit(1)

audio_path = Path("test_silent.wav")
import wave
with wave.open(str(audio_path), "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(24000)
    wf.writeframes(b"\x00\x00" * 24000 * 7)

duration = 7.0
input_args = ["-f", "lavfi", "-i", f"color=c=0x1E2332:s=1280x720:d={duration:.3f}"]

z_filter = "min(zoom+0.0018,1.25)"
x_filter = "iw/2-(iw/zoom/2)"
y_filter = "ih*0.35-(ih/zoom*0.35)"
fps = 30
total_frames = int(duration * fps)

vf_parts = [
    "scale=1280:720",
    f"zoompan=z='{z_filter}':d={total_frames}:x='{x_filter}':y='{y_filter}':s=1280x720:fps={fps}",
    "eq=contrast=1.06:brightness=0.01:saturation=1.10",
    "vignette=PI/4",
    "drawbox=y=ih-115:color=black@0.78:width=iw:height=115:t=fill",
    f"drawtext=text='ACTION':fontcolor=0xF5A623:fontsize=22:x=60:y=h-98",
    f"drawtext=text='test':fontcolor=0xFFFFFF:fontsize=20:x=60:y=h-58",
]

cmd = [
    ffmpeg_exe, "-y",
    *input_args,
    "-i", str(audio_path),
    "-vf", ",".join(vf_parts),
    "-t", f"{duration:.3f}",
    "-c:v", "libx264",
    "-preset", "fast",
    "-pix_fmt", "yuv420p",
    "-c:a", "aac",
    "-b:a", "192k",
    "test_out.mp4",
]

print("Running command:", " ".join(cmd))
proc = subprocess.run(cmd, capture_output=True)
print("Code:", proc.returncode)
print("Stderr:", proc.stderr.decode('utf-8')[:500])
