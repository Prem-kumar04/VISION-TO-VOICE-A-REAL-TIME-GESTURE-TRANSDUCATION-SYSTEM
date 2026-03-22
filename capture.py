import cv2
import mediapipe as mp
import os

if not os.path.exists('references'):
    os.makedirs('references')

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

cap = cv2.VideoCapture(0)

print("--- INSTRUCTIONS ---")
print("1. Press 'A' through 'Z' to save letters.")
print("2. Press SPACEBAR to save 'SPACE'.")
print("3. Press ESC to quit.")

while True:
    success, frame = cap.read()
    if not success: break
    
    # Flip for mirror view
    frame = cv2.flip(frame, 1)
    
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb)
    
    display_text = "Press Key to Save"
    color = (255, 0, 0)
    
    if results.multi_hand_landmarks:
        color = (0, 255, 0)
        display_text = "Hand Detected!"
        for hand_landmarks in results.multi_hand_landmarks:
            mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
    
    cv2.putText(frame, display_text, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    cv2.imshow("Capture Tool (ESC to Quit)", frame)
    
    key = cv2.waitKey(1)
    
    # QUIT on ESC key (ASCII 27)
    if key == 27:
        break
    
    # Save SPACE on Spacebar (ASCII 32)
    elif key == 32:
        if results.multi_hand_landmarks:
            cv2.imwrite("references/SPACE.jpg", frame)
            print("Saved references/SPACE.jpg")
        else:
            print("No hand detected!")
            
    # Save Letters A-Z (including Q)
    elif 65 <= key <= 90 or 97 <= key <= 122:
        char = chr(key).upper()
        if results.multi_hand_landmarks:
            filename = f"references/{char}.jpg"
            cv2.imwrite(filename, frame)
            print(f"Saved {filename}")
        else:
            print("No hand detected!")

cap.release()
cv2.destroyAllWindows()