import sys, json, subprocess, time
from pathlib import Path
import numpy as np
sys.path.insert(0, "scripts")
import s1_synth_digital as sd
ff = sd.find_ffmpeg(None)
R = Path("data/derived/s1_synthetic_v1c_r2"); O = Path("work/s1_cm_try")
def enc(path, frames, codec, kbps):
    extra = ["-c:v","libx264","-pix_fmt","yuv420p"] if codec=="x264" else ["-c:v","mpeg4","-tag:v","mp4v","-g","12","-bf","0","-pix_fmt","yuv420p"]
    cmd=[ff,"-y","-v","error","-f","rawvideo","-pix_fmt","bgr24","-s","1280x720","-r","10","-i","-",*extra,"-b:v",f"{kbps}k",str(path)]
    p=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    for f in frames: p.stdin.write(np.ascontiguousarray(f).tobytes())
    p.stdin.close(); assert p.wait()==0
    return path.stat().st_size
for src in sys.argv[1:]:
    orig=R/f"{src}_ORIG.mp4"; dig=R/f"{src}_DIG0.mp4"
    dec,_=sd.read_frames(orig)
    ob, db = orig.stat().st_size, dig.stat().st_size
    t=time.time()
    xb=enc(O/"x.mp4",dec,"x264",int(db*8/5/1000))
    hx=sd.hf_ratio(dec, sd.read_frames(O/"x.mp4")[0])
    res={"src":src,"orig_b":ob,"dig_b":db,"origx_b":xb,"origx_hf":round(hx,3)}
    for sig in (3,6,10):
        p={"grain_sigma":sig,"contrast":1.03,"black":1.5}
        rng=np.random.default_rng(1)
        mb=enc(O/"m.mp4",[sd.tone(f,rng,p) for f in dec],"mp4v",int(ob*8/5/1000))
        res[f"digm_s{sig}"]=(mb, round(sd.hf_ratio(dec, sd.read_frames(O/"m.mp4")[0]),3))
    res["sec"]=round(time.time()-t,1)
    print(json.dumps(res))
