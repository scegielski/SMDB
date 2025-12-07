from PyQt5.QtWidgets import QOpenGLWidget
from PyQt5.QtCore import Qt, pyqtSignal, QRect, QTime
from PyQt5.QtGui import QImage, QPainter, QFont, QColor, QFontMetrics
from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader
from OpenGL.GLU import *
import numpy as np
import threading
import os
import ujson

# Anisotropic filtering extension constants
GL_TEXTURE_MAX_ANISOTROPY_EXT = 0x84FE
GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT = 0x84FF

# Vertex Shader - transforms vertices and passes data to fragment shader
VERTEX_SHADER = """
#version 120
varying vec3 fragNormal;
varying vec3 fragPosition;
varying vec2 fragTexCoord;
varying vec4 fragColor;

void main() {
    // Transform vertex position to view space
    fragPosition = vec3(gl_ModelViewMatrix * gl_Vertex);
    
    // Transform normal to view space
    fragNormal = normalize(gl_NormalMatrix * gl_Normal);
    
    // Pass through texture coordinates
    fragTexCoord = vec2(gl_MultiTexCoord0);
    
    // Pass through vertex color
    fragColor = gl_Color;
    
    // Transform vertex to clip space
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
"""

# Fragment Shader - per-pixel spotlight lighting calculation
FRAGMENT_SHADER = """
#version 120
varying vec3 fragNormal;
varying vec3 fragPosition;
varying vec2 fragTexCoord;
varying vec4 fragColor;

uniform sampler2D textureSampler;
uniform bool useTexture;
uniform vec3 lightPosition;      // Spotlight position in view space
uniform vec3 lightDirection;     // Spotlight direction
uniform float spotCutoff;        // Spotlight cone angle (degrees)
uniform float spotExponent;      // Spotlight falloff
uniform vec3 lightDiffuse;       // Light diffuse color
uniform vec3 lightSpecular;      // Light specular color
uniform float materialShininess; // Material shininess
uniform vec3 materialSpecular;   // Material specular color
uniform float constantAtten;     // Constant attenuation
uniform float linearAtten;       // Linear attenuation
uniform float quadraticAtten;    // Quadratic attenuation

void main() {
    // Base color from texture or vertex color
    vec4 baseColor;
    if (useTexture) {
        baseColor = texture2D(textureSampler, fragTexCoord);
    } else {
        baseColor = fragColor;  // Use color from glColor3f/glColor4f
    }
    
    // Normalize the interpolated normal
    vec3 N = normalize(fragNormal);
    
    // Calculate light direction from fragment to light
    vec3 L = lightPosition - fragPosition;
    float distance = length(L);
    L = normalize(L);
    
    // Calculate spotlight effect
    vec3 spotDir = normalize(lightDirection);
    float spotDot = dot(-L, spotDir);
    
    // Convert cutoff angle to cosine for comparison
    float cutoffCos = cos(spotCutoff * 3.14159265 / 180.0);
    
    // Create a wider soft edge region (20 degrees of smooth falloff)
    float outerCutoff = cos((spotCutoff + 20.0) * 3.14159265 / 180.0);
    
    // Smooth falloff from outer edge to inner cone
    float spotEffect = smoothstep(outerCutoff, cutoffCos, spotDot);
    
    // Apply additional exponential falloff within the cone for smooth gradient
    spotEffect = pow(spotEffect, spotExponent);
    
    // Calculate attenuation
    float attenuation = 1.0 / (constantAtten + linearAtten * distance + quadraticAtten * distance * distance);
    
    // Diffuse lighting
    float diffuse = max(dot(N, L), 0.0);
    vec3 diffuseColor = lightDiffuse * diffuse * baseColor.rgb;
    
    // Specular lighting (Blinn-Phong)
    vec3 V = normalize(-fragPosition);  // View direction
    vec3 H = normalize(L + V);          // Halfway vector
    float specular = pow(max(dot(N, H), 0.0), materialShininess);
    vec3 specularColor = lightSpecular * materialSpecular * specular;
    
    // Combine lighting components with spotlight and attenuation
    vec3 finalColor = (diffuseColor + specularColor) * spotEffect * attenuation;
    
    gl_FragColor = vec4(finalColor, baseColor.a);
}
"""

class CoverFlowGLWidget(QOpenGLWidget):
    import threading
    from PyQt5.QtCore import QMutex, QMutexLocker

    CACHE_RADIUS = 25
    STANDARD_ASPECT_RATIO = 2.0 / 3.0  # Standard movie poster aspect ratio (width/height)
    
    # Spotlight configuration - adjust these to control the lighting effect
    SPOTLIGHT_HEIGHT = 15.0          # How high above the movies (units)
    SPOTLIGHT_FORWARD = 8.0          # How far in front of center movie (units)
    SPOTLIGHT_CONE_ANGLE = 30.5      # Cone angle in degrees (smaller = tighter beam)
    SPOTLIGHT_EXPONENT = 3.0         # Falloff sharpness (higher = sharper, lower = softer)
    SPOTLIGHT_DIFFUSE = (5.0, 5.0, 5.0)   # Light color intensity (RGB 0-1)
    SPOTLIGHT_SPECULAR = (5.0, 5.0, 5.0)   # Specular highlight color (RGB 0-1)
    SPOTLIGHT_CONSTANT_ATTEN = 1.0    # Constant attenuation factor
    SPOTLIGHT_LINEAR_ATTEN = 0.00001    # Linear distance attenuation
    SPOTLIGHT_QUADRATIC_ATTEN = 0.001  # Quadratic distance attenuation
    
    # Material properties for VHS boxes
    MATERIAL_SHININESS = 50.0         # Plastic shininess (higher = glossier)
    MATERIAL_SPECULAR = (5.0, 5.0, 5.0)  # Specular reflection color
    
    # VHS box surface color (RGB 0-1) - used for all non-textured surfaces
    BOX_COLOR = (0.2, 0.0, 0.0)

    def setModelAndIndex(self, model, current_index, proxy_model=None, table_view=None):
        # Detect if proxy model changed (filter was applied or removed)
        # Force refresh if row count changed significantly (indicates filter change)
        old_row_count = getattr(self, '_cached_row_count', -1)
        new_row_count = proxy_model.rowCount() if proxy_model else (model.rowCount() if model else 0)
        row_count_changed = old_row_count != new_row_count
        
        proxy_changed = not hasattr(self, '_proxy_model') or self._proxy_model != proxy_model or row_count_changed
        
        # Store proxy model and table view if provided (for filtering support)
        old_proxy = getattr(self, '_proxy_model', None)
        self._proxy_model = proxy_model
        self._table_view = table_view
        self._cached_row_count = new_row_count
        
        # If proxy changed or row count changed significantly, clear cache since indices are no longer valid
        if proxy_changed and hasattr(self, '_cover_cache'):
            self._cover_cache = {}
            # Also clear the current cover image to force reload
            if hasattr(self, 'cover_image'):
                from PyQt5 import QtGui
                self.cover_image = QtGui.QImage()
            self.texture_id = None
        
        # Check if we're just updating the index (same model)
        if hasattr(self, '_model') and self._model == model and hasattr(self, '_current_index') and not proxy_changed:
            # Store the old index for animation
            old_index = self._current_index
            
            # Check if user is actively dragging
            is_dragging = (hasattr(self, 'last_mouse_x') and self.last_mouse_x is not None) or \
                         (hasattr(self, 'is_momentum_scrolling') and self.is_momentum_scrolling)
            
            # Always animate the transition when index changes (even when zoomed in)
            # BUT skip animation if user is actively dragging
            if old_index != current_index:
                # Don't delete rotation immediately - let it fade out smoothly during scroll
                # Mark it for cleanup instead
                if not hasattr(self, '_rotations_to_clear'):
                    self._rotations_to_clear = set()
                self._rotations_to_clear.add(old_index)
                
                if is_dragging:
                    # User is dragging - just update index silently without animation
                    # (Views will be updated directly in MainWindow.coverFlowWheelNavigate)
                    self._current_index = current_index
                else:
                    # Stop any existing animation timers
                    if hasattr(self, '_animating') and self._animating:
                        self._animating = False
                        if hasattr(self, '_anim_timer') and self._anim_timer:
                            try:
                                self.killTimer(self._anim_timer)
                            except:
                                pass
                            self._anim_timer = None
                    
                    # Start smooth scroll animation
                    self._scroll_from = old_index
                    self._scroll_to = current_index
                    self._scroll_progress = 0.0
                    self._scrolling = True
                    # Don't update _current_index yet - wait for animation to complete
                    # This keeps the rendering centered on the correct index during animation
                    if hasattr(self, '_scroll_timer') and self._scroll_timer:
                        try:
                            self.killTimer(self._scroll_timer)
                        except:
                            pass
                    self._scroll_timer = self.startTimer(16)  # ~60 FPS
                    from PyQt5.QtCore import QElapsedTimer
                    self._scroll_elapsed = QElapsedTimer()
                    self._scroll_elapsed.start()
            else:
                # Index hasn't changed, just update
                self._current_index = current_index
            
            # Start async cache for new surrounding covers
            self._start_async_cache()
            self.update()
        else:
            # New model or first time - reset everything
            self._model = model
            self._current_index = current_index
            self._cover_cache = {}
            self._cover_cache_mutex = self.QMutex()
            self._start_async_cache()

    def _start_async_cache(self):
        # Start a background thread to cache cover images (textures created on-demand in main thread)
        def cache_worker():
            try:
                # Get row count from proxy model (which already handles filtering)
                if hasattr(self, '_proxy_model') and self._proxy_model:
                    model_row_count = self._proxy_model.rowCount()
                else:
                    model_row_count = self._model.rowCount() if self._model else 0
                
                # Determine which indices to cache (all rows in proxy are visible)
                indices_to_cache = []
                
                # Use radius around current index - proxy model handles filtering
                for offset in range(-self.CACHE_RADIUS, self.CACHE_RADIUS + 1):
                        idx = self._current_index + offset
                        if idx >= 0 and idx < model_row_count:
                            indices_to_cache.append(idx)
                
                for idx in indices_to_cache:
                    
                    with self.QMutexLocker(self._cover_cache_mutex):
                        if idx in self._cover_cache:
                            continue
                    
                    # Get cover path - if using proxy model, map to source
                    try:
                        if hasattr(self, '_proxy_model') and self._proxy_model and self._proxy_model == self._model:
                            # _model IS the proxy model, need to map to source
                            proxy_index = self._model.index(idx, 0)
                            source_index = self._model.mapToSource(proxy_index)
                            source_row = source_index.row()
                            # Get cover path from source model
                            source_model = self._model.sourceModel()
                            cover_path = source_model.getCoverPath(source_row)
                        else:
                            # No proxy or model is already source model
                            cover_path = self._model.getCoverPath(idx)
                    except Exception as e:
                        # Handle case where proxy model changed during caching
                        continue
                    
                    if cover_path:
                        image = QImage(cover_path)
                        quad_geom = None
                        if not image.isNull():
                            # Precompute quad geometry (width, height, aspect)
                            # Textures will be created on-demand in the main thread
                            aspect = image.width() / image.height() if image.height() != 0 else 1.0
                            quad_geom = (aspect, image.width(), image.height())
                        with self.QMutexLocker(self._cover_cache_mutex):
                            # Store as (image, front_texture, back_texture, quad_geom)
                            self._cover_cache[idx] = (image, None, None, quad_geom)
            except Exception as e:
                # Silently handle errors (e.g., model changed during caching)
                pass
        threading.Thread(target=cache_worker, daemon=True).start()

    def getCachedCover(self, idx):
        """Get cached cover data including front and back textures.
        
        Returns:
            Tuple of (image, front_texture_id, back_texture_id, quad_geom)
        """
        with self.QMutexLocker(self._cover_cache_mutex):
            return self._cover_cache.get(idx, (None, None, None, None))


    def _store_prev_cover(self):
        self._prev_cover_image = self.cover_image
        self._prev_texture_id = self.texture_id

    def animate_cover_transition(self, direction):
        from PyQt5.QtCore import QElapsedTimer
        self._store_prev_cover()
        self._anim_direction = direction
        self._anim_progress = 0.0
        self._animating = True
        self._anim_timer = self.startTimer(16)  # ~60 FPS
        self._anim_elapsed = QElapsedTimer()
        self._anim_elapsed.start()
        self.update()

    def timerEvent(self, event):
        if self.zoom_animation_timer and event.timerId() == self.zoom_animation_timer:
            # Animate zoom smoothly toward target
            zoom_speed = 0.08  # Units per frame at 60fps (reduced for smoother motion)
            
            diff = self.zoom_target - self.camera_z
            
            # Check if we're close enough to target
            if abs(diff) < 0.01:
                self.camera_z = self.zoom_target
                try:
                    self.killTimer(self.zoom_animation_timer)
                except:
                    pass
                self.zoom_animation_timer = None
            else:
                # Move toward target at constant speed
                step = zoom_speed if abs(diff) > zoom_speed else abs(diff)
                if diff < 0:
                    step = -step
                self.camera_z += step
            
            self.update()
        elif self.camera_reset_timer and event.timerId() == self.camera_reset_timer:
            # Animate camera back to origin
            duration_ms = 300  # 300ms animation
            elapsed_ms = self.camera_reset_elapsed.elapsed() if hasattr(self, 'camera_reset_elapsed') else 0
            self.camera_reset_progress = min(1.0, elapsed_ms / duration_ms)
            
            # Ease out cubic for smooth deceleration
            progress = self.camera_reset_progress
            eased_progress = 1 - pow(1 - progress, 3)
            
            # Interpolate from start position to (0, 0) and camera_z to INITIAL_CAMERA_Z
            self.camera_pan_x = self.camera_reset_start_x * (1 - eased_progress)
            self.camera_pan_y = self.camera_reset_start_y * (1 - eased_progress)
            self.camera_z = self.camera_reset_start_z * (1 - eased_progress) + self.INITIAL_CAMERA_Z * eased_progress
            
            if self.camera_reset_progress >= 1.0:
                self.camera_pan_x = 0.0
                self.camera_pan_y = 0.0
                self.camera_z = self.INITIAL_CAMERA_Z
                try:
                    self.killTimer(self.camera_reset_timer)
                except:
                    pass
                self.camera_reset_timer = None
            
            self.update()
        elif self.rotation_animation_timer and event.timerId() == self.rotation_animation_timer:
            # Animate rotations toward their targets
            rotation_speed = 10.0  # Degrees per frame at 60fps
            all_complete = True
            
            for idx in list(self.target_rotations.keys()):
                target = self.target_rotations[idx]
                current = self.movie_rotations.get(idx, 0.0)
                
                # Calculate shortest path to target
                diff = target - current
                if diff > 180:
                    diff -= 360
                elif diff < -180:
                    diff += 360
                
                # Check if we're close enough to target
                if abs(diff) < 0.5:
                    self.movie_rotations[idx] = target
                    del self.target_rotations[idx]
                else:
                    # Move toward target
                    step = rotation_speed if abs(diff) > rotation_speed else abs(diff)
                    if diff < 0:
                        step = -step
                    self.movie_rotations[idx] = current + step
                    all_complete = False
            
            # Stop timer if all animations complete
            if all_complete:
                try:
                    self.killTimer(self.rotation_animation_timer)
                except:
                    pass
                self.rotation_animation_timer = None
            
            self.update()
        elif getattr(self, '_animating', False) and hasattr(self, '_anim_timer') and event.timerId() == self._anim_timer:
            # Use elapsed time for constant speed
            duration_ms = 740  # Animation duration in ms (slowed down by 0.5x)
            elapsed_ms = self._anim_elapsed.elapsed() if hasattr(self, '_anim_elapsed') else 0
            self._anim_progress = min(1.0, elapsed_ms / duration_ms)
            if self._anim_progress >= 1.0:
                self._anim_progress = 1.0
                self._animating = False
                try:
                    self.killTimer(self._anim_timer)
                except:
                    pass
                self._anim_timer = None
                self._prev_cover_image = None
                self._prev_texture_id = None
            self.update()
        elif getattr(self, '_scrolling', False) and hasattr(self, '_scroll_timer') and event.timerId() == self._scroll_timer:
            # Smooth scroll animation for multi-cover mode
            duration_ms = 600  # Slower scroll animation for visibility
            elapsed_ms = self._scroll_elapsed.elapsed() if hasattr(self, '_scroll_elapsed') else 0
            self._scroll_progress = min(1.0, elapsed_ms / duration_ms)
            if self._scroll_progress >= 1.0:
                self._scroll_progress = 1.0
                self._scrolling = False
                try:
                    self.killTimer(self._scroll_timer)
                except:
                    pass
                self._scroll_timer = None
                # Now update the current index at the end of the animation
                self._current_index = self._scroll_to
                # Apply pending cover image if one was stored
                if hasattr(self, '_pending_cover_qimage') and self._pending_cover_qimage:
                    self.set_cover_image_from_qimage(self._pending_cover_qimage)
                    self._pending_cover_qimage = None
                elif hasattr(self, '_pending_cover_image') and self._pending_cover_image:
                    self.set_cover_image(self._pending_cover_image)
                    self._pending_cover_image = None
                # Emit signal to notify that animation is complete
                self.scrollAnimationComplete.emit(self._current_index)
                
                # Start timer to show title after scroll animation completes
                if not hasattr(self, '_title_show_timer') or not self._title_show_timer:
                    from PyQt5.QtCore import QElapsedTimer
                    self._title_show_elapsed = QElapsedTimer()
                    self._title_show_elapsed.start()
                    self._title_show_timer = self.startTimer(16)
                    self._title_visible = False
            self.update()
        elif getattr(self, 'is_momentum_scrolling', False) and hasattr(self, '_momentum_timer') and event.timerId() == self._momentum_timer:
            # Physics-based momentum scrolling after mouse release
            friction = 0.92  # Deceleration factor (lower = faster stop)
            
            # Apply velocity to offset
            self.drag_offset += self.drag_velocity * 16  # 16ms frame time
            
            # Check if momentum scrolling crosses the threshold to cycle movies
            if hasattr(self, '_model') and hasattr(self, '_current_index'):
                threshold = 0.5  # Half a cover width
                if self.drag_offset >= threshold:
                    # Positive offset - moving to next movie (direction +1)
                    if not self._is_at_boundary(1):
                        # Momentum carried us to next movie
                        self.drag_offset -= 1.0
                        self.wheelMovieChange.emit(1)  # Next movie (direction +1)
                    else:
                        # At boundary - stop momentum
                        self.drag_offset = 0.0
                        self.drag_velocity = 0.0
                        self.is_momentum_scrolling = False
                elif self.drag_offset <= -threshold:
                    # Negative offset - moving to previous movie (direction -1)
                    if not self._is_at_boundary(-1):
                        # Momentum carried us to previous movie
                        self.drag_offset += 1.0
                        self.wheelMovieChange.emit(-1)  # Previous movie (direction -1)
                    else:
                        # At boundary - stop momentum
                        self.drag_offset = 0.0
                        self.drag_velocity = 0.0
                        self.is_momentum_scrolling = False
            
            # Apply friction
            self.drag_velocity *= friction
            
            # Stop if velocity is very low - then start settling to center
            if abs(self.drag_velocity) < 0.0001:
                self.is_momentum_scrolling = False
                try:
                    self.killTimer(self._momentum_timer)
                except:
                    pass
                self._momentum_timer = None
                
                # Start settling animation to snap to nearest cover (offset 0)
                if abs(self.drag_offset) > 0.01:  # Only settle if noticeably off-center
                    self.is_settling = True
                    self.settling_start_offset = self.drag_offset
                    self.settling_progress = 0.0
                    self._settling_timer = self.startTimer(16)  # 60 FPS
                    from PyQt5.QtCore import QElapsedTimer
                    self._settling_elapsed = QElapsedTimer()
                    self._settling_elapsed.start()
            
            self.update()
        elif getattr(self, 'is_settling', False) and hasattr(self, '_settling_timer') and event.timerId() == self._settling_timer:
            # Smooth settling animation to snap to center (offset 0)
            duration_ms = 200  # Quick settling animation
            elapsed_ms = self._settling_elapsed.elapsed() if hasattr(self, '_settling_elapsed') else 0
            self.settling_progress = min(1.0, elapsed_ms / duration_ms)
            
            # Ease out cubic for smooth deceleration
            progress = self.settling_progress
            eased_progress = 1 - pow(1 - progress, 3)
            
            # Interpolate from settling_start_offset to 0
            self.drag_offset = self.settling_start_offset * (1 - eased_progress)
            
            if self.settling_progress >= 1.0:
                self.drag_offset = 0.0
                self.is_settling = False
                try:
                    self.killTimer(self._settling_timer)
                except:
                    pass
                self._settling_timer = None
            
            self.update()
    
    def _is_at_boundary(self, direction):
        """Check if we're at a boundary in the given direction.
        direction: +1 for next, -1 for previous
        Returns True if at boundary, False otherwise"""
        if not hasattr(self, '_model') or not hasattr(self, '_current_index'):
            return True
        
        if not hasattr(self, '_table_view') or not self._table_view:
            # No filtering - simple boundary check
            if direction > 0:
                return self._current_index >= self._model.rowCount() - 1
            else:
                return self._current_index <= 0
        
        # With filtering - find all visible rows and check position
        visible_rows = []
        for idx in range(self._model.rowCount()):
            if not self._table_view.isRowHidden(idx):
                visible_rows.append(idx)
        
        if not visible_rows:
            return True
        
        try:
            current_pos = visible_rows.index(self._current_index)
            if direction > 0:
                return current_pos >= len(visible_rows) - 1
            else:
                return current_pos <= 0
        except ValueError:
            return True
    
    wheelMovieChange = pyqtSignal(int)  # +1 for next, -1 for previous
    scrollAnimationComplete = pyqtSignal(int)  # Emitted when scroll animation completes with the new index
    
    def wheelEvent(self, event):
        # Adjust FOV if Ctrl+Shift, adjust camera_z if Ctrl, otherwise toggle rotation
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.ControlModifier and event.modifiers() & Qt.ShiftModifier:
            # Adjust FOV, clamp to reasonable range
            if not hasattr(self, 'current_fov'):
                self.current_fov = self.INITIAL_FOV
            fov_step = 1.0
            if delta > 0:
                self.current_fov -= fov_step
            elif delta < 0:
                self.current_fov += fov_step
            # Clamp FOV between 10.0 and 90.0 degrees
            self.current_fov = max(10.0, min(90.0, self.current_fov))
            # Update projection matrix with new FOV
            w = self.width()
            h = self.height()
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            gluPerspective(self.current_fov, w / h if h != 0 else 1, 0.1, 500.0)
            glMatrixMode(GL_MODELVIEW)
            self.update()
            event.accept()
        elif event.modifiers() & Qt.ControlModifier:
            # Adjust camera_z with animation
            if not hasattr(self, 'camera_z'):
                self.camera_z = self.INITIAL_CAMERA_Z
            
            camera_step = 0.5
            new_target = self.zoom_target  # Start from current target
            if delta > 0:
                new_target -= camera_step
            elif delta < 0:
                new_target += camera_step
            
            # Clamp target between -2.0 and 30.0
            new_target = max(-2.0, min(30.0, new_target))
            
            # Update target (don't restart animation, just change destination)
            if new_target != self.zoom_target:
                # If no animation is running, set the start point
                if self.zoom_animation_timer is None:
                    self.zoom_start = self.camera_z
                    self.zoom_progress = 0.0
                    from PyQt5.QtCore import QElapsedTimer
                    self.zoom_elapsed = QElapsedTimer()
                    self.zoom_elapsed.start()
                    self.zoom_animation_timer = self.startTimer(16)  # ~60 fps
                # If animation is running, just update the target without resetting start/progress
                # This allows smooth continuation
                self.zoom_target = new_target
            
            event.accept()  # Prevent propagation to parent (no text size change)
        else:
            # Toggle rotation on mouse wheel
            if hasattr(self, '_current_index'):
                current_rotation = self.movie_rotations.get(self._current_index, 0.0)
                if abs(current_rotation - 180) < 10:  # Already rotated to back
                    self.target_rotations[self._current_index] = 0.0
                else:  # Not rotated or partially rotated
                    self.target_rotations[self._current_index] = 180.0
                
                # Start animation timer if not already running
                if self.rotation_animation_timer is None:
                    self.rotation_animation_timer = self.startTimer(16)  # ~60 fps
            
            event.accept()

    # Camera and viewport settings (configurable in one place)
    INITIAL_FOV = 20.0  # Field of view in degrees (lower = less fisheye)
    INITIAL_CAMERA_Z = 1.0  # Initial camera z-offset (higher = pulled back further)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Enable sample buffers for anti-aliasing
        fmt = self.format()
        fmt.setSamples(4)  # Increased from 8 to 16 for better anti-aliasing
        self.setFormat(fmt)
        self.cover_image = None
        self.texture_id = None
        self.y_rotation = 0.0
        self.last_mouse_x = None
        self.movie_rotations = {}  # Store current rotation per movie index
        self.target_rotations = {}  # Store target rotation per movie index
        self.rotation_animation_timer = None  # Timer for rotation animation
        self.aspect_ratio = 1.0
        self.camera_z = self.INITIAL_CAMERA_Z  # Camera z translation
        self.camera_pan_x = 0.0  # Camera horizontal pan offset
        self.camera_pan_y = 0.0  # Camera vertical pan offset
        
        # Display list cache for box geometry
        self._box_display_list = None  # Cached compiled box geometry
        self._box_cache_mutex = None  # Will be initialized in initializeGL
        
        # Drag scrolling state (left button)
        self.drag_start_x = None
        self.drag_offset = 0.0  # Current drag offset in cover units
        self.drag_velocity = 0.0  # Velocity for momentum
        self.is_momentum_scrolling = False
        self.last_drag_time = None
        self.drag_history = []  # Track recent drag movements for velocity calculation
        
        # Camera panning state (middle button)
        self.is_panning = False
        self.pan_start_x = None
        self.pan_start_y = None
        
        # Camera reset animation
        self.camera_reset_timer = None
        self.camera_reset_start_x = 0.0
        self.camera_reset_start_y = 0.0
        self.camera_reset_start_z = 0.0
        self.camera_reset_progress = 0.0
        
        # Zoom animation
        self.zoom_animation_timer = None
        self.zoom_start = self.INITIAL_CAMERA_Z
        self.zoom_target = self.INITIAL_CAMERA_Z
        self.zoom_progress = 0.0

    def set_cover_image(self, image_path):
        self.cover_image = QImage(image_path)
        self.texture_id = None  # Force recreation of texture for new image
        if not self.cover_image.isNull():
            self.aspect_ratio = self.cover_image.width() / self.cover_image.height()
        self.update()
    
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MiddleButton:
            # Start camera reset animation
            self.camera_reset_start_x = self.camera_pan_x
            self.camera_reset_start_y = self.camera_pan_y
            self.camera_reset_start_z = self.camera_z
            self.camera_reset_progress = 0.0
            
            if self.camera_reset_timer is None:
                from PyQt5.QtCore import QElapsedTimer
                self.camera_reset_elapsed = QElapsedTimer()
                self.camera_reset_elapsed.start()
                self.camera_reset_timer = self.startTimer(16)  # ~60 fps
            event.accept()
    
    def set_cover_image_from_qimage(self, qimage):
        """Set cover image from an already-loaded QImage to avoid duplicate file loading"""
        self.cover_image = qimage
        self.texture_id = None  # Force recreation of texture for new image
        if not self.cover_image.isNull():
            self.aspect_ratio = self.cover_image.width() / self.cover_image.height()
        self.update()

    def createTextTexture(self, movie_path, movie_folder, width=1024, height=1536):
        """Create an OpenGL texture from movie plot/synopsis text.
        
        Args:
            movie_path: Path to the movie folder
            movie_folder: Movie folder name
            width: Texture width in pixels
            height: Texture height in pixels
            
        Returns:
            OpenGL texture ID or None if no text available
        """
        # Check cache first
        cache_key = (movie_path, movie_folder)
        if not hasattr(self, '_text_texture_cache'):
            self._text_texture_cache = {}
        
        if cache_key in self._text_texture_cache:
            return self._text_texture_cache[cache_key]
        
        # Load JSON data
        json_file = os.path.join(movie_path, f'{movie_folder}.json')
        if not os.path.exists(json_file):
            print(f"No JSON file found: {json_file}")
            return None
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                movie_data = ujson.load(f)
        except Exception as e:
            print(f"Error loading JSON {json_file}: {e}")
            return None
        
        # Get plot and synopsis (try multiple variations)
        synopsis = movie_data.get('synopsis', movie_data.get('Synopsis', ''))
        plot_outline = movie_data.get('plot outline', '')
        summary = movie_data.get('summary', '')
        plot = movie_data.get('plot', movie_data.get('Plot', ''))
        title = movie_data.get('title', movie_data.get('Title', ''))
        year = movie_data.get('year', '')
        
        # Format title with year
        if year:
            title_with_year = f"{title} ({year})"
        else:
            title_with_year = title
        
        # Convert lists to strings early
        if isinstance(synopsis, list):
            synopsis = ' '.join(str(s) for s in synopsis if s)
        if isinstance(plot_outline, list):
            plot_outline = ' '.join(str(p) for p in plot_outline if p)
        if isinstance(summary, list):
            summary = ' '.join(str(s) for s in summary if s)
        if isinstance(plot, list):
            plot = ' '.join(str(p) for p in plot if p)
        
        # Debug: show available keys in first call
        if not hasattr(self, '_shown_json_keys'):
            self._shown_json_keys = True
            print(f"Available JSON keys: {list(movie_data.keys())}")
        
        print(f"Creating text texture for: {title}")
        print(f"  Has Synopsis: {len(synopsis) if synopsis else 0} chars")
        print(f"  Has Plot outline: {len(plot_outline) if plot_outline else 0} chars")
        print(f"  Has Summary: {len(summary) if summary else 0} chars")
        print(f"  Has Plot: {len(plot) if plot else 0} chars")
        
        # Prefer summary (formatted) over other fields
        # Summary usually contains formatted info like "Movie\n=====\nTitle: ...\nGenres: ..."
        # Only fall back to synopsis/plot_outline if summary is empty or very short
        if summary and len(summary) > 50:
            text = summary
            # If we have a synopsis, append it after the summary
            # Check that synopsis is meaningful (not just a single character like "1")
            if synopsis and len(synopsis) > 100:
                text += "\n\nSynopsis:\n\n" + synopsis
                print(f"  Added synopsis: {len(synopsis)} chars")
            elif plot_outline and len(plot_outline) > 100:
                text += "\n\nSynopsis:\n\n" + plot_outline
                print(f"  Added plot outline: {len(plot_outline)} chars")
        else:
            text = synopsis or plot_outline or summary or plot
            
        if not text or (isinstance(text, list) and len(text) == 0):
            print(f"  No text available for {title}")
            return None
        
        # Convert to string if still a list (shouldn't happen but just in case)
        if isinstance(text, list):
            text = ' '.join(str(t) for t in text if t)
        
        print(f"  Using text (first 100 chars): {text[:100]}...")
        print(f"  Text type: {type(text)}, Length: {len(text)}")
        
        # Clean up summary text - remove redundant elements
        # Remove "Movie" line
        text = text.replace('Movie\n', '')
        text = text.replace('Movie', '')
        # Remove "=====" separator lines
        text = text.replace('=====\n', '')
        text = text.replace('=====', '')
        # Remove Title line since we render it separately at the top
        # Use regex for more flexible matching
        import re
        if title:
            # Remove any "Title: ..." line regardless of what follows
            text = re.sub(r'Title:\s*.*?\n', '', text, flags=re.IGNORECASE)
            # Also try without the newline in case it's at the end
            text = re.sub(r'Title:\s*.*?$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        # Clean up any double blank lines that may have been created
        while '\n\n\n' in text:
            text = text.replace('\n\n\n', '\n\n')
        text = text.strip()
        
        # Create QImage for rendering text
        image = QImage(width, height, QImage.Format_RGBA8888)
        image.fill(QColor(20, 20, 20, 255))  # Dark background
        
        # Set up painter
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        
        # Set up fonts
        title_font = QFont("Arial", 32, QFont.Bold)
        header_font = QFont("Arial", 26, QFont.Bold)
        text_font = QFont("Arial", 18)
        
        # Draw title at top
        painter.setFont(title_font)
        painter.setPen(QColor(220, 220, 220))
        title_rect = QRect(20, 20, width - 40, 80)
        painter.drawText(title_rect, Qt.AlignTop | Qt.TextWordWrap, title_with_year)
        
        # Calculate text area
        fm = QFontMetrics(title_font)
        title_height = fm.boundingRect(title_rect, Qt.AlignTop | Qt.TextWordWrap, title).height()
        
        # Parse and draw text with different fonts for headers vs content
        y_position = 20 + title_height + 30
        text_rect_area = QRect(20, y_position, width - 40, height - y_position - 20)
        
        # Save the clip region to prevent overflow
        painter.setClipRect(text_rect_area)
        
        # Split text by lines and render with appropriate fonts
        lines = text.split('\n')
        current_y = y_position
        line_spacing = 8
        
        for line in lines:
            if current_y >= height - 20:  # Stop if we've reached the bottom
                break
            
            # Skip empty lines at the start but keep them for spacing elsewhere
            if not line.strip() and current_y == y_position:
                continue
            
            # Check if line contains a header with content (e.g., "Director: John Smith")
            # Split it into header and content
            if ':' in line and not line.strip().startswith('====='):
                parts = line.split(':', 1)
                if len(parts) == 2 and len(parts[0].strip()) < 50:
                    # This is a "Label: Content" line - render separately
                    label = parts[0].strip() + ':'
                    content = parts[1].strip()
                    
                    # Draw the label in header font
                    painter.setFont(header_font)
                    painter.setPen(QColor(240, 240, 240))
                    fm = QFontMetrics(header_font)
                    line_rect = QRect(20, current_y, width - 40, fm.height())
                    painter.drawText(line_rect, Qt.AlignTop, label)
                    current_y += fm.height() + 4
                    
                    # Draw the content in body font if not empty
                    if content:
                        painter.setFont(text_font)
                        painter.setPen(QColor(200, 200, 200))
                        fm = QFontMetrics(text_font)
                        line_rect = QRect(20, current_y, width - 40, fm.height() * 3)
                        bounding_rect = painter.boundingRect(line_rect, Qt.AlignTop | Qt.TextWordWrap, content)
                        painter.drawText(line_rect, Qt.AlignTop | Qt.TextWordWrap, content)
                        current_y += bounding_rect.height() + line_spacing
                    continue
                
            # Check if this is a header line (special lines or very short lines ending with :)
            is_header = (line.strip().endswith(':') and len(line.strip()) < 50)
            
            if is_header:
                painter.setFont(header_font)
                painter.setPen(QColor(240, 240, 240))
                fm = QFontMetrics(header_font)
            else:
                painter.setFont(text_font)
                painter.setPen(QColor(200, 200, 200))
                fm = QFontMetrics(text_font)
            
            # Draw the line
            line_rect = QRect(20, current_y, width - 40, fm.height() * 3)  # Allow for wrapping
            bounding_rect = painter.boundingRect(line_rect, Qt.AlignTop | Qt.TextWordWrap, line)
            painter.drawText(line_rect, Qt.AlignTop | Qt.TextWordWrap, line)
            
            # Move y position down by the actual height used
            current_y += bounding_rect.height() + line_spacing
        
        # MUST end painter before creating OpenGL texture
        painter.end()
        
        # Make a copy to ensure QImage is fully detached from painter
        image_copy = image.copy()
        
        # Convert QImage to OpenGL texture
        texture_id = self.createTextureFromQImage(image_copy)
        
        print(f"  Created texture ID: {texture_id}")
        
        # Cache the texture
        if texture_id:
            self._text_texture_cache[cache_key] = texture_id
        
        return texture_id

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_MULTISAMPLE)
        glEnable(GL_LINE_SMOOTH)  # Smooth lines
        glEnable(GL_POLYGON_SMOOTH)  # Smooth polygon edges
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
        glHint(GL_POLYGON_SMOOTH_HINT, GL_NICEST)
        glHint(GL_PERSPECTIVE_CORRECTION_HINT, GL_NICEST)  # Best perspective correction
        glClearColor(0.0, 0.0, 0.0, 1.0)  # Pure black background
        
        # Enable blending for transparency/opacity effects
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        # Compile and link shader program for per-pixel lighting
        try:
            vertex_shader = compileShader(VERTEX_SHADER, GL_VERTEX_SHADER)
            fragment_shader = compileShader(FRAGMENT_SHADER, GL_FRAGMENT_SHADER)
            self.shader_program = compileProgram(vertex_shader, fragment_shader)
            
            # Get uniform locations
            self.uniform_texture = glGetUniformLocation(self.shader_program, "textureSampler")
            self.uniform_use_texture = glGetUniformLocation(self.shader_program, "useTexture")
            self.uniform_light_pos = glGetUniformLocation(self.shader_program, "lightPosition")
            self.uniform_light_dir = glGetUniformLocation(self.shader_program, "lightDirection")
            self.uniform_spot_cutoff = glGetUniformLocation(self.shader_program, "spotCutoff")
            self.uniform_spot_exponent = glGetUniformLocation(self.shader_program, "spotExponent")
            self.uniform_light_diffuse = glGetUniformLocation(self.shader_program, "lightDiffuse")
            self.uniform_light_specular = glGetUniformLocation(self.shader_program, "lightSpecular")
            self.uniform_material_shininess = glGetUniformLocation(self.shader_program, "materialShininess")
            self.uniform_material_specular = glGetUniformLocation(self.shader_program, "materialSpecular")
            self.uniform_constant_atten = glGetUniformLocation(self.shader_program, "constantAtten")
            self.uniform_linear_atten = glGetUniformLocation(self.shader_program, "linearAtten")
            self.uniform_quadratic_atten = glGetUniformLocation(self.shader_program, "quadraticAtten")
        except Exception as e:
            print(f"Shader compilation failed: {e}")
            self.shader_program = None
        
        self.texture_id = None
        
        # Initialize display list cache mutex
        self._box_cache_mutex = self.QMutex()
        
        # Pre-compile box geometry into a display list for reuse
        self._compileBoxDisplayList()

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        # Use current FOV if adjusted, otherwise use initial FOV
        fov = getattr(self, 'current_fov', self.INITIAL_FOV)
        # Increased far plane to 500.0 to accommodate max camera_z of 30.0
        gluPerspective(fov, w / h if h != 0 else 1, 0.1, 500.0)
        glMatrixMode(GL_MODELVIEW)

    def _compileBoxDisplayList(self):
        """Pre-compile the box geometry (sides, edges, corners) into a display list.
        This is called once at init and reused for all boxes. Only textures change per box."""
        
        # Create a display list
        self._box_display_list = glGenLists(1)
        
        # We'll compile a unit box (1x1x1) that can be scaled
        # Width, height, depth will all be 1.0
        # Chamfer will be proportional
        width = height = depth = 1.0
        chamfer = min(width, height, depth) * 0.025
        
        half_w = width / 2
        half_h = height / 2
        half_d = depth / 2
        
        glNewList(self._box_display_list, GL_COMPILE)
        
        # NOTE: Front and back faces with textures are drawn separately
        # This display list contains only the non-textured geometry (edges, corners, sides)
        
        # Front face chamfer edges - batched for performance
        glColor3f(0.35, 0.35, 0.35)
        glBegin(GL_QUADS)
        # Top edge chamfer
        glNormal3f(0.0, 0.707, 0.707)
        glVertex3f(-half_w + chamfer, half_h - chamfer, half_d)
        glVertex3f(half_w - chamfer, half_h - chamfer, half_d)
        glVertex3f(half_w - chamfer, half_h, half_d - chamfer)
        glVertex3f(-half_w + chamfer, half_h, half_d - chamfer)
        # Bottom edge chamfer
        glNormal3f(0.0, -0.707, 0.707)
        glVertex3f(-half_w + chamfer, -half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h + chamfer, half_d)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, half_d)
        # Left edge chamfer
        glNormal3f(-0.707, 0.0, 0.707)
        glVertex3f(-half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, half_d)
        glVertex3f(-half_w + chamfer, half_h - chamfer, half_d)
        glVertex3f(-half_w, half_h - chamfer, half_d - chamfer)
        # Right edge chamfer
        glNormal3f(0.707, 0.0, 0.707)
        glVertex3f(half_w - chamfer, -half_h + chamfer, half_d)
        glVertex3f(half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(half_w - chamfer, half_h - chamfer, half_d)
        glEnd()
        
        # Front face corner chamfers (4 corners) - batched triangles
        glBegin(GL_TRIANGLES)
        # Top-left corner
        glNormal3f(-0.577, 0.577, 0.577)
        glVertex3f(-half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(-half_w + chamfer, half_h, half_d - chamfer)
        glVertex3f(-half_w + chamfer, half_h - chamfer, half_d)
        # Top-right corner
        glNormal3f(0.577, 0.577, 0.577)
        glVertex3f(half_w - chamfer, half_h, half_d - chamfer)
        glVertex3f(half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(half_w - chamfer, half_h - chamfer, half_d)
        # Bottom-left corner
        glNormal3f(-0.577, -0.577, 0.577)
        glVertex3f(-half_w + chamfer, -half_h, half_d - chamfer)
        glVertex3f(-half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, half_d)
        # Bottom-right corner
        glNormal3f(0.577, -0.577, 0.577)
        glVertex3f(half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h + chamfer, half_d)
        glEnd()
        
        # Back face chamfer edges - batched for performance
        glColor3f(0.18, 0.18, 0.18)
        glBegin(GL_QUADS)
        # Top edge chamfer
        glNormal3f(0.0, 0.707, -0.707)
        glVertex3f(-half_w + chamfer, half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h - chamfer, -half_d)
        glVertex3f(-half_w + chamfer, half_h - chamfer, -half_d)
        # Bottom edge chamfer
        glNormal3f(0.0, -0.707, -0.707)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, -half_d)
        glVertex3f(half_w - chamfer, -half_h + chamfer, -half_d)
        glVertex3f(half_w - chamfer, -half_h, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, -half_h, -half_d + chamfer)
        # Left edge chamfer
        glNormal3f(-0.707, 0.0, -0.707)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, -half_d)
        glVertex3f(-half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(-half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, half_h - chamfer, -half_d)
        # Right edge chamfer
        glNormal3f(0.707, 0.0, -0.707)
        glVertex3f(half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(half_w - chamfer, -half_h + chamfer, -half_d)
        glVertex3f(half_w - chamfer, half_h - chamfer, -half_d)
        glVertex3f(half_w, half_h - chamfer, -half_d + chamfer)
        glEnd()
        
        # Back face corner chamfers (4 corners) - batched triangles
        glBegin(GL_TRIANGLES)
        # Top-left corner
        glNormal3f(-0.577, 0.577, -0.577)
        glVertex3f(-half_w + chamfer, half_h, -half_d + chamfer)
        glVertex3f(-half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, half_h - chamfer, -half_d)
        # Top-right corner
        glNormal3f(0.577, 0.577, -0.577)
        glVertex3f(half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h - chamfer, -half_d)
        # Bottom-left corner
        glNormal3f(-0.577, -0.577, -0.577)
        glVertex3f(-half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, -half_h, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, -half_d)
        # Bottom-right corner
        glNormal3f(0.577, -0.577, -0.577)
        glVertex3f(half_w - chamfer, -half_h, -half_d + chamfer)
        glVertex3f(half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(half_w - chamfer, -half_h + chamfer, -half_d)
        glEnd()
        
        # Top face - chamfered (main surface inset from edges)
        glColor3f(0.15, 0.15, 0.15)
        glBegin(GL_QUADS)
        glNormal3f(0.0, 1.0, 0.0)  # Normal pointing up
        glVertex3f(-half_w + chamfer, half_h, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, half_h, -half_d + chamfer)
        glEnd()
        
        # Top face edge chamfers - batched
        glBegin(GL_QUADS)
        # Front-top edge
        glNormal3f(0.0, 0.707, 0.707)
        glVertex3f(-half_w + chamfer, half_h - chamfer, half_d)
        glVertex3f(half_w - chamfer, half_h - chamfer, half_d)
        glVertex3f(half_w - chamfer, half_h, half_d - chamfer)
        glVertex3f(-half_w + chamfer, half_h, half_d - chamfer)
        # Back-top edge
        glNormal3f(0.0, 0.707, -0.707)
        glVertex3f(-half_w + chamfer, half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h - chamfer, -half_d)
        glVertex3f(-half_w + chamfer, half_h - chamfer, -half_d)
        # Left-top edge
        glNormal3f(-0.707, 0.707, 0.0)
        glVertex3f(-half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, half_h, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, half_h, half_d - chamfer)
        glVertex3f(-half_w, half_h - chamfer, half_d - chamfer)
        # Right-top edge
        glNormal3f(0.707, 0.707, 0.0)
        glVertex3f(half_w - chamfer, half_h, -half_d + chamfer)
        glVertex3f(half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(half_w - chamfer, half_h, half_d - chamfer)
        glEnd()
        
        # Top face corner chamfers - batched triangles
        glBegin(GL_TRIANGLES)
        # Front-left-top corner
        glNormal3f(-0.577, 0.577, 0.577)
        glVertex3f(-half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(-half_w + chamfer, half_h, half_d - chamfer)
        glVertex3f(-half_w + chamfer, half_h - chamfer, half_d)
        # Front-right-top corner
        glNormal3f(0.577, 0.577, 0.577)
        glVertex3f(half_w - chamfer, half_h, half_d - chamfer)
        glVertex3f(half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(half_w - chamfer, half_h - chamfer, half_d)
        # Back-left-top corner
        glNormal3f(-0.577, 0.577, -0.577)
        glVertex3f(-half_w + chamfer, half_h, -half_d + chamfer)
        glVertex3f(-half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, half_h - chamfer, -half_d)
        # Back-right-top corner
        glNormal3f(0.577, 0.577, -0.577)
        glVertex3f(half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h - chamfer, -half_d)
        glEnd()
        
        # Bottom face - chamfered (main surface inset from edges)
        glColor3f(0.15, 0.15, 0.15)
        glBegin(GL_QUADS)
        glNormal3f(0.0, -1.0, 0.0)  # Normal pointing down
        glVertex3f(-half_w + chamfer, -half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, -half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, -half_h, half_d - chamfer)
        glVertex3f(-half_w + chamfer, -half_h, half_d - chamfer)
        glEnd()
        
        # Bottom face edge chamfers - batched
        glBegin(GL_QUADS)
        # Front-bottom edge
        glNormal3f(0.0, -0.707, 0.707)
        glVertex3f(-half_w + chamfer, -half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h + chamfer, half_d)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, half_d)
        # Back-bottom edge
        glNormal3f(0.0, -0.707, -0.707)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, -half_d)
        glVertex3f(half_w - chamfer, -half_h + chamfer, -half_d)
        glVertex3f(half_w - chamfer, -half_h, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, -half_h, -half_d + chamfer)
        # Left-bottom edge
        glNormal3f(-0.707, -0.707, 0.0)
        glVertex3f(-half_w + chamfer, -half_h, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, -half_h, half_d - chamfer)
        glVertex3f(-half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(-half_w, -half_h + chamfer, -half_d + chamfer)
        # Right-bottom edge
        glNormal3f(0.707, -0.707, 0.0)
        glVertex3f(half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h, -half_d + chamfer)
        glEnd()
        
        # Bottom face corner chamfers - batched triangles
        glBegin(GL_TRIANGLES)
        # Front-left-bottom corner
        glNormal3f(-0.577, -0.577, 0.577)
        glVertex3f(-half_w + chamfer, -half_h, half_d - chamfer)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, half_d)
        glVertex3f(-half_w, -half_h + chamfer, half_d - chamfer)
        # Front-right-bottom corner
        glNormal3f(0.577, -0.577, 0.577)
        glVertex3f(half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h + chamfer, half_d)
        glVertex3f(half_w - chamfer, -half_h, half_d - chamfer)
        # Back-left-bottom corner
        glNormal3f(-0.577, -0.577, -0.577)
        glVertex3f(-half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, -half_d)
        glVertex3f(-half_w + chamfer, -half_h, -half_d + chamfer)
        # Back-right-bottom corner
        glNormal3f(0.577, -0.577, -0.577)
        glVertex3f(half_w - chamfer, -half_h + chamfer, -half_d)
        glVertex3f(half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(half_w - chamfer, -half_h, -half_d + chamfer)
        glEnd()
        
        # Left and right face chamfers - batched
        glColor3f(0.25, 0.25, 0.25)
        glBegin(GL_QUADS)
        # Left face
        glNormal3f(-1.0, 0.0, 0.0)
        glVertex3f(-half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(-half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(-half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(-half_w, half_h - chamfer, -half_d + chamfer)
        # Right face
        glNormal3f(1.0, 0.0, 0.0)
        glVertex3f(half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(half_w, -half_h + chamfer, half_d - chamfer)
        glEnd()
        
        glEndList()

    def drawGroundPlane(self, quad_h):
        """Draw a large ground plane that the VHS boxes sit on.
        
        Args:
            quad_h: Height of the VHS box quad (used to position the ground plane)
        """
        # Ground plane sits at the bottom of the boxes
        ground_y = -quad_h / 2
        
        # Extend the plane 10000 units in all directions
        plane_size = 10000.0
        
        # Dark ground color - very dark gray, almost black
        ground_color = (0.05, 0.05, 0.05)
        
        glColor3f(*ground_color)
        glBegin(GL_QUADS)
        glNormal3f(0.0, 1.0, 0.0)  # Normal pointing up
        glVertex3f(-plane_size, ground_y, -plane_size)
        glVertex3f(plane_size, ground_y, -plane_size)
        glVertex3f(plane_size, ground_y, plane_size)
        glVertex3f(-plane_size, ground_y, plane_size)
        glEnd()

    def drawVHSBox(self, width, height, texture_id, back_texture_id=None, image_aspect=None):
        """Draw a 3D VHS box with the cover texture on front, text on back, and solid sides with chamfered edges
        
        Args:
            width: Width of the box
            height: Height of the box
            texture_id: OpenGL texture ID for the front cover
            back_texture_id: Optional OpenGL texture ID for back (plot/synopsis text)
            image_aspect: Optional aspect ratio of the source image (width/height)
        """
        # VHS depth is approximately 1 inch (25mm) relative to typical 7.5" height
        # Using a depth ratio of about 0.13 (1/7.5)
        depth = height * 0.13
        
        # Chamfer size - small bevel on edges (about 2-3% of smallest dimension)
        chamfer = min(width, height, depth) * 0.025
        
        half_w = width / 2
        half_h = height / 2
        half_d = depth / 2
        
        # Front face (with texture or placeholder) - chamfered version
        if texture_id and texture_id != 0:
            glBindTexture(GL_TEXTURE_2D, texture_id)
            glEnable(GL_TEXTURE_2D)
            
            # Tell shader to use texture
            if self.shader_program:
                glUniform1i(self.uniform_use_texture, 1)
            
            # Set texture to border color (dark grey to match box sides) outside texture region
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER)
            border_color = [0.2, 0.2, 0.2, 1.0]
            glTexParameterfv(GL_TEXTURE_2D, GL_TEXTURE_BORDER_COLOR, border_color)
            
            # Calculate UV coordinates to fit image within box while maintaining aspect ratio
            # Box aspect ratio
            box_aspect = width / height if height != 0 else 1.0
            
            # Default to box aspect if image aspect not provided
            if image_aspect is None:
                image_aspect = box_aspect
            
            # Calculate UV scaling to fit the largest dimension
            u_scale = 1.0
            v_scale = 1.0
            
            if image_aspect > box_aspect:
                # Image is wider - scale V (height) to fit
                v_scale = image_aspect / box_aspect
            else:
                # Image is taller - scale U (width) to fit
                u_scale = box_aspect / image_aspect
            
            # Center the scaled UVs
            u_min = (1.0 - u_scale) / 2.0
            u_max = (1.0 + u_scale) / 2.0
            v_min = (1.0 - v_scale) / 2.0
            v_max = (1.0 + v_scale) / 2.0
            
            # Don't override color here - use whatever was set before (for dimming effect)
            # Main front face (inset by chamfer)
            glBegin(GL_QUADS)
            glNormal3f(0.0, 0.0, 1.0)  # Normal pointing forward
            glTexCoord2f(u_min, v_max); glVertex3f(-half_w + chamfer, -half_h + chamfer, half_d)
            glTexCoord2f(u_max, v_max); glVertex3f(half_w - chamfer, -half_h + chamfer, half_d)
            glTexCoord2f(u_max, v_min); glVertex3f(half_w - chamfer, half_h - chamfer, half_d)
            glTexCoord2f(u_min, v_min); glVertex3f(-half_w + chamfer, half_h - chamfer, half_d)
            glEnd()
            glDisable(GL_TEXTURE_2D)
            if self.shader_program:
                glUniform1i(self.uniform_use_texture, 0)
        else:
            # No texture - draw placeholder front face (inset by chamfer)
            if self.shader_program:
                glUniform1i(self.uniform_use_texture, 0)
            glColor3f(*self.BOX_COLOR)
            glBegin(GL_QUADS)
            glNormal3f(0.0, 0.0, 1.0)
            glVertex3f(-half_w + chamfer, -half_h + chamfer, half_d)
            glVertex3f(half_w - chamfer, -half_h + chamfer, half_d)
            glVertex3f(half_w - chamfer, half_h - chamfer, half_d)
            glVertex3f(-half_w + chamfer, half_h - chamfer, half_d)
            glEnd()
        
        # Front face chamfer edges - batched for performance
        # Slightly higher shininess for chamfered edges to catch light
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 48.0)
        glColor3f(*self.BOX_COLOR)
        glBegin(GL_QUADS)
        # Top edge chamfer
        glNormal3f(0.0, 0.707, 0.707)
        glVertex3f(-half_w + chamfer, half_h - chamfer, half_d)
        glVertex3f(half_w - chamfer, half_h - chamfer, half_d)
        glVertex3f(half_w - chamfer, half_h, half_d - chamfer)
        glVertex3f(-half_w + chamfer, half_h, half_d - chamfer)
        # Bottom edge chamfer
        glNormal3f(0.0, -0.707, 0.707)
        glVertex3f(-half_w + chamfer, -half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h + chamfer, half_d)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, half_d)
        # Left edge chamfer
        glNormal3f(-0.707, 0.0, 0.707)
        glVertex3f(-half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, half_d)
        glVertex3f(-half_w + chamfer, half_h - chamfer, half_d)
        glVertex3f(-half_w, half_h - chamfer, half_d - chamfer)
        # Right edge chamfer
        glNormal3f(0.707, 0.0, 0.707)
        glVertex3f(half_w - chamfer, -half_h + chamfer, half_d)
        glVertex3f(half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(half_w - chamfer, half_h - chamfer, half_d)
        glEnd()
        
        # Front face corner chamfers (4 corners) - batched triangles
        glBegin(GL_TRIANGLES)
        # Top-left corner
        glNormal3f(-0.577, 0.577, 0.577)
        glVertex3f(-half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(-half_w + chamfer, half_h, half_d - chamfer)
        glVertex3f(-half_w + chamfer, half_h - chamfer, half_d)
        # Top-right corner
        glNormal3f(0.577, 0.577, 0.577)
        glVertex3f(half_w - chamfer, half_h, half_d - chamfer)
        glVertex3f(half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(half_w - chamfer, half_h - chamfer, half_d)
        # Bottom-left corner
        glNormal3f(-0.577, -0.577, 0.577)
        glVertex3f(-half_w + chamfer, -half_h, half_d - chamfer)
        glVertex3f(-half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, half_d)
        # Bottom-right corner
        glNormal3f(0.577, -0.577, 0.577)
        glVertex3f(half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h + chamfer, half_d)
        glEnd()
        
        # Back face (with text texture if available, otherwise dark gray) - chamfered version
        if back_texture_id and back_texture_id != 0:
            glBindTexture(GL_TEXTURE_2D, back_texture_id)
            glEnable(GL_TEXTURE_2D)
            if self.shader_program:
                glUniform1i(self.uniform_use_texture, 1)
            glColor3f(1.0, 1.0, 1.0)  # Full brightness for text visibility
            glBegin(GL_QUADS)
            glNormal3f(0.0, 0.0, -1.0)  # Normal pointing backward
            # Flip texture coordinates to read correctly from back (inset by chamfer)
            glTexCoord2f(1.0, 1.0); glVertex3f(-half_w + chamfer, -half_h + chamfer, -half_d)
            glTexCoord2f(1.0, 0.0); glVertex3f(-half_w + chamfer, half_h - chamfer, -half_d)
            glTexCoord2f(0.0, 0.0); glVertex3f(half_w - chamfer, half_h - chamfer, -half_d)
            glTexCoord2f(0.0, 1.0); glVertex3f(half_w - chamfer, -half_h + chamfer, -half_d)
            glEnd()
            glDisable(GL_TEXTURE_2D)
            if self.shader_program:
                glUniform1i(self.uniform_use_texture, 0)
        else:
            # No text texture - draw solid dark gray back (inset by chamfer)
            if self.shader_program:
                glUniform1i(self.uniform_use_texture, 0)
            glColor3f(*self.BOX_COLOR)
            glBegin(GL_QUADS)
            glNormal3f(0.0, 0.0, -1.0)  # Normal pointing backward
            glVertex3f(-half_w + chamfer, -half_h + chamfer, -half_d)
            glVertex3f(-half_w + chamfer, half_h - chamfer, -half_d)
            glVertex3f(half_w - chamfer, half_h - chamfer, -half_d)
            glVertex3f(half_w - chamfer, -half_h + chamfer, -half_d)
            glEnd()
        
        # Back face chamfer edges - batched for performance
        if self.shader_program:
            glUniform1i(self.uniform_use_texture, 0)
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 48.0)
        glColor3f(*self.BOX_COLOR)
        glBegin(GL_QUADS)
        # Top edge chamfer
        glNormal3f(0.0, 0.707, -0.707)
        glVertex3f(-half_w + chamfer, half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h - chamfer, -half_d)
        glVertex3f(-half_w + chamfer, half_h - chamfer, -half_d)
        # Bottom edge chamfer
        glNormal3f(0.0, -0.707, -0.707)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, -half_d)
        glVertex3f(half_w - chamfer, -half_h + chamfer, -half_d)
        glVertex3f(half_w - chamfer, -half_h, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, -half_h, -half_d + chamfer)
        # Left edge chamfer
        glNormal3f(-0.707, 0.0, -0.707)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, -half_d)
        glVertex3f(-half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(-half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, half_h - chamfer, -half_d)
        # Right edge chamfer
        glNormal3f(0.707, 0.0, -0.707)
        glVertex3f(half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(half_w - chamfer, -half_h + chamfer, -half_d)
        glVertex3f(half_w - chamfer, half_h - chamfer, -half_d)
        glVertex3f(half_w, half_h - chamfer, -half_d + chamfer)
        glEnd()
        
        # Back face corner chamfers (4 corners) - batched triangles
        glBegin(GL_TRIANGLES)
        # Top-left corner
        glNormal3f(-0.577, 0.577, -0.577)
        glVertex3f(-half_w + chamfer, half_h, -half_d + chamfer)
        glVertex3f(-half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, half_h - chamfer, -half_d)
        # Top-right corner
        glNormal3f(0.577, 0.577, -0.577)
        glVertex3f(half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h - chamfer, -half_d)
        # Bottom-left corner
        glNormal3f(-0.577, -0.577, -0.577)
        glVertex3f(-half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, -half_h, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, -half_d)
        # Bottom-right corner
        glNormal3f(0.577, -0.577, -0.577)
        glVertex3f(half_w - chamfer, -half_h, -half_d + chamfer)
        glVertex3f(half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(half_w - chamfer, -half_h + chamfer, -half_d)
        glEnd()
        
        # Top face - chamfered (main surface inset from edges)
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 32.0)
        glColor3f(*self.BOX_COLOR)
        glBegin(GL_QUADS)
        glNormal3f(0.0, 1.0, 0.0)  # Normal pointing up
        glVertex3f(-half_w + chamfer, half_h, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, half_h, -half_d + chamfer)
        glEnd()
        
        # Top face edge chamfers - batched
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 48.0)
        glBegin(GL_QUADS)
        # Front-top edge
        glNormal3f(0.0, 0.707, 0.707)
        glVertex3f(-half_w + chamfer, half_h - chamfer, half_d)
        glVertex3f(half_w - chamfer, half_h - chamfer, half_d)
        glVertex3f(half_w - chamfer, half_h, half_d - chamfer)
        glVertex3f(-half_w + chamfer, half_h, half_d - chamfer)
        # Back-top edge
        glNormal3f(0.0, 0.707, -0.707)
        glVertex3f(-half_w + chamfer, half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h - chamfer, -half_d)
        glVertex3f(-half_w + chamfer, half_h - chamfer, -half_d)
        # Left-top edge
        glNormal3f(-0.707, 0.707, 0.0)
        glVertex3f(-half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, half_h, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, half_h, half_d - chamfer)
        glVertex3f(-half_w, half_h - chamfer, half_d - chamfer)
        # Right-top edge
        glNormal3f(0.707, 0.707, 0.0)
        glVertex3f(half_w - chamfer, half_h, -half_d + chamfer)
        glVertex3f(half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(half_w - chamfer, half_h, half_d - chamfer)
        glEnd()
        
        # Top face corner chamfers - batched triangles
        glBegin(GL_TRIANGLES)
        # Front-left-top corner
        glNormal3f(-0.577, 0.577, 0.577)
        glVertex3f(-half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(-half_w + chamfer, half_h, half_d - chamfer)
        glVertex3f(-half_w + chamfer, half_h - chamfer, half_d)
        # Front-right-top corner
        glNormal3f(0.577, 0.577, 0.577)
        glVertex3f(half_w - chamfer, half_h, half_d - chamfer)
        glVertex3f(half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(half_w - chamfer, half_h - chamfer, half_d)
        # Back-left-top corner
        glNormal3f(-0.577, 0.577, -0.577)
        glVertex3f(-half_w + chamfer, half_h, -half_d + chamfer)
        glVertex3f(-half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, half_h - chamfer, -half_d)
        # Back-right-top corner
        glNormal3f(0.577, 0.577, -0.577)
        glVertex3f(half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, half_h - chamfer, -half_d)
        glEnd()
        
        # Bottom face - chamfered (main surface inset from edges)
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 32.0)
        glColor3f(*self.BOX_COLOR)
        glBegin(GL_QUADS)
        glNormal3f(0.0, -1.0, 0.0)  # Normal pointing down
        glVertex3f(-half_w + chamfer, -half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, -half_h, -half_d + chamfer)
        glVertex3f(half_w - chamfer, -half_h, half_d - chamfer)
        glVertex3f(-half_w + chamfer, -half_h, half_d - chamfer)
        glEnd()
        
        # Bottom face edge chamfers - batched
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 48.0)
        glBegin(GL_QUADS)
        # Front-bottom edge
        glNormal3f(0.0, -0.707, 0.707)
        glVertex3f(-half_w + chamfer, -half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h + chamfer, half_d)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, half_d)
        # Back-bottom edge
        glNormal3f(0.0, -0.707, -0.707)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, -half_d)
        glVertex3f(half_w - chamfer, -half_h + chamfer, -half_d)
        glVertex3f(half_w - chamfer, -half_h, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, -half_h, -half_d + chamfer)
        # Left-bottom edge
        glNormal3f(-0.707, -0.707, 0.0)
        glVertex3f(-half_w + chamfer, -half_h, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, -half_h, half_d - chamfer)
        glVertex3f(-half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(-half_w, -half_h + chamfer, -half_d + chamfer)
        # Right-bottom edge
        glNormal3f(0.707, -0.707, 0.0)
        glVertex3f(half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h, -half_d + chamfer)
        glEnd()
        
        # Bottom face corner chamfers - batched triangles
        glBegin(GL_TRIANGLES)
        # Front-left-bottom corner
        glNormal3f(-0.577, -0.577, 0.577)
        glVertex3f(-half_w + chamfer, -half_h, half_d - chamfer)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, half_d)
        glVertex3f(-half_w, -half_h + chamfer, half_d - chamfer)
        # Front-right-bottom corner
        glNormal3f(0.577, -0.577, 0.577)
        glVertex3f(half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(half_w - chamfer, -half_h + chamfer, half_d)
        glVertex3f(half_w - chamfer, -half_h, half_d - chamfer)
        # Back-left-bottom corner
        glNormal3f(-0.577, -0.577, -0.577)
        glVertex3f(-half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(-half_w + chamfer, -half_h + chamfer, -half_d)
        glVertex3f(-half_w + chamfer, -half_h, -half_d + chamfer)
        # Back-right-bottom corner
        glNormal3f(0.577, -0.577, -0.577)
        glVertex3f(half_w - chamfer, -half_h + chamfer, -half_d)
        glVertex3f(half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(half_w - chamfer, -half_h, -half_d + chamfer)
        glEnd()
        
        # Left and right face chamfers - batched
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 40.0)
        glColor3f(*self.BOX_COLOR)
        glBegin(GL_QUADS)
        # Left face
        glNormal3f(-1.0, 0.0, 0.0)
        glVertex3f(-half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(-half_w, -half_h + chamfer, half_d - chamfer)
        glVertex3f(-half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(-half_w, half_h - chamfer, -half_d + chamfer)
        # Right face
        glNormal3f(1.0, 0.0, 0.0)
        glVertex3f(half_w, -half_h + chamfer, -half_d + chamfer)
        glVertex3f(half_w, half_h - chamfer, -half_d + chamfer)
        glVertex3f(half_w, half_h - chamfer, half_d - chamfer)
        glVertex3f(half_w, -half_h + chamfer, half_d - chamfer)
        glEnd()
        
        # Reset color
        glColor3f(1.0, 1.0, 1.0)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        
        # Apply camera panning
        glTranslatef(self.camera_pan_x, self.camera_pan_y, 0.0)
        
        widget_w = self.width()
        widget_h = self.height()
        if widget_h == 0:
            widget_h = 1
        window_aspect = widget_w / widget_h
        # Define max quad dimensions based on window aspect
        max_quad_h = 1.0
        max_quad_w = window_aspect
        
        import math
        # Use a reference quad height for camera positioning
        current_fov = getattr(self, 'current_fov', self.INITIAL_FOV)
        z = (max_quad_h / 2) / math.tan(math.radians(current_fov / 2))
        camera_z = getattr(self, 'camera_z', 0.0)
        z += camera_z
        
        # Activate shader program for per-pixel lighting
        if self.shader_program:
            glUseProgram(self.shader_program)
            
            # Set up spotlight parameters using class constants
            light_pos_world = [0.0, self.SPOTLIGHT_HEIGHT, -z + self.SPOTLIGHT_FORWARD, 1.0]
            
            # Transform light position to view space using current modelview matrix
            modelview = glGetFloatv(GL_MODELVIEW_MATRIX)
            light_pos_view = [
                modelview[0][0] * light_pos_world[0] + modelview[1][0] * light_pos_world[1] + modelview[2][0] * light_pos_world[2] + modelview[3][0] * light_pos_world[3],
                modelview[0][1] * light_pos_world[0] + modelview[1][1] * light_pos_world[1] + modelview[2][1] * light_pos_world[2] + modelview[3][1] * light_pos_world[3],
                modelview[0][2] * light_pos_world[0] + modelview[1][2] * light_pos_world[1] + modelview[2][2] * light_pos_world[2] + modelview[3][2] * light_pos_world[3]
            ]
            
            # Light direction (straight down)
            light_dir = [0.0, -1.0, 0.0]
            
            # Set shader uniforms using class constants
            glUniform3f(self.uniform_light_pos, light_pos_view[0], light_pos_view[1], light_pos_view[2])
            glUniform3f(self.uniform_light_dir, light_dir[0], light_dir[1], light_dir[2])
            glUniform1f(self.uniform_spot_cutoff, self.SPOTLIGHT_CONE_ANGLE)
            glUniform1f(self.uniform_spot_exponent, self.SPOTLIGHT_EXPONENT)
            glUniform3f(self.uniform_light_diffuse, *self.SPOTLIGHT_DIFFUSE)
            glUniform3f(self.uniform_light_specular, *self.SPOTLIGHT_SPECULAR)
            glUniform1f(self.uniform_material_shininess, self.MATERIAL_SHININESS)
            glUniform3f(self.uniform_material_specular, *self.MATERIAL_SPECULAR)
            glUniform1f(self.uniform_constant_atten, self.SPOTLIGHT_CONSTANT_ATTEN)
            glUniform1f(self.uniform_linear_atten, self.SPOTLIGHT_LINEAR_ATTEN)
            glUniform1f(self.uniform_quadratic_atten, self.SPOTLIGHT_QUADRATIC_ATTEN)
            glUniform1i(self.uniform_texture, 0)  # Texture unit 0
        
        # Draw ground plane first (so boxes render on top)
        # Calculate quad_h for ground plane positioning
        max_quad_h = 1.0
        quad_h_for_ground = max_quad_h * 0.8  # Match the scaling used for boxes in multi-cover mode
        self.drawGroundPlane(quad_h_for_ground)
        
        # Determine how many surrounding covers to show
        # Reduced for better performance with chamfered boxes
        num_surrounding = 10  # 10 left + 1 center + 10 right = 21 total
        
        # Check if dragging for other logic
        is_dragging = (hasattr(self, 'last_mouse_x') and self.last_mouse_x is not None) or \
                     getattr(self, 'is_momentum_scrolling', False) or \
                     abs(getattr(self, 'drag_offset', 0.0)) > 0.01
        show_surrounding = True  # Always show surrounding covers
        
        # Animation: dual covers (only when not showing surrounding covers and not scrolling)
        if getattr(self, '_animating', False) and self._prev_cover_image is not None and not show_surrounding and not getattr(self, '_scrolling', False):
            progress = self._anim_progress
            smooth_progress = progress * progress * (3 - 2 * progress)
            direction = getattr(self, '_anim_direction', 1)
            # Outgoing cover offset (closer to current cover)
            vertical_distance = 1.2  # Reduce from 2.0 to 0.7 for visibility
            if direction == 1:
                prev_y_offset = -(smooth_progress) * vertical_distance
                curr_y_offset = (1.0 - smooth_progress) * vertical_distance
            else:
                prev_y_offset = smooth_progress * vertical_distance
                curr_y_offset = -(1.0 - smooth_progress) * vertical_distance
            
            # Draw previous cover with its own quad dimensions
            glPushMatrix()
            glTranslatef(0.0, prev_y_offset, -z)
            glRotatef(self.y_rotation, 0.0, 1.0, 0.0)
            # Use cached texture and geometry if available
            prev_texture_id = self._prev_texture_id
            prev_back_texture_id = None
            prev_quad_geom = None
            if hasattr(self, '_prev_cover_idx'):
                _, prev_texture_id, prev_back_texture_id, prev_quad_geom = self.getCachedCover(self._prev_cover_idx)
            if prev_texture_id is None and self._prev_cover_image and not self._prev_cover_image.isNull():
                prev_texture_id = self.createTextureFromQImage(self._prev_cover_image)
            
            # Calculate previous cover's quad dimensions using standard aspect ratio
            prev_quad_h = max_quad_h
            prev_quad_w = self.STANDARD_ASPECT_RATIO * prev_quad_h
            if prev_quad_w > max_quad_w:
                prev_quad_w = max_quad_w
                prev_quad_h = prev_quad_w / self.STANDARD_ASPECT_RATIO
            
            # Get image aspect ratio
            prev_img_aspect = None
            if prev_quad_geom:
                prev_img_aspect, _, _ = prev_quad_geom
            elif self._prev_cover_image and not self._prev_cover_image.isNull() and self._prev_cover_image.height() != 0:
                prev_img_aspect = self._prev_cover_image.width() / self._prev_cover_image.height()
            
            if prev_texture_id:
                self.drawVHSBox(prev_quad_w, prev_quad_h, prev_texture_id, prev_back_texture_id, prev_img_aspect)
            glPopMatrix()
            
            # Draw current cover with its own quad dimensions
            glPushMatrix()
            glTranslatef(0.0, curr_y_offset, -z)
            glRotatef(self.y_rotation, 0.0, 1.0, 0.0)
            curr_texture_id = self.texture_id
            curr_back_texture_id = None
            curr_quad_geom = None
            if hasattr(self, '_current_index'):
                _, curr_texture_id, curr_back_texture_id, curr_quad_geom = self.getCachedCover(self._current_index)
            
            # Calculate current cover's quad dimensions using standard aspect ratio
            curr_quad_h = max_quad_h
            curr_quad_w = self.STANDARD_ASPECT_RATIO * curr_quad_h
            if curr_quad_w > max_quad_w:
                curr_quad_w = max_quad_w
                curr_quad_h = curr_quad_w / self.STANDARD_ASPECT_RATIO
            
            # Get image aspect ratio
            curr_img_aspect = None
            if curr_quad_geom:
                curr_img_aspect, _, _ = curr_quad_geom
            elif self.cover_image and not self.cover_image.isNull() and self.cover_image.height() != 0:
                curr_img_aspect = self.cover_image.width() / self.cover_image.height()
            
            if self.cover_image and not self.cover_image.isNull():
                if curr_texture_id is None:
                    curr_texture_id = self.createTextureFromQImage(self.cover_image)
                # Get back texture for current cover
                if curr_back_texture_id is None and hasattr(self, '_model'):
                    try:
                        if hasattr(self, '_proxy_model') and self._proxy_model and self._proxy_model == self._model:
                            proxy_index = self._model.index(self._current_index, 0)
                            source_index = self._model.mapToSource(proxy_index)
                            source_row = source_index.row()
                            source_model = self._model.sourceModel()
                            movie_path = source_model.getPath(source_row)
                            movie_folder = source_model.getFolderName(source_row)
                        else:
                            movie_path = self._model.getPath(self._current_index)
                            movie_folder = self._model.getFolderName(self._current_index)
                        if movie_path and movie_folder:
                            curr_back_texture_id = self.createTextTexture(movie_path, movie_folder)
                    except Exception:
                        pass
                self.drawVHSBox(curr_quad_w, curr_quad_h, curr_texture_id, curr_back_texture_id, curr_img_aspect)
            glPopMatrix()
        else:
            # Multi-cover rendering (always active, even when zoomed in)
            # Always show at least the current cover even if we can't show surrounding ones
            has_index = hasattr(self, '_current_index')
            has_model = hasattr(self, '_model')
            
            if not has_index or not has_model:
                # Fall back to single cover rendering
                glTranslatef(0.0, 0.0, -z)
                glRotatef(self.y_rotation, 0.0, 1.0, 0.0)
                if self.cover_image and not self.cover_image.isNull():
                    if self.texture_id is None:
                        self.texture_id = self.createTextureFromQImage(self.cover_image)
                    quad_h = max_quad_h
                    quad_w = self.STANDARD_ASPECT_RATIO * quad_h
                    if quad_w > max_quad_w:
                        quad_w = max_quad_w
                        quad_h = quad_w / self.STANDARD_ASPECT_RATIO
                    # Get image aspect ratio
                    img_aspect = self.cover_image.width() / self.cover_image.height() if self.cover_image.height() != 0 else None
                    # Get back texture
                    back_tex = None
                    if hasattr(self, '_model') and hasattr(self, '_current_index'):
                        try:
                            movie_path = self._model.getPath(self._current_index)
                            movie_folder = self._model.getFolderName(self._current_index)
                            if movie_path and movie_folder:
                                back_tex = self.createTextTexture(movie_path, movie_folder)
                        except Exception:
                            pass
                    self.drawVHSBox(quad_w, quad_h, self.texture_id, back_tex, img_aspect)
            else:
                vertical_spacing = 0.65  # Fixed spacing between covers (reduced from 0.85 for tighter packing)
                
                # Calculate scroll offset for smooth animation
                scroll_offset = 0.0
                if getattr(self, '_scrolling', False):
                    progress = self._scroll_progress
                    smooth_progress = progress * progress * (3 - 2 * progress)  # Smoothstep
                    index_delta = self._scroll_to - self._scroll_from
                    scroll_offset = index_delta * smooth_progress
                
                # Add drag offset (user is dragging with mouse)
                if hasattr(self, 'drag_offset'):
                    scroll_offset += self.drag_offset
                
                # Expand the range during scrolling to show covers moving in/out
                extra_range = 0
                if getattr(self, '_scrolling', False):
                    extra_range = abs(self._scroll_to - self._scroll_from)
                
                # Draw covers from left to right (farthest to nearest for proper depth)
                covers_drawn = 0
                
                # Build list of visible row indices
                all_visible_rows = []
                if hasattr(self, '_table_view') and self._table_view:
                    # Find ALL visible rows in the entire dataset
                    for idx in range(self._model.rowCount()):
                        if not self._table_view.isRowHidden(idx):
                            all_visible_rows.append(idx)
                    
                    # Find current index position in visible rows
                    try:
                        current_pos = all_visible_rows.index(self._current_index)
                    except ValueError:
                        # Current index is hidden - this shouldn't happen if setModelAndIndex worked correctly
                        # but handle it gracefully by rendering nothing
                        current_pos = -1
                        visible_rows = []
                        return  # Don't render anything until selection is updated
                    
                    # Select surrounding visible rows based on position in the visible list
                    if current_pos >= 0 and all_visible_rows:
                        start_pos = max(0, current_pos - num_surrounding - extra_range)
                        end_pos = min(len(all_visible_rows), current_pos + num_surrounding + extra_range + 1)
                        visible_rows = all_visible_rows[start_pos:end_pos]
                    else:
                        visible_rows = []
                else:
                    # No filtering, use sequential indices
                    visible_rows = []
                    for offset in range(-num_surrounding - extra_range, num_surrounding + extra_range + 1):
                        idx = self._current_index + offset
                        if idx >= 0 and idx < self._model.rowCount():
                            visible_rows.append(idx)
                
                # Now render visible rows
                current_row_pos = visible_rows.index(self._current_index) if self._current_index in visible_rows else 0
                for i, idx in enumerate(visible_rows):
                    offset_from_current = i - current_row_pos
                    
                    # Get cached cover data
                    cover_img, texture_id, back_texture_id, quad_geom = self.getCachedCover(idx)
                    
                    # For current cover (offset_from_current == 0), always try to load if not cached
                    if cover_img is None and offset_from_current == 0:
                        cover_img = self.cover_image
                    
                    # If not cached, try to load it on-demand (with proxy mapping if needed)
                    if cover_img is None:
                        try:
                            # Map proxy index to source index if using proxy model
                            if hasattr(self, '_proxy_model') and self._proxy_model and self._proxy_model == self._model:
                                # _model IS the proxy model, need to map to source
                                proxy_index = self._model.index(idx, 0)
                                source_index = self._model.mapToSource(proxy_index)
                                source_row = source_index.row()
                                # Get cover path from source model
                                source_model = self._model.sourceModel()
                                cover_path = source_model.getCoverPath(source_row)
                            else:
                                # No proxy or model is already source
                                cover_path = self._model.getCoverPath(idx)
                            
                            if cover_path:
                                cover_img = QImage(cover_path)
                                if not cover_img.isNull():
                                    aspect = cover_img.width() / cover_img.height() if cover_img.height() != 0 else 1.0
                                    quad_geom = (aspect, cover_img.width(), cover_img.height())
                        except Exception as e:
                            # Handle case where proxy model changed during rendering
                            continue
                    
                    # Skip if no image available
                    if cover_img is None or cover_img.isNull():
                        continue
                    
                    # Create front texture on-demand if not cached (OpenGL operations must be on main thread)
                    if texture_id is None and cover_img and not cover_img.isNull():
                        texture_id = self.createTextureFromQImage(cover_img)
                    
                    # Create back texture ONLY for current movie (offset_from_current == 0)
                    # since only the current movie can be rotated to show its back
                    if back_texture_id is None and offset_from_current == 0:
                        # Get movie path and folder name for this index
                        try:
                            if hasattr(self, '_proxy_model') and self._proxy_model and self._proxy_model == self._model:
                                proxy_index = self._model.index(idx, 0)
                                source_index = self._model.mapToSource(proxy_index)
                                source_row = source_index.row()
                                source_model = self._model.sourceModel()
                                movie_path = source_model.getPath(source_row)
                                movie_folder = source_model.getFolderName(source_row)
                            else:
                                movie_path = self._model.getPath(idx)
                                movie_folder = self._model.getFolderName(idx)
                            
                            if movie_path and movie_folder:
                                back_texture_id = self.createTextTexture(movie_path, movie_folder)
                        except Exception:
                            pass  # Back texture is optional
                    
                    # Update cache with both textures
                    if texture_id is not None:
                        with self.QMutexLocker(self._cover_cache_mutex):
                            self._cover_cache[idx] = (cover_img, texture_id, back_texture_id, quad_geom)
                    
                    covers_drawn += 1
                    
                    # Calculate quad dimensions using standard aspect ratio
                    quad_h = max_quad_h * 0.8  # Scale down a bit when showing multiple
                    quad_w = self.STANDARD_ASPECT_RATIO * quad_h
                    if quad_w > max_quad_w * 0.8:
                        quad_w = max_quad_w * 0.8
                        quad_h = quad_w / self.STANDARD_ASPECT_RATIO
                    
                    # Get image aspect ratio for proper texture fitting
                    img_aspect = None
                    if quad_geom:
                        img_aspect, _, _ = quad_geom
                    elif cover_img and not cover_img.isNull() and cover_img.height() != 0:
                        img_aspect = cover_img.width() / cover_img.height()
                    
                    # Position the cover horizontally with parabolic arc into z-depth
                    # Apply scroll offset during animation
                    effective_offset = offset_from_current - scroll_offset
                    x_offset = effective_offset * vertical_spacing  # Using same spacing value, but horizontally
                    
                    # Parabolic curve for first 2 covers on each side, then linear extrapolation
                    # Using smaller coefficient for wider, gentler curve
                    parabola_range = 3.0
                    parabola_coef = 0.3  # Reduced from 0.3 for gentler curve
                    
                    abs_offset = abs(effective_offset)
                    if abs_offset <= parabola_range:
                        # Parabolic region: z = coef * x^2
                        z_curve = (effective_offset * effective_offset) * parabola_coef
                        # Derivative for rotation: dz/dx = 2 * coef * x
                        curve_slope = 2 * parabola_coef * effective_offset
                        # Scale up the angle to better match visual alignment
                        curve_angle = math.atan(curve_slope) * (180.0 / math.pi) * 1.1
                    else:
                        # Linear extrapolation from the parabola endpoint
                        # At x = ±parabola_range: z = parabola_coef * parabola_range^2
                        # Slope at that point: dz/dx = 2 * parabola_coef * parabola_range
                        z_at_boundary = parabola_coef * parabola_range * parabola_range
                        slope_at_boundary = 2 * parabola_coef * parabola_range
                        
                        # Linear continuation: z = z_boundary + slope * (|x| - parabola_range)
                        # Keep the sign of effective_offset for proper direction
                        sign = 1 if effective_offset >= 0 else -1
                        distance_beyond = abs_offset - parabola_range
                        z_curve = z_at_boundary + slope_at_boundary * distance_beyond
                        
                        # Angle is constant in linear region (tangent at boundary) - scaled for visual alignment
                        curve_angle = math.atan(slope_at_boundary) * (180.0 / math.pi) * sign * 1.1
                    
                    # Fade covers based on distance from center
                    distance = abs(effective_offset)
                    alpha = max(0.3, 1.0 - (distance * 0.15))  # Fade based on distance
                    
                    glPushMatrix()
                    glTranslatef(x_offset, 0.0, -z - z_curve)  # Move back in z based on curve
                    
                    # Get stored rotation for this movie, default to 0
                    # Use current rotation (which is being animated toward target)
                    movie_rotation = self.movie_rotations.get(idx, 0.0)
                    
                    # Smoothly interpolate rotation based on distance from center
                    # At center (offset 0): full movie_rotation
                    # At offset ±1 or more: rotation goes to 0
                    rotation_factor = max(0.0, 1.0 - abs(effective_offset))
                    
                    # For rotations at 180°, choose rotation direction based on scroll direction
                    if movie_rotation > 90:
                        # Scrolling right (positive offset): rotate counter-clockwise (180 → -180 → 0)
                        # Scrolling left (negative offset): rotate clockwise (180 → 0)
                        if effective_offset > 0:
                            # Exiting right side - go the short way via negative
                            normalized_rotation = movie_rotation - 360
                            current_rotation = normalized_rotation * rotation_factor
                        else:
                            # Exiting left side - go the long way via positive
                            current_rotation = movie_rotation * rotation_factor
                    else:
                        current_rotation = movie_rotation * rotation_factor
                    
                    # Clear rotation from dictionary once it's fully faded out (offset >= 1.0)
                    if hasattr(self, '_rotations_to_clear') and idx in self._rotations_to_clear:
                        if abs(effective_offset) >= 1.0 and idx in self.movie_rotations:
                            del self.movie_rotations[idx]
                            self._rotations_to_clear.discard(idx)
                    
                    glRotatef(current_rotation + curve_angle, 0.0, 1.0, 0.0)
                    
                    # Let lighting handle all visibility - no manual alpha fading
                    glColor4f(1.0, 1.0, 1.0, 1.0)
                    
                    self.drawVHSBox(quad_w, quad_h, texture_id, back_texture_id, img_aspect)
                    
                    glPopMatrix()

    def createTextureFromQImage(self, qimage):
        qimage = qimage.convertToFormat(QImage.Format_RGBA8888)
        width = qimage.width()
        height = qimage.height()
        ptr = qimage.bits()
        ptr.setsize(qimage.byteCount())
        data = np.array(ptr, dtype=np.uint8).reshape((height, width, 4))
        texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        
        # Use mipmaps with trilinear filtering for best quality
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        
        # Enable anisotropic filtering if available for even better quality
        try:
            max_anisotropy = glGetFloatv(GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT)
            glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAX_ANISOTROPY_EXT, max_anisotropy)
        except:
            pass  # Extension not available
        
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
        glGenerateMipmap(GL_TEXTURE_2D)  # Generate mipmaps
        return texture_id

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            # Start camera panning
            self.is_panning = True
            self.pan_start_x = event.x()
            self.pan_start_y = event.y()
            return
        
        if event.button() == Qt.LeftButton:
            self.drag_start_x = event.x()
            self.last_mouse_x = event.x()
            # Don't reset drag_offset - continue from where we left off
            self.is_momentum_scrolling = False
            self.drag_velocity = 0.0
            self.last_drag_time = QTime.currentTime()
            self.drag_history = []
            
            # Stop any ongoing scroll animation
            if hasattr(self, '_scrolling') and self._scrolling:
                self._scrolling = False
                if hasattr(self, '_scroll_timer') and self._scroll_timer:
                    try:
                        self.killTimer(self._scroll_timer)
                    except:
                        pass
                    self._scroll_timer = None
            
            # Stop any ongoing momentum
            if hasattr(self, '_momentum_timer') and self._momentum_timer:
                try:
                    self.killTimer(self._momentum_timer)
                except:
                    pass
                self._momentum_timer = None
            
            # Stop any ongoing settling animation
            if hasattr(self, 'is_settling') and self.is_settling:
                self.is_settling = False
                if hasattr(self, '_settling_timer') and self._settling_timer:
                    try:
                        self.killTimer(self._settling_timer)
                    except:
                        pass
                    self._settling_timer = None

    def mouseMoveEvent(self, event):
        # Handle camera panning with middle button
        if self.is_panning and self.pan_start_x is not None:
            import math
            dx = event.x() - self.pan_start_x
            dy = event.y() - self.pan_start_y
            
            # Convert pixel movement to world space
            z = 3.0 + self.camera_z
            current_fov = getattr(self, 'current_fov', self.INITIAL_FOV)
            fov_rad = math.radians(current_fov)
            view_height = 2.0 * z * math.tan(fov_rad / 2.0)
            aspect = self.width() / self.height() if self.height() != 0 else 1.0
            view_width = view_height * aspect
            
            # Scale factor for converting pixels to world units
            pixels_per_unit_x = self.width() / view_width
            pixels_per_unit_y = self.height() / view_height
            
            # Update camera pan (invert Y for intuitive up/down)
            self.camera_pan_x += dx / pixels_per_unit_x
            self.camera_pan_y -= dy / pixels_per_unit_y
            
            self.pan_start_x = event.x()
            self.pan_start_y = event.y()
            self.update()
            return
        
        # Handle movie scrolling with left button
        if self.last_mouse_x is not None:
            from PyQt5.QtCore import QTime
            import math
            current_time = QTime.currentTime()
            dx = event.x() - self.last_mouse_x
            
            # Convert pixel movement to cover offset
            # We need to calculate how much of the world space one pixel represents
            # at the current camera z and projection settings
            
            # Camera distance from origin
            z = 3.0 + self.camera_z
            
            # FOV, convert to radians
            current_fov = getattr(self, 'current_fov', self.INITIAL_FOV)
            fov_rad = math.radians(current_fov)
            
            # Calculate the width of the view frustum at distance z
            # Using tan(fov/2) * distance * 2
            view_height = 2.0 * z * math.tan(fov_rad / 2.0)
            aspect = self.width() / self.height() if self.height() != 0 else 1.0
            view_width = view_height * aspect
            
            # Pixels per world unit
            pixels_per_unit = self.width() / view_width
            
            # Cover spacing is 0.65 world units (matches vertical_spacing in paintGL)
            spacing = 0.65
            pixels_per_cover = pixels_per_unit * spacing
            
            # Convert mouse movement to cover offset
            # Negative to match intuitive drag direction (drag right = scroll left)
            cover_delta = -dx / pixels_per_cover
            
            # Check boundary before applying delta
            new_offset = self.drag_offset + cover_delta
            
            # Prevent dragging past boundaries
            # Note: Due to the coordinate system and drag offset calculation:
            # - Dragging RIGHT (mouse right) makes covers move right, showing what's on the LEFT (earlier movies)
            # - This creates NEGATIVE offset, which would cycle to NEXT movie (emit -1)
            # - At FIRST movie, we need to BLOCK NEGATIVE offset (can't show earlier movies)
            # - Dragging LEFT (mouse left) makes covers move left, showing what's on the RIGHT (later movies)  
            # - This creates POSITIVE offset, which would cycle to PREVIOUS movie (emit 1)
            # - At LAST movie, we need to BLOCK POSITIVE offset (can't show later movies)
            at_first = self._is_at_boundary(-1)
            at_last = self._is_at_boundary(1)
            
            if at_first and at_last:
                # Only one movie - no dragging at all
                self.drag_offset = 0
                cover_delta = 0
            elif at_first:
                # At first movie - can't show movies before it
                # Block negative offset ONLY (don't let offset go below 0)
                if new_offset < 0:
                    # Clamp to 0, don't allow negative
                    if self.drag_offset > 0:
                        # Currently positive, allow movement toward 0
                        self.drag_offset = max(0, new_offset)
                    else:
                        # Already at 0, block further negative movement
                        self.drag_offset = 0
                    cover_delta = 0
                else:
                    # Positive offset is fine (showing next movies)
                    self.drag_offset += cover_delta
            elif at_last:
                # At last movie - can't show movies after it
                # Block positive offset ONLY (don't let offset go above 0)
                if new_offset > 0:
                    # Clamp to 0, don't allow positive
                    if self.drag_offset < 0:
                        # Currently negative, allow movement toward 0
                        self.drag_offset = min(0, new_offset)
                    else:
                        # Already at 0, block further positive movement
                        self.drag_offset = 0
                    cover_delta = 0
                else:
                    # Negative offset is fine (showing previous movies)
                    self.drag_offset += cover_delta
            else:
                # Not at boundary - allow any direction
                self.drag_offset += cover_delta
            
            # Check if we've dragged past the threshold to cycle to next/previous movie
            # Similar to mouse wheel behavior
            if hasattr(self, '_model') and hasattr(self, '_current_index'):
                threshold = 0.5  # Half a cover width
                if self.drag_offset >= threshold:
                    # Positive offset - moving to next movie (direction +1)
                    if not self._is_at_boundary(1):
                        # Dragged left - move to next movie
                        self.drag_offset -= 1.0
                        self.wheelMovieChange.emit(1)  # Next movie (direction +1)
                    else:
                        # At boundary - clamp offset
                        self.drag_offset = min(self.drag_offset, threshold * 0.9)
                elif self.drag_offset <= -threshold:
                    # Negative offset - moving to previous movie (direction -1)
                    if not self._is_at_boundary(-1):
                        # Dragged right - move to previous movie
                        self.drag_offset += 1.0
                        self.wheelMovieChange.emit(-1)  # Previous movie (direction -1)
                    else:
                        # At boundary - clamp offset
                        self.drag_offset = max(self.drag_offset, -threshold * 0.9)
            
            # Track movement history for velocity calculation
            elapsed = self.last_drag_time.msecsTo(current_time)
            if elapsed > 0:
                self.drag_history.append((cover_delta, elapsed))
                # Keep only recent history (last 100ms)
                total_time = 0
                for i in range(len(self.drag_history) - 1, -1, -1):
                    total_time += self.drag_history[i][1]
                    if total_time > 100:
                        self.drag_history = self.drag_history[i:]
                        break
            
            self.last_mouse_x = event.x()
            self.last_drag_time = current_time
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.is_panning = False
            self.pan_start_x = None
            self.pan_start_y = None
            return
        
        if event.button() == Qt.LeftButton:
            self.last_mouse_x = None
            
            # Calculate velocity from recent drag history
            has_momentum = False
            if len(self.drag_history) > 0:
                total_delta = sum(d[0] for d in self.drag_history)
                total_time = sum(d[1] for d in self.drag_history)
                if total_time > 0:
                    # Velocity in covers per millisecond
                    self.drag_velocity = total_delta / total_time
                    # Apply momentum if velocity is significant
                    if abs(self.drag_velocity) > 0.001:
                        self.is_momentum_scrolling = True
                        has_momentum = True
                        if not hasattr(self, '_momentum_timer') or not self._momentum_timer:
                            self._momentum_timer = self.startTimer(16)  # 60 FPS
            
            # If no momentum, start settling immediately to snap to center
            if not has_momentum and abs(self.drag_offset) > 0.01:
                self.is_settling = True
                self.settling_start_offset = self.drag_offset
                self.settling_progress = 0.0
                self._settling_timer = self.startTimer(16)  # 60 FPS
                from PyQt5.QtCore import QElapsedTimer
                self._settling_elapsed = QElapsedTimer()
                self._settling_elapsed.start()
            
            self.drag_history = []
