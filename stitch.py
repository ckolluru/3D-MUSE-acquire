import os
import itk
from tqdm import tqdm
import numpy as np
import zarr

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

        # Convert to image indices
        xy_positions = np.round(xy_positions / pixel_size)
        x_stage_max = np.round(x_stage_max / pixel_size)
        y_stage_max = np.round(y_stage_max / pixel_size)

        # Our stages are setup such that y is positive going up and x is positive going left
        # Instead we want our top left tile to be (0, 0)
        # Subtract xy_positions from max values
        for index in range(xy_positions.shape[0]):
            xy_positions[index, :] = [x_stage_max - xy_positions[index, 0], y_stage_max - xy_positions[index, 1]]

        # Tile positions in X, Y
        min_x = min(position[0] for position in xy_positions)
        min_y = min(position[1] for position in xy_positions)

        for index in range(xy_positions.shape[0]):
            xy_positions[index, :] = [xy_positions[index, 0] - min_x, xy_positions[index, 1] - min_y]

        # Sort the positions as desired by ITK montage (https://github.com/InsightSoftwareConsortium/ITKMontage/issues/190)
        x_positions = xy_positions[:,0]
        y_positions = xy_positions[:,1]

        sorted_indices = np.lexsort((x_positions, y_positions))
        xy_positions_sorted = xy_positions.take(tuple(sorted_indices), axis=0)

        # Create tile config text string
        tile_config_str = f"# Tile coordinates are in index space, not physical space\ndim = 2\n"

        # If there is a tile config path with the same name, delete it
        if os.path.exists(tile_config_path):
            os.remove(tile_config_path)

        # Create output dir and save tile config, file names are dummy
        with open(tile_config_path, 'w') as fp:
            fp.write(tile_config_str)

            for index in range(xy_positions_sorted.shape[0]):
                fp.write('img_' + str(index) + '.h5;;(' + str(xy_positions_sorted[index, 0]) + ', ' + str(xy_positions_sorted[index, 1]) + ')\n')

        print('Sorted XY tile positions:\n ', xy_positions_sorted)
        print('Sorted indices: ', sorted_indices)

        return sorted_indices

    # Set up the Zarr store to save the stitched images
    def set_up_zarr_store_for_stitched_images(self, stitched_directory, num_images, num_tiles, tile_size_x, tile_size_y, num_tiles_x, num_tiles_y):
        
        self.Y_SHAPE_ZARR = int(tile_size_y * num_tiles_y * 1.05)
        self.X_SHAPE_ZARR = int(tile_size_x * num_tiles_x * 1.05)

        # Create new zarr folder

        store = zarr.DirectoryStore(stitched_directory, dimension_separator='/')
        root = zarr.group(store=store, overwrite=True)
        muse = root.create_group('muse')
        self.DS = muse.zeros('stitched', shape=(num_images, self.Y_SHAPE_ZARR, self.X_SHAPE_ZARR), chunks=(16, self.Y_SHAPE_ZARR, self.X_SHAPE_ZARR), dtype="i2" )

        return True

    # Pad the arrays
    def pad_array(self, a):
        y, x = a.shape
        y_pad = int(self.Y_SHAPE_ZARR-y)
        x_pad = int(self.X_SHAPE_ZARR-x)
        
        try:
            return np.pad(a,((y_pad//2, y_pad//2 + y_pad%2), 
                        (x_pad//2, x_pad//2 + x_pad%2)),
                    mode = 'constant') 
        
        except ValueError:

            if x_pad < 0:
                x_pad = 0

            if y_pad < 0:
                y_pad = 0
            
            # Pad in the dimension that is not an issue
            b = np.pad(a,((y_pad//2, y_pad//2 + y_pad%2), 
                        (x_pad//2, x_pad//2 + x_pad%2)),
                    mode = 'constant') 

            # Crop the center portion
            if x_pad == 0:
                startx = x//2-(self.X_SHAPE_ZARR//2)
                return b[:,startx:startx+self.X_SHAPE_ZARR]      
            if y_pad == 0:
                starty = y//2-(self.Y_SHAPE_ZARR//2)
                return b[starty:starty+self.Y_SHAPE_ZARR,:]  


    # Images should be a list of 2D numpy arrays
    # xy_positions is a 2D numpy array with positions of x and y stage
    def stitch_tiles(self, images, tile_configuration_path, pixel_size, time_index):

        dimension = 2
        stage_tiles = itk.TileConfiguration[dimension]()
        stage_tiles.Parse(str(tile_configuration_path))
        
        if len(images) != stage_tiles.LinearSize():
            raise ValueError("Images should have the same length as number of xy positions in the tile configuration file.")

        # For registration
        itk_images = []  
        for t in range(stage_tiles.LinearSize()):
            origin = stage_tiles.GetTile(t).GetPosition()
            image = itk.GetImageFromArray(np.ascontiguousarray(images[t]))
            image.SetSpacing((pixel_size, pixel_size))
            spacing = image.GetSpacing()

            # Tile configurations are in pixel (index) coordinates
            # So we convert them into physical ones
            for d in range(dimension):
                origin[d] *= spacing[d]

            image.SetOrigin(origin)
            itk_images.append(image)

        # Only float is wrapped as coordinate representation type in TileMontage
        montage = itk.TileMontage[type(itk_images[0]), itk.F].New()
        montage.SetMontageSize(stage_tiles.GetAxisSizes())
        for t in range(stage_tiles.LinearSize()):
            montage.SetInputTile(t, itk_images[t])

        montage.Update()

        resampleF = itk.TileMergeImageFilter[type(itk_images[0]), itk.D].New()
        resampleF.SetMontageSize(stage_tiles.GetAxisSizes())
        for t in range(stage_tiles.LinearSize()):
            resampleF.SetInputTile(t, itk_images[t])
            index = stage_tiles.LinearIndexToNDIndex(t)
            resampleF.SetTileTransform(index, montage.GetOutputTransform(index))
        resampleF.Update()

        array = self.pad_array(np.array(resampleF.GetOutput()))
        
        self.DS[int(time_index), :, :] = np.round(array).astype(np.uint16)