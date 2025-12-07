"""
Lighting and material configuration constants for CoverFlow 3D rendering.

This module defines the physical-based rendering (PBR) parameters and
spotlight configuration used to render VHS box covers in the cover flow widget.
"""

# Spotlight configuration - adjust these to control the lighting effect
SPOTLIGHT_HEIGHT = 15.0          # How high above the movies (units)
SPOTLIGHT_FORWARD = 8.0          # How far in front of center movie (units)
SPOTLIGHT_CONE_ANGLE = 30.5      # Cone angle in degrees (smaller = tighter beam)
SPOTLIGHT_EXPONENT = 3.0         # Falloff sharpness (higher = sharper, lower = softer)
SPOTLIGHT_COLOR = (1.0, 1.0, 0.98)  # Warm white light (RGB 0-1)
SPOTLIGHT_INTENSITY = 100.0      # Light intensity (higher = brighter)
AMBIENT_LIGHT = 0.0              # Ambient lighting constant (0 = no ambient light)

# PBR Material properties for VHS boxes
MATERIAL_BASE_COLOR = (1.0, 1.0, 1.0)  # Base color tint (multiplied with texture)
MATERIAL_METALLIC = 0.0          # 0.0 = dielectric (plastic), 1.0 = metallic
MATERIAL_ROUGHNESS = 0.3         # 0.0 = smooth/glossy, 1.0 = rough/matte
MATERIAL_AO = 1.0                # Ambient occlusion factor (0-1)

# VHS box surface color (RGB 0-1) - used for all non-textured surfaces
BOX_COLOR = (0.0, 0.1, 0.0)
