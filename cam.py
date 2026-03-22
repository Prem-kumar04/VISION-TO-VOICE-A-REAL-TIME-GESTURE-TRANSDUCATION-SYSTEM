# test_cam.py
import cv2, time
backends = [
    ("CAP_DSHOW", cv2.CAP_DSHOW),
    ("CAP_MSMF", cv2.CAP_MSMF),
    ("CAP_VFW", cv2.CAP_VFW),
    ("CAP_ANY", cv2.CAP_ANY),
]
for name, backend in backends:
    cap = cv2.VideoCapture(0, backend)
    ok = cap.isOpened()
    print(f"{name}: opened={ok}")
    if ok:
        ret, frame = cap.read()
        print(f"  read={ret}, shape={(None if frame is None else frame.shape)}")
        cap.release()
    time.sleep(0.3)