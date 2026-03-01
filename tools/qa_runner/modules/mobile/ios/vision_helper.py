"""
macOS Vision Framework OCR Helper

Uses macOS built-in Vision framework to detect text in screenshots.
Zero external dependencies — uses Swift CLI to invoke Vision APIs.
"""

import hashlib
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class TextRegion:
    """A detected text region from OCR."""

    text: str
    x: int  # Left edge in pixels
    y: int  # Top edge in pixels
    width: int
    height: int
    confidence: float

    @property
    def center(self) -> tuple:
        """Center point of the text region."""
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def bounds(self) -> tuple:
        """(left, top, right, bottom) bounds."""
        return (self.x, self.y, self.x + self.width, self.y + self.height)


# Swift script for Vision OCR — compiled once, cached
_VISION_OCR_SWIFT = """\
import Foundation
import Vision
import AppKit

guard CommandLine.arguments.count > 1 else {
    fputs("Usage: vision_ocr <image_path>\\n", stderr)
    exit(1)
}

let imagePath = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: imagePath),
      let tiffData = image.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiffData),
      let cgImage = bitmap.cgImage else {
    fputs("Failed to load image: \\(imagePath)\\n", stderr)
    exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true

let handler = VNImageRequestHandler(cgImage: cgImage)
do {
    try handler.perform([request])
} catch {
    fputs("Vision error: \\(error)\\n", stderr)
    exit(1)
}

let imageHeight = CGFloat(cgImage.height)
let imageWidth = CGFloat(cgImage.width)

for observation in request.results ?? [] {
    guard let candidate = observation.topCandidates(1).first else { continue }
    let box = observation.boundingBox
    // Convert from Vision coords (bottom-left, normalized) to pixel coords (top-left)
    let x = Int(box.origin.x * imageWidth)
    let y = Int((1.0 - box.origin.y - box.size.height) * imageHeight)
    let w = Int(box.size.width * imageWidth)
    let h = Int(box.size.height * imageHeight)
    print("\\(candidate.string)|\\(x)|\\(y)|\\(w)|\\(h)|\\(candidate.confidence)")
}
"""


class VisionHelper:
    """
    macOS Vision framework text recognition.

    Compiles a Swift OCR helper on first use and caches the binary.
    Subsequent calls use the cached binary for fast execution.
    """

    def __init__(self):
        self._binary_path: Optional[str] = None
        self._cache_dir = Path(tempfile.gettempdir()) / "ciris_vision_ocr"
        self._cache_dir.mkdir(exist_ok=True)

    def _get_binary(self) -> str:
        """Get or compile the Vision OCR binary."""
        if self._binary_path and os.path.exists(self._binary_path):
            return self._binary_path

        # Hash the Swift source to detect changes
        source_hash = hashlib.md5(_VISION_OCR_SWIFT.encode()).hexdigest()[:8]
        binary_path = self._cache_dir / f"vision_ocr_{source_hash}"

        if binary_path.exists():
            self._binary_path = str(binary_path)
            return self._binary_path

        # Compile the Swift script
        source_path = self._cache_dir / "vision_ocr.swift"
        source_path.write_text(_VISION_OCR_SWIFT)

        result = subprocess.run(
            ["swiftc", "-O", "-o", str(binary_path), str(source_path),
             "-framework", "Vision", "-framework", "AppKit"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to compile Vision OCR helper: {result.stderr}")

        self._binary_path = str(binary_path)
        return self._binary_path

    def recognize_text(self, image_path: str) -> List[TextRegion]:
        """
        Recognize text in an image using macOS Vision framework.

        Args:
            image_path: Path to a screenshot PNG file.

        Returns:
            List of TextRegion objects with text and bounding boxes.
        """
        binary = self._get_binary()

        result = subprocess.run(
            [binary, image_path],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            # Non-fatal — may just have no text
            return []

        regions = []
        for line in result.stdout.strip().split("\n"):
            if not line or "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) != 6:
                continue
            try:
                regions.append(TextRegion(
                    text=parts[0],
                    x=int(parts[1]),
                    y=int(parts[2]),
                    width=int(parts[3]),
                    height=int(parts[4]),
                    confidence=float(parts[5]),
                ))
            except (ValueError, IndexError):
                continue

        return regions

    def find_text(self, image_path: str, target: str, exact: bool = False) -> Optional[TextRegion]:
        """
        Find specific text in an image.

        Args:
            image_path: Path to screenshot.
            target: Text to find.
            exact: If True, match exactly. If False, check if target is contained.

        Returns:
            TextRegion if found, None otherwise.
        """
        regions = self.recognize_text(image_path)
        target_lower = target.lower()

        for region in regions:
            if exact:
                if region.text == target:
                    return region
            else:
                if target_lower in region.text.lower():
                    return region

        return None

    def is_text_visible(self, image_path: str, target: str, exact: bool = False) -> bool:
        """Check if text is visible in the image."""
        return self.find_text(image_path, target, exact) is not None

    def get_all_text(self, image_path: str) -> List[str]:
        """Get all text strings from the image."""
        regions = self.recognize_text(image_path)
        return [r.text for r in regions]
