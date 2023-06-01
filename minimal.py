import numpy as np
import time
from pycromanager import Acquisition, Studio, multi_d_acquisition_events, Core
import os

class acquisition():
    def __init__(self):
        self.core = None

        self.NUM_TILES = 1
        self.PIXEL_SIZE = 0
        self.STORAGE_DIRECTORY = None
        self.TILE_SIZE_X = None
        self.TILE_SIZE_Y = None

    # Get XY positions, set in MDA window in MM
    def get_xy_positions(self):

        studio = Studio()

        # pull current MDA window positions
        acq_manager = studio.acquisitions()
        acq_settings = acq_manager.get_acquisition_settings()
        position_list_manager = studio.positions()
        position_list = position_list_manager.get_position_list()
        number_positions = position_list.get_number_of_positions()
        xy_positions = np.empty((number_positions,2))

        # iterate through position list to extract XY positions    
        for idx in range(number_positions):
            pos = position_list.get_position(idx)
            for ipos in range(pos.size()):
                stage_pos = pos.get(ipos)
                if (stage_pos.get_stage_device_label() == 'XYStage'):
                    xy_positions[idx,:] = [stage_pos.x, stage_pos.y]

        return xy_positions

    # Just before capturing an image
    def post_hardware_hook_fn(self, event):
        
        return event

    # After capturing an image
    def image_process_fn(self, image, metadata):

        return image, metadata

    def run_acquisition(self):
        
        self.PIXEL_SIZE = 1
        self.STORAGE_DIRECTORY = r'D:\\data\\sample2'

        self.TILE_SIZE_X = 512
        self.TILE_SIZE_Y = 512

        os.makedirs(self.STORAGE_DIRECTORY, exist_ok=True)

        xy_positions = self.get_xy_positions()
        self.NUM_TILES = xy_positions.shape[0]
        assert self.NUM_TILES == 1

        num_time_points = 4
        time_interval_s = [0]
        time_per_slice = (0 + 3 * self.NUM_TILES)
        time_interval_s = time_interval_s + [time_per_slice] * (num_time_points-1)

        self.core = Core()

        with Acquisition(directory=self.STORAGE_DIRECTORY, name='pycromanager_acq', image_process_fn=self.image_process_fn, post_hardware_hook_fn=self.post_hardware_hook_fn) as acq:
            events = multi_d_acquisition_events(xy_positions=xy_positions, num_time_points=num_time_points, time_interval_s=time_interval_s)
            acq.acquire(events)

if __name__ == '__main__':
    acquisition = acquisition()
    acquisition.run_acquisition()