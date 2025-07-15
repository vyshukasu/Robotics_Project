
# 🗣️ Speech-to-Text Robotic Writing System ✍️

## Overview

This project presents a fully automated, real-time **Speech-to-G-code system** that allows **hands-free control of a CNC-based handwriting plotter**. The system listens to the user's voice, converts speech to text, generates corresponding G-code, and commands a CNC machine to draw the transcribed content as handwriting on paper.

## 🚀 Features

* 🎤 Real-time Speech Recognition (Google API)
* ✍️ G-code generation from spoken text
* 🛠️ Automated control of CNC Plotter (via UGS & PyAutoGUI)
* 🔄 Multithreaded architecture for parallel transcription and plotting
* ⚙️ Auto line wrapping, spacing, and pen control
* 🧠 Modular and extensible design

## 🧩 System Architecture

1. **Audio Input**: Captured via microphone.
2. **Speech-to-Text**: Real-time transcription using Google Speech API.
3. **Text Processing**: Batch-wise segmentation, cleaning, formatting.
4. **G-code Generation**: Character mapping using predefined stroke paths.
5. **Execution**: UGS GUI automated using PyAutoGUI to send G-code to CNC Plotter.
6. **Plotting**: Robotic writing simulated via servo and stepper motors.

## 🖥️ Tech Stack

### Software

| Component               | Description                      |
| ----------------------- | -------------------------------- |
| Python 3.10+            | Core programming language        |
| Google Speech API       | Online speech recognition        |
| PyAutoGUI               | GUI automation                   |
| Universal G-code Sender | G-code streaming interface       |
| GRBL Firmware           | Arduino firmware for CNC control |
| Windows/Linux           | Compatible platforms             |
| NumPy, Math Libraries   | For path/stroke calculations     |

### Hardware

| Component              | Quantity | Description                         |
| ---------------------- | -------- | ----------------------------------- |
| NEMA 17 Stepper Motors | 2        | Drives X and Y axes                 |
| SG90 Servo Motor       | 1        | Controls pen lift (Z-axis)          |
| Arduino Nano           | 1        | Preloaded with GRBL firmware        |
| A4988 Drivers          | 2        | Motor drivers                       |
| CNC Frame, Rods, Belts | Various  | Structure and motion transmission   |
| Writing Area           | -        | \~180mm × 270mm (A4 effective area) |

## 🛠️ Installation and Setup

### Prerequisites

* Python 3.10+
* pip (Python package manager)
* CNC Plotter with GRBL-compatible Arduino
* Internet connection for Google API

### Installation

```bash
pip install pyautogui speechrecognition numpy
```

### Run the System

```bash
python main.py
```


<img width="645" height="514" alt="image" src="https://github.com/user-attachments/assets/64d66d67-7481-46ee-8142-37bbf05658dc" />
<img width="670" height="395" alt="image" src="https://github.com/user-attachments/assets/cc441219-a27b-40d5-a4f0-975394043210" />
<img width="769" height="480" alt="image" src="https://github.com/user-attachments/assets/72a3bfc0-2edb-47dc-8185-20d6637b87c9" />


