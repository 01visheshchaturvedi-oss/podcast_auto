"""Wrapper: run edge-tts with hard kill timeout (manual poll + taskkill /F /T).
Exits with 0 on success, 1 on fail/timeout."""
import os, sys, time, subprocess

text = sys.argv[1]
voice = sys.argv[2]
out_path = sys.argv[3]
timeout_s = int(sys.argv[4])
rate = sys.argv[5] if len(sys.argv) > 5 else '+0%'
pitch = sys.argv[6] if len(sys.argv) > 6 else '+0Hz'
volume = sys.argv[7] if len(sys.argv) > 7 else '+0%'

cmd = [sys.executable, '-m', 'edge_tts', '--text', text,
       '--voice', voice, '--write-media', out_path]
if rate != '+0%':
    cmd.extend(['--rate', rate])
if pitch != '+0Hz':
    cmd.extend(['--pitch', pitch])
if volume != '+0%':
    cmd.extend(['--volume', volume])

# Start process with minimal overhead
proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW)

# Manual poll loop (every 0.5s) — guarantees we can always kill
start = time.monotonic()
ok = False
while time.monotonic() - start < timeout_s:
    rc = proc.poll()
    if rc is not None:
        ok = (rc == 0)
        break
    time.sleep(0.5)
else:
    # Timeout — use taskkill /F /T (guaranteed termination on Windows)
    subprocess.run(
        ['C:\\Windows\\System32\\taskkill.exe', '/F', '/T', '/PID', str(proc.pid)],
        capture_output=True, timeout=10
    )
    # Clean up
    try:
        proc.wait(timeout=5)
    except:
        pass
    
    # Also kill any orphan edge-tts python processes
    subprocess.run(
        ['C:\\Windows\\System32\\taskkill.exe', '/F', '/IM', 'python.exe',
         '/FI', f'PID ge {proc.pid}'],
        capture_output=True, timeout=10
    )

# Check result
if ok and os.path.exists(out_path) and os.path.getsize(out_path) > 500:
    sys.exit(0)
else:
    sys.exit(1)
