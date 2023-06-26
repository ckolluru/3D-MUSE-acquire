import zarr
store = zarr.DirectoryStore('new.zarr', dimension_separator='/')
root = zarr.group(store=store, overwrite=True)
muse = root.create_group('muse') 
ds = muse.zeros('stitched', shape=(512, 512, 512), chunks=(1, 512, 512), dtype='i2')
import numpy as np
ds[...] = (np.random.randn(512, 512, 512)*255).astype(np.uint16)

# import zarr
# store = zarr.DirectoryStore('new.zarr', dimension_separator='/')
# root = zarr.group(store=store, overwrite=True)
# foo = root.create_group('foo')
# bar = foo.zeros('bar', shape=(10, 10), chunks=(5, 5))
# bar[...] = 42