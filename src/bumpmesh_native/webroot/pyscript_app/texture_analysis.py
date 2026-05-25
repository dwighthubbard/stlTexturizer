"""Texture detail analysis for smart resolution."""

from __future__ import annotations

import math
import weakref


SHARP_THRESHOLD = 30
_cache = weakref.WeakKeyDictionary()


def analyze_texture(image_data):
    if not image_data:
        return {"meanGrad": 0, "sharpFrac": 0, "pixelsPerEdge": 4.0}

    try:
        cached = _cache.get(image_data)
        if cached:
            return cached
    except TypeError:
        cached = None

    width = int(image_data.width)
    height = int(image_data.height)
    data = image_data.data
    if width < 3 or height < 3:
        fallback = {"meanGrad": 0, "sharpFrac": 0, "pixelsPerEdge": 4.0}
        try:
            _cache[image_data] = fallback
        except TypeError:
            pass
        return fallback

    stride = width * 4
    sum_grad = 0
    sharp_count = 0
    pixel_count = 0
    for y in range(1, height - 1):
        row_off = y * stride
        for x in range(1, width - 1):
            i = row_off + x * 4
            left = data[i - 4]
            right = data[i + 4]
            up = data[i - stride]
            down = data[i + stride]
            dx = (right - left) * 0.5
            dy = (down - up) * 0.5
            mag = math.sqrt(dx * dx + dy * dy)
            sum_grad += mag
            if mag > SHARP_THRESHOLD:
                sharp_count += 1
            pixel_count += 1

    mean_grad = sum_grad / pixel_count
    sharp_frac = sharp_count / pixel_count
    if sharp_frac > 0.15 or mean_grad > 50:
        pixels_per_edge = 1.0
    elif sharp_frac > 0.05 or mean_grad > 20:
        pixels_per_edge = 1.5
    elif mean_grad > 8:
        pixels_per_edge = 2.5
    else:
        pixels_per_edge = 4.0

    result = {"meanGrad": mean_grad, "sharpFrac": sharp_frac, "pixelsPerEdge": pixels_per_edge}
    try:
        _cache[image_data] = result
    except TypeError:
        pass
    return result
