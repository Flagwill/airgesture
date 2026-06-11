import cv2
import mediapipe as mp
import numpy as np
import gpiozero
import serial

print('OpenCV:', cv2.__version__)
print('MediaPipe:', mp.__version__)
print('NumPy:', np.__version__)

hands = mp.solutions.hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)
blank = np.zeros((480, 640, 3), dtype=np.uint8)
result = hands.process(cv2.cvtColor(blank, cv2.COLOR_BGR2RGB))
hands.close()
print('MediaPipe Hands object: OK')
print('Blank frame processed:', result.multi_hand_landmarks is None)

for idx in range(4):
    cap = cv2.VideoCapture(idx)
    ok = cap.isOpened()
    print(f'cv2 camera index {idx}:', 'open' if ok else 'not open')
    cap.release()
