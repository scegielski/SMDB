"""
Lighting and material configuration constants for CoverFlow 3D rendering.

This module defines the physical-based rendering (PBR) parameters and
spotlight configuration used to render VHS box covers in the cover flow widget.
"""

# Spotlight configuration - adjust these to control the lighting effect
# Fixed spotlight position in world space (does not move)
SPOTLIGHT_POSITION_X = -1.0       # X position (centered)
SPOTLIGHT_POSITION_Y = 25.0      # Y position (height above origin)
SPOTLIGHT_POSITION_Z = 15.0       # Z position (in front of origin)

SPOTLIGHT_CONE_ANGLE = 5.0     # Cone angle in degrees (smaller = tighter beam)
SPOTLIGHT_EXPONENT = 1.0        # Falloff sharpness (higher = sharper, lower = softer)
SPOTLIGHT_COLOR = (1.0, 1.0, 1.0)  # Warm white light (RGB 0-1)
SPOTLIGHT_INTENSITY = 20.0      # Light intensity (higher = brighter)
SPOTLIGHT_ATTENUATION_LINEAR = 0.0   # Linear distance falloff (lower = softer, 0 = no falloff)
SPOTLIGHT_ATTENUATION_QUADRATIC = 0.0  # Quadratic distance falloff (lower = softer, 0 = no falloff)
AMBIENT_LIGHT = 0.0              # Ambient lighting constant (0 = no ambient light)

# PBR Material properties for VHS boxes
MATERIAL_BASE_COLOR = (1.0, 1.0, 1.0)  # Base color tint (multiplied with texture)
MATERIAL_METALLIC = 0.0          # 0.0 = dielectric (plastic), 1.0 = metallic
MATERIAL_ROUGHNESS = 0.1         # 0.0 = smooth/glossy, 1.0 = rough/matte
MATERIAL_AO = 1.0                # Ambient occlusion factor (0-1)

# VHS box surface color (RGB 0-1) - used for all non-textured surfaces
BOX_COLOR = (0.001, 0.001, 0.001)
