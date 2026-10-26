import subprocess

out = subprocess.check_output(['tasklist', '/FO', 'CSV', '/NH'], text=True)
for line in out.splitlines():
    parts = line.strip().split(',')
    if len(parts) >= 2:
        pname = parts[0].strip('"')
        pid = parts[1].strip('"')
        if 'share' in pname.lower() or 'fileexchange' in pname.lower():
            if 'code' not in pname.lower():
                print(f"Terminating {pname} (PID: {pid})")
                subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
