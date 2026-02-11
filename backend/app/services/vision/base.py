
from abc import ABC, abstractmethod
from typing import Dict, Any, List
import numpy as np

class VisionProvider(ABC):
    @abstractmethod
    async def analyze(self, image: np.ndarray, prompt: str, status_callback=None) -> Dict[str, Any]:
        """
        Analyzes the image and returns a structured JSON.
        """
        pass
