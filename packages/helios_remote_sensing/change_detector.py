"""Remote sensing logic for detecting earth and structural disturbance from raster metrics."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ChangeResult:
    """The result of change detection on satellite imagery metrics."""
    confidence: float
    is_significant: bool
    description: str


def analyze_change(ndsi_change: float, ndvi_change: float, cloud_cover: float) -> ChangeResult:
    """Analyze raster metrics to determine if a significant construction event has occurred.
    
    Args:
        ndsi_change: Change in Normalized Difference Soil Index (NDSI). High positive implies more bare earth.
        ndvi_change: Change in Normalized Difference Vegetation Index (NDVI). Negative implies vegetation cleared.
        cloud_cover: Percentage of cloud cover in the area. High cloud cover reduces confidence.

    Returns:
        ChangeResult with confidence and boolean significance.
    """
    if cloud_cover > 20.0:
        return ChangeResult(
            confidence=0.1, 
            is_significant=False, 
            description="Obscured by cloud cover; cannot determine disturbance."
        )

    # Simplified statistical model:
    # Bare earth increases significantly while vegetation drops
    disturbance_score = 0.0
    
    if ndsi_change > 0.3:
        disturbance_score += ndsi_change
        
    if ndvi_change < -0.2:
        disturbance_score += abs(ndvi_change)
        
    # Apply cloud penalty (higher clouds = lower confidence in the signal)
    cloud_penalty = cloud_cover / 100.0
    disturbance_score = max(0.0, disturbance_score * (1.0 - cloud_penalty))
    
    # Cap at 0.99
    confidence = min(0.99, disturbance_score)
    is_significant = confidence > 0.65
    
    if is_significant:
        description = f"Significant earth disturbance detected via Sentinel-2 (score: {confidence:.2f})"
    elif confidence > 0.3:
        description = f"Minor disturbance detected (score: {confidence:.2f})"
    else:
        description = "No significant disturbance detected."
        
    return ChangeResult(
        confidence=confidence,
        is_significant=is_significant,
        description=description,
    )
