# Vantage Core

`vantage_core.py` is the real-time loop for the Vantage assistive wearable. It runs on a
Raspberry Pi Compute Module 5 (Waveshare carrier) with:

| Part | Interface |
|---|---|
| Raspberry Pi AI Camera (Sony IMX500) | CSI port **CAM0** |
| Benewake TFmini Plus LiDAR | UART, `/dev/serial0`, 115200 baud |
| Shokz bone-conduction headset | Bluetooth (A2DP via PipeWire) |

## What it does

```
 IMX500 (on-sensor MobileNet-SSD) ─┐
                                   ├─► tracker ─► fusion ─► announcer ─► espeak-ng ─► PipeWire ─► Shokz (BT)
 TFmini Plus (bg thread, 100 Hz) ──┘                │
                                                     └─► preview window / browser stream / terminal dashboard
```

1. **Camera:** the IMX500 runs the detector on the sensor itself, so the CPU only reads
   the results (boxes, labels, scores). Detections go through a small IoU tracker. An
   object has to show up in at least 2 frames before the system trusts it, which keeps the
   speech from flickering.
2. **LiDAR:** a background thread reads the 9-byte frames (`0x59 0x59 …`) and checks
   each checksum. If the stream gets out of step it finds the next frame header. It drops
   readings with a weak signal (strength < 100) or a saturated one (65535), then applies a
   median filter. It also estimates closing speed and **time-to-contact**. If the UART
   goes silent, it scans the other serial ports and reconnects.
3. **Fusion:** the TFmini beam (3.6°) is projected into the camera image. This corrects
   for parallax if you set the LiDAR's mounting offset. The detected box that covers the
   beam is the object the distance belongs to.
4. **Speech** (priority queue, cached TTS):
   * **< 50 cm:** a two-tone beep, then **"Person too close, 40 centimeters"**. It
     interrupts anything else that is playing, repeats every 2.5 s while the object stays
     that close, and repeats right away if the object changes.
   * **< 100 cm, or approaching fast:** "Chair ahead, 80 centimeters, approaching fast".
   * Something close that wasn't recognized: "Obstacle too close, 35 centimeters".
   * The LiDAR can't measure (closer than about 10 cm, or a black or glass surface), but
     a box fills the frame: "Person very close".
   * `--describe` mode: "Chair on your left", "Person ahead", …
   * Press `s` to have the whole scene read out.
   * Messages are dropped once they are out of date. Hysteresis stops alerts flapping at
     the thresholds.
5. **Preview** (so you can check what it's doing):
   * Each object gets a colored box with its label and confidence. The target object
     turns red and shows its distance.
   * The LiDAR aim point is drawn as a crosshair.
   * A distance bar on the right edge marks the 50 cm and 100 cm thresholds.
   * A flashing red banner reads `!! PERSON TOO CLOSE, 40 CENTIMETERS (TTC 0.6s)`.
   * The bottom line shows exactly what was just spoken.

   The same picture is available in a browser through `--stream-port`. The terminal
   dashboard shows FPS, LiDAR distance, strength, temperature and speed, the objects
   list, the audio sink and recent events.

## 1. One-time setup on the CM5

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y imx500-all python3-picamera2 python3-opencv python3-serial python3-numpy \
                    espeak-ng pulseaudio-utils bluez
sudo reboot
```

`imx500-all` installs the IMX500 firmware and the models in `/usr/share/imx500-models/`.
Check the camera with:

```bash
rpicam-hello -t 0s --post-process-file /usr/share/rpi-camera-assets/imx500_mobilenet_ssd.json --viewfinder-width 1920 --viewfinder-height 1080 --framerate 30
```

### UART for the TFmini Plus

Wiring: TFmini **TX → GPIO15 (RXD)**, TFmini **RX → GPIO14 (TXD)**, 5 V, and GND.

```bash
sudo raspi-config   # Interface Options → Serial Port → login shell: NO, hardware: YES
echo "dtparam=uart0=on" | sudo tee -a /boot/firmware/config.txt
sudo usermod -aG dialout $USER
sudo reboot
ls -l /dev/serial0    # on Pi 5 / CM5 this should point at ttyAMA0
```

On Pi 5 and CM5 boards, `serial0` can point to the debug UART (`ttyAMA10`) instead. If
nothing arrives on the configured port, the script tries `/dev/ttyAMA0`, `ttyAMA10`,
`ttyS0` and `ttyUSB0` automatically. You can also set the port yourself with
`--serial /dev/ttyAMA0`.

### Bluetooth: pair the Shokz once

Put the headset in pairing mode, then run:

```bash
bluetoothctl
  power on
  scan on            # wait for "Shokz ..." and note its MAC
  pair XX:XX:XX:XX:XX:XX
  trust XX:XX:XX:XX:XX:XX
  connect XX:XX:XX:XX:XX:XX
  quit
pactl list short sinks                 # should list a bluez_output.XX_XX_... sink
espeak-ng "Vantage audio test"         # should come out of the headset
```

The script checks the audio sink every 5 seconds. If the headset is connected but isn't
the default output, the script switches audio to it. Pass `--bt-mac XX:XX:...` and it
will also reconnect the headset when the connection drops.

> **Don't run it with `sudo`.** Bluetooth audio runs in your user's PipeWire session.
> Root can't reach it, and you'll get silence.

## 2. Run it

```bash
cd ~/Vantage-Training

# Test the whole pipeline without any hardware (works on a laptop too)
python3 vantage_core.py --simulate

# Real hardware, preview window on the desktop / HDMI
python3 vantage_core.py --bt-mac XX:XX:XX:XX:XX:XX

# Headless (SSH): watch the annotated preview from your phone or laptop browser
python3 vantage_core.py --headless --stream-port 8080
#   then open http://<pi-ip>:8080/

# Camera only, fake LiDAR (useful while wiring)
python3 vantage_core.py --simulate-lidar
```

Preview window keys: **q**/ESC quit · **m** mute · **s** speak the scene · **d** toggle
track IDs. Press **Ctrl+C** in the terminal to stop. The script stops speech, closes the
camera, closes the serial port and restores the terminal before it exits.

### Useful options

| Option | Default | Meaning |
|---|---|---|
| `--critical CM` | 50 | "too close" distance |
| `--warning CM` | 100 | "ahead" distance |
| `--threshold P` | 0.55 | detection confidence threshold |
| `--repeat S` | 2.5 | seconds between repeated critical alerts |
| `--describe` | off | also announce new objects and their direction |
| `--lidar-offset-x/-y CM` | 0 | where the LiDAR sits relative to the lens (right/down positive) |
| `--lidar-rate HZ` | – | program the TFmini output rate, e.g. `100` |
| `--rotate-180` | off | camera mounted upside down |
| `--voice / --rate / --volume` | en-us/175/160 | espeak-ng voice settings |
| `--audio-backend` | auto | `paplay`, `pw-play`, `aplay`, `pygame`, or `espeak` |
| `--model PATH` | SSD MobileNetV2 FPN-Lite | any IMX500 object detection `.rpk` |
| `--labels FILE` | COCO-80 | label file for a custom-trained network |
| `--no-audio`, `--headless`, `--no-dashboard`, `--duration S` | | |

`python3 vantage_core.py --help` lists everything. Logs go to `vantage.log`, and every
spoken message is logged as `SAY[...]`.

### Calibrating the LiDAR aim point

Stand about 1.5 m from a wall with a person or chair in front of it. Watch where the
crosshair sits on the preview, compared with where the TFmini actually points. You can
find that spot by moving a hand into the beam until the distance changes. Then set
`--lidar-offset-x` / `--lidar-offset-y` to the physical offset between the TFmini and the
camera lens, in cm.

## 3. Start automatically on boot (optional)

```bash
mkdir -p ~/.config/systemd/user
cp vantage.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now vantage.service
sudo loginctl enable-linger $USER          # start at boot without logging in
journalctl --user -u vantage -f            # follow output
```

This is a *user* service, so it can reach the PipeWire session and the Bluetooth
headset.

## 4. Text reader (`vantage_reader.py`)

Point the camera at text (a book page, a medicine box, a sign, a screen) and the reader
speaks it on the Shokz. It's a separate program from the obstacle detector, so the two
never talk over each other. Only one program can use the camera at a time, so stop
`vantage_core.py` before you start the reader.

### Install (once)

```bash
sudo apt install -y tesseract-ocr tesseract-ocr-eng espeak-ng
```

Keep `vantage_reader.py` and `vantage_core.py` in the same folder. The reader reuses
the Bluetooth and preview helpers from the core.

### Run

```bash
python3 vantage_reader.py                  # automatic: hold text steady and it reads it
python3 vantage_reader.py --manual         # reads only when you press SPACE
python3 vantage_reader.py --headless --stream-port 8080   # over SSH: watch at http://<pi-ip>:8080
python3 vantage_reader.py --self-test      # check recognition quality on this Pi
```

**Keys** work in the preview window, or in the terminal when there's no window:

| Key | Action |
|---|---|
| SPACE / Enter | read now |
| r | repeat |
| p | pause / resume |
| x | stop |
| n / b | next / previous sentence |
| + / - | faster / slower |
| a | auto on/off |
| m | mute |
| q | quit |

### How it works

1. In auto mode it waits until it sees text and the camera has been still for 0.7 s.
   It then plays a short "click" and captures 5 frames, keeping the sharpest one.
2. It crops to the text area and removes noise in low light. It evens out the lighting,
   so shadows and uneven light disappear, and corrects for white text on a dark sign.
3. It resizes the text so letters are about 30 px tall, the size Tesseract reads best,
   and straightens tilted text. Upside-down or sideways text is turned the right way up
   automatically.
4. It tries page, block and sign layouts and keeps whichever gives the most confident
   result.
5. It drops low-confidence words and junk lines, so texture like bricks or fabric isn't
   read out as nonsense. If the overall confidence is borderline, it starts with "Not
   sure, but it says…".
6. It reads sentence by sentence, so it starts talking quickly and you can skip, go back
   or pause. Lines it has already read aren't repeated. When you move along a page, only
   the new lines are read.
7. If it can't read something, it tells you why. For example: too dark, glare, blurry,
   text too small, or too close (with `--lidar`).

The preview shows:
- the detected text lines, with live **sharp / light / steady** meters;
- after reading, each recognised word boxed and colour-coded by confidence (green means
  sure);
- on the right, the full text with the sentence being spoken highlighted.

### Getting the best results

* Hold text **25–40 cm** from the camera, as flat and straight as you can. The AI
  Camera has no autofocus, so very close text is blurry. Watch the "sharp" meter.
* Good, even light helps more than anything else. Avoid shiny glare on glossy packaging.
* For small print (medicine leaflets), use the full sensor resolution:
  `--size 4056x3040`. It's slower but sees finer detail.
* Other languages: `sudo apt install tesseract-ocr-spa`, then run with
  `--lang eng+spa --voice es`.
* Higher accuracy, but about 2× slower: download Tesseract's "best" model:
  ```bash
  mkdir -p ~/tessdata_best && cd ~/tessdata_best
  wget https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata
  cp /usr/share/tesseract-ocr/5/tessdata/osd.traineddata .
  python3 ~/Vantage-Training/vantage_reader.py --tessdata ~/tessdata_best
  ```

### When something doesn't read right

Run with `--save-debug debug/`. Every capture then saves the camera frame, the cleaned-up
image Tesseract saw, an annotated result and a text file with each word's confidence.
You can also test any photo directly:

```bash
python3 vantage_reader.py --image photo.jpg --save-debug debug/ --speak
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `LiDAR no serial port` / `silent port` | Check that TX/RX are crossed, `dtparam=uart0=on` is set, the serial console is disabled, and you're in the `dialout` group. |
| LiDAR `weak signal` | The target is black, glass or more than 12 m away. Vision fallback still works for large objects. |
| No sound | Run `pactl get-default-sink`; it should name a `bluez_output…` sink. Run without sudo. Run `espeak-ng test`. |
| The first word gets clipped | That's the Bluetooth sink waking up. The beep starts with 150 ms of silence to cover it. Using `--no-beep` makes clipping more likely. |
| Very slow first start | The network firmware uploads to the IMX500 on the first run, which takes about a minute. |
| `No desktop display found` | Expected over SSH. Use `--stream-port 8080`. |
| Reader: `Could not open camera` | `vantage_core.py` (or another camera program) is still running. Stop it first. |
| Reader: reads only part of the text | Hold it steadier and closer, add light, or try `--size 4056x3040`. Use `--save-debug` to see what the camera captured. |
| Reader: "Tesseract is not installed" | `sudo apt install tesseract-ocr tesseract-ocr-eng` |
