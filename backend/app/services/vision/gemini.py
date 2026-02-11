
import json
from typing import Dict, Any, Union
import numpy as np
import cv2
from loguru import logger
from google import genai
from google.genai import types
from backend.app.core.config import settings
from backend.app.core.errors import VisionFailure
from backend.app.services.vision.base import VisionProvider
from PIL import Image

class GeminiVisionProvider(VisionProvider):
    def __init__(self):
        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set. GeminiVisionProvider might fail.")
            return
        
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = "gemini-2.5-flash"

    def _convert_to_pil(self, image: np.ndarray) -> Image.Image:
        """Converts BGR numpy image to RGB PIL Image."""
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb_image)

    async def analyze(self, image: np.ndarray, prompt: str, status_callback=None) -> Dict[str, Any]:
        logger.info(f"Sending image to Gemini Vision API ({self.model_name})...")
        pil_image = self._convert_to_pil(image)

        retry_count = 0
        max_retries = 3
        
        while retry_count <= max_retries:
            try:
                # The prompt structure for multimodal in the new SDK:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[
                        prompt,
                        pil_image
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                
                content = response.text
                if not content:
                     raise VisionFailure("Gemini returned empty response")
    
                # Clean content (remove markdown fences)
                cleaned_content = self._clean_json(content)
                logger.debug(f"Raw Gemini response: {content}")
                logger.debug(f"Cleaned Gemini response: {cleaned_content}")
    
                return json.loads(cleaned_content)
    
            except Exception as e:
                error_str = str(e)
                # Check for rate limit error (429)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    retry_count += 1
                    if retry_count > max_retries:
                        logger.error(f"Gemini Vision API Rate Limit Exceeded after {max_retries} retries: {e}")
                        raise VisionFailure(f"Rate limit exceeded (429). Please wait a minute and try again. Details: {e}")
                    
                    import time
                    import re
                    import asyncio
                    
                    # Try to parse 'retry in X s' from error message
                    # Example: "Please retry in 47.142904658s."
                    wait_time = 5 * (2 ** (retry_count - 1)) # Default exponential backoff: 5, 10, 20
                    
                    match = re.search(r"retry in (\d+(\.\d+)?)s", error_str)
                    if match:
                        try:
                            parsed_wait = float(match.group(1))
                            wait_time = parsed_wait + 1 # Add 1s buffer
                        except ValueError:
                            pass
                            
                    logger.warning(f"Rate limit hit. Waiting {wait_time:.2f}s before retry {retry_count}/{max_retries}...")
                    
                    if status_callback:
                        status_callback(f"waiting_rate_limit_{int(wait_time)}s")
                    
                    # Use asyncio.sleep instead of time.sleep to not block the event loop
                    await asyncio.sleep(wait_time)
                    
                    # Reset status to processing before retrying
                    if status_callback:
                        status_callback("processing_retrying")
                        
                    continue
                
                # Non-retriable error
                logger.error(f"Gemini Vision API failed: {e}")
                if 'content' in locals() and content:
                    logger.error(f"Failed content was: {content}")
                raise VisionFailure(str(e))

    def _clean_json(self, text: str) -> str:
        """
        Extracts the first valid JSON object from the text using a stack-based approach.
        This is more robust than regex for nested structures and markdown.
        """
        text = text.strip()
        
        # Remove potential markdown wrappers first
        if "```" in text:
            # simple split to find content between fences if they exist
            # This handles ```json ... ``` or just ``` ... ```
            parts = text.split("```")
            for part in parts:
                if "{" in part:
                    # Found a candidate block, let's clean it up
                    candidate = part.strip()
                    if candidate.startswith("json"):
                        candidate = candidate[4:].strip()
                    text = candidate
                    break
        
        # Finidng the first '{'
        start_idx = text.find("{")
        if start_idx == -1:
            return text # Let json.loads fail naturally or return empty
            
        # Stack counter
        balance = 0
        end_idx = -1
        
        for i in range(start_idx, len(text)):
            char = text[i]
            if char == "{":
                balance += 1
            elif char == "}":
                balance -= 1
                if balance == 0:
                    end_idx = i
                    break
                    
        if end_idx != -1:
            return text[start_idx : end_idx + 1]
            
        # Fallback to loose find if stack fails (e.g. malformed JSON)
        return text[start_idx : text.rfind("}") + 1]
