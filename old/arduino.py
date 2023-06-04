import pyfirmata                        # if you did not import the module
import time


board = pyfirmata.Arduino('COM5')


board.digital[12].mode = pyfirmata.INPUT
board.digital[8].mode = pyfirmata.OUTPUT

it = pyfirmata.util.Iterator(board)
it.start()

while True:

    board.digital[8].write(1)
    time.sleep(2)
    # board.digital[8].write(0)
    # time.sleep(1)

    take_picture_signal = board.digital[12].read()
    print(take_picture_signal)