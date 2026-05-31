"""
ML model handler: MegaDetector + SpeciesNet inference pipeline.

Flow:
  1. MegaDetector v5a — detect objects (animal/person/vehicle) in image
  2. Crop animal regions
  3. SpeciesNet — classify each crop to species
  4. Aggregate tag counts with confidence scores

Models are downloaded from GCS on first load and cached locally.
"""
import logging
import os
from typing import Optional, Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image

from config import (
    GCS_BUCKET,
    MODEL_BASE_PATH,
    MODEL_CACHE_DIR,
    MEGADETECTOR_MODEL,
    SPECIESNET_MODEL,
    SPECIESNET_LABELS,
    CONFIDENCE_THRESHOLD,
    DEV_MODE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model download helpers (GCS → local cache)
# ---------------------------------------------------------------------------

def _ensure_models_downloaded():
    """Download models from GCS to local cache if not already present."""
    os.makedirs(MODEL_CACHE_DIR, exist_ok=True)

    # In DEV_MODE, skip GCS download — use mock inference
    if DEV_MODE:
        logger.info("DEV_MODE: skipping GCS model download (using mock)")
        return

    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)

        for blob_name in [MEGADETECTOR_MODEL, SPECIESNET_MODEL, SPECIESNET_LABELS]:
            local_path = os.path.join(MODEL_CACHE_DIR, blob_name)
            # Remove corrupted placeholder files
            if os.path.exists(local_path) and os.path.getsize(local_path) < 1024:
                logger.warning("Removing corrupted file: %s", local_path)
                os.remove(local_path)
            if not os.path.exists(local_path):
                gcs_path = f"{MODEL_BASE_PATH}/{blob_name}"
                logger.info("Downloading gs://%s/%s -> %s", GCS_BUCKET, gcs_path, local_path)
                blob = bucket.blob(gcs_path)
                blob.download_to_filename(local_path)
            else:
                logger.info("Model already cached: %s", local_path)
    except Exception as e:
        logger.error("GCS model download failed: %s", e)
        logger.error(
            "Models unavailable — inference will fail. "
            "Set DEV_MODE=true for local development with mock models."
        )
        # Don't raise — let individual requests handle the missing model gracefully


# ---------------------------------------------------------------------------
# MegaDetector wrapper
# ---------------------------------------------------------------------------

class MegaDetector:
    """
    Wraps MegaDetector v5a (PyTorch).
    Detects bounding boxes with class: 0=animal, 1=person, 2=vehicle.
    We only keep detections with class=0 (animal).
    """

    def __init__(self):
        self.model = None
        self.device = None

    def load(self):
        import torch
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model_path = os.path.join(MODEL_CACHE_DIR, MEGADETECTOR_MODEL)

        if not os.path.exists(model_path):
            if DEV_MODE:
                logger.warning("MegaDetector model not found; using mock mode")
            else:
                raise FileNotFoundError(f"Model not found: {model_path}")
            return

        # Skip loading if file is too small (corrupted / empty)
        if os.path.getsize(model_path) < 1024:
            logger.warning(f"Model file {model_path} is too small ({os.path.getsize(model_path)} bytes) - skipping")
            if DEV_MODE:
                os.remove(model_path)  # Clean up corrupted file
            return

        try:
            logger.info(f"Loading MegaDetector from {model_path} on {self.device}")
            self.model = torch.load(model_path, map_location=self.device, weights_only=False)
            self.model.eval()
        except Exception as e:
            logger.error(f"Failed to load MegaDetector model: {e}")
            os.remove(model_path)  # Remove corrupted file
            if not DEV_MODE:
                raise

    def detect(self, image: np.ndarray) -> List[dict]:
        """
        Run MegaDetector on an image (BGR numpy array).
        Returns list of detections: [{"bbox": [x1,y1,x2,y2], "confidence": float}, ...]
        Only returns animal detections (class 0).
        """
        if self.model is None:
            logger.warning("MegaDetector not loaded; returning empty detections")
            return []

        import torch
        from torchvision.transforms import functional as F

        # Convert BGR → RGB → PIL
        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)
        img_tensor = F.to_tensor(pil_img).unsqueeze(0).to(self.device)

        with torch.no_grad():
            predictions = self.model(img_tensor)

        detections = []
        if predictions is not None and len(predictions) > 0:
            for pred in predictions[0]:
                if hasattr(pred, "get_field"):
                    labels = pred.get_field("labels").cpu().numpy()
                    boxes = pred.get_field("boxes").cpu().numpy()
                    scores = pred.get_field("scores").cpu().numpy()
                else:
                    # Fallback: handle different output formats
                    continue

                for label, box, score in zip(labels, boxes, scores):
                    if int(label) == 0 and score >= CONFIDENCE_THRESHOLD:  # animal
                        detections.append({
                            "bbox": box.tolist(),
                            "confidence": float(score),
                        })

        return detections


# ---------------------------------------------------------------------------
# SpeciesNet wrapper
# ---------------------------------------------------------------------------

class SpeciesNet:
    """Wraps SpeciesNet model for species classification on cropped animal images."""

    def __init__(self):
        self.model = None
        self.labels: List[str] = []
        self.device = None

    def load(self):
        import torch
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        model_path = os.path.join(MODEL_CACHE_DIR, SPECIESNET_MODEL)
        labels_path = os.path.join(MODEL_CACHE_DIR, SPECIESNET_LABELS)

        # Load labels
        if os.path.exists(labels_path):
            with open(labels_path, "r") as f:
                self.labels = [line.strip() for line in f if line.strip()]
            logger.info(f"Loaded {len(self.labels)} species labels")
        else:
            logger.warning(f"Labels file not found: {labels_path}")
            self.labels = ["animal"]

        if not os.path.exists(model_path):
            if DEV_MODE:
                logger.warning("SpeciesNet model not found; using mock mode")
            else:
                raise FileNotFoundError(f"Model not found: {model_path}")
            return

        if os.path.getsize(model_path) < 1024:
            logger.warning(f"Model file {model_path} is too small - skipping")
            if DEV_MODE:
                os.remove(model_path)
            return

        try:
            logger.info(f"Loading SpeciesNet from {model_path} on {self.device}")
            self.model = torch.load(model_path, map_location=self.device, weights_only=False)
            self.model.eval()
        except Exception as e:
            logger.error(f"Failed to load SpeciesNet model: {e}")
            os.remove(model_path)
            if not DEV_MODE:
                raise

    def classify(self, image_crop: np.ndarray) -> Tuple[str, float]:
        """
        Classify a cropped animal image.
        Returns (species_name, confidence).
        """
        if self.model is None or not self.labels:
            return ("unknown_animal", 0.0)

        import torch
        from torchvision.transforms import functional as F

        img_rgb = cv2.cvtColor(image_crop, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb).resize((224, 224))
        img_tensor = F.to_tensor(pil_img).unsqueeze(0).to(self.device)

        with torch.no_grad():
            logits = self.model(img_tensor)
            probs = torch.softmax(logits, dim=1)
            max_prob, max_idx = torch.max(probs, dim=1)

        idx = int(max_idx.item())
        confidence = float(max_prob.item())

        if idx < len(self.labels) and confidence >= CONFIDENCE_THRESHOLD:
            return (self.labels[idx].lower().replace(" ", "_"), confidence)
        return ("unknown_animal", confidence)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class InferencePipeline:
    """Full pipeline: image → MegaDetector → crop → SpeciesNet → tagCounts."""

    def __init__(self):
        self.detector = MegaDetector()
        self.classifier = SpeciesNet()
        self._loaded = False

    def load_models(self):
        if self._loaded:
            return
        _ensure_models_downloaded()
        self.detector.load()
        self.classifier.load()
        self._loaded = True
        logger.info("Inference pipeline ready")

    def predict(self, image: np.ndarray) -> Dict[str, int]:
        """
        Run full inference pipeline on a single image.
        Returns tagCounts dict, e.g. {"kangaroo": 3, "wombat": 1}.
        """
        self.load_models()

        # Step 1: Detect animals
        detections = self.detector.detect(image)
        if not detections:
            return {}

        # Step 2: Classify each animal detection
        tag_counts: Dict[str, int] = {}
        h, w = image.shape[:2]

        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            # Clamp to image bounds
            x1, y1 = max(0, int(x1)), max(0, int(y1))
            x2, y2 = min(w, int(x2)), min(h, int(y2))
            if x2 <= x1 or y2 <= y1:
                continue

            crop = image[y1:y2, x1:x2]
            if crop.size == 0:
                continue

            species, confidence = self.classifier.classify(crop)
            tag_counts[species] = tag_counts.get(species, 0) + 1

        return tag_counts

    def predict_mock(self, image: np.ndarray) -> Dict[str, int]:
        """Mock inference for development/testing without real models."""
        import hashlib
        # Deterministic mock based on image content hash
        h, w = image.shape[:2]
        img_hash = hashlib.md5(image.tobytes()[:4096]).hexdigest()
        hash_int = int(img_hash[:8], 16)

        species_pool = ["kangaroo", "koala", "wombat", "dingo", "emu",
                        "platypus", "echidna", "magpie", "cockatoo", "wallaby"]
        num_species = (hash_int % 3) + 1
        result = {}
        for i in range(num_species):
            species = species_pool[(hash_int + i * 7) % len(species_pool)]
            count = (hash_int >> (i * 4)) % 4 + 1
            result[species] = count
        return result


# Global singleton
_pipeline: Optional[InferencePipeline] = None


def get_pipeline() -> InferencePipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = InferencePipeline()
    return _pipeline
