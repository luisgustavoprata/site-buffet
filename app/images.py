"""Tratamento das fotos enviadas: confere o formato, reduz o tamanho e limpa os metadados.

Toda foto é reaberta e salva de novo pelo Pillow. Assim só entra imagem de verdade (um
arquivo disfarçado de .jpg é recusado), o GPS e outros dados EXIF do celular não vão para
o site e uma foto de 12 MB vira algumas centenas de KB.
"""

import io
from dataclasses import dataclass

from PIL import Image as PILImage
from PIL import ImageOps, UnidentifiedImageError

MAX_SIDE = 1920  # lado maior, em pixels: nítido em telas grandes, leve no celular
QUALITY = 82
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "MPO"}  # MPO: JPEG de algumas câmeras de celular
PILImage.MAX_IMAGE_PIXELS = 60_000_000  # recusa "bombas" de descompressão


class InvalidImage(ValueError):
    pass


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    content_type: str
    width: int
    height: int


def process_upload(raw: bytes) -> ProcessedImage:
    try:
        with PILImage.open(io.BytesIO(raw)) as source:
            if source.format not in ALLOWED_FORMATS:
                raise InvalidImage("Envie uma foto em JPG, PNG ou WebP.")
            image = ImageOps.exif_transpose(source)  # foto de celular "deitada" fica em pé
            image.thumbnail((MAX_SIDE, MAX_SIDE), PILImage.Resampling.LANCZOS)
            keeps_transparency = image.mode in ("RGBA", "LA") or "transparency" in image.info
            output = io.BytesIO()
            if keeps_transparency:
                image = image.convert("RGBA")
                image.save(output, "WEBP", quality=QUALITY, method=4)
                content_type = "image/webp"
            else:
                image = image.convert("RGB")
                image.save(output, "JPEG", quality=QUALITY, optimize=True, progressive=True)
                content_type = "image/jpeg"
    except (UnidentifiedImageError, OSError, PILImage.DecompressionBombError) as exc:
        raise InvalidImage("Não foi possível ler esta imagem. Envie um JPG, PNG ou WebP.") from exc
    return ProcessedImage(output.getvalue(), content_type, image.width, image.height)
