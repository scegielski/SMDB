"""
Lighting and material configuration constants for CoverFlow 3D rendering.

This module defines the physical-based rendering (PBR) parameters and
spotlight configuration used to render VHS box covers in the cover flow widget.
"""

# Spotlight configuration - adjust these to control the lighting effect
# Fixed spotlight position in world space (does not move)
SPOTLIGHT_POSITION_X = -0.570
SPOTLIGHT_POSITION_Y = 1.5
SPOTLIGHT_POSITION_Z = 3.6

# Spotlight target position (where the light points at)
SPOTLIGHT_TARGET_X = 0.000
SPOTLIGHT_TARGET_Y = 0.000
SPOTLIGHT_TARGET_Z = 0.360

SPOTLIGHT_CONE_ANGLE = 12.0
SPOTLIGHT_INNER_CONE_ANGLE = 0.000
SPOTLIGHT_CENTER_BOOST = 0.000
SPOTLIGHT_CENTER_COLOR = (0.994, 1.000, 0.997)
SPOTLIGHT_EDGE_COLOR = (1.000, 1.000, 1.000)
SPOTLIGHT_COLOR_BLEND_EXPONENT = 4.2
SPOTLIGHT_COLOR_BLEND_START = 0.020
SPOTLIGHT_COLOR_BLEND_END = 0.990
SPOTLIGHT_INTENSITY = 13.4
SPOTLIGHT_ATTENUATION_LINEAR = 0.000
SPOTLIGHT_ATTENUATION_QUADRATIC = 0.000
AMBIENT_LIGHT = 0.000

# PBR Material properties for VHS boxes
MATERIAL_BASE_COLOR = (0.300, 0.300, 0.300)
MATERIAL_METALLIC = 0.000
MATERIAL_ROUGHNESS = 0.062
MATERIAL_AO = 1.0

# Ground/checkerboard material properties
GROUND_BASE_COLOR = (0.300, 0.286, 0.300)

# VHS box surface color (RGB 0-1) - used for all non-textured surfaces
BOX_COLOR = (0.100, 0.100, 0.100)

# Spotlight visualization
SPOTLIGHT_WIREFRAME_ENABLED = False

# Shadow configuration - Real shadow mapping from spotlight
SHADOW_ENABLED = False
SHADOW_MAP_SIZE = 1408.0
SHADOW_BIAS = 0.0050
SHADOW_DARKNESS = 0.700
