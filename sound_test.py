import os
import subprocess

print("--- SOUND TEST STARTING ---")

# Method 1: The Simple Way
print("Testing Method 1 (os.system)...")
exit_code = os.system('say "Method one working"')
print(f"Method 1 finished with code: {exit_code}")

# Method 2: The Robust Way (Subprocess)
print("Testing Method 2 (subprocess)...")
try:
    subprocess.run(["say", "Method two working"], check=True)
    print("Method 2 success.")
except Exception as e:
    print(f"Method 2 failed: {e}")

# Method 3: Forced Voice
print("Testing Method 3 (Forced Voice)...")
os.system('say -v Fred "Method three working"')

print("--- TEST COMPLETE ---")