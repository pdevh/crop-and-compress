import base64
from contextlib import ExitStack
import math
import mimetypes
import os
from pathlib import Path
import logging
import sys

import requests
from dotenv import load_dotenv
from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger("CropAndCompress.OpenAIWorker")

OPENAI_IMAGE_MODEL = "gpt-image-2"
OPENAI_IMAGE_ENDPOINT = "https://api.openai.com/v1/images"
MAX_REFERENCE_IMAGES = 16

RESOLUTION_TIER_LONG_EDGE = {
    "1K": 1024,
    "2K": 2048,
    "4K": 3840,
}

OUTPUT_FORMAT = "png"
OUTPUT_MIME_TYPE = "image/png"
QUALITY = "high"
BACKGROUND = "opaque"

TEXT_INPUT_DOLLARS_PER_1M = 5.00
IMAGE_INPUT_DOLLARS_PER_1M = 8.00
IMAGE_OUTPUT_DOLLARS_PER_1M = 30.00


def get_env_path() -> Path:
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            return Path(sys.executable).parent.parent.parent.parent / ".env"
        return Path(sys.executable).parent / ".env"
    return Path(__file__).resolve().parent.parent / ".env"


load_dotenv(get_env_path())
load_dotenv(".env")

DEFAULT_SYSTEM_PROMPT = """Use the attached images as STYLE references only — not to copy.
Analyze their shared visual DNA: motif subject matter, illustration
technique, color palette, line/texture quality, mood, and era/subculture.

Generate ONE original graphic design that matches this vibe.

CRITICAL CONSTRAINTS:

Output the motif/artwork ALONE as a standalone graphic.
NO mockups, NO product photos.
NO background scenes — isolated on a plain background.
Do not replicate any single reference; synthesize a new composition
that feels like it belongs in the same collection.
Match the references' aesthetic exactly: same art style, color tone,
texture, and emotional energy. Treat this as artwork ready to
be printed."""


def output_size_for_aspect_ratio(aspect_ratio: str, resolution: str = "1K") -> str:
    # Ensure dimensions are multiples of 16
    def round_16(val: float) -> int:
        return max(16, int(round(val / 16.0) * 16))

    long_edge = RESOLUTION_TIER_LONG_EDGE.get(resolution, 1024)
    try:
        w_ratio, h_ratio = map(float, aspect_ratio.split(":"))
    except ValueError:
        w_ratio, h_ratio = 1.0, 1.0

    if w_ratio > h_ratio:
        width = long_edge
        height = round_16(width * (h_ratio / w_ratio))
    else:
        height = long_edge
        width = round_16(height * (w_ratio / h_ratio))
        
    return f"{width}x{height}"


def parse_size(size: str) -> tuple[int, int]:
    width, height = size.lower().split("x", 1)
    return int(width), int(height)


def estimate_image_tokens(width: int, height: int) -> int:
    return 70 + (140 * math.ceil(width / 512) * math.ceil(height / 512))


def estimate_text_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def estimate_generation_cost(
    prompt: str,
    image_paths: list[Path],
    output_size: str,
) -> dict[str, float | int]:
    image_input_tokens = 0
    for image_path in image_paths[:MAX_REFERENCE_IMAGES]:
        try:
            with Image.open(image_path) as image:
                width, height = image.size
            image_input_tokens += estimate_image_tokens(width, height)
        except Exception as exc:
            logger.warning("Could not estimate image tokens for %s: %s", image_path, exc)

    output_width, output_height = parse_size(output_size)
    output_tokens = estimate_image_tokens(output_width, output_height)
    text_tokens = estimate_text_tokens(prompt)

    text_cost = text_tokens * TEXT_INPUT_DOLLARS_PER_1M / 1_000_000
    image_input_cost = image_input_tokens * IMAGE_INPUT_DOLLARS_PER_1M / 1_000_000
    image_output_cost = output_tokens * IMAGE_OUTPUT_DOLLARS_PER_1M / 1_000_000

    return {
        "text_tokens": text_tokens,
        "image_input_tokens": image_input_tokens,
        "image_output_tokens": output_tokens,
        "estimated_cost": text_cost + image_input_cost + image_output_cost,
    }


def format_cost_estimate(estimate: dict[str, float | int]) -> str:
    cost = float(estimate["estimated_cost"])
    return (
        f"Est. ${cost:.4f} "
        f"({estimate['image_input_tokens']} image input tokens, "
        f"{estimate['image_output_tokens']} image output tokens)"
    )


class OpenAIWorker(QThread):
    """Background thread that calls the OpenAI image generation API."""

    image_ready = pyqtSignal(bytes, str)
    text_chunk = pyqtSignal(str)
    error = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(
        self,
        prompt: str,
        image_paths: list[Path],
        aspect_ratio: str,
        resolution: str = "1K",
    ):
        super().__init__()
        self.prompt = prompt
        self.image_paths = image_paths
        self.aspect_ratio = aspect_ratio
        self.resolution = resolution
        self.output_size = output_size_for_aspect_ratio(aspect_ratio, resolution)
        self._cancelled = False
        logger.debug(
            "Initialized OpenAIWorker with prompt_len=%s, "
            "references=%s, aspect_ratio=%s, resolution=%s, output_size=%s",
            len(prompt),
            len(image_paths),
            aspect_ratio,
            resolution,
            self.output_size,
        )

    def cancel(self):
        logger.info("OpenAIWorker cancel requested")
        self._cancelled = True

    def run(self):
        logger.info("OpenAIWorker thread started")
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            logger.error("OPENAI_API_KEY is not set in the environment")
            self.error.emit(
                "OPENAI_API_KEY not found in environment.\n"
                "Add it to your .env file or set the environment variable."
            )
            self.finished_signal.emit()
            return

        try:
            if len(self.image_paths) > MAX_REFERENCE_IMAGES:
                raise ValueError(
                    f"GPT Image 2 supports up to {MAX_REFERENCE_IMAGES} reference images. "
                    f"Remove {len(self.image_paths) - MAX_REFERENCE_IMAGES} image(s) and try again."
                )

            payload = self._build_payload()
            endpoint = (
                f"{OPENAI_IMAGE_ENDPOINT}/edits"
                if self.image_paths
                else f"{OPENAI_IMAGE_ENDPOINT}/generations"
            )

            logger.info("Calling OpenAI image API endpoint: %s", endpoint)
            if self.image_paths:
                response = self._post_edit_request(endpoint, api_key, payload)
            else:
                response = requests.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=180,
                )

            if self._cancelled:
                logger.info("Worker cancelled after API response")
                return

            try:
                response_body = response.json()
            except ValueError:
                response_body = {}

            if response.status_code >= 400:
                error = response_body.get("error", {})
                message = error.get("message") or response.text
                raise RuntimeError(f"OpenAI API error ({response.status_code}): {message}")

            image_data = self._extract_image(response_body)
            usage = response_body.get("usage")
            if usage:
                self.text_chunk.emit(f"OpenAI usage: {usage}")
            self.image_ready.emit(image_data, OUTPUT_MIME_TYPE)
        except Exception as exc:
            logger.exception("Error occurred during OpenAI image generation")
            self.error.emit(str(exc))
        except BaseException as exc:
            logger.exception("Critical/System error in OpenAIWorker thread")
            self.error.emit(f"System/Thread Error: {exc}")
        finally:
            logger.info("OpenAIWorker thread finished execution")
            self.finished_signal.emit()

    def _build_payload(self) -> dict:
        payload = {
            "model": OPENAI_IMAGE_MODEL,
            "prompt": self.prompt,
            "n": 1,
            "size": self.output_size,
            "quality": QUALITY,
            "output_format": OUTPUT_FORMAT,
            "background": BACKGROUND,
        }

        return payload

    def _post_edit_request(self, endpoint: str, api_key: str, payload: dict):
        with ExitStack() as stack:
            files = []
            for image_path in self.image_paths:
                mime_type = self._mime_type_for_path(image_path)
                image_file = stack.enter_context(open(image_path, "rb"))
                files.append(("image[]", (image_path.name, image_file, mime_type)))

            return requests.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                data=payload,
                files=files,
                timeout=180,
            )

    def _mime_type_for_path(self, image_path: Path) -> str:
        mime_type, _ = mimetypes.guess_type(str(image_path))
        if not mime_type:
            mime_type = "image/png"
        return mime_type

    def _extract_image(self, response_body: dict) -> bytes:
        images = response_body.get("data") or []
        if not images:
            raise RuntimeError("OpenAI API response did not include an image.")

        b64_json = images[0].get("b64_json")
        if not b64_json:
            raise RuntimeError("OpenAI API response did not include base64 image data.")

        return base64.b64decode(b64_json)
