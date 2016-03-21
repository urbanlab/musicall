import sys
import os
import subprocess
import serial
import random
import signal as syssig
from HDmx import DmxPy

# NOTES
NOTES = ["Do", "Fa", "Sol", "Do_aigu"]

# CONFIG
CONFIG = []
for i in range(4):
	bar = []
	for j in range(0):
		bar.append([2+i, 324+i+j, NOTES[j]])
	CONFIG.append(bar)
# CONFIG.append([ [2, 324, "Do"], [2, 325, "Fa"], [2, 326, "Sol"], [2, 327, "Do_aigu"] ])
# CONFIG.append([ [3, 321, "Fa"], [3, 321, "Fa"], [3, 321, "Fa"], [3, 321, "Fa"] ])
# CONFIG.append([ [4, 321, "Sol"], [4, 321, "Sol"], [4, 321, "Sol"], [4, 321, "Sol"] ])
# CONFIG.append([ [5, 321, "Do_aigu"], [5, 321, "Do_aigu"], [5, 321, "Do_aigu"], [5, 321, "Do_aigu"] ])

SEGMENT_PRE = 3		# Number of Segment to introduce (minimum 1)
SEGMENT_KEEP = 1	# Number of Segment to keep playing while note active anymore

LED_OFF = 0
LED_READY = 30
LED_ACTIVE = 250
LED_ERROR = 10

# SONS
SOUND_PATH = os.path.join(os.getcwd(), "sons")

# CTRL-C Handler
RUN = True
def signal_handler(signal, frame):
	global RUN
	RUN = False
	dmx_interface.blackout()
	dmx_interface.render()
	print('You pressed Ctrl+C!')

# SEGMENT
class Segment:
	def __init__(self, config):
		self.dmx = config[1]
		self.note = config[2]
		self.pin = config[0]

		self.player = None

	# Music STOP
	def stop(self):
		if self.player:
			self.player.terminate()
			self.player = None

	# Music PLAY
	def play(self, file):
		if self.player:
			self.stop()
		audiofile = os.path.join(SOUND_PATH, file+".wav")
		self.player = subprocess.Popen(["aplay", audiofile], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)

	# State OFF
	def off(self):
		dmx_interface.setChannel(self.dmx, LED_OFF)
		dmx_interface.render()
		self.stop()

	# State READY
	def ready(self, percent=1.0):
		dmx_interface.setChannel(self.dmx, int(LED_READY*percent) )
		dmx_interface.render()

	# State ACTIVE
	def active(self):
		dmx_interface.setChannel(self.dmx, LED_ACTIVE)
		dmx_interface.render()
		self.play(self.note)

	# State ERROR
	def error(self):
		dmx_interface.setChannel(self.dmx, LED_ERROR)
		dmx_interface.render()
		self.play("error")


# BARREAU
class Barreau:
	def __init__(self, config):
		self.segments = []
		self.target = -1
		for seg_conf in config:
			self.segments.append( Segment(seg_conf) )

	# Stop all segments, and remove target
	def stop(self):
		self.target = -1
		for seg in self.segments:
			seg.off()

	# Init target segment
	def init(self, target=-1):
		if target == -1:
			target = random.randint(0, len(self.segments)-1)
		self.target = target

	# State READY
	def ready(self, percent=1.0):
		self.segments[self.target].ready(percent)

	# Event TOUCH
	def touch(self, pin):
		# Good segment touched
		if self.segments[self.target].pin == pin:
			self.segments[self.target].active()
			print 'Touched the good SEG'
			return True

		# Wrong segment touched
		for seg in self.segments:
			if seg.pin == pin:
				self.segments[self.target].error()
				print 'Touched the wrong SEG'
				return True

		# print 'Touched outside the BAR'
		return False

	# Event RELEASE
	def release(self, pin):
		# Inner segment released
		for seg in self.segments:
			if seg.pin == pin:
				print 'Released BAR'
				return True

		return False


# BARRIERE
class Barriere:
	def __init__(self, config):
		self.barreaux = []
		self.readybar = -1
		for bar_conf in config:
			self.barreaux.append( Barreau(bar_conf) )
		self.size = len(self.barreaux)

	# Stop all
	def stop(self):
		self.readybar = -1
		for bar in self.barreaux:
			bar.stop()

	# Init every BAR and start sequence
	def start(self):
		self.stop()
		for bar in self.barreaux:
			bar.init()
		self.next()

	def next(self):
		# STOP N-SEGMENT_KEEP BAR
		indexStop = (self.readybar+self.size-1-SEGMENT_KEEP) % self.size
		self.barreaux[indexStop].stop()

		# INCREASE ready index
		self.readybar = (self.readybar + 1) % self.size

		# READY next BAR
		percent = 1.0
		for indexReady in range(self.readybar, self.readybar+SEGMENT_PRE):
			self.barreaux[ (indexReady % self.size) ].ready(percent)
			percent -= 1.0/(SEGMENT_PRE+1)

	def touch(self, pin):
		doNext = self.barreaux[self.readybar].touch(pin)
		if doNext:
			self.next()

	def release(self, pin):
		# doNext = self.barreaux[self.readybar].release(pin)
		# if doNext:
		# 	self.next()
		# else:
		# 	print 'Release outside ready BAR'
		pass


if __name__ == '__main__':

	# Handle CTRL-C
	syssig.signal(syssig.SIGINT, signal_handler)

	# DMX INTERFACE
	dmx_interface = DmxPy.DmxPy('/dev/ttyUSB0')
	dmx_interface.blackout()
	dmx_interface.render()


	# ARDUINO INTERFACE
	arduino = serial.Serial('/dev/ttyACM0', 9600, timeout=0.01)

	# CREATE BARRIERE
	barriere = Barriere(CONFIG)
	barriere.start()

	while RUN:
		dmx_interface.full()
		# Read arduino serial
		val_read_raw = arduino.readline().strip()
		if val_read_raw != "":
			val_read = val_read_raw.split(":")
			if val_read[0] == 'PIN':
				if val_read[2] == '1':
					barriere.touch(int(val_read[1]))
				else:
					barriere.release(int(val_read[1]))
