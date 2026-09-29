"""ffprobe stream/encoder info for S1 videos (read-only). usage: s1_probe.py <mp4>..."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

FF = shutil.which("ffprobe") or str(next(Path.home().glob(
    "AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/ffmpeg-*/bin/ffprobe.exe")))


def probe(p):
    out = subprocess.run([FF, "-v", "error", "-show_entries",
                          "stream=codec_name,profile,pix_fmt,bit_rate,r_frame_rate,nb_frames,has_b_frames,level"
                          ":format=bit_rate:format_tags:stream_tags",
                          "-of", "json", str(p)], capture_output=True, text=True).stdout
    info = json.loads(out)
    fr = subprocess.run([FF, "-v", "error", "-select_streams", "v", "-show_entries", "frame=pict_type",
                         "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout.split()
    raw = Path(p).read_bytes()
    m = re.search(rb"x264 - core \d+.{0,400}?(?=\x00)", raw, re.S)
    return {"file": str(p), "streams": info.get("streams"), "format": info.get("format"),
            "gop": "".join(x[0] for x in fr if x),
            "x264_settings": m.group(0).decode("latin1") if m else None}


if __name__ == "__main__":
    print(json.dumps([probe(p) for p in sys.argv[1:]], indent=1))
