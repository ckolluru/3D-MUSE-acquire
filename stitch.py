import os
import itk
from pathlib import Path

import matplotlib.pyplot as plt
from tqdm import tqdm
import numpy as np
import zarr
import math

# Pre-load ITKMontage components
itk.auto_progress(1)
itk.TileConfiguration.GetTypes()
itk.auto_progress(0)

class Stitcher():

    def __init__(self):

        self.ZARR_STORE = None
        self.DS = None
        self.Y_SHAPE_ZARR = None
        self.X_SHAPE_ZARR = None

    def convert_xy_positions_to_tile_configuration(self, xy_positions, pixel_size, tile_config_path, x_stage_max=25000, y_stage_max=20000):

        # convert to image indices
        xy_positions = np.round(xy_positions / pixel_size)
        x_stage_max = np.round(x_stage_max / pixel_size)
        y_stage_max = np.round(y_stage_max / pixel_size)

        # our stages are setup such that y is positive going up and x is positive going left
        # instead we want our top left tile to be (0, 0)
        # subtract xy_positions from max values
        for index in range(xy_positions.shape[0]):
            xy_positions[index, :] = [x_stage_max - xy_positions[index, 0], y_stage_max - xy_positions[index, 1]]

        # tile positions in X, Y
        min_x = min(position[0] for position in xy_positions)
        min_y = min(position[1] for position in xy_positions)

        for index in range(xy_positions.shape[0]):
            xy_positions[index, :] = [xy_positions[index, 0] - min_x, xy_positions[index, 1] - min_y]

        # Sort the positions as desired by ITK montage (https://github.com/InsightSoftwareConsortium/ITKMontage/issues/190)
        x_positions = xy_positions[:,0]
        y_positions = xy_positions[:,1]

        sorted_indices = np.lexsort((x_positions, y_positions))
        xy_positions_sorted = xy_positions.take(tuple(sorted_indices), axis=0)

        # create tile config text string
        tile_config_str = f"# Tile coordinates are in index space, not physical space\ndim = 2\n"

        # create output dir and save tile config, file names are dummy
        with open(tile_config_path, 'w') as fp:
            fp.write(tile_config_str)

            for index in range(xy_positions_sorted.shape[0]):
                fp.write('img_' + str(index) + '.h5;;(' + str(xy_positions_sorted[index, 0]) + ', ' + str(xy_positions_sorted[index, 1]) + ')\n')

        print('Sorted XY tile positions:\n ', xy_positions_sorted)

        return sorted_indices

    def set_up_zarr_store_for_stitched_images(self, stitched_directory, num_time_points, num_tiles, tile_size_x, tile_size_y):

        num_tiles_x = int(math.sqrt(num_tiles))
        num_tiles_y = int(math.sqrt(num_tiles))
        
        self.Y_SHAPE_ZARR = tile_size_y * num_tiles_y    
        self.X_SHAPE_ZARR = tile_size_x * num_tiles_x

        if len(os.listdir(stitched_directory)) != 0:
            print('Stitching directory file path already exists. Returning..')
            return False

        # Create new zarr folder
        root = zarr.open(stitched_directory, mode="w")
        ch0 = root.zeros(
            "muse", shape=(num_time_points, 1, tile_size_y*num_tiles_y, tile_size_x*num_tiles_x), chunks=(1, 1, tile_size_y*num_tiles_y, tile_size_x*num_tiles_x), dtype="i2"
        )
        print(root.tree())

        # open the zarr folder to save data into it
        self.ZARR_STORE = zarr.open(stitched_directory, mode="rw")
        self.DS = self.ZARR_STORE["muse"]

        return True

    def pad_array(self, a):
        y, x = a.shape
        y_pad = (self.Y_SHAPE_ZARR-y)
        x_pad = (self.X_SHAPE_ZARR-x)
        return np.pad(a,((y_pad//2, y_pad//2 + y_pad%2), 
                        (x_pad//2, x_pad//2 + x_pad%2)),
                    mode = 'constant')

    # images should be a list of 2D numpy arrays
    # xy_positions is a 2D numpy array with positions of x and y stage
    def stitch_tiles(self,images, tile_configuration_path, pixel_size, time_index):

        dimension = 2
        stage_tiles = itk.TileConfiguration[dimension]()
        stage_tiles.Parse(str(tile_configuration_path))
        
        if len(images) != stage_tiles.LinearSize():
            raise ValueError("Images should have the same length as number of xy positions in the tile configuration file.")

        print('Load tiles..')
        itk_images = []  # for registration
        for t in tqdm(range(stage_tiles.LinearSize())):
            origin = stage_tiles.GetTile(t).GetPosition()
            image = itk.GetImageFromArray(np.ascontiguousarray(images[t]))
            image.SetSpacing((pixel_size, pixel_size))
            spacing = image.GetSpacing()

            # tile configurations are in pixel (index) coordinates
            # so we convert them into physical ones
            for d in range(dimension):
                origin[d] *= spacing[d]

            image.SetOrigin(origin)
            itk_images.append(image)

        # View one tile
        # tile_index = 0
        # plt.imshow(itk_images[tile_index])
        # plt.colorbar()
        # plt.show()

        # only float is wrapped as coordinate representation type in TileMontage
        montage = itk.TileMontage[type(itk_images[0]), itk.F].New()
        montage.SetMontageSize(stage_tiles.GetAxisSizes())
        for t in range(stage_tiles.LinearSize()):
            montage.SetInputTile(t, itk_images[t])

        print("Computing tile registration transforms")
        montage.Update()

        print("Producing the mosaic")
        resampleF = itk.TileMergeImageFilter[type(itk_images[0]), itk.D].New()
        resampleF.SetMontageSize(stage_tiles.GetAxisSizes())
        for t in tqdm(range(stage_tiles.LinearSize())):
            resampleF.SetInputTile(t, itk_images[t])
            index = stage_tiles.LinearIndexToNDIndex(t)
            resampleF.SetTileTransform(index, montage.GetOutputTransform(index))
        resampleF.Update()
        print("Resampling complete")

        # plt.imshow(resampleF.GetOutput())
        # plt.colorbar()
        # plt.show()

        print('Resample array shape: ', resampleF.GetOutput().shape)
        self.DS[time_index, 0, :, :] = self.pad_array(np.array(resampleF.GetOutput()))