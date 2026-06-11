#!/usr/bin/env python3
import argparse
from collections import Counter, deque
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
stats = {
    "fps": 0.0,
    "pose": False,
    "face_front": False,
    "left_hand": "",
    "right_hand": "",
    "state": "IDLE",
    "command": "",
    "event": "",
    "ready_remaining": 0.0,
    "wave": False,
    "control_hand": "right",
    "control_label": "",
}

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AirGesture Lite Monitor</title>
<style>
  html,body{margin:0;min-height:100%;background:#111719;color:#eef6f1;font-family:Arial,sans-serif;}
  body{display:grid;grid-template-rows:auto 1fr;}
  header{padding:8px 14px;background:#182125;display:flex;gap:10px;align-items:center;flex-wrap:wrap;border-bottom:1px solid #2b383d;}
  h1{font-size:16px;margin:0;color:#fff;}
  .pill{font-size:12px;color:#cbd8d4;background:#253138;border:1px solid #3a484e;padding:4px 8px;border-radius:4px;}
  .ok{color:#88f5ae;}
  .no{color:#ff9d9d;}
  .ready{color:#ffd36d;}
  .exec{color:#93d7ff;}
  main{display:grid;place-items:start center;padding:10px;overflow:auto;}
  img{width:min(96vw,860px);height:auto;max-height:calc(100vh - 58px);object-fit:contain;border:1px solid #314045;background:#000;}
</style>
</head>
<body>
<header>
  <h1>AirGesture Lite Monitor</h1>
  <span class="pill" id="fps">FPS --</span>
  <span class="pill" id="pose">Pose --</span>
  <span class="pill" id="face">Face front --</span>
  <span class="pill" id="hands">Hands --</span>
  <span class="pill" id="state">State IDLE</span>
  <span class="pill" id="command">Command --</span>
  <span class="pill" id="event">Event --</span>
</header>
<main><img src="/stream.mjpg" alt="live stream"></main>
<script>
async function refreshStats(){
  try{
    const text = await fetch('/health', {cache:'no-store'}).then(r=>r.text());
    const data = JSON.parse(text);
    document.getElementById('fps').textContent = 'FPS ' + Number(data.fps || 0).toFixed(1);
    const pose = document.getElementById('pose');
    pose.textContent = 'Pose ' + (data.pose ? 'OK' : 'NO');
    pose.className = 'pill ' + (data.pose ? 'ok' : 'no');
    const face = document.getElementById('face');
    face.textContent = 'Face front ' + (data.face_front ? 'YES' : 'NO');
    face.className = 'pill ' + (data.face_front ? 'ok' : 'no');
    const handName = data.control_hand === 'left' ? 'Left' : data.control_hand === 'both' ? 'Both' : 'Right';
    document.getElementById('hands').textContent = 'Control ' + handName + ' ' + (data.control_label || '-');
    const state = document.getElementById('state');
    state.textContent = 'State ' + (data.state || 'IDLE') + (data.ready_remaining ? ' ' + Number(data.ready_remaining).toFixed(1) + 's' : '');
    state.className = 'pill ' + (data.state === 'READY' ? 'ready' : data.state === 'EXECUTE' ? 'exec' : '');
    document.getElementById('command').textContent = 'Command ' + (data.command || '--');
    document.getElementById('event').textContent = data.event ? ('Event ' + data.event) : 'Event --';
  } catch(e) {}
}
setInterval(refreshStats, 300);
refreshStats();
</script>
</body>
</html>""".encode("utf-8")


class Handler(server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_HEAD(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
        else:
            self.send_error(404)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)
            return
        if self.path == "/health":
            import json

            body = (json.dumps(stats, ensure_ascii=True) + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/snapshot.jpg":
            frame = get_frame(timeout=3)
            if frame is None:
                self.send_error(503, "No frame ready")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame)))
            self.end_headers()
            self.wfile.write(frame)
            return
        if self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while running:
                    frame = get_frame(timeout=2)
                    if frame is None:
                        continue
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(frame)))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                    time.sleep(0.02)
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
        time.sleep(0.02)
    return None


def jpg_frames_from_rpicam(width, height, fps):
    cmd = [
        "rpicam-vid",
        "--codec",
        "mjpeg",
        "--nopreview",
        "-t",
        "0",
        "--width",
        str(width),
        "--height",
        str(height),
        "--framerate",
        str(fps),
        "-o",
        "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
    buf = bytearray()
    try:
        while running:
            chunk = proc.stdout.read(8192)
            if not chunk:
                time.sleep(0.01)
                continue
            buf.extend(chunk)
            while True:
                start = buf.find(b"\xff\xd8")
                end = buf.find(b"\xff\xd9", start + 2)
                if start != -1 and end != -1:
                    jpg = bytes(buf[start : end + 2])
                    del buf[: end + 2]
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


def classify_gesture(hand_lm):
    if not hand_lm:
        return ""
    lm = hand_lm.landmark
    fingers = {
        "index": lm[8].y < lm[6].y,
        "middle": lm[12].y < lm[10].y,
        "ring": lm[16].y < lm[14].y,
        "pinky": lm[20].y < lm[18].y,
    }
    fingers["thumb"] = abs(lm[4].x - lm[0].x) > abs(lm[3].x - lm[0].x) * 1.12
    opened = [name for name, is_open in fingers.items() if is_open]
    count = len(opened)
    if count == 0:
        return "Fist"
    if count >= 5:
        return "Open"
    if opened == ["index"]:
        return "Index"
    if opened == ["thumb"]:
        return "Thumb"
    if fingers["index"] and fingers["middle"] and count == 2:
        return "Two"
    return f"{count} fingers"


def command_from_gesture(label):
    if not label:
        return None
    if label == "Fist":
        return "POWER_TOGGLE"
    if label == "Open":
        return "CANCEL"
    if label == "Index":
        return "MODE_NEXT"
    if label == "Thumb":
        return "FAN_UP"
    if label == "Two":
        return "TEMP_UP"
    if label.endswith("fingers"):
        return "TEMP_DOWN"
    return None


class WaveDetector:
    def __init__(self):
        self.points = deque(maxlen=40)
        self.last_wave_time = 0.0

    def update(self, hand_lm, now):
        if not hand_lm:
            return False
        wrist = hand_lm.landmark[0]
        return self.update_point(wrist.x, wrist.y, now)

    def update_point(self, x, y, now):
        self.points.append((now, x, y))
        while self.points and now - self.points[0][0] > 1.75:
            self.points.popleft()
        if now - self.last_wave_time < 1.0 or len(self.points) < 4:
            return False
        xs = [p[1] for p in self.points]
        ys = [p[2] for p in self.points]
        span_x = max(xs) - min(xs)
        span_y = max(ys) - min(ys)
        if span_x < 0.11 or span_y > max(0.27, span_x * 1.18):
            return False
        signs = []
        last_x = xs[0]
        for x in xs[1:]:
            dx = x - last_x
            last_x = x
            if abs(dx) < 0.014:
                continue
            sign = 1 if dx > 0 else -1
            if not signs or signs[-1] != sign:
                signs.append(sign)
        if len(signs) >= 2:
            self.last_wave_time = now
            self.points.clear()
            return True
        return False


class GestureStateMachine:
    def __init__(self):
        self.mode = "IDLE"
        self.ready_until = 0.0
        self.execute_until = 0.0
        self.event_until = 0.0
        self.event = ""
        self.command = ""
        self.release_required = None
        self.votes = deque(maxlen=8)

    def _set_event(self, text, now, duration=1.2):
        self.event = text
        self.event_until = now + duration

    def update(self, now, face_front, wave_detected, control_label):
        raw_cmd = command_from_gesture(control_label)
        if self.event and now > self.event_until:
            self.event = ""

        if self.mode == "EXECUTE" and now > self.execute_until:
            self.mode = "READY" if now < self.ready_until else "IDLE"

        if self.release_required and raw_cmd != self.release_required:
            self.release_required = None

        if self.mode == "IDLE":
            self.command = ""
            self.votes.clear()
            if face_front and wave_detected:
                self.mode = "READY"
                self.ready_until = now + 5.0
                self.release_required = None
                self._set_event("WAVE ACTIVATED", now)
            elif wave_detected and not face_front:
                self._set_event("LOOK AT CAMERA", now)

        elif self.mode == "READY":
            if now > self.ready_until:
                self.mode = "IDLE"
                self.command = ""
                self.votes.clear()
                self._set_event("TIMEOUT", now)
            elif not face_front:
                self.votes.clear()
                self.command = ""
                self._set_event("LOOK AT CAMERA", now, duration=0.7)
            elif self.release_required:
                self.command = "release hand"
                self.votes.clear()
            elif raw_cmd:
                self.votes.append(raw_cmd)
                common, count = Counter(self.votes).most_common(1)[0]
                self.command = common
                if count >= 5 and len(self.votes) >= 6:
                    if common == "CANCEL":
                        self.mode = "IDLE"
                        self.command = ""
                        self.votes.clear()
                        self._set_event("CANCELED", now)
                    else:
                        self.mode = "EXECUTE"
                        self.execute_until = now + 0.9
                        self.ready_until = max(self.ready_until, now + 2.2)
                        self.command = common
                        self.release_required = raw_cmd
                        self.votes.clear()
                        self._set_event("EXECUTE " + common, now, duration=1.0)
            else:
                self.command = ""
                self.votes.clear()

        return {
            "state": self.mode,
            "command": self.command,
            "event": self.event,
            "ready_remaining": max(0.0, self.ready_until - now) if self.mode in ("READY", "EXECUTE") else 0.0,
        }


def face_front_from_pose(pose_landmarks):
    if not pose_landmarks:
        return False, "Front: NO"
    mp_pose = mp.solutions.pose
    lm = pose_landmarks.landmark
    nose = lm[mp_pose.PoseLandmark.NOSE]
    left_eye = lm[mp_pose.PoseLandmark.LEFT_EYE]
    right_eye = lm[mp_pose.PoseLandmark.RIGHT_EYE]
    min_vis = min(nose.visibility, left_eye.visibility, right_eye.visibility)
    eye_dist = abs(left_eye.x - right_eye.x)
    if min_vis < 0.45 or eye_dist < 0.025:
        return False, "Front: NO"
    eye_mid = (left_eye.x + right_eye.x) / 2.0
    centered = abs(nose.x - eye_mid) / eye_dist
    front = centered < 0.38
    return front, f"Front: {'YES' if front else 'NO'}"


def assign_hands(results, swap_handedness=False):
    left_lm = None
    right_lm = None
    if not results.multi_hand_landmarks:
        return left_lm, right_lm
    handed = results.multi_handedness or []
    for idx, lm in enumerate(results.multi_hand_landmarks):
        label = ""
        if idx < len(handed):
            label = handed[idx].classification[0].label
        if swap_handedness and label in ("Left", "Right"):
            label = "Right" if label == "Left" else "Left"
        if label == "Left":
            left_lm = lm
        elif label == "Right":
            right_lm = lm
        elif left_lm is None:
            left_lm = lm
        else:
            right_lm = lm
    return left_lm, right_lm


def pose_wrist_points(pose_landmarks):
    if not pose_landmarks:
        return None, None
    mp_pose = mp.solutions.pose
    lm = pose_landmarks.landmark
    left = lm[mp_pose.PoseLandmark.LEFT_WRIST]
    right = lm[mp_pose.PoseLandmark.RIGHT_WRIST]
    left_pt = (left.x, left.y) if left.visibility > 0.35 else None
    right_pt = (right.x, right.y) if right.visibility > 0.35 else None
    return left_pt, right_pt


def hand_tracking_points(hand_lm, width, height):
    if not hand_lm:
        return None
    pts = []
    for idx in (0, 5, 9, 13, 17):
        lm = hand_lm.landmark[idx]
        pts.append([lm.x * width, lm.y * height])
    return np.array(pts, dtype=np.float32).reshape(-1, 1, 2)


def track_hand_points(prev_gray, gray, points):
    if prev_gray is None or points is None or len(points) < 2:
        return None
    next_pts, status, _ = cv2.calcOpticalFlowPyrLK(
        prev_gray,
        gray,
        points,
        None,
        winSize=(15, 15),
        maxLevel=2,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03),
    )
    if next_pts is None or status is None:
        return None
    valid = next_pts[status.reshape(-1) == 1].reshape(-1, 2)
    if len(valid) < 2:
        return None
    h, w = gray.shape[:2]
    valid[:, 0] = np.clip(valid[:, 0], 0, w - 1)
    valid[:, 1] = np.clip(valid[:, 1], 0, h - 1)
    return valid.reshape(-1, 1, 2).astype(np.float32)


def tracked_center(points, width, height):
    if points is None or len(points) == 0:
        return None
    center = np.median(points.reshape(-1, 2), axis=0)
    return float(center[0] / width), float(center[1] / height)


def selected_label(control_hand, left_label, right_label):
    if control_hand == "left":
        return left_label
    if control_hand == "right":
        return right_label
    return right_label or left_label


def put_frame_badge(img, front, control_state):
    h, w = img.shape[:2]
    state = control_state.get("state", "IDLE")
    command = control_state.get("command", "")
    if state == "EXECUTE":
        color = (255, 215, 90)
        label = "EXECUTE " + (command or "")
    elif state == "READY":
        color = (80, 210, 255)
        label = "READY"
    else:
        color = (70, 235, 120) if front else (70, 90, 235)
        label = "FRONT" if front else "NOT FRONT"
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
    x = max(8, w - tw - 20)
    y = 18
    cv2.rectangle(img, (x - 6, y - 13), (x + tw + 6, y + 7), (0, 0, 0), -1)
    cv2.rectangle(img, (x - 6, y - 13), (x + tw + 6, y + 7), color, 1)
    cv2.putText(img, label, (x, y + 2), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1, cv2.LINE_AA)


def draw_face_points(img, pose_landmarks, w, h, front):
    if not pose_landmarks:
        return
    mp_pose = mp.solutions.pose
    color = (80, 255, 120) if front else (80, 80, 255)
    for idx in [mp_pose.PoseLandmark.NOSE, mp_pose.PoseLandmark.LEFT_EYE, mp_pose.PoseLandmark.RIGHT_EYE]:
        pt = pose_landmarks.landmark[idx]
        if pt.visibility > 0.35:
            cv2.circle(img, (int(pt.x * w), int(pt.y * h)), 5, color, -1)


def process_loop(
    width,
    height,
    fps,
    process_width,
    quality,
    hand_interval,
    pose_interval,
    frame_skip,
    idle_hand_interval,
    idle_pose_interval,
    control_hand,
    swap_handedness,
):
    global latest_jpeg, stats, running
    mp_drawing = mp.solutions.drawing_utils
    mp_pose = mp.solutions.pose
    mp_hands = mp.solutions.hands
    pose_style = mp_drawing.DrawingSpec(color=(80, 230, 120), thickness=2, circle_radius=2)
    pose_conn = mp_drawing.DrawingSpec(color=(80, 160, 80), thickness=2)
    lh_style = mp_drawing.DrawingSpec(color=(255, 180, 70), thickness=2, circle_radius=2)
    rh_style = mp_drawing.DrawingSpec(color=(70, 220, 255), thickness=2, circle_radius=2)
    last_left = None
    last_right = None
    last_pose = None
    front = False
    face_label = "Front: NO"
    left_label = ""
    right_label = ""
    last_left_seen = 0
    last_right_seen = 0
    prev_gray = None
    left_track = None
    right_track = None
    frame_id = 0
    source_frame_id = 0
    hand_wave_left = WaveDetector()
    hand_wave_right = WaveDetector()
    pose_wave_left = WaveDetector()
    pose_wave_right = WaveDetector()
    state_machine = GestureStateMachine()
    control_state = {
        "state": "IDLE",
        "command": "",
        "event": "",
        "ready_remaining": 0.0,
    }

    with mp_pose.Pose(
        static_image_mode=False,
        model_complexity=0,
        smooth_landmarks=True,
        min_detection_confidence=0.42,
        min_tracking_confidence=0.42,
    ) as pose, mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        model_complexity=0,
        min_detection_confidence=0.45,
        min_tracking_confidence=0.45,
    ) as hands:
        smoothed_fps = 0.0
        alpha = 0.12
        last_time = time.time()
        target_process_fps = fps / max(1, frame_skip)
        while running:
            try:
                for jpg in jpg_frames_from_rpicam(width, height, fps):
                    source_frame_id += 1
                    if frame_skip > 1 and source_frame_id % frame_skip != 0:
                        continue
                    frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                    if frame is None:
                        continue
                    now = time.time()
                    inst = min(1.0 / max(now - last_time, 1e-6), target_process_fps)
                    smoothed_fps = inst if smoothed_fps == 0 else (1 - alpha) * smoothed_fps + alpha * inst
                    last_time = now
                    frame_id += 1

                    h, w = frame.shape[:2]
                    process_h = int(h * process_width / w)
                    small = cv2.resize(frame, (process_width, process_h), interpolation=cv2.INTER_AREA)
                    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                    rgb.flags.writeable = False

                    idle_mode = state_machine.mode == "IDLE"
                    hand_every = max(1, idle_hand_interval if idle_mode else hand_interval)
                    pose_every = max(1, idle_pose_interval if idle_mode else pose_interval)
                    wave_detected = False

                    left_track = track_hand_points(prev_gray, gray, left_track)
                    right_track = track_hand_points(prev_gray, gray, right_track)
                    left_center = tracked_center(left_track, process_width, process_h)
                    right_center = tracked_center(right_track, process_width, process_h)
                    if left_center and control_hand in ("left", "both"):
                        wave_detected = hand_wave_left.update_point(left_center[0], left_center[1], now) or wave_detected
                    if right_center and control_hand in ("right", "both"):
                        wave_detected = hand_wave_right.update_point(right_center[0], right_center[1], now) or wave_detected

                    if frame_id % pose_every == 0 or last_pose is None:
                        pose_results = pose.process(rgb)
                        last_pose = pose_results.pose_landmarks
                        front, face_label = face_front_from_pose(last_pose)
                        left_wrist, right_wrist = pose_wrist_points(last_pose)
                        if left_wrist and control_hand in ("left", "both"):
                            wave_detected = pose_wave_left.update_point(left_wrist[0], left_wrist[1], now) or wave_detected
                        if right_wrist and control_hand in ("right", "both"):
                            wave_detected = pose_wave_right.update_point(right_wrist[0], right_wrist[1], now) or wave_detected

                    if frame_id % hand_every == 0:
                        hand_results = hands.process(rgb)
                        new_left, new_right = assign_hands(hand_results, swap_handedness)
                        if new_left:
                            last_left = new_left
                            last_left_seen = frame_id
                            left_track = hand_tracking_points(last_left, process_width, process_h)
                            if control_hand in ("left", "both"):
                                wave_detected = hand_wave_left.update(last_left, now) or wave_detected
                            left_label = classify_gesture(last_left)
                        if new_right:
                            last_right = new_right
                            last_right_seen = frame_id
                            right_track = hand_tracking_points(last_right, process_width, process_h)
                            if control_hand in ("right", "both"):
                                wave_detected = hand_wave_right.update(last_right, now) or wave_detected
                            right_label = classify_gesture(last_right)
                    hand_stale_frames = max(hand_every, hand_interval) * 4
                    if frame_id - last_left_seen > hand_stale_frames:
                        last_left = None
                        left_label = ""
                        left_track = None
                    if frame_id - last_right_seen > hand_stale_frames:
                        last_right = None
                        right_label = ""
                        right_track = None

                    out = frame.copy()
                    pose_landmarks = last_pose
                    if pose_landmarks:
                        mp_drawing.draw_landmarks(out, pose_landmarks, mp_pose.POSE_CONNECTIONS, pose_style, pose_conn)
                    if last_left and control_hand in ("left", "both"):
                        mp_drawing.draw_landmarks(out, last_left, mp_hands.HAND_CONNECTIONS, lh_style, lh_style)
                    if last_right and control_hand in ("right", "both"):
                        mp_drawing.draw_landmarks(out, last_right, mp_hands.HAND_CONNECTIONS, rh_style, rh_style)

                    draw_face_points(out, pose_landmarks, w, h, front)
                    control_label = selected_label(control_hand, left_label, right_label)
                    control_state = state_machine.update(now, front, wave_detected, control_label)
                    put_frame_badge(out, front, control_state)

                    stats = {
                        "fps": round(smoothed_fps, 2),
                        "pose": bool(pose_landmarks),
                        "face_front": front,
                        "left_hand": left_label,
                        "right_hand": right_label,
                        "control_hand": control_hand,
                        "control_label": control_label,
                        "wave": wave_detected,
                        **control_state,
                    }
                    ok, enc = cv2.imencode(".jpg", out, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
                    if ok:
                        with latest_lock:
                            latest_jpeg = enc.tobytes()
                    prev_gray = gray
            except Exception as exc:
                print("process loop error:", repr(exc), flush=True)
                time.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--process-width", type=int, default=320)
    parser.add_argument("--quality", type=int, default=72)
    parser.add_argument("--hand-interval", type=int, default=2)
    parser.add_argument("--pose-interval", type=int, default=1)
    parser.add_argument("--frame-skip", type=int, default=1)
    parser.add_argument("--idle-hand-interval", type=int, default=3)
    parser.add_argument("--idle-pose-interval", type=int, default=5)
    parser.add_argument("--control-hand", choices=("left", "right", "both"), default="right")
    parser.add_argument("--swap-handedness", action="store_true")
    args = parser.parse_args()
    t = threading.Thread(
        target=process_loop,
        args=(
            args.width,
            args.height,
            args.fps,
            args.process_width,
            args.quality,
            args.hand_interval,
            args.pose_interval,
            args.frame_skip,
            args.idle_hand_interval,
            args.idle_pose_interval,
            args.control_hand,
            args.swap_handedness,
        ),
        daemon=True,
    )
    t.start()
    httpd = ThreadedHTTPServer((args.host, args.port), Handler)
    print(f"AirGesture lite monitor running on http://{args.host}:{args.port}/", flush=True)
    try:
        httpd.serve_forever()
    finally:
        global running
        running = False
        httpd.server_close()


if __name__ == "__main__":
    main()
