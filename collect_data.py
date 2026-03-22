import cv2
import mediapipe as mp
import numpy as np
import csv
import os

# Create file to save data
if not os.path.exists('data.csv'):
    with open('data.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        # Header: Label, then 63 coordinates (21 points * 3 dims)
        header = ['label'] + [f'coord_{i}' for i in range(63)]
        writer.writerow(header)

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

cap = cv2.VideoCapture(0)

print("--- INSTRUCTIONS ---")
print("1. Type the letter you want to record (e.g. 'A') in this terminal and press Enter.")
print("2. The camera window will open. Move your hand slightly to capture angles.")
print("3. Press 'ESC' to stop recording that letter and go back to the terminal.")
print("4. Type 'EXIT' in the terminal to finish.")

while True:
    # 1. Get input from terminal
    target_letter = input("\n>> Enter letter to record (or 'EXIT'): ").upper()
    if target_letter == 'EXIT': break
    
    print(f"Starting camera for '{target_letter}'... Press ESC to stop.")
    
    while True:
        success, frame = cap.read()
        if not success: break
        
        # Flip and Process
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb)
        
        status = "Show Hand"
        color = (0, 0, 255) # Red (Waiting)
        
        if results.multi_hand_landmarks:
            status = f"Recording {target_letter}..."
            color = (0, 255, 0) # Green (Recording)
            
            for hand_landmarks in results.multi_hand_landmarks:
                mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                
                # Extract Coordinates (Normalization happens later in training)
                row = [target_letter]
                for lm in hand_landmarks.landmark:
                    row.append(lm.x)
                    row.append(lm.y)
                    row.append(lm.z)
                
                # Save to CSV
                with open('data.csv', 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(row)
        
        # UI
        cv2.rectangle(frame, (0, 0), (640, 50), (0, 0, 0), -1)
        cv2.putText(frame, status, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
        cv2.putText(frame, "Press ESC to finish letter", (20, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        
        cv2.imshow("Data Collector", frame)
        
        # Check for ESC key (ASCII 27)
        if cv2.waitKey(1) == 27:
            print(f"Stopped recording '{target_letter}'.")
            break

cap.release()
cv2.destroyAllWindows()