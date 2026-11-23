import io
import os

import pytest
from conftest import jpeg_bytes, noisy_jpeg
from PIL import Image

from ezina_id_verify.images import REKOGNITION_LIMIT_BYTES, detect_format, prepare_image
from ezina_id_verify.models import UnsupportedFile


def size_of(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as im:
        return im.size


def test_file_type_comes_from_the_bytes(jpeg, png):
    assert detect_format(jpeg) == "JPEG"
    assert detect_format(png) == "PNG"
    assert detect_format(b"%PDF-1.7 ...") is None
    assert detect_format(b"GIF89a....") is None
    assert detect_format(b"") is None


def test_jpeg_and_png_pass_through_unchanged(jpeg, png):
    out = prepare_image(jpeg)
    assert out.data == jpeg and out.format == "JPEG" and (out.width, out.height) == (1200, 800)
    out = prepare_image(png)
    assert out.data == png and out.format == "PNG"


@pytest.mark.parametrize("data", [b"%PDF-1.7\n%...", b"GIF89a" + b"\x00" * 50, b"RIFF....WEBPVP8 ", b"hello, I am not an image",
                                  b"\x00" * 100])
def test_anything_but_jpeg_and_png_is_rejected_with_a_clear_message(data):
    with pytest.raises(UnsupportedFile, match="Only JPEG and PNG images are supported"):
        prepare_image(data)


def test_a_pdf_gets_a_specific_hint():
    with pytest.raises(UnsupportedFile, match="PDF files are not accepted"):
        prepare_image(b"%PDF-1.4 fake")


def test_empty_and_non_bytes_are_rejected():
    with pytest.raises(UnsupportedFile, match="empty"):
        prepare_image(b"")
    with pytest.raises(UnsupportedFile, match="bytes"):
        prepare_image("not bytes")  # type: ignore[arg-type]


def test_oversized_upload_is_rejected(jpeg):
    with pytest.raises(UnsupportedFile, match="larger than"):
        prepare_image(jpeg, max_upload_mb=0.001)


def test_max_upload_mb_comes_from_settings(jpeg):
    from conftest import make_settings
    from ezina_id_verify.config import set_settings

    set_settings(make_settings(max_upload_mb=0.001))
    with pytest.raises(UnsupportedFile, match="larger than"):
        prepare_image(jpeg)


@pytest.mark.parametrize("data", [b"\xff\xd8\xff\xe0" + b"garbage" * 40, b"\x89PNG\r\n\x1a\n" + b"garbage" * 40])
def test_unreadable_images_are_rejected(data):
    with pytest.raises(UnsupportedFile, match="could not be read"):
        prepare_image(data)


def test_exif_rotation_is_fixed():
    # 1200x800 stored sideways with EXIF orientation 6 (rotate 90): the prepared image is 800x1200
    data = jpeg_bytes((1200, 800), orientation=6)
    out = prepare_image(data)
    assert (out.width, out.height) == (800, 1200) and size_of(out.data) == (800, 1200)
    assert out.data != data


def test_orientation_1_needs_no_change():
    data = jpeg_bytes((1200, 800), orientation=1)
    assert prepare_image(data).data == data


def test_a_large_image_is_shrunk_under_the_5mb_limit_keeping_1000px():
    data = noisy_jpeg(2400, 2400, quality=95)  # random noise: compresses badly
    assert len(data) > REKOGNITION_LIMIT_BYTES
    out = prepare_image(data, max_upload_mb=50)
    assert len(out.data) <= REKOGNITION_LIMIT_BYTES
    assert out.format == "JPEG" and max(size_of(out.data)) >= 1000


def test_a_large_png_becomes_a_jpeg_under_the_limit():
    img = Image.frombytes("RGB", (1800, 1800), os.urandom(1800 * 1800 * 3))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    assert len(buf.getvalue()) > REKOGNITION_LIMIT_BYTES
    out = prepare_image(buf.getvalue(), max_upload_mb=50)
    assert out.format == "JPEG" and len(out.data) <= REKOGNITION_LIMIT_BYTES and out.data[:3] == b"\xff\xd8\xff"


def test_small_images_are_never_enlarged():
    out = prepare_image(jpeg_bytes((300, 200), orientation=6))
    assert (out.width, out.height) == (200, 300)


def test_png_with_transparency_is_accepted_unchanged():
    img = Image.new("RGBA", (1200, 800), (255, 0, 0, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    out = prepare_image(buf.getvalue())
    assert out.format == "PNG" and out.data == buf.getvalue()
