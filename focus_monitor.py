
#!/usr/bin/env python3
import argparse
import io
import threading
import time
from http import server
from socketserver import ThreadingMixIn

import cv2
import numpy as np
from picamera2 import Picamera2

latest_jpeg = None
latest_lock = threading.Lock()
running = True

PAGE = b'<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>AirGesture Focus Monitor</title>\n<style>\n  html,body{margin:0;height:100%;background:#101416;color:#edf5f2;font-family:Arial,"Microsoft YaHei",sans-serif;}\n  body{display:grid;grid-template-rows:auto 1fr;}\n  header{padding:12px 18px;background:#182024;display:flex;gap:18px;align-items:center;flex-wrap:wrap;border-bottom:1px solid #2d383d;}\n  h1{font-size:18px;margin:0;color:#fff;}\n  .pill{font-size:13px;color:#c8d6d1;background:#253036;border:1px solid #3a474d;padding:6px 10px;border-radius:4px;}\n  main{display:grid;place-items:center;padding:14px;overflow:hidden;}\n  img{max-width:100%;max-height:calc(100vh - 74px);object-fit:contain;border:1px solid #2f3d42;background:#000;}\n</style>\n</head>\n<body>\n<header>\n  <h1>?????????</h1>\n  <span class="pill">????????????</span>\n  <span class="pill">? 15pin ??????</span>\n  <span class="pill">???????</span>\n</header>\n<main><img src="/stream.mjpg" alt="live camera stream"></main>\n</body>\n</html>'

class Handler(server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)
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
        time.sleep(0.03)
    return None


def draw_overlay(frame, focus_score, fps):
    h, w = frame.shape[:2]
    color = (70, 230, 170)
    dim = (255, 255, 255)
    red = (60, 80, 235)

    # rule-of-thirds grid and central focus box
    for x in (w // 3, 2 * w // 3):
        cv2.line(frame, (x, 0), (x, h), (70, 130, 125), 1)
    for y in (h // 3, 2 * h // 3):
        cv2.line(frame, (0, y), (w, y), (70, 130, 125), 1)
    cv2.line(frame, (w // 2 - 24, h // 2), (w // 2 + 24, h // 2), color, 2)
    cv2.line(frame, (w // 2, h // 2 - 24), (w // 2, h // 2 + 24), color, 2)

    box_w, box_h = int(w * 0.34), int(h * 0.34)
    x1, y1 = (w - box_w) // 2, (h - box_h) // 2
    x2, y2 = x1 + box_w, y1 + box_h
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    # top info plate
    cv2.rectangle(frame, (16, 14), (430, 104), (0, 0, 0), -1)
    cv2.rectangle(frame, (16, 14), (430, 104), (90, 110, 115), 1)
    cv2.putText(frame, f'Focus score: {focus_score:8.1f}', (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.78, color, 2, cv2.LINE_AA)
    cv2.putText(frame, f'FPS: {fps:4.1f}   Move lens until score peaks', (30, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.58, dim, 1, cv2.LINE_AA)

    # simple visual bar
    bar_x, bar_y, bar_w, bar_h = 16, h - 42, 420, 18
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (30, 35, 38), -1)
    normalized = max(0.0, min(1.0, focus_score / 900.0))
    fill = int(bar_w * normalized)
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + fill, bar_y + bar_h), red if normalized > 0.65 else color, -1)
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (95, 115, 120), 1)
    return frame


def capture_loop(width, height, quality):
    global latest_jpeg, running
    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={'size': (width, height), 'format': 'RGB888'},
        controls={'FrameDurationLimits': (33333, 33333)},
    )
    picam2.configure(config)
    picam2.start()
    time.sleep(0.8)

    last = time.time()
    fps = 0.0
    alpha = 0.12
    try:
        while running:
            frame = picam2.capture_array()
            now = time.time()
            inst = 1.0 / max(now - last, 1e-6)
            fps = inst if fps == 0 else (1 - alpha) * fps + alpha * inst
            last = now

            # focus metric on central crop
            h, w = frame.shape[:2]
            crop = frame[h//3:2*h//3, w//3:2*w//3]
            gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
            focus_score = cv2.Laplacian(gray, cv2.CV_64F).var()

            bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            bgr = draw_overlay(bgr, focus_score, fps)
            ok, enc = cv2.imencode('.jpg', bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if ok:
                with latest_lock:
                    latest_jpeg = enc.tobytes()
    finally:
        picam2.stop()


def main():
    parser = argparse.ArgumentParser(description='Web focus monitor for Raspberry Pi CSI camera')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--quality', type=int, default=82)
    args = parser.parse_args()

    t = threading.Thread(target=capture_loop, args=(args.width, args.height, args.quality), daemon=True)
    t.start()
    httpd = ThreadedHTTPServer((args.host, args.port), Handler)
    print(f'Focus monitor running at http://{args.host}:{args.port}/')
    print('Open from your PC: http://192.168.31.97:8080/')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        global running
        running = False
        httpd.server_close()

if __name__ == '__main__':
    main()
