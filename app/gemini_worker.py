import os
import mimetypes
from pathlib import Path
import logging
from PyQt6.QtCore import QThread, pyqtSignal
from dotenv import load_dotenv

import sys

logger = logging.getLogger("CropAndCompress.GeminiWorker")

def get_env_path() -> Path:
    if getattr(sys, 'frozen', False):
        if sys.platform == 'darwin':
            return Path(sys.executable).parent.parent.parent.parent / '.env'
        else:
            return Path(sys.executable).parent / '.env'
    return Path(__file__).resolve().parent.parent / '.env'

# Try to load from the executable's directory or the project root
load_dotenv(get_env_path())
# Fallback to CWD just in case
load_dotenv('.env')
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


class GeminiWorker(QThread):
    """Background thread that calls the Gemini image generation API."""
    
    image_ready = pyqtSignal(bytes, str)     # (raw_data, mime_type)
    text_chunk = pyqtSignal(str)             # text response chunk
    error = pyqtSignal(str)                  # error message
    finished_signal = pyqtSignal()           # done (success or fail)
    
    def __init__(self, prompt: str, system_prompt: str, image_paths: list[Path],
                 aspect_ratio: str):
        super().__init__()
        self.prompt = prompt
        self.system_prompt = system_prompt
        self.image_paths = image_paths
        self.aspect_ratio = aspect_ratio
        self._cancelled = False
        logger.debug(
            f"Initialized GeminiWorker with prompt_len={len(prompt)}, "
            f"system_prompt_len={len(system_prompt)}, references={len(image_paths)}, "
            f"aspect_ratio={aspect_ratio}"
        )
    
    def cancel(self):
        logger.info("GeminiWorker cancel requested")
        self._cancelled = True
    
    def run(self):
        logger.info("GeminiWorker thread started")
        try:
            logger.debug("Importing google-genai SDK")
            from google import genai
            from google.genai import types
        except Exception as e:
            logger.exception(f"Failed to import google-genai SDK: {e}")
            self.error.emit(
                f"Could not load the Gemini AI engine.\nError: {e}"
            )
            self.finished_signal.emit()
            return
        
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY is not set in the environment")
            self.error.emit(
                "GEMINI_API_KEY not found in environment.\n"
                "Add it to your .env file or set the environment variable."
            )
            self.finished_signal.emit()
            return
        
        try:
            logger.debug("Initializing genai.Client")
            client = genai.Client(api_key=api_key)
            
            # Build parts: reference images + text prompt
            parts = []
            
            # Add reference images as inline data
            logger.info(f"Processing {len(self.image_paths)} reference image(s)")
            for img_path in self.image_paths:
                if self._cancelled:
                    logger.info("Worker cancelled during image processing")
                    self.finished_signal.emit()
                    return
                    
                mime_type, _ = mimetypes.guess_type(str(img_path))
                if not mime_type:
                    mime_type = "image/png"
                
                logger.debug(f"Reading image {img_path} with mime_type {mime_type}")
                with open(img_path, "rb") as f:
                    image_data = f.read()
                
                parts.append(types.Part.from_bytes(
                    data=image_data,
                    mime_type=mime_type
                ))
            
            # Add text prompt
            logger.debug(f"Adding prompt: {self.prompt}")
            parts.append(types.Part.from_text(text=self.prompt))
            
            contents = [
                types.Content(
                    role="user",
                    parts=parts,
                ),
            ]
            
            generate_content_config = types.GenerateContentConfig(
                image_config=types.ImageConfig(
                    aspect_ratio=self.aspect_ratio,
                ),
                response_modalities=["IMAGE", "TEXT"],
                system_instruction=[
                    types.Part.from_text(text=self.system_prompt),
                ],
            )
            
            logger.info("Calling client.models.generate_content_stream")
            logger.debug(f"Model: gemini-2.5-flash-image, Config: {generate_content_config}")
            
            chunk_count = 0
            for chunk in client.models.generate_content_stream(
                model="gemini-2.5-flash-image",
                contents=contents,
                config=generate_content_config,
            ):
                if self._cancelled:
                    logger.info("Worker cancelled during stream reading")
                    self.finished_signal.emit()
                    return
                
                chunk_count += 1
                logger.debug(f"Received chunk #{chunk_count}")
                
                if chunk.parts is None:
                    logger.debug(f"Chunk #{chunk_count} has no parts")
                    continue
                    
                for part in chunk.parts:
                    if part.inline_data and part.inline_data.data:
                        logger.info(f"Received image data in chunk #{chunk_count} ({len(part.inline_data.data)} bytes)")
                        self.image_ready.emit(
                            part.inline_data.data,
                            part.inline_data.mime_type or "image/png"
                        )
                    elif part.text:
                        logger.debug(f"Received text chunk of size {len(part.text)}")
                        self.text_chunk.emit(part.text)
            
            logger.info(f"Finished reading stream. Total chunks received: {chunk_count}")
                        
        except Exception as e:
            logger.exception("Error occurred during content generation")
            self.error.emit(str(e))
        except BaseException as e:
            logger.exception("Critical/System error in GeminiWorker thread")
            self.error.emit(f"System/Thread Error: {e}")
        finally:
            logger.info("GeminiWorker thread finished execution")
            self.finished_signal.emit()


