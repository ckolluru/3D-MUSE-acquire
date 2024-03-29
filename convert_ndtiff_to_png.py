from ndtiff import Dataset
from skimage import exposure
import numpy as np
import cv2
from tqdm import tqdm
from PIL import Image
import os

# Inputs - this will work if only a single tile was collected (only NDTiffStacks are available)
acq_cycle = 2
ndtiff_folder = r'D:\chaitanya\MUSE datasets SPIE\S4\MUSE_acq_' + str(acq_cycle)
saveEvery = 1

# Outputs - directory with individual png files
output_folder = r'D:\chaitanya\MUSE datasets SPIE\S4\PNG images acq ' + str(acq_cycle) 

# Image contrast brightness adjustments
gamma = 0.75

# ---------
# Algorithm
# ---------

os.makedirs(output_folder, exist_ok=True)

# Get the NDTiff dataset, this will look at all the ndtiff stacks in a folder
data = Dataset(ndtiff_folder)
dask_array = data.as_array()

print('Dataset shape:')
print(dask_array.shape)

sample_image = np.squeeze(np.array(dask_array[:,0,:,:,:]))

vmin = np.percentile(sample_image, 0.01)
vmax = np.percentile(sample_image, 99.99)

print('Considering ' + str(vmin) + ' ' + str(vmax) + ' as the minimum and maximum intensity limits, the final pngs will be rescaled to 0-255 in this min-max range.')

# Loop through the slices
for k in tqdm(range(0, dask_array.shape[1], saveEvery)):
    image = np.squeeze(np.array(dask_array[:, k, :, :, :]))

    if np.sum(image) == 0:
        print('\n Found empty image, stopping at ' + str(k) + 'images')
        break
    
    # Equivalent to setting the min max values on the histogram
    image[image > vmax] = vmax
    image[image < vmin] = vmin

    image = cv2.normalize(image, None, alpha = 0, beta = 255, norm_type = cv2.NORM_MINMAX, dtype = cv2.CV_32F)

    image[image > 255] = 255
    image[image < 0] = 0

    # Setting the gamma
    image = exposure.adjust_gamma(image, gamma = gamma) 

    # Normalizing this back to 0-255
    image = np.floor(cv2.normalize(image, None, alpha = 0, beta = 255, norm_type = cv2.NORM_MINMAX, dtype = cv2.CV_32F)).astype('uint8')

    # Save the image as png
    pillow_image = Image.fromarray(image)
    pillow_image.save(output_folder + r'\\Image_' + str(k).zfill(5) + '.png')