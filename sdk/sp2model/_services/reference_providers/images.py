"""Offline image registration and metadata. Pixel normalization uses the worker."""
from __future__ import annotations

from pathlib import Path
import struct
from .common import ProviderError, source_info


def _tiff_metadata(data):
    if data[:2] not in (b"II", b"MM") or len(data) < 8:
        raise ProviderError("invalid_exif", "Unrecognized TIFF/EXIF header.")
    endian = "<" if data[:2] == b"II" else ">"
    def number(offset, kind):
        return struct.unpack_from(endian+kind, data, offset)[0]
    if number(2, "H") != 42:
        raise ProviderError("invalid_exif", "Unrecognized TIFF version.")
    offset = number(4, "I")
    count = number(offset, "H")
    result = {}
    for index in range(count):
        location = offset + 2 + index*12
        tag, kind, length = struct.unpack_from(endian+"HHI", data, location)
        if tag in (256,257,274) and length == 1 and kind in (3,4):
            result[tag] = number(location+8, "H" if kind == 3 else "I")
    return result


def _header(path):
    # Metadata only: no decompression, no unbounded scan/read of image pixels.
    with path.open("rb") as stream:
        header = stream.read(32)
        if header.startswith(b"\x89PNG\r\n\x1a\n") and header[12:16] == b"IHDR":
            width, height = struct.unpack(">II", header[16:24])
            orientation = 1
            stream.seek(8)
            while True:
                chunk = stream.read(8)
                if len(chunk) != 8:
                    break
                length, name = struct.unpack(">I4s", chunk)
                if name == b"eXIf":
                    if length > 1024*1024:
                        raise ProviderError("image_metadata_too_large", "EXIF chunk exceeds metadata budget.")
                    orientation = _tiff_metadata(stream.read(length)).get(274, 1)
                    break
                if name == b"IEND":
                    break
                stream.seek(length+4, 1)
            return "png", width, height, orientation
        if header[:6] in (b"GIF87a", b"GIF89a"):
            width, height = struct.unpack("<HH", header[6:10])
            return "gif", width, height, 1
        if header[:2] == b"BM" and len(header) >= 26:
            width, height = struct.unpack("<ii", header[18:26])
            return "bmp", abs(width), abs(height), 1
        if header[:2] in (b"II", b"MM"):
            stream.seek(0)
            tags = _tiff_metadata(stream.read(1024*1024))
            return "tiff", tags.get(256), tags.get(257), tags.get(274, 1)
        if header[:2] == b"\xff\xd8":
            stream.seek(2)
            width = height = None
            orientation = 1
            scanned = 0
            while scanned < 16*1024*1024:
                marker = stream.read(1)
                scanned += 1
                if not marker:
                    break
                if marker != b"\xff":
                    continue
                code = stream.read(1)
                scanned += 1
                while code == b"\xff":
                    code = stream.read(1)
                    scanned += 1
                if code in (b"\xda", b"\xd9"):
                    break
                if code == b"\x00" or code == b"\xd8" or code and 0xd0 <= code[0] <= 0xd7:
                    continue
                size = stream.read(2)
                if len(size) != 2:
                    break
                length = struct.unpack(">H", size)[0]-2
                if length < 0:
                    raise ProviderError("invalid_image", "JPEG segment has invalid length.")
                data = stream.read(length)
                scanned += length+2
                if len(data) != length:
                    raise ProviderError("invalid_image", "Truncated JPEG segment.")
                if code == b"\xe1" and data.startswith(b"Exif\x00\x00"):
                    orientation = _tiff_metadata(data[6:]).get(274, 1)
                if code and code[0] in (0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf):
                    if len(data) < 5:
                        raise ProviderError("invalid_image", "JPEG frame metadata is truncated.")
                    height, width = struct.unpack(">HH", data[1:5])
            return "jpeg", width, height, orientation
        if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
            if header[12:16] == b"VP8X":
                return "webp", 1+int.from_bytes(header[24:27],"little"), 1+int.from_bytes(header[27:30],"little"), None
            # Lossless/lossy WebP metadata is intentionally left to Pillow.
            return "webp", None, None, None
    return "unknown", None, None, None


def _orientation_matrix(orientation, width, height):
    w, h = width-1, height-1
    return {
        1:[[1,0,0],[0,1,0],[0,0,1]], 2:[[-1,0,w],[0,1,0],[0,0,1]],
        3:[[-1,0,w],[0,-1,h],[0,0,1]], 4:[[1,0,0],[0,-1,h],[0,0,1]],
        5:[[0,1,0],[1,0,0],[0,0,1]], 6:[[0,-1,h],[1,0,0],[0,0,1]],
        7:[[0,-1,h],[-1,0,w],[0,0,1]], 8:[[0,1,0],[-1,0,w],[0,0,1]]
    }[orientation]


def inspect_image(path, options=None):
    source = source_info(path)
    try:
        kind, width, height, orientation = _header(Path(source["path"]))
    except (struct.error, IndexError) as error:
        raise ProviderError("invalid_image_metadata", "Truncated image metadata.") from error
    if width is not None and (width <= 0 or height is None or height <= 0):
        raise ProviderError("invalid_image_metadata", "Image dimensions must be positive.")
    if orientation is not None and orientation not in range(1,9):
        raise ProviderError("invalid_exif", "EXIF orientation must be 1 through 8.")
    return {"kind": "image", "path": source["path"], "sha256": source["sha256"], "source": source,
            "format": kind, "rawSize": {"width": width, "height": height}, "exifOrientation": orientation,
            "normalizedSize": {"width": height if orientation in (5,6,7,8) else width, "height": width if orientation in (5,6,7,8) else height},
            "rawToNormalized": _orientation_matrix(orientation,width,height) if width and height and orientation else None,
            "pixelConvention": "zero_based_pixel_centers", "normalizationRequiresWorker": orientation != 1,
            "pixelNormalizationPerformed": False, "metadataStatus": "header_only" if width and height else "worker_required_for_full_metadata",
            "integrityStatus": "not_decoded", "requiresGame": False, "missingDependencies": []}


def normalize_image(payload):
    metadata = inspect_image(payload["path"])
    try:
        from ..dependencies import worker_call
    except ImportError:
        from ..dependencies import worker_call
    result = worker_call("image.normalize", payload)
    return {**result, "original": metadata}
