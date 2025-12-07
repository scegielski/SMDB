"""
Lighting and material configuration constants for CoverFlow 3D rendering.

This module defines the physical-based rendering (PBR) parameters and
spotlight configuration used to render VHS box covers in the cover flow widget.
"""

# Spotlight configuration - adjust these to control the lighting effect
# Fixed spotlight position in world space (does not move)
SPOTLIGHT_POSITION_X = -10.0       # X position (centered)
SPOTLIGHT_POSITION_Y = 10.0      # Y position (height above origin)
SPOTLIGHT_POSITION_Z = 55.0       # Z position (in front of origin)

SPOTLIGHT_CONE_ANGLE = 10.0     # Cone angle in degrees (smaller = tighter beam)
SPOTLIGHT_EXPONENT = 1.0        # Falloff sharpness (higher = sharper, lower = softer)
SPOTLIGHT_RADIAL_FALLOFF = 100.0  # Radial falloff from center to edge (higher = darker edges, 0 = no falloff)
SPOTLIGHT_CENTER_BOOST = 0.0    # Center brightness boost (higher = brighter center)
SPOTLIGHT_CENTER_COLOR = (1.0, 1.0, 1.0)  # Light color at center of cone (RGB 0-1)
SPOTLIGHT_EDGE_COLOR = (1.0, 1.0, 1.0)    # Light color at edge of cone (RGB 0-1)
SPOTLIGHT_COLOR_BLEND_EXPONENT = 1.0      # Color blending curve (higher = more center color, lower = more edge color)
SPOTLIGHT_COLOR_BLEND_START = 0.9         # Radial position where color blend starts (0=edge, 1=center)
SPOTLIGHT_COLOR_BLEND_END = 1.0           # Radial position where color blend ends (0=edge, 1=center)
SPOTLIGHT_COLOR = (1.0, 1.0, 1.0)  # Warm white light (RGB 0-1)
SPOTLIGHT_INTENSITY = 20.0      # Light intensity (higher = brighter)
SPOTLIGHT_ATTENUATION_LINEAR = 0.01   # Linear distance falloff (lower = softer, 0 = no falloff)
SPOTLIGHT_ATTENUATION_QUADRATIC = 0.001  # Quadratic distance falloff (lower = softer, 0 = no falloff)
AMBIENT_LIGHT = 0.0              # Ambient lighting constant (0 = no ambient light)

# PBR Material properties for VHS boxes
MATERIAL_BASE_COLOR = (0.5, 0.5, 0.5)  # Base color tint (multiplied with texture)
MATERIAL_METALLIC = 0.0          # 0.0 = dielectric (plastic), 1.0 = metallic
MATERIAL_ROUGHNESS = 0.075         # 0.0 = smooth/glossy, 1.0 = rough/matte
MATERIAL_AO = 1.0                # Ambient occlusion factor (0-1)

# VHS box surface color (RGB 0-1) - used for all non-textured surfaces
BOX_COLOR = (0.001, 0.001, 0.001)

# Shadow configuration - Real shadow mapping from spotlight
SHADOW_ENABLED = False           # Enable/disable shadows (work in progress)
SHADOW_MAP_SIZE = 2048           # Shadow map resolution (higher = sharper shadows, more expensive)
SHADOW_BIAS = 0.005              # Shadow bias to prevent shadow acne
SHADOW_DARKNESS = 0.7            # How dark shadows are (0-1, higher = darker)
