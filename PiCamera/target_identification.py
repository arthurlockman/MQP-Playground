#!/usr/bin/python
# import the necessary packages
import argparse
import cv2
from picamera import PiCamera
from picamera.array import PiRGBArray
from time import sleep
import numpy as np
import time
from multiprocessing import Queue, Process
import sys
import Image
import StringIO
import time
from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer

capture=None

# Inter-process queues
original_queue = Queue(maxsize=3)
final_queue = Queue(maxsize=3)

# Constants
RESOLUTION = 480

class CamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith('.mjpg'):
            self.send_response(200)
            self.send_header('Content-type','multipart/x-mixed-replace; boundary=--jpgboundary')
            self.end_headers()
            while True:
                try:

                    jpg = Image.fromarray(final_queue.get(block=True, timeout=None), 'RGB')

                    tmpFile = StringIO.StringIO()
                    jpg.save(tmpFile,'JPEG')
                    self.wfile.write("--jpgboundary")
                    self.send_header('Content-type','image/jpeg')
                    self.send_header('Content-length',str(tmpFile.len))
                    self.end_headers()
                    jpg.save(self.wfile,'JPEG')
                except KeyboardInterrupt:
                    break
            return
        if self.path.endswith('.html'):
            self.send_response(200)
            self.send_header('Content-type','text/html')
            self.end_headers()
            self.wfile.write('<html><head></head><body>')
            self.wfile.write('<img src="cam.mjpg"/>')
            self.wfile.write('</body></html>')
            return

def identifySquare():
    while True:
        image = original_queue.get(block=True, timeout=None)

        # Cast the image to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Gaussian blur the image
        blur = cv2.GaussianBlur(gray, (7, 7), 0)
            
        # Detect the edges
        edge = cv2.Canny(blur, 50, 150)

        # find contours in the edge map
        (_, cnts, _) = cv2.findContours(edge, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # loop over the contours
        for c in cnts:
            # approximate the contour
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.01 * peri, True)

            # ensure that the approximated contour is "roughly" rectangular
            if len(approx) >= 4 and len(approx) <= 6:
                # compute the bounding box of the approximated contour and
                # use the bounding box to compute the aspect ratio
                (x, y, w, h) = cv2.boundingRect(approx)
                aspectRatio = w / float(h)

                # compute the solidity of the original contour
                area = cv2.contourArea(c)
                hullArea = cv2.contourArea(cv2.convexHull(c))
                solidity = area / float(hullArea)

                # compute whether or not the width and height, solidity, and
                # aspect ratio of the contour falls within appropriate bounds
                keepDims = w > 30 and h > 30
                keepSolidity = solidity > 0.8
                keepAspectRatio= aspectRatio >= 0.8 and aspectRatio <= 1.2

                # ensure that the contour passes all our tests
                if keepDims and keepSolidity and keepAspectRatio:
                    # draw an outline around the target and update the status
                    cv2.drawContours(image, [approx], -1, (255, 0, 0), 4)

                    try:
                        # compute the center of the contour region and draw the
                        # crosshairs
                        M = cv2.moments(approx)
                        (cX, cY) = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
                        (startX, endX) = (int(cX - (w * 0.15)), int(cX + (w * 0.15)))
                        (startY, endY) = (int(cY - (h * 0.15)), int(cY + (h * 0.15)))
                        cv2.line(image, (startX, cY), (endX, cY), (0, 0, 255), 3)
                        cv2.line(image, (cX, startY), (cX, endY), (0, 0, 255), 3)
                    except Exception:
                        print "Divide by zero"

        final_queue.put(image, block=True, timeout=None) 

def putImage():
    global RESOLUTION

    # Set up the PiCamera
    camera = PiCamera()
    camera.framerate = 30

    if RESOLUTION == 1080:
        camera.resolution = (1920, 1080)
        rawCapture = PiRGBArray(camera, size=(1920, 1080))
    elif RESOLUTION == 720:
        camera.resolution = (1280, 720)
        rawCapture = PiRGBArray(camera, size=(1280, 720))
    elif RESOLUTION == 480:
        camera.resolution = (640, 480)
        rawCapture = PiRGBArray(camera, size=(640, 480))
    else:
        print 'Wrong Resolution'
        exit()

    # allow the camera to warmup
    sleep(0.1)

    # capture frames from the camera
    for frame in camera.capture_continuous(rawCapture, format="bgr", use_video_port=True):
        frame = frame.array

        # Add the next image to process. If it blocks and times out, continue without adding a frame
        try:
            original_queue.put(frame, block=False)
        except:
            pass
        # clear the stream in preparation for the next frame
        rawCapture.truncate(0)

    # cleanup the camera and close any open windows
    camera.release()
    cv2.destroyAllWindows()
    exit()


def displayImage():
    last_time = 0
    while True:
        # Get the final image to be displayed, if there is none, continue the loop
        final_image = final_queue.get(block=True, timeout=None)

        # show the frame and record if a key is pressed
        cv2.imshow("Frame", final_image)
        key = cv2.waitKey(1) & 0xFF # DONT DELETE NEED TO SHOW IMAGE

def main():
    global start_time, capture, img

    # Start all the processes
    P1 = Process(target=identifySquare)
    P2 = Process(target=identifySquare)
    P3 = Process(target=identifySquare)
    # disp = Process(target=displayImage)
    put = Process(target=putImage)

    P1.start()
    P2.start()
    P3.start()
    # disp.start()
    put.start()

    try:
        server = HTTPServer(('',8080),CamHandler)
        print "server started"
        server.serve_forever()
    except KeyboardInterrupt:
        capture.release()
        server.socket.close()

    P1.join()
    P2.join()
    P3.join()
    # disp.join()
    put.join()



if __name__ == '__main__':
    main()
