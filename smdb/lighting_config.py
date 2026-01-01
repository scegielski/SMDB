"""
Lighting and material configuration constants for CoverFlow 3D rendering.

This module defines the physical-based rendering (PBR) parameters and
spotlight configuration used to render VHS box covers in the cover flow widget.
"""

# Spotlight configuration - adjust these to control the lighting effect
# Fixed spotlight position in world space (does not move)
SPOTLIGHT_POSITION_X = 0.000
SPOTLIGHT_POSITION_Y = 2.0
SPOTLIGHT_POSITION_Z = 2.0

# Spotlight target position (where the light points at)
SPOTLIGHT_TARGET_X = 0.000
SPOTLIGHT_TARGET_Y = 0.000
SPOTLIGHT_TARGET_Z = 0.360

SPOTLIGHT_CONE_ANGLE = 32.8
SPOTLIGHT_INNER_CONE_ANGLE = 0.000
SPOTLIGHT_CENTER_BOOST = 0.000
SPOTLIGHT_CENTER_COLOR = (0.994, 0.997, 0.967)
SPOTLIGHT_EDGE_COLOR = (1.000, 0.979, 0.985)
SPOTLIGHT_COLOR_BLEND_EXPONENT = 3.6
SPOTLIGHT_COLOR_BLEND_START = 0.000
SPOTLIGHT_COLOR_BLEND_END = 1.0
SPOTLIGHT_INTENSITY = 50.0
SPOTLIGHT_ATTENUATION_LINEAR = 1.0
SPOTLIGHT_ATTENUATION_QUADRATIC = 1.0
AMBIENT_LIGHT = 0.000

# PBR Material properties for VHS boxes
MATERIAL_BASE_COLOR = (0.515, 0.515, 0.515)
MATERIAL_METALLIC = 0.000
MATERIAL_ROUGHNESS = 0.100
MATERIAL_AO = 1.0

# Ground/checkerboard material properties
GROUND_BASE_COLOR = (0.300, 0.286, 0.300)

# VHS box surface color (RGB 0-1) - used for all non-textured surfaces
BOX_COLOR = (0.029, 0.000, 0.000)

# Spotlight visualization
SPOTLIGHT_WIREFRAME_ENABLED = False

# Shadow configuration - Real shadow mapping from spotlight
SHADOW_ENABLED = True
SHADOW_MAP_SIZE = 1408.0
SHADOW_BIAS = 0.0050
SHADOW_DARKNESS = 0.700
