#!/usr/bin/env python3
import argparse
import subprocess
import threading
import time
from http import server
from socketserver import ThreadingMixIn

import cv2
import mediapipe as mp
import numpy as np

latest_jpeg = None
latest_lock = threading.Lock()
running = True
stats = {'fps': 0.0, 'pose': False, 'face': False, 'left_hand': '', 'right_hand': '', 'face_dir': 'Not detected'}

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AirGesture Body Monitor</title>
<style>
  html,body{margin:0;height:100%;background:#101416;color:#edf5f2;font-family:Arial,sans-serif;}
  body{display:grid;grid-template-rows:auto 1fr;}
  header{padding:12px 18px;background:#182024;display:flex;gap:14px;align-items:center;flex-wrap:wrap;border-bottom:1px solid #2d383d;}
  h1{font-size:18px;margin:0;color:#fff;}
  .pill{font-size:13px;color:#c8d6d1;background:#253036;border:1px solid #3a474d;padding:6px 10px;border-radius:4px;}
  main{display:grid;place-items:center;padding:12px;overflow:hidden;}
  img{max-width:100%;max-height:calc(100vh - 74px);object-fit:contain;border:1px solid #2f3d42;background:#000;}
</style>
</head>
<body>
<header>
  <h1>Body Skeleton / Hand Gesture / Face Direction Monitor</h1>
  <span class="pill">Green: pose skeleton</span>
  <span class="pill">Cyan / Orange: hand landmarks</span>
  <span class="pill">Purple: face contour and direction</span>
  <span class="pill">Refresh to reconnect</span>
</header>
<main><img src="/stream.mjpg" alt="live body skeleton stream"></main>
</body>
</html>""".encode('utf-8')

class Handler(server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_HEAD(self):
        if self.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(PAGE)))
            self.end_headers()
        else:
            self.send_error(404)

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)
            return
        if self.path == '/health':
            body = (str(stats) + '\n').encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == '/snapshot.jpg':
            frame = get_frame(timeout=3)
            if frame is None:
                self.send_error(503, 'No frame ready')
                return
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(frame)))
            self.end_headers()
            self.wfile.write(frame)
            return
        if self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', '0')
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while running:
                    frame = get_frame(timeout=2)
                    if frame is None:
                        continue
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', str(len(frame)))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
                    time.sleep(0.03)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        self.send_error(404)

class ThreadedHTTPServer(ThreadingMixIn, server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

def get_frame(timeout=1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with latest_lock:
            frame = latest_jpeg
        if frame is not None:
            return frame
        time.sleep(0.03)
    return None

def jpg_frames_from_rpicam(width, height, fps):
    cmd = ['rpicam-vid', '--codec', 'mjpeg', '--nopreview', '-t', '0', '--width', str(width), '--height', str(height), '--framerate', str(fps), '-o', '-']
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
    buf = bytearray()
    try:
        while running:
            chunk = proc.stdout.read(8192)
            if not chunk:
                time.sleep(0.02)
                continue
            buf.extend(chunk)
            while True:
                start = buf.find(b'\xff\xd8')
                end = buf.find(b'\xff\xd9', start + 2)
                if start != -1 and end != -1:
                    jpg = bytes(buf[start:end + 2])
                    del buf[:end + 2]
                    yield jpg
                else:
                    if start > 0:
                        del buf[:start]
                    break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except Exception:
            proc.kill()

def fingers_state(hand_lm):
    lm = hand_lm.landmark
    fingers = {
        'index': lm[8].y < lm[6].y,
        'middle': lm[12].y < lm[10].y,
        'ring': lm[16].y < lm[14].y,
        'pinky': lm[20].y < lm[18].y,
    }
    fingers['thumb'] = abs(lm[4].x - lm[0].x) > abs(lm[3].x - lm[0].x) * 1.12
    return fingers

def classify_gesture(hand_lm):
    if not hand_lm:
        return ''
    fingers = fingers_state(hand_lm)
    opened = [name for name, is_open in fingers.items() if is_open]
    count = len(opened)
    if count == 0:
        return 'Fist'
    if count >= 5:
        return 'Open palm'
    if opened == ['index']:
        return 'Index finger'
    if opened == ['thumb']:
        return 'Thumb'
    if fingers['index'] and fingers['middle'] and count == 2:
        return 'Two fingers'
    return f'{count} fingers'

def face_orientation(face_lm, w, h):
    if not face_lm:
        return 'Not detected', None
    lm = face_lm.landmark
    ids = [1, 152, 33, 263, 61, 291]
    if max(ids) >= len(lm):
        return 'Not detected', None
    image_points = np.array([(lm[1].x*w, lm[1].y*h), (lm[152].x*w, lm[152].y*h), (lm[33].x*w, lm[33].y*h), (lm[263].x*w, lm[263].y*h), (lm[61].x*w, lm[61].y*h), (lm[291].x*w, lm[291].y*h)], dtype=np.float64)
    model_points = np.array([(0.0,0.0,0.0), (0.0,-63.0,-12.0), (-43.0,32.0,-26.0), (43.0,32.0,-26.0), (-28.0,-28.0,-24.0), (28.0,-28.0,-24.0)], dtype=np.float64)
    cam = np.array([[w, 0, w/2], [0, w, h/2], [0, 0, 1]], dtype=np.float64)
    dist = np.zeros((4, 1), dtype=np.float64)
    ok, rvec, tvec = cv2.solvePnP(model_points, image_points, cam, dist, flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        return 'Not detected', None
    rmat, _ = cv2.Rodrigues(rvec)
    angles, *_ = cv2.RQDecomp3x3(rmat)
    pitch, yaw, roll = angles
    label = 'Front'
    if yaw > 15:
        label = 'Look left'
    elif yaw < -15:
        label = 'Look right'
    if pitch > 18:
        label += ' / down'
    elif pitch < -18:
        label += ' / up'
    return f'{label}  yaw:{yaw:+.0f} pitch:{pitch:+.0f}', (rvec, tvec, cam, dist)

def draw_face_axis(img, pose):
    if not pose:
        return
    rvec, tvec, cam, dist = pose
    axis = np.float64([[0, 0, 0], [55, 0, 0], [0, 55, 0], [0, 0, 55]])
    pts, _ = cv2.projectPoints(axis, rvec, tvec, cam, dist)
    pts = pts.reshape(-1, 2).astype(int)
    origin = tuple(pts[0])
    cv2.line(img, origin, tuple(pts[1]), (0, 0, 255), 2)
    cv2.line(img, origin, tuple(pts[2]), (0, 255, 0), 2)
    cv2.line(img, origin, tuple(pts[3]), (255, 0, 0), 2)

def put_panel(img, fps, left_label, right_label, face_label, pose_ok):
    cv2.rectangle(img, (12, 12), (450, 150), (0, 0, 0), -1)
    cv2.rectangle(img, (12, 12), (450, 150), (80, 100, 105), 1)
    lines = [f'FPS: {fps:4.1f}', f'Pose: {"OK" if pose_ok else "No body"}', f'Left hand: {left_label or "Not detected"}', f'Right hand: {right_label or "Not detected"}', f'Face: {face_label}']
    colors = [(80,240,170), (80,220,120), (255,190,70), (90,220,255), (220,160,255)]
    for i, line in enumerate(lines):
        cv2.putText(img, line, (26, 42 + i*24), cv2.FONT_HERSHEY_SIMPLEX, 0.60, colors[i], 2 if i == 0 else 1, cv2.LINE_AA)

def process_loop(width, height, fps, process_width, quality):
    global latest_jpeg, stats, running
    mp_drawing = mp.solutions.drawing_utils
    mp_holistic = mp.solutions.holistic
    mp_face_mesh = mp.solutions.face_mesh
    pose_style = mp_drawing.DrawingSpec(color=(80,230,120), thickness=2, circle_radius=3)
    pose_conn = mp_drawing.DrawingSpec(color=(80,160,80), thickness=2)
    lh_style = mp_drawing.DrawingSpec(color=(255,180,70), thickness=2, circle_radius=3)
    rh_style = mp_drawing.DrawingSpec(color=(70,220,255), thickness=2, circle_radius=3)
    face_style = mp_drawing.DrawingSpec(color=(220,130,255), thickness=1, circle_radius=1)
    with mp_holistic.Holistic(static_image_mode=False, model_complexity=0, smooth_landmarks=True, refine_face_landmarks=False, min_detection_confidence=0.45, min_tracking_confidence=0.45) as holistic:
        smoothed_fps = 0.0
        alpha = 0.12
        last = time.time()
        while running:
            try:
                for jpg in jpg_frames_from_rpicam(width, height, fps):
                    frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                    if frame is None:
                        continue
                    now = time.time()
                    inst = 1.0 / max(now - last, 1e-6)
                    smoothed_fps = inst if smoothed_fps == 0 else (1-alpha)*smoothed_fps + alpha*inst
                    last = now
                    h, w = frame.shape[:2]
                    process_h = int(h * process_width / w)
                    small = cv2.resize(frame, (process_width, process_h), interpolation=cv2.INTER_AREA)
                    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                    rgb.flags.writeable = False
                    results = holistic.process(rgb)
                    out = frame.copy()
                    if results.pose_landmarks:
                        mp_drawing.draw_landmarks(out, results.pose_landmarks, mp_holistic.POSE_CONNECTIONS, pose_style, pose_conn)
                    if results.left_hand_landmarks:
                        mp_drawing.draw_landmarks(out, results.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS, lh_style, lh_style)
                    if results.right_hand_landmarks:
                        mp_drawing.draw_landmarks(out, results.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS, rh_style, rh_style)
                    if results.face_landmarks:
                        mp_drawing.draw_landmarks(out, results.face_landmarks, mp_face_mesh.FACEMESH_CONTOURS, face_style, face_style)
                    left_label = classify_gesture(results.left_hand_landmarks)
                    right_label = classify_gesture(results.right_hand_landmarks)
                    face_label, face_pose = face_orientation(results.face_landmarks, w, h)
                    draw_face_axis(out, face_pose)
                    put_panel(out, smoothed_fps, left_label, right_label, face_label, bool(results.pose_landmarks))
                    stats = {'fps': round(smoothed_fps, 2), 'pose': bool(results.pose_landmarks), 'face': bool(results.face_landmarks), 'left_hand': left_label, 'right_hand': right_label, 'face_dir': face_label}
                    ok, enc = cv2.imencode('.jpg', out, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
                    if ok:
                        with latest_lock:
                            latest_jpeg = enc.tobytes()
            except Exception as exc:
                print('capture/process loop error:', repr(exc), flush=True)
                time.sleep(2)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8081)
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=480)
    parser.add_argument('--fps', type=int, default=10)
    parser.add_argument('--process-width', type=int, default=480)
    parser.add_argument('--quality', type=int, default=78)
    args = parser.parse_args()
    t = threading.Thread(target=process_loop, args=(args.width, args.height, args.fps, args.process_width, args.quality), daemon=True)
    t.start()
    httpd = ThreadedHTTPServer((args.host, args.port), Handler)
    print(f'Body monitor running at http://{args.host}:{args.port}/', flush=True)
    try:
        httpd.serve_forever()
    finally:
        global running
        running = False
        httpd.server_close()

if __name__ == '__main__':
    main()
