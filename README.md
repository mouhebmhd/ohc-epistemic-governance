# Reddit Health-Community Rules Pipeline

## Setup

### 1. Dataset Acquisition

The Reddit dataset can be downloaded via BitTorrent from [Academic Torrents](https://academictorrents.com/details/c902f4b65f0e82a5e37db205c3405f02a028ecdf/tech).

Download the dataset and place the compressed archive files (`.zst`) in the project directory.

### 2. Dataset Extraction and Decompression

Install the Python `zstandard` package, which is required to decompress the dataset archives:

```bash
# Install the Zstandard Python library
python -m pip install zstandard

# Decompress the downloaded .zst archives
python decompress.py
```

The `decompress.py` script decompresses the configured archives and saves the resulting files in the same directory while preserving the original compressed files.

**Note:** Ensure that Python is installed, the required package is available, and sufficient disk space is available before starting the decompression process.
