import zarr
import matplotlib.pyplot as plt
from skimage import exposure
import numpy as np
import cv2

from PIL import Image

plt.ion()

# Inputs
zarr_filename = r'D:\chaitanya\data\S4\MUSE_stitched_acq_3.zarr'
skip = 100

gamma = 0.75
vmin = 0
vmax = 2500

# Visualization
zarr_file = zarr.open(zarr_filename)
muse_data = zarr_file['muse']

print('Dataset shape:')
print(muse_data.shape)

for k in range(0, muse_data.shape[0], skip):
    image = np.squeeze(muse_data[k, :, :, :])

    image[image > vmax] = vmax
    image[image < vmin] = vmin

    image = cv2.normalize(image, None, alpha = 0, beta = 255, norm_type = cv2.NORM_MINMAX, dtype = cv2.CV_32F)

    image = exposure.adjust_gamma(image, gamma = gamma) 

    image = np.floor(cv2.normalize(image, None, alpha = 0, beta = 255, norm_type = cv2.NORM_MINMAX, dtype = cv2.CV_32F)).astype('uint8')

    pillow_image = Image.fromarray(image)
    pillow_image.save(r'intermediate slices\\' + str(k).zfill(4) + '.png')
                      
    plt.imshow(image, cmap='gray')
    plt.show()
    plt.pause(1)
    plt.clf()