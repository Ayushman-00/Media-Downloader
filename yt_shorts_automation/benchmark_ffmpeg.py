import os
import sys
import time
import subprocess

def benchmark():
    clip_path = "output/clips/I Saved 1,000 Animals From Dying [Oo9EbArcQ1c]_clip.mp4"
    track_path = "output/clips/dummy_track.mp3"
    ass_path = "output/clips/I Saved 1,000 Animals From Dying [Oo9EbArcQ1c]_clip_music.ass"
    
    if not all(os.path.exists(p) for p in [clip_path, track_path, ass_path]):
        print("Required files not found for benchmark.")
        return
        
    ass_for_filter = ass_path.replace("\\", "/").replace(":", "\\:")
    volume = 0.5
    
    out_two_pass_temp = "output/clips/bench_temp.mp4"
    out_two_pass_final = "output/clips/bench_two_pass.mp4"
    out_one_pass = "output/clips/bench_one_pass.mp4"
    
    # ----------------------------------------------------
    # TWO PASS METHOD
    # ----------------------------------------------------
    start = time.time()
    
    # Pass 1: Music
    cmd1 = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", clip_path,
        "-i", track_path,
        "-filter_complex",
        f"[0:a]volume={volume}[a0]; [1:a]volume={volume}[a1]; [a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac",
        out_two_pass_temp
    ]
    subprocess.run(cmd1, check=True)
    
    # Pass 2: Captions
    cmd2 = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", out_two_pass_temp,
        "-vf", f"subtitles='{ass_for_filter}'",
        "-c:a", "copy",
        out_two_pass_final
    ]
    subprocess.run(cmd2, check=True)
    
    two_pass_time = time.time() - start
    print(f"Two-pass took: {two_pass_time:.2f}s")
    
    # ----------------------------------------------------
    # ONE PASS METHOD
    # ----------------------------------------------------
    start = time.time()
    
    cmd_combined = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", clip_path,
        "-i", track_path,
        "-vf", f"subtitles='{ass_for_filter}'",
        "-filter_complex",
        f"[0:a]volume={volume}[a0]; [1:a]volume={volume}[a1]; [a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "libx264", "-c:a", "aac",
        out_one_pass
    ]
    subprocess.run(cmd_combined, check=True)
    
    one_pass_time = time.time() - start
    print(f"One-pass took: {one_pass_time:.2f}s")
    print(f"Difference: {two_pass_time - one_pass_time:.2f}s")

if __name__ == "__main__":
    benchmark()
