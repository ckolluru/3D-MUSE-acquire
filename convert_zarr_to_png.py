import zarr
from skimage import exposure
import numpy as np
import cv2
from tqdm import tqdm
from PIL import Image
import os

# Inputs, if saveEvery is 1, all images are saved
acq_cycle = 1
zarr_filename = r'E:\P8\MUSE_stitched_acq_' + str(acq_cycle) + '.zarr'
saveEvery = 1

# Output folder
output_folder = r'E:\P8\PNG images acq ' + str(acq_cycle) 

# Window, gamma contrast adjustments
gamma = 0.75
vmin = 0
vmax = 2500

# ---------
# Algorithm
# ---------

# Make the output directory if needed
os.makedirs(output_folder, exist_ok=True)

# Pull array from the zarr dataset
zarr_file = zarr.open(zarr_filename)
muse_data = zarr_file['muse/stitched']

print('Dataset shape:')
print(muse_data.shape)

# Loop through the slices
for k in tqdm(range(0, muse_data.shape[0], saveEvery)):
    image = np.squeeze(muse_data[k, :, :])

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