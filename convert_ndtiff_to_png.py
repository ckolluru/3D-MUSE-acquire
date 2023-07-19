from ndtiff import Dataset
import matplotlib.pyplot as plt
from skimage import exposure
import numpy as np
import cv2
from tqdm import tqdm
from PIL import Image
import os

plt.ion()

# Inputs - this will work if only a single tile was collected
acq_cycle = 2
ndtiff_folder = r'E:\P7\MUSE_acq_' + str(acq_cycle)

# Outputs - directory with individual png files
output_folder = r'E:\P7\PNG images acq ' + str(acq_cycle) 

os.makedirs(output_folder, exist_ok=True)

# Skip images (1 for do not skip)
skip = 25

# Image contrast brightness adjustments
gamma = 0.75
vmin = 0
vmax = 2500

# Visualization
data = Dataset(ndtiff_folder)
dask_array = data.as_array()

print('Dataset shape:')
print(dask_array.shape)

# Loop through the slices, adjust min-max limits and gamma contrast
for k in tqdm(range(0, dask_array.shape[1], skip)):
    image = np.squeeze(np.array(dask_array[:, k, :, :, :]))

    image[image > vmax] = vmax
    image[image < vmin] = vmin

    image = cv2.normalize(image, None, alpha = 0, beta = 255, norm_type = cv2.NORM_MINMAX, dtype = cv2.CV_32F)

    image[image > 255] = 255
    image[image < 0] = 0

    image = exposure.adjust_gamma(image, gamma = gamma) 

    image = np.floor(cv2.normalize(image, None, alpha = 0, beta = 255, norm_type = cv2.NORM_MINMAX, dtype = cv2.CV_32F)).astype('uint8')

    pillow_image = Image.fromarray(image)
    pillow_image.save(output_folder + r'\\Image_' + str(k).zfill(5) + '.png')