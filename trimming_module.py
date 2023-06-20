from PyQt5 import QtCore
import time
from tqdm import tqdm

import humanize
import datetime as dt

class trimmingClass(QtCore.QThread):
	
	progressSignal = QtCore.pyqtSignal(int)
	progressMinimumSignal = QtCore.pyqtSignal(int)
	progressMaximumSignal = QtCore.pyqtSignal(int)
	completeSignal = QtCore.pyqtSignal(int) 
	statusBarSignal = QtCore.pyqtSignal(str)
	
	def __init__(self, timepoints, board):
		
		super(trimmingClass, self).__init__(None)
		self.board = board
		self.timepoints = timepoints

		self.progressMinimumSignal.emit(0)
		self.progressMaximumSignal.emit(timepoints)

		self.threadActive = True

	def stop(self):
		self.threadActive = False
		self.wait()

	def run(self):
		print('Trimming block-face')

		for i in tqdm(range(self.timepoints)):

			# Cutting signal
			self.board.digital[9].write(0)
			time.sleep(3)
			self.board.digital[9].write(1)

			# Poll every second to see if cut complete signal is high
			while (not self.board.digital[12].read()):
				time.sleep(1)

			self.statusBarSignal.emit('Trimming: End of section ' + str(i + 1) + ' out of ' + str(self.timepoints))
			self.progressSignal.emit(i + 1)

			# Break out of the for loop if user clicks stop acquisition button
			if not self.threadActive:
				break
			
		self.completeSignal.emit(2)

	# Stop the thread
	def terminate_thread(self):
		
		self.quit()
		self.wait()