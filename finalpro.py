import sys
import time
import numpy as np
import speech_recognition as sr
import queue
import threading
import os
import subprocess
from datetime import datetime
import pyautogui
import math

class SpeechToGCodeProcessor:
     def __init__(self, ugs_path=None):
        self.text_queue = queue.Queue()
        self.is_running = True
        self.ugs_path = ugs_path or self._find_ugs_path()
        self.batch_text = ""
        self.batch_threshold = 20
        self.processing_lock = threading.Lock()  # Lock for thread safety
        # Default starting positions and spacing
        self.start_x = 10
        self.start_y = 10
        self.char_width = 5
        self.char_height = 10
        self.line_spacing = 15
        self.current_x = self.start_x
        self.current_y = self.start_y
        self.max_line_width = 190# For A4 paper (210mm minus margins)
        self.travel_speed = 500    # Fast movement when not drawing
        self.drawing_speed = 500    # Slower movement when drawing
        self.pen_lift_speed = 100   # Slower movement when lifting or lowering pen
        self.pen_z_up = 5.0         # Z position when pen is up
        self.pen_z_down = 0.0
        self.is_connected = False  # Track connection state
        self.position_initialized = False  # Flag to track if position has been initialized

     def _find_ugs_path(self):
        possible_paths = [
            r"C:\\Program Files\\Universal-G-Code-Sender\\UniversalGcodeSender.jar",
            r"C:\\Program Files (x86)\\Universal-G-Code-Sender\\UniversalGcodeSender.jar",
            "/usr/local/bin/UniversalGcodeSender.jar",
            "/opt/UniversalGcodeSender/UniversalGcodeSender.jar"
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None

     def real_time_transcription(self):
        recognizer = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=2)
                print("Listening...")
                while self.is_running:
                    try:
                        audio = recognizer.listen(source, timeout=5)
                        text = recognizer.recognize_google(audio).strip()
                        if text:
                            self.batch_text += " " + text
                            print(f"Recognized: {text}")
                            if len(self.batch_text.split()) >= self.batch_threshold:
                                self.text_queue.put(self.batch_text.strip())
                                self.batch_text = ""
                    except sr.WaitTimeoutError:
                        if self.batch_text:
                            self.text_queue.put(self.batch_text.strip())
                            self.batch_text = ""
                    except sr.UnknownValueError:
                        print("Could not understand audio")
                    except sr.RequestError as e:
                        print(f"Speech recognition error: {e}")
        except Exception as e:
            print(f"Error in transcription: {e}")
            self.is_running = False


     def calculate_plotting_time(self, gcode):
        """
        Calculate approximate time needed for the plotter to complete the GCode
        """
        total_time = 0
        current_x, current_y = 0, 0
        is_pen_down = False
        
        for line in gcode.split('\n'):
            line = line.strip()
            if not line or line.startswith(';'):
                continue
                
            # Pen up/down operations
            if "M03" in line:  # Pen up
                total_time += 0.5  # Time for pen to move up in seconds
                is_pen_down = False
            elif "M05" in line:  # Pen down
                total_time += 0.5  # Time for pen to move down in seconds
                is_pen_down = True
                
            # Movement operations
            if "G0" in line or "G1" in line:
                parts = line.split()
                new_x, new_y = current_x, current_y
                speed = self.travel_speed  # Default to travel speed
                
                for part in parts:
                    if part.startswith('X'):
                        new_x = float(part[1:])
                    elif part.startswith('Y'):
                        new_y = float(part[1:])
                    elif part.startswith('F'):
                        speed = float(part[1:])
                
                # Calculate distance
                distance = math.sqrt((new_x - current_x)**2 + (new_y - current_y)**2)
                
                # Calculate time for this movement (distance / speed in mm per minute)
                if distance > 0:
                    # Convert speed from mm/min to mm/sec
                    speed_mm_per_sec = speed / 60
                    move_time = distance / speed_mm_per_sec
                    total_time += move_time
                
                current_x, current_y = new_x, new_y
        
        # Add safety buffer (20% extra time)
        total_time *= 1.2
        return total_time

     def text_to_gcode(self, text, char_width=None, char_height=None, line_spacing=None):
        """
        Convert text to G-code for CNC machines using M03/M05 for pen control
        """
        # Use provided values or default class values
        char_width = char_width or self.char_width
        char_height = char_height or self.char_height
        line_spacing = line_spacing or self.line_spacing
        
        gcode = []
        
        # Define machine parameters
        travel_speed = 500   # Fast movement when not drawing
        drawing_speed = 500   # Slower movement when drawing
        
        # Initial setup
        gcode.append("; G-code generated from text")
        gcode.append("G21 ; Set units to millimeters")
        gcode.append("G90 ; Set absolute positioning")
        
        # Standard format M03/M05 commands
        pen_up_cmd = "M03 S90"  # Standard spindle on (pen up in this case)
        pen_down_cmd = "M05"    # Standard spindle off (pen down in this case)
        
        # Initial pen up and move to start - only if this is the first batch
        if not hasattr(self, 'position_initialized') or not self.position_initialized:
            gcode.append(f"{pen_up_cmd} ; Pen up")
            gcode.append(f"G0 X{self.current_x} Y{self.current_y} F{travel_speed} ; Move to starting position")
            self.position_initialized = True
        else:
            # For subsequent batches, we're already at the correct position
            gcode.append(f"{pen_up_cmd} ; Pen up")
            gcode.append(f"G0 X{self.current_x} Y{self.current_y} F{travel_speed} ; Continue from previous position")
        
        # Comprehensive font dictionary for all uppercase letters, numbers, and common punctuation
        font = {
            'A': [(0, 0, False), (0, char_height, True), (char_width, char_height, True), 
                 (char_width, 0, True), (char_width, char_height/2, False), (0, char_height/2, True)],
            
            'B': [(0, 0, False), (0, char_height, True), (char_width*0.8, char_height, True), 
                 (char_width, char_height*0.8, True), (char_width, char_height*0.6, True),
                 (char_width*0.8, char_height*0.5, True), (0, char_height*0.5, True), (char_width*0.8, char_height*0.5, False),
                 (char_width, char_height*0.4, True), (char_width, char_height*0.2, True),
                 (char_width*0.8, 0, True), (0, 0, True)],
            
            'C': [(char_width, char_height*0.8, False), (char_width*0.8, char_height, True),
                 (char_width*0.2, char_height, True), (0, char_height*0.8, True),
                 (0, char_height*0.2, True), (char_width*0.2, 0, True),
                 (char_width*0.8, 0, True), (char_width, char_height*0.2, True)],
            
            'D': [(0, 0, False), (0, char_height, True), (char_width*0.8, char_height, True), 
                 (char_width, char_height*0.8, True), (char_width, char_height*0.2, True),
                 (char_width*0.8, 0, True), (0, 0, True)],
            
            'E': [(char_width, 0, False), (0, 0, True), (0, char_height, True), 
                 (char_width, char_height, True), (0, char_height, False),
                 (0, char_height/2, True), (char_width*0.8, char_height/2, True)],
            
            'F': [(0, 0, False), (0, char_height, True), (char_width, char_height, True),
                 (0, char_height, False), (0, char_height/2, True), (char_width*0.8, char_height/2, True)],
            
            'G': [(char_width, char_height*0.8, False), (char_width*0.8, char_height, True),
                 (char_width*0.2, char_height, True), (0, char_height*0.8, True),
                 (0, char_height*0.2, True), (char_width*0.2, 0, True),
                 (char_width*0.8, 0, True), (char_width, char_height*0.2, True),
                 (char_width, char_height*0.5, True), (char_width*0.5, char_height*0.5, True)],
            
            'H': [(0, 0, False), (0, char_height, True), (0, char_height/2, False),
                 (char_width, char_height/2, True), (char_width, char_height, False),
                 (char_width, 0, True)],
            
            'I': [(char_width*0.2, 0, False), (char_width*0.8, 0, True),
                 (char_width/2, 0, False), (char_width/2, char_height, True),
                 (char_width*0.2, char_height, False), (char_width*0.8, char_height, True)],
            
            'J': [(char_width*0.8, char_height, False), (char_width*0.8, char_height*0.2, True),
                 (char_width*0.6, 0, True), (char_width*0.2, 0, True),
                 (0, char_height*0.2, True)],
            
            'K': [(0, 0, False), (0, char_height, True), (0, char_height/2, False),
                 (char_width, char_height, True), (0, char_height/2, False),
                 (char_width, 0, True)],
            
            'L': [(0, char_height, False), (0, 0, True), (char_width, 0, True)],
            
            'M': [(0, 0, False), (0, char_height, True), (char_width/2, char_height*0.6, True),
                 (char_width, char_height, True), (char_width, 0, True)],
            
            'N': [(0, 0, False), (0, char_height, True), (char_width, 0, True),
                 (char_width, char_height, True)],
            
            'O': [(0, char_height*0.2, False), (0, char_height*0.8, True),
                 (char_width*0.2, char_height, True), (char_width*0.8, char_height, True),
                 (char_width, char_height*0.8, True), (char_width, char_height*0.2, True),
                 (char_width*0.8, 0, True), (char_width*0.2, 0, True),
                 (0, char_height*0.2, True)],
            
            'P': [(0, 0, False), (0, char_height, True), (char_width*0.8, char_height, True),
                 (char_width, char_height*0.8, True), (char_width, char_height*0.6, True),
                 (char_width*0.8, char_height*0.5, True), (0, char_height*0.5, True)],
            
            'Q': [(0, char_height*0.2, False), (0, char_height*0.8, True),
                 (char_width*0.2, char_height, True), (char_width*0.8, char_height, True),
                 (char_width, char_height*0.8, True), (char_width, char_height*0.2, True),
                 (char_width*0.8, 0, True), (char_width*0.2, 0, True),
                 (0, char_height*0.2, True), (char_width*0.5, char_height*0.3, False),
                 (char_width, 0, True)],
            
            'R': [(0, 0, False), (0, char_height, True), (char_width*0.8, char_height, True),
                 (char_width, char_height*0.8, True), (char_width, char_height*0.6, True),
                 (char_width*0.8, char_height*0.5, True), (0, char_height*0.5, True),
                 (char_width*0.4, char_height*0.5, False), (char_width, 0, True)],
            
            'S': [(char_width, char_height*0.8, False), (char_width*0.8, char_height, True),
                 (char_width*0.2, char_height, True), (0, char_height*0.8, True),
                 (0, char_height*0.6, True), (char_width*0.2, char_height*0.5, True),
                 (char_width*0.8, char_height*0.5, True), (char_width, char_height*0.4, True),
                 (char_width, char_height*0.2, True), (char_width*0.8, 0, True),
                 (char_width*0.2, 0, True), (0, char_height*0.2, True)],
            
            'T': [(0, char_height, False), (char_width, char_height, True),
                 (char_width/2, char_height, False), (char_width/2, 0, True)],
            
            'U': [(0, char_height, False), (0, char_height*0.2, True),
                 (char_width*0.2, 0, True), (char_width*0.8, 0, True),
                 (char_width, char_height*0.2, True), (char_width, char_height, True)],
            
            'V': [(0, char_height, False), (char_width/2, 0, True), (char_width, char_height, True)],
            
            'W': [(0, char_height, False), (char_width*0.2, 0, True),
                 (char_width*0.5, char_height*0.4, True), (char_width*0.8, 0, True),
                 (char_width, char_height, True)],
            
            'X': [(0, char_height, False), (char_width, 0, True),
                 (char_width/2, char_height/2, False), (0, 0, True),
                 (char_width, char_height, True)],
            
            'Y': [(0, char_height, False), (char_width/2, char_height/2, True),
                 (char_width, char_height, True), (char_width/2, char_height/2, False),
                 (char_width/2, 0, True)],
            
            'Z': [(0, char_height, False), (char_width, char_height, True),
                 (0, 0, True), (char_width, 0, True)],

            # Add these lowercase letters to your font dictionary
            'a': [(char_width, char_height*0.3, False), (char_width, 0, True),
                  (char_width*0.2, 0, True), (0, char_height*0.2, True),
                  (0, char_height*0.5, True), (char_width*0.2, char_height*0.7, True),
                  (char_width, char_height*0.7, True)],
            
            'b': [(0, 0, False), (0, char_height, True), 
                  (0, char_height*0.4, False), (char_width*0.8, char_height*0.4, True),
                  (char_width, char_height*0.3, True), (char_width, char_height*0.1, True),
                  (char_width*0.8, 0, True), (0, 0, True)],
            
            'c': [(char_width, char_height*0.6, False), (char_width*0.8, char_height*0.7, True),
                  (char_width*0.2, char_height*0.7, True), (0, char_height*0.5, True),
                  (0, char_height*0.2, True), (char_width*0.2, 0, True),
                  (char_width*0.8, 0, True), (char_width, char_height*0.1, True)],
            
            'd': [(char_width, 0, False), (char_width, char_height, True),
                  (char_width, char_height*0.4, False), (char_width*0.2, char_height*0.4, True),
                  (0, char_height*0.3, True), (0, char_height*0.1, True),
                  (char_width*0.2, 0, True), (char_width, 0, True)],
            
            'e': [(0, char_height*0.3, False), (char_width, char_height*0.3, True),
                  (char_width, char_height*0.5, True), (char_width*0.2, char_height*0.7, True),
                  (0, char_height*0.5, True), (0, char_height*0.2, True),
                  (char_width*0.2, 0, True), (char_width*0.8, 0, True)],
            
            'f': [(char_width, char_height, False), (char_width*0.5, char_height, True),
                  (char_width*0.3, char_height*0.9, True), (char_width*0.3, 0, True),
                  (char_width*0.3, char_height*0.5, False), (0, char_height*0.5, True)],
            
            'g': [(char_width, char_height*0.7, False), (char_width, -char_height*0.2, True),
                  (char_width*0.7, -char_height*0.3, True), (char_width*0.2, -char_height*0.3, True),
                  (0, -char_height*0.2, True), (char_width, -char_height*0.2, False),
                  (char_width, char_height*0.7, True), (char_width*0.2, char_height*0.7, True),
                  (0, char_height*0.5, True), (0, char_height*0.2, True),
                  (char_width*0.2, 0, True), (char_width, 0, True)],
            
            'h': [(0, 0, False), (0, char_height, True),
                  (0, char_height*0.5, False), (char_width*0.7, char_height*0.5, True),
                  (char_width, char_height*0.3, True), (char_width, 0, True)],
            
            'i': [(char_width*0.5, char_height*0.7, False), (char_width*0.5, 0, True),
                  (char_width*0.5, char_height*0.9, False), (char_width*0.5, char_height, True)],
            
            'j': [(char_width*0.7, char_height*0.7, False), (char_width*0.7, -char_height*0.2, True),
                  (char_width*0.5, -char_height*0.3, True), (char_width*0.2, -char_height*0.3, True),
                  (0, -char_height*0.2, True), (char_width*0.7, char_height*0.9, False),
                  (char_width*0.7, char_height, True)],
            
            'k': [(0, 0, False), (0, char_height, True),
                  (0, char_height*0.3, False), (char_width, char_height*0.7, True),
                  (0, char_height*0.3, False), (char_width, 0, True)],
            
            'l': [(char_width*0.3, char_height, False), (char_width*0.3, 0, True),
                  (char_width*0.7, 0, True)],
            
            'm': [(0, 0, False), (0, char_height*0.7, True),
                  (char_width*0.3, char_height*0.7, True), (char_width*0.5, char_height*0.5, True),
                  (char_width*0.5, 0, True), (char_width*0.5, char_height*0.5, False),
                  (char_width*0.7, char_height*0.7, True), (char_width, char_height*0.5, True),
                  (char_width, 0, True)],
            
            'n': [(0, 0, False), (0, char_height*0.7, True),
                  (char_width*0.7, char_height*0.7, True), (char_width, char_height*0.5, True),
                  (char_width, 0, True)],
            
            'o': [(0, char_height*0.2, False), (0, char_height*0.5, True),
                  (char_width*0.2, char_height*0.7, True), (char_width*0.8, char_height*0.7, True),
                  (char_width, char_height*0.5, True), (char_width, char_height*0.2, True),
                  (char_width*0.8, 0, True), (char_width*0.2, 0, True),
                  (0, char_height*0.2, True)],
            
            'p': [(0, -char_height*0.3, False), (0, char_height*0.7, True),
                  (char_width*0.8, char_height*0.7, True), (char_width, char_height*0.5, True),
                  (char_width, char_height*0.2, True), (char_width*0.8, 0, True),
                  (0, 0, True)],
            
            'q': [(char_width, -char_height*0.3, False), (char_width, char_height*0.7, True),
                  (char_width*0.2, char_height*0.7, True), (0, char_height*0.5, True),
                  (0, char_height*0.2, True), (char_width*0.2, 0, True),
                  (char_width, 0, True)],
            
            'r': [(0, 0, False), (0, char_height*0.7, True),
                  (char_width*0.2, char_height*0.7, True), (char_width*0.8, char_height*0.5, True),
                  (char_width, char_height*0.7, True)],
            
            's': [(char_width, char_height*0.6, False), (char_width*0.8, char_height*0.7, True),
                  (char_width*0.2, char_height*0.7, True), (0, char_height*0.6, True),
                  (char_width*0.2, char_height*0.4, True), (char_width*0.8, char_height*0.3, True),
                  (char_width, char_height*0.1, True), (char_width*0.8, 0, True),
                  (char_width*0.2, 0, True), (0, char_height*0.1, True)],
            
            't': [(char_width*0.3, char_height, False), (char_width*0.3, char_height*0.1, True),
                  (char_width*0.5, 0, True), (char_width*0.8, 0, True),
                  (char_width*0.3, char_height*0.7, False), (0, char_height*0.7, True),
                  (char_width*0.7, char_height*0.7, True)],
            
            'u': [(0, char_height*0.7, False), (0, char_height*0.1, True),
                  (char_width*0.2, 0, True), (char_width*0.8, 0, True),
                  (char_width, char_height*0.1, True), (char_width, char_height*0.7, True)],
            
            'v': [(0, char_height*0.7, False), (char_width*0.5, 0, True),
                  (char_width, char_height*0.7, True)],
            
            'w': [(0, char_height*0.7, False), (char_width*0.2, 0, True),
                  (char_width*0.5, char_height*0.4, True), (char_width*0.8, 0, True),
                  (char_width, char_height*0.7, True)],
            
            'x': [(0, char_height*0.7, False), (char_width, 0, True),
                  (char_width*0.5, char_height*0.35, False), (0, 0, True),
                  (char_width, char_height*0.7, True)],
            
            'y': [(0, char_height*0.7, False), (0, char_height*0.3, True),
                  (char_width*0.5, 0, True), (char_width, char_height*0.3, True),
                  (char_width, char_height*0.7, True), (char_width, -char_height*0.2, True),
                  (char_width*0.8, -char_height*0.3, True), (char_width*0.2, -char_height*0.3, True),
                  (0, -char_height*0.2, True)],
            
            'z': [(0, char_height*0.7, False), (char_width, char_height*0.7, True),
                  (0, 0, True), (char_width, 0, True)],
            
            '0': [(0, char_height*0.2, False), (0, char_height*0.8, True),
                 (char_width*0.2, char_height, True), (char_width*0.8, char_height, True),
                 (char_width, char_height*0.8, True), (char_width, char_height*0.2, True),
                 (char_width*0.8, 0, True), (char_width*0.2, 0, True),
                 (0, char_height*0.2, True)],
            
            '1': [(char_width*0.2, char_height*0.8, False), (char_width*0.5, char_height, True),
                 (char_width*0.5, 0, True)],
            
            '2': [(0, char_height*0.8, False), (char_width*0.2, char_height, True),
                 (char_width*0.8, char_height, True), (char_width, char_height*0.8, True),
                 (char_width, char_height*0.6, True), (0, 0, True),
                 (char_width, 0, True)],
            
            '3': [(0, char_height*0.8, False), (char_width*0.2, char_height, True),
                 (char_width*0.8, char_height, True), (char_width, char_height*0.8, True),
                 (char_width, char_height*0.6, True), (char_width*0.2, char_height*0.5, True),
                 (char_width, char_height*0.4, True), (char_width, char_height*0.2, True),
                 (char_width*0.8, 0, True), (char_width*0.2, 0, True),
                 (0, char_height*0.2, True)],
            
            '4': [(char_width*0.8, 0, False), (char_width*0.8, char_height, True),
                 (0, char_height*0.4, True), (char_width, char_height*0.4, True)],
            
            '5': [(char_width, char_height, False), (0, char_height, True),
                 (0, char_height*0.5, True), (char_width*0.8, char_height*0.5, True),
                 (char_width, char_height*0.4, True), (char_width, char_height*0.1, True),
                 (char_width*0.2, 0, True), (0, char_height*0.1, True)],
            
            '6': [(char_width, char_height*0.8, False), (char_width*0.8, char_height, True),
                 (char_width*0.2, char_height, True), (0, char_height*0.8, True),
                 (0, char_height*0.2, True), (char_width*0.2, 0, True),
                 (char_width*0.8, 0, True), (char_width, char_height*0.2, True),
                 (char_width, char_height*0.4, True), (char_width*0.8, char_height*0.5, True),
                 (0, char_height*0.5, True)],
            
            '7': [(0, char_height, False), (char_width, char_height, True),
                 (char_width*0.5, 0, True)],
            
            '8': [(char_width*0.2, char_height*0.5, False), (0, char_height*0.7, True),
                 (0, char_height*0.8, True), (char_width*0.2, char_height, True),
                 (char_width*0.8, char_height, True), (char_width, char_height*0.8, True),
                 (char_width, char_height*0.7, True), (char_width*0.8, char_height*0.5, True),
                 (char_width*0.2, char_height*0.5, True), (0, char_height*0.3, True),
                 (0, char_height*0.2, True), (char_width*0.2, 0, True),
                 (char_width*0.8, 0, True), (char_width, char_height*0.2, True),
                 (char_width, char_height*0.3, True), (char_width*0.8, char_height*0.5, True)],
            
            '9': [(0, char_height*0.2, False), (char_width*0.2, 0, True),
                 (char_width*0.8, 0, True), (char_width, char_height*0.2, True),
                 (char_width, char_height*0.8, True), (char_width*0.8, char_height, True),
                 (char_width*0.2, char_height, True), (0, char_height*0.8, True),
                 (0, char_height*0.6, True), (char_width*0.2, char_height*0.5, True),
                 (char_width, char_height*0.5, True)],
            
            '.': [(char_width*0.4, 0, False), (char_width*0.6, 0, True),
                 (char_width*0.6, char_height*0.2, True), (char_width*0.4, char_height*0.2, True),
                 (char_width*0.4, 0, True)],
            
            ',': [(char_width*0.6, 0, False), (char_width*0.4, -char_height*0.2, True),
                 (char_width*0.4, 0, True), (char_width*0.6, 0, True),
                 (char_width*0.6, char_height*0.2, True), (char_width*0.4, char_height*0.2, True),
                 (char_width*0.4, 0, True)],
            
            '!': [(char_width*0.5, char_height, False), (char_width*0.5, char_height*0.2, True),
                 (char_width*0.5, 0, False), (char_width*0.3, 0, True),
                 (char_width*0.3, char_height*0.1, True), (char_width*0.7, char_height*0.1, True),
                 (char_width*0.7, 0, True), (char_width*0.5, 0, True)],
            
            '?': [(0, char_height*0.8, False), (char_width*0.2, char_height, True),
                 (char_width*0.8, char_height, True), (char_width, char_height*0.8, True),
                 (char_width, char_height*0.6, True), (char_width*0.5, char_height*0.4, True),
                 (char_width*0.5, char_height*0.2, True), (char_width*0.5, 0, False),
                 (char_width*0.3, 0, True), (char_width*0.3, char_height*0.1, True),
                 (char_width*0.7, char_height*0.1, True), (char_width*0.7, 0, True),
                 (char_width*0.5, 0, True)],
            
            ' ': [(0, 0, False)]  # Space
        }
        
        # Process text
        for line in text.split('\n'):
            for char in line:  # Convert to uppercase for simplicity
                if char not in font:
                    char = ' '  # Default to space for undefined characters
                
                # Check if we need to start a new line (wrap)
                if self.current_x + char_width * 1.2 > self.max_line_width:
                    self.current_x = self.start_x
                    self.current_y -= line_spacing
                
                # Get character path
                path = font[char]
                
                # Draw character
                for point in path:
                    x_offset, y_offset, pen_down = point
                    x = self.current_x + x_offset
                    y = self.current_y + y_offset
                    
                    if pen_down:
                        # Put pen down and draw
                        gcode.append(f"{pen_down_cmd} ; Pen down")
                        gcode.append(f"G1 X{x} Y{y} F{drawing_speed} ; Draw line")
                    else:
                        # Lift pen and move
                        gcode.append(f"{pen_up_cmd} ; Pen up")
                        gcode.append(f"G0 X{x} Y{y} F{travel_speed} ; Move without drawing")
                
                # Move to next character position
                self.current_x += char_width * 1.2
        
        # Important: Don't reset position at the end of lines anymore
        # Remove these lines:
        # self.current_x = self.start_x
        # self.current_y -= line_spacing
        
        # End G-code - don't return to origin
        gcode.append(f"{pen_up_cmd} ; Pen up")
        # Removed: gcode.append(f"G0 X0 Y0 F{travel_speed} ; Return to origin")
        gcode.append("M2 ; End program")
        
        return '\n'.join(gcode)

     def send_to_ugs(self, gcode_file):
         if not self.ugs_path:
             print("UGS not found.")
             return False
         
         try:
             # Get absolute path to G-code file
             gcode_absolute_path = os.path.abspath(gcode_file)
             if not os.path.exists(gcode_absolute_path):
                 print(f"Error: G-code file {gcode_absolute_path} not found")
                 return False
             
             # Launch UGS with the G-code file
             if self.ugs_path.endswith('.jar'):
                 subprocess.Popen(["java", "-jar", self.ugs_path, "--open", gcode_absolute_path])
             else:
                 subprocess.Popen([self.ugs_path, "--open", gcode_absolute_path, "--console", "new"])
                 
             print(f"Sent G-code to UGS: {gcode_absolute_path}")
             
             # Wait for UGS to start
             time.sleep(60)
             
             return True
         except Exception as e:
             print(f"Error sending to UGS: {e}")
             return False
     
     def connect_to_machine(self):
        """Connect to the machine if not already connected"""
        try:
            # Find and click connect button
            print("Looking for connect button...")
            connect_button_path = "connect_button.png"
            connect_location = pyautogui.locateOnScreen(connect_button_path, confidence=0.6)
            if connect_location:
                center = pyautogui.center(connect_location)
                pyautogui.click(center)
                print("Clicked connect button!")
                
                # Wait for connection to establish
                time.sleep(10)
                return True
            else:
                print("Connect button not found, might already be connected")
                return True  # Assume connected if button not found
                
        except Exception as e:
            print(f"Error clicking connect button: {e}")
        return False

     def run_gcode_file(self):
        """Start running the loaded G-code file"""
        try:
            # Find and click start button
            print("Looking for start button...")
            start_button_path = "start_button.png"
            start_location = pyautogui.locateOnScreen(start_button_path, confidence=0.6)
            if start_location:
                center = pyautogui.center(start_location)
                pyautogui.click(center)
                print("Clicked start button!")
                return True
            else:
                print("Start button not found")
                
        except Exception as e:
            print(f"Error clicking start button: {e}")
        
        return False
             
         

     def process_queue(self):
        gcode_files_queue = []  # Queue to store generated G-code files
        connected = False  # Track connection state
        
        while self.is_running:
            # Process new speech input
            if not self.text_queue.empty():
                with self.processing_lock:  # Ensure only one batch is processed at a time
                    text = self.text_queue.get().strip()
                    if text:
                        print(f"Processing: {text}")
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        gcode_file = f"output_{timestamp}.gcode"
                        gcode = self.text_to_gcode(text)
                        
                        # Write to file
                        with open(gcode_file, "w") as f:
                            f.write(gcode)
                        
                        print(f"G-code saved to {gcode_file}")
    
                        # Calculate estimated plotting time
                        plotting_time = self.calculate_plotting_time(gcode)
                        print(f"Estimated plotting time: {plotting_time:.2f} seconds")
                        
                        # Add the file and its plotting time to the queue
                        gcode_files_queue.append((gcode_file, plotting_time))
            
            # Process the next file in the queue if not currently plotting
            if gcode_files_queue and not hasattr(self, 'plotting_in_progress'):
                self.plotting_in_progress = True
                current_file, plotting_time = gcode_files_queue.pop(0)
                
                try:
                    print(f"Sending file to UGS: {current_file}")
                    success = self.send_to_ugs(current_file)
                    
                    if success:
                        # Connect only if not already connected
                        if not connected:
                            connected = self.connect_to_machine()
                        
                        # Always run the file
                        if self.run_gcode_file():
                            print(f"Waiting {plotting_time:.2f} seconds for plotting to complete...")
                            time.sleep(plotting_time)
                            print("Plotting complete. Ready for next file.")
                        else:
                            print("Failed to start plotting.")
                            # If running failed, we might need to reconnect next time
                            connected = False
                    else:
                        print("Failed to send file to UGS.")
                finally:
                    # Clear the plotting flag regardless of success
                    delattr(self, 'plotting_in_progress')
                    
            time.sleep(0.1)
    
    
     def run(self):
        try:
            # Start transcription thread
            threading.Thread(target=self.real_time_transcription, daemon=True).start()
            # Start processing thread
            threading.Thread(target=self.process_queue, daemon=True).start()
            
            print("Speech-to-GCode converter running!")
            print("Press Ctrl+C to stop.")
            
            while self.is_running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.is_running = False
            if self.batch_text:  # Process any remaining text
                self.text_queue.put(self.batch_text.strip())
            print("Shutting down...")
            time.sleep(2)  # Give time for remaining processing

if __name__ == "__main__":
    # Try to find UGS path or use the one provided
    ugs_path = None
    if len(sys.argv) > 1:
        ugs_path = sys.argv[1]
    
    processor = SpeechToGCodeProcessor("C:\\Users\\vyshu\\Downloads\\ugs\\ugsplatform-win\\bin\\ugsplatform64.exe")
    processor.run()