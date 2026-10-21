"""Bounded visual material decoding; never trust extensions or keep EXIF metadata."""
import base64
from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from zhiyin_kernel.errors import InvalidRequest

IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}


def image_data_url(data: bytes) -> str:
    if not data or len(data) > 2_000_000:
        raise InvalidRequest('图片不能为空，且需小于 2MB。')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in {'PNG', 'JPEG', 'GIF', 'WEBP'}:
                    raise InvalidRequest('请上传 PNG、JPEG、GIF 或 WebP 图片。')
                if image.width * image.height > 16_000_000 or max(image.size) > 8192:
                    raise InvalidRequest('图片尺寸过大，请裁剪需要识别的区域后上传。')
                if getattr(image, 'n_frames', 1) > 1:
                    raise InvalidRequest('请上传静态图片，动图请先截取需要的那一帧。')
                image.load()
                normalized = ImageOps.exif_transpose(image).convert('RGB')
                output = BytesIO()
                normalized.save(output, format='JPEG', quality=95)
                if output.tell() > 4_000_000:
                    raise InvalidRequest('图片内容过大，请裁剪需要识别的区域后上传。')
        return 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode('ascii')
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise InvalidRequest('这不是可读取的图片，或图片已损坏，请重新导出 PNG/JPEG 后上传。') from exc
