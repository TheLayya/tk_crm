"""Validate the small static raster screenshots attached to failure reports."""

import base64
import binascii
import struct
import zlib
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr, model_validator


MAX_IMAGE_BYTES = 3 * 1024 * 1024
MAX_TOTAL_BYTES = 10 * 1024 * 1024
MAX_DIMENSION = 12000
MAX_PIXELS = 40_000_000


class ScreenshotBody(BaseModel):
    name: str = Field(max_length=200)
    content_type: Literal["image/png", "image/jpeg", "image/webp"]
    data: str = Field(min_length=1, max_length=4194304)


class FailureBody(BaseModel):
    remark: str = Field(default="", max_length=2000)
    screenshots: list[ScreenshotBody] = Field(default_factory=list, min_length=1, max_length=5)
    _verified_screenshots: list[dict[str, str | int]] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def validate_report(self) -> "FailureBody":
        self.remark = self.remark.strip()
        if not self.screenshots:
            raise ValueError("请上传至少 1 张失败截图")
        self._verified_screenshots = validate_screenshots(self.screenshots)
        return self

    @property
    def verified_screenshots(self) -> list[dict[str, str | int]]:
        return self._verified_screenshots


def _dimensions(width: int, height: int) -> tuple[int, int]:
    if not 0 < width <= MAX_DIMENSION or not 0 < height <= MAX_DIMENSION or width * height > MAX_PIXELS:
        raise ValueError("截图尺寸请控制在 12000 像素及 4000 万像素以内")
    return width, height


def _png_size(data: bytes) -> tuple[int, int]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG 图片格式错误")
    offset = 8
    width = height = 0
    idat = bytearray()
    palette = seen_data = data_ended = False
    bit_depth = color_type = interlace = 0
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("PNG 图片内容不完整")
        length, kind = struct.unpack_from(">I4s", data, offset)
        end = offset + length + 12
        if end > len(data) or not all(65 <= char <= 90 or 97 <= char <= 122 for char in kind) or kind[2] & 32:
            raise ValueError("PNG 数据块错误")
        payload = data[offset + 8:end - 4]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != struct.unpack_from(">I", data, end - 4)[0]:
            raise ValueError("PNG 图片校验失败")
        if offset == 8 and kind != b"IHDR":
            raise ValueError("PNG 缺少图片头")
        if kind == b"IHDR":
            if offset != 8 or length != 13:
                raise ValueError("PNG 图片头错误")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            _dimensions(width, height)
            depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
            if bit_depth not in depths.get(color_type, ()) or compression or filtering or interlace not in (0, 1):
                raise ValueError("PNG 编码格式错误")
        elif kind == b"PLTE":
            if palette or seen_data or color_type in (0, 4) or not length or length % 3 or length > 768:
                raise ValueError("PNG 调色板错误")
            if color_type == 3 and length // 3 > 2 ** bit_depth:
                raise ValueError("PNG 调色板错误")
            palette = True
        elif kind == b"IDAT":
            if data_ended or (color_type == 3 and not palette):
                raise ValueError("PNG 图像数据顺序错误")
            seen_data = True
            idat.extend(payload)
        elif kind == b"IEND":
            if length or not seen_data or not idat or end != len(data):
                raise ValueError("PNG 图片内容不完整")
            _check_png_pixels(bytes(idat), width, height, bit_depth, color_type, interlace)
            return width, height
        elif kind in (b"acTL", b"fcTL", b"fdAT") or not kind[0] & 32:
            raise ValueError("请上传静态 PNG 截图")
        if seen_data and kind != b"IDAT":
            data_ended = True
        offset = end
    raise ValueError("PNG 缺少结束标记")


def _check_png_pixels(data: bytes, width: int, height: int, depth: int, color: int, interlace: int) -> None:
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    passes = ((0, 0, 1, 1),) if not interlace else (
        (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
        (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
    rows = []
    for x, y, dx, dy in passes:
        columns = max(0, (width - x + dx - 1) // dx)
        count = max(0, (height - y + dy - 1) // dy)
        if columns and count:
            rows.extend([1 + (columns * channels * depth + 7) // 8] * count)
    decoder = zlib.decompressobj()
    remaining = 0
    row_index = 0
    pending = data
    try:
        while pending:
            output = decoder.decompress(pending, 65536)
            pending = decoder.unconsumed_tail
            position = 0
            while position < len(output):
                if not remaining:
                    if row_index == len(rows) or output[position] > 4:
                        raise ValueError("PNG 像素数据错误")
                    remaining = rows[row_index]
                    row_index += 1
                consumed = min(remaining, len(output) - position)
                remaining -= consumed
                position += consumed
            if decoder.unused_data:
                raise ValueError("PNG 图片含额外压缩数据")
        if not decoder.eof or remaining or row_index != len(rows):
            raise ValueError("PNG 像素数据不完整")
    except zlib.error:
        raise ValueError("PNG 压缩数据错误") from None


def _jpeg_size(data: bytes) -> tuple[int, int]:
    if not data.startswith(b"\xff\xd8"):
        raise ValueError("JPEG 图片格式错误")
    offset = 2
    width = height = 0
    scan = entropy = False
    quantization: set[int] = set()
    huffman: set[tuple[int, int]] = set()
    frame_components: dict[int, int] = {}
    progressive = False
    while offset < len(data):
        if data[offset] != 0xFF:
            raise ValueError("JPEG 标记错误")
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset == len(data):
            break
        marker = data[offset]
        offset += 1
        if marker == 0xD9:
            if not width or not scan or not entropy or offset != len(data):
                raise ValueError("JPEG 图片内容不完整")
            return width, height
        if marker in (0, 0xD8) or 0xD0 <= marker <= 0xD7 or marker == 1 or offset + 2 > len(data):
            raise ValueError("JPEG 图片标记错误")
        length = int.from_bytes(data[offset:offset + 2], "big")
        if length < 2 or offset + length > len(data):
            raise ValueError("JPEG 图片内容不完整")
        payload = data[offset + 2:offset + length]
        if marker in (0xC0, 0xC1, 0xC2):
            if width or len(payload) < 6 or len(payload) != 6 + 3 * payload[5] or payload[0] != 8 or not 1 <= payload[5] <= 4:
                raise ValueError("JPEG 图片头错误")
            height, width = struct.unpack_from(">HH", payload, 1)
            _dimensions(width, height)
            progressive = marker == 0xC2
            for component in range(payload[5]):
                key, sampling, table = payload[6 + component * 3:9 + component * 3]
                if key in frame_components or not 1 <= sampling >> 4 <= 4 or not 1 <= sampling & 15 <= 4 or table > 3:
                    raise ValueError("JPEG 颜色分量错误")
                frame_components[key] = table
        elif marker == 0xDB:
            position = 0
            while position < len(payload):
                table = payload[position]
                precision = table >> 4
                end = position + 1 + 64 * (precision + 1)
                if precision > 1 or table & 15 > 3 or end > len(payload):
                    raise ValueError("JPEG 量化表错误")
                values = payload[position + 1:end]
                if any(not int.from_bytes(values[i:i + precision + 1], "big") for i in range(0, len(values), precision + 1)):
                    raise ValueError("JPEG 量化表错误")
                quantization.add(table & 15)
                position = end
        elif marker == 0xC4:
            position = 0
            while position < len(payload):
                if position + 17 > len(payload):
                    raise ValueError("JPEG 霍夫曼表错误")
                table = payload[position]
                counts = payload[position + 1:position + 17]
                symbols = sum(counts)
                end = position + 17 + symbols
                if table >> 4 > 1 or table & 15 > 3 or not symbols or symbols > 256 or end > len(payload):
                    raise ValueError("JPEG 霍夫曼表错误")
                available = 1
                for count in counts:
                    available = 2 * available - count
                    if available < 0:
                        raise ValueError("JPEG 霍夫曼表错误")
                huffman.add((table >> 4, table & 15))
                position = end
        elif 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            raise ValueError("请上传常规 JPEG 截图")
        offset += length
        if marker == 0xDA:
            if not width or not payload or not 1 <= payload[0] <= 4 or len(payload) != 4 + 2 * payload[0]:
                raise ValueError("JPEG 扫描头错误")
            if not set(frame_components.values()) <= quantization:
                raise ValueError("JPEG 缺少量化表")
            start, end, approximation = payload[-3:]
            if (not progressive and (start, end, approximation) != (0, 63, 0)) or (progressive and (start > end or end > 63 or approximation >> 4 > 13 or approximation & 15 > 13 or (start == 0 and end != 0) or (start > 0 and payload[0] != 1))):
                raise ValueError("JPEG 扫描参数错误")
            components = set()
            for component in range(payload[0]):
                key, table = payload[1 + component * 2:3 + component * 2]
                if key not in frame_components or key in components or table >> 4 > 3 or table & 15 > 3:
                    raise ValueError("JPEG 扫描分量错误")
                components.add(key)
                if (not progressive or payload[-3] == 0) and (0, table >> 4) not in huffman:
                    raise ValueError("JPEG 缺少编码表")
                if (not progressive or payload[-3] > 0) and (1, table & 15) not in huffman:
                    raise ValueError("JPEG 缺少编码表")
            scan = True
            while offset < len(data):
                if data[offset] != 0xFF:
                    entropy = True
                    offset += 1
                elif offset + 1 < len(data) and data[offset + 1] == 0:
                    entropy = True
                    offset += 2
                elif offset + 1 < len(data) and 0xD0 <= data[offset + 1] <= 0xD7:
                    offset += 2
                else:
                    break
    raise ValueError("JPEG 缺少结束标记")


def _webp_size(data: bytes) -> tuple[int, int]:
    if len(data) < 20 or data[:4] != b"RIFF" or data[8:12] != b"WEBP" or int.from_bytes(data[4:8], "little") + 8 != len(data):
        raise ValueError("WebP 图片格式错误")
    offset = 12
    canvas = None
    dimensions = None
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError("WebP 图片内容不完整")
        kind = data[offset:offset + 4]
        size = int.from_bytes(data[offset + 4:offset + 8], "little")
        end = offset + 8 + size
        if end + (size & 1) > len(data):
            raise ValueError("WebP 数据块错误")
        payload = data[offset + 8:end]
        if kind == b"VP8X":
            if offset != 12 or size != 10 or payload[0] & 0xC3 or payload[1:4] != b"\0\0\0":
                raise ValueError("请上传静态 WebP 截图")
            canvas = _dimensions(1 + int.from_bytes(payload[4:7], "little"), 1 + int.from_bytes(payload[7:10], "little"))
        elif kind == b"VP8 ":
            if dimensions or size < 11 or payload[0] & 1 or not payload[0] & 0x10 or payload[3:6] != b"\x9d\x01\x2a":
                raise ValueError("WebP 图像数据错误")
            first_partition = int.from_bytes(payload[:3], "little") >> 5
            if first_partition < 7 or first_partition + 3 >= size:
                raise ValueError("WebP 图像数据不完整")
            dimensions = _dimensions(int.from_bytes(payload[6:8], "little") & 0x3FFF, int.from_bytes(payload[8:10], "little") & 0x3FFF)
        elif kind == b"VP8L":
            if dimensions or size < 8 or payload[0] != 0x2F or payload[4] & 0xE0:
                raise ValueError("WebP 无损图像数据错误")
            bits = int.from_bytes(payload[1:5], "little")
            dimensions = _dimensions((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        elif kind in (b"ANIM", b"ANMF"):
            raise ValueError("请上传静态 WebP 截图")
        if size & 1 and data[end] != 0:
            raise ValueError("WebP 数据填充错误")
        offset = end + (size & 1)
    if not dimensions or (canvas and canvas != dimensions):
        raise ValueError("WebP 缺少有效图像数据")
    return dimensions


def validate_screenshots(images: list[ScreenshotBody]) -> list[dict[str, str | int]]:
    """Return canonical base64 and server-derived metadata; raise ValueError on invalid input."""
    if len(images) > 5:
        raise ValueError("每次最多上传 5 张截图")
    results: list[dict[str, str | int]] = []
    total = 0
    for image in images:
        try:
            data = base64.b64decode(image.data, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("截图 Base64 编码错误") from None
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise ValueError("每张截图请控制在 3 MiB 以内")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("截图总大小请控制在 10 MiB 以内")
        parser = {"image/png": _png_size, "image/jpeg": _jpeg_size, "image/webp": _webp_size}[image.content_type]
        width, height = parser(data)
        name = image.name.replace("\\", "/").rsplit("/", 1)[-1]
        name = "".join(char for char in name if ord(char) >= 32 and ord(char) != 127).strip()
        results.append({"name": name or "截图", "content_type": image.content_type,
                        "data": base64.b64encode(data).decode("ascii"), "width": width, "height": height, "size": len(data)})
    return results


def _self_check() -> None:
    """A dependency-free parser regression check: python -m app.services.failure_report_service."""
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"\0\0\0\0")) + chunk(b"IEND", b""))
    jpeg = base64.b64decode(
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/"
        "2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/"
        "wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAj/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFAEBAAAAAAAAAAAAAAAAAAAAAP/"
        "EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AJ/AB//Z")
    webp = base64.b64decode("UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAUAmJaQAA3AA/v02aAA=")
    for raw, mime in ((png, "image/png"), (jpeg, "image/jpeg"), (webp, "image/webp")):
        screenshot = {"name": "folder/image", "content_type": mime, "data": base64.b64encode(raw).decode()}
        result = FailureBody.model_validate({"screenshots": [screenshot]}).verified_screenshots[0]
        assert (result["name"], result["width"], result["height"], result["size"]) == ("image", 1, 1, len(raw))
        for damaged in (raw[:-1], raw + b"extra", b"<svg/>", raw[:10]):
            try:
                FailureBody.model_validate({"screenshots": [{**screenshot, "data": base64.b64encode(damaged).decode()}]})
            except ValueError:
                pass
            else:
                raise AssertionError("Damaged screenshot accepted")
    for values in ({}, {"remark": "  "}, {"remark": "说明仍需截图"}, {"screenshots": [{"name": "x", "content_type": "image/png", "data": "!!"}]}):
        try:
            FailureBody.model_validate(values)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid report accepted")


if __name__ == "__main__":
    _self_check()
    print("Failure screenshot validation passed")
