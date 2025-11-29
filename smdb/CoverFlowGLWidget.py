from PyQt5.QtWidgets import QOpenGLWidget
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QImage
from OpenGL.GL import *
from OpenGL.GLU import *
import numpy as np
import threading

# Anisotropic filtering extension constants
GL_TEXTURE_MAX_ANISOTROPY_EXT = 0x84FE
GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT = 0x84FF

class CoverFlowGLWidget(QOpenGLWidget):
    import threading
    from PyQt5.QtCore import QMutex, QMutexLocker

    CACHE_RADIUS = 25

    def setModelAndIndex(self, model, current_index):
        # Check if we're just updating the index (same model)
        if hasattr(self, '_model') and self._model == model and hasattr(self, '_current_index'):
            # Store the old index for animation
            old_index = self._current_index
            
            # Check if user is actively dragging
            is_dragging = (hasattr(self, 'last_mouse_x') and self.last_mouse_x is not None) or \
                         (hasattr(self, 'is_momentum_scrolling') and self.is_momentum_scrolling)
            
            # Always animate the transition when index changes (even when zoomed in)
            # BUT skip animation if user is actively dragging
            if old_index != current_index:
                if is_dragging:
                    # User is dragging - just update index silently without animation
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
            for offset in range(-self.CACHE_RADIUS, self.CACHE_RADIUS + 1):
                idx = self._current_index + offset
                if idx < 0 or idx >= self._model.rowCount():
                    continue
                with self.QMutexLocker(self._cover_cache_mutex):
                    if idx in self._cover_cache:
                        continue
                cover_path = self._model.getCoverPath(idx)
                if cover_path:
                    image = QImage(cover_path)
                    quad_geom = None
                    if not image.isNull():
                        # Precompute quad geometry (width, height, aspect)
                        # Texture will be created on-demand in the main thread
                        aspect = image.width() / image.height() if image.height() != 0 else 1.0
                        quad_geom = (aspect, image.width(), image.height())
                    with self.QMutexLocker(self._cover_cache_mutex):
                        # Cache: (image, texture_id, quad_geom) - texture_id created later
                        self._cover_cache[idx] = (image, None, quad_geom)
        threading.Thread(target=cache_worker, daemon=True).start()

    def getCachedCover(self, idx):
        with self.QMutexLocker(self._cover_cache_mutex):
            return self._cover_cache.get(idx, (None, None, None))


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
        if getattr(self, '_animating', False) and hasattr(self, '_anim_timer') and event.timerId() == self._anim_timer:
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
                if hasattr(self, '_pending_cover_image') and self._pending_cover_image:
                    self.set_cover_image(self._pending_cover_image)
                    self._pending_cover_image = None
                # Emit signal to notify that animation is complete
                self.scrollAnimationComplete.emit(self._current_index)
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
                    # Momentum carried us to previous movie
                    self.drag_offset -= 1.0
                    self.wheelMovieChange.emit(1)  # Previous movie
                elif self.drag_offset <= -threshold:
                    # Momentum carried us to next movie
                    self.drag_offset += 1.0
                    self.wheelMovieChange.emit(-1)  # Next movie
            
            # Apply friction
            self.drag_velocity *= friction
            
            # Stop if velocity is very low - just stop, don't snap
            if abs(self.drag_velocity) < 0.0001:
                self.is_momentum_scrolling = False
                try:
                    self.killTimer(self._momentum_timer)
                except:
                    pass
                self._momentum_timer = None
                # Keep the drag_offset where it stopped
                # Don't reset it or trigger any animations
            
            self.update()
    wheelMovieChange = pyqtSignal(int)  # +1 for next, -1 for previous
    scrollAnimationComplete = pyqtSignal(int)  # Emitted when scroll animation completes with the new index
    
    def wheelEvent(self, event):
        # Zoom in/out if Ctrl is held, otherwise animate cover change
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.ControlModifier:
            # Zoom: adjust zoom_level, clamp to reasonable range
            if not hasattr(self, 'zoom_level'):
                self.zoom_level = 0.0
            zoom_step = 0.2
            if delta > 0:
                self.zoom_level -= zoom_step
            elif delta < 0:
                self.zoom_level += zoom_step
            # Clamp zoom_level between -2.0 and 4.0 (increased max for more surrounding covers)
            self.zoom_level = max(-2.0, min(4.0, self.zoom_level))
            self.update()
            event.accept()  # Prevent propagation to parent (no text size change)
        else:
            if delta > 0:
                self.animate_cover_transition(1)
                self.wheelMovieChange.emit(1)
            elif delta < 0:
                self.animate_cover_transition(-1)
                self.wheelMovieChange.emit(-1)
            event.accept()

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
        self.aspect_ratio = 1.0
        self.zoom_level = 0.0  # Camera translation for zoom
        
        # Drag scrolling state
        self.drag_start_x = None
        self.drag_offset = 0.0  # Current drag offset in cover units
        self.drag_velocity = 0.0  # Velocity for momentum
        self.is_momentum_scrolling = False
        self.last_drag_time = None
        self.drag_history = []  # Track recent drag movements for velocity calculation

    def set_cover_image(self, image_path):
        self.cover_image = QImage(image_path)
        self.texture_id = None  # Force recreation of texture for new image
        if not self.cover_image.isNull():
            self.aspect_ratio = self.cover_image.width() / self.cover_image.height()
        self.update()

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
        
        # Enable lighting for 3D depth perception
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        
        # Set up light position and properties
        glLightfv(GL_LIGHT0, GL_POSITION, [0.0, 0.0, 1.0, 0.0])  # Directional light from front
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.3, 0.3, 0.3, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.8, 0.8, 0.8, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [0.5, 0.5, 0.5, 1.0])
        
        self.texture_id = None

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        # Use a moderate FOV and set near/far for a good fit
        gluPerspective(30.0, w / h if h != 0 else 1, 0.1, 10.0)
        glMatrixMode(GL_MODELVIEW)

    def drawVHSBox(self, width, height, texture_id):
        """Draw a 3D VHS box with the cover texture on front, and solid sides"""
        # VHS depth is approximately 1 inch (25mm) relative to typical 7.5" height
        # Using a depth ratio of about 0.13 (1/7.5)
        depth = height * 0.13
        
        half_w = width / 2
        half_h = height / 2
        half_d = depth / 2
        
        # Front face (with texture)
        if texture_id:
            glBindTexture(GL_TEXTURE_2D, texture_id)
            glEnable(GL_TEXTURE_2D)
            glColor3f(1.0, 1.0, 1.0)  # White to show texture properly
            glBegin(GL_QUADS)
            glNormal3f(0.0, 0.0, 1.0)  # Normal pointing forward
            glTexCoord2f(0.0, 1.0); glVertex3f(-half_w, -half_h, half_d)
            glTexCoord2f(1.0, 1.0); glVertex3f(half_w, -half_h, half_d)
            glTexCoord2f(1.0, 0.0); glVertex3f(half_w, half_h, half_d)
            glTexCoord2f(0.0, 0.0); glVertex3f(-half_w, half_h, half_d)
            glEnd()
            glDisable(GL_TEXTURE_2D)
        
        # Back face (dark gray)
        glColor3f(0.2, 0.2, 0.2)
        glBegin(GL_QUADS)
        glNormal3f(0.0, 0.0, -1.0)  # Normal pointing backward
        glVertex3f(-half_w, -half_h, -half_d)
        glVertex3f(-half_w, half_h, -half_d)
        glVertex3f(half_w, half_h, -half_d)
        glVertex3f(half_w, -half_h, -half_d)
        glEnd()
        
        # Top face
        glColor3f(0.15, 0.15, 0.15)
        glBegin(GL_QUADS)
        glNormal3f(0.0, 1.0, 0.0)  # Normal pointing up
        glVertex3f(-half_w, half_h, -half_d)
        glVertex3f(-half_w, half_h, half_d)
        glVertex3f(half_w, half_h, half_d)
        glVertex3f(half_w, half_h, -half_d)
        glEnd()
        
        # Bottom face
        glColor3f(0.15, 0.15, 0.15)
        glBegin(GL_QUADS)
        glNormal3f(0.0, -1.0, 0.0)  # Normal pointing down
        glVertex3f(-half_w, -half_h, -half_d)
        glVertex3f(half_w, -half_h, -half_d)
        glVertex3f(half_w, -half_h, half_d)
        glVertex3f(-half_w, -half_h, half_d)
        glEnd()
        
        # Left face
        glColor3f(0.25, 0.25, 0.25)
        glBegin(GL_QUADS)
        glNormal3f(-1.0, 0.0, 0.0)  # Normal pointing left
        glVertex3f(-half_w, -half_h, -half_d)
        glVertex3f(-half_w, -half_h, half_d)
        glVertex3f(-half_w, half_h, half_d)
        glVertex3f(-half_w, half_h, -half_d)
        glEnd()
        
        # Right face
        glColor3f(0.25, 0.25, 0.25)
        glBegin(GL_QUADS)
        glNormal3f(1.0, 0.0, 0.0)  # Normal pointing right
        glVertex3f(half_w, -half_h, -half_d)
        glVertex3f(half_w, half_h, -half_d)
        glVertex3f(half_w, half_h, half_d)
        glVertex3f(half_w, -half_h, half_d)
        glEnd()
        
        # Reset color
        glColor3f(1.0, 1.0, 1.0)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        widget_w = self.width()
        widget_h = self.height()
        if widget_h == 0:
            widget_h = 1
        window_aspect = widget_w / widget_h
        # Define max quad dimensions based on window aspect
        max_quad_h = 1.0
        max_quad_w = window_aspect
        
        import math
        fov_y = 30.0
        # Use a reference quad height for camera positioning
        z = (max_quad_h / 2) / math.tan(math.radians(fov_y / 2))
        zoom_level = getattr(self, 'zoom_level', 0.0)
        z += zoom_level
        
        # Determine how many surrounding covers to show based on zoom level
        # Always render at least 3 above and below for animation
        # At zoom_level <= 0.3: render 3 surrounding but only show current (others off-screen)
        # As zoom increases (positive), show more surrounding covers (up to 7 above and below)
        min_surrounding = 3  # Always render at least 3 for smooth transitions
        max_surrounding = 7  # Maximum when fully zoomed out
        
        if zoom_level <= 0.3:
            num_surrounding = min_surrounding
            # When zoomed in, we'll position others far off-screen
            show_surrounding = False
        else:
            # Gradually increase from 3 to 7 as zoom goes from 0.3 to 4.0
            num_surrounding = max(min_surrounding, int(min(max_surrounding, min_surrounding + (zoom_level - 0.3) / 3.7 * (max_surrounding - min_surrounding))))
            show_surrounding = True
        
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
            prev_quad_geom = None
            if hasattr(self, '_prev_cover_idx'):
                _, prev_texture_id, prev_quad_geom = self.getCachedCover(self._prev_cover_idx)
            if prev_texture_id is None and self._prev_cover_image and not self._prev_cover_image.isNull():
                prev_texture_id = self.createTextureFromQImage(self._prev_cover_image)
            
            # Calculate previous cover's quad dimensions
            if prev_quad_geom:
                prev_aspect, w, h = prev_quad_geom
            else:
                prev_aspect = self._prev_cover_image.width() / self._prev_cover_image.height() if self._prev_cover_image and not self._prev_cover_image.isNull() and self._prev_cover_image.height() != 0 else 1.0
            
            prev_quad_h = max_quad_h
            prev_quad_w = prev_aspect * prev_quad_h
            if prev_quad_w > max_quad_w:
                prev_quad_w = max_quad_w
                prev_quad_h = prev_quad_w / prev_aspect
            
            if prev_texture_id:
                self.drawVHSBox(prev_quad_w, prev_quad_h, prev_texture_id)
            glPopMatrix()
            
            # Draw current cover with its own quad dimensions
            glPushMatrix()
            glTranslatef(0.0, curr_y_offset, -z)
            glRotatef(self.y_rotation, 0.0, 1.0, 0.0)
            curr_texture_id = self.texture_id
            curr_quad_geom = None
            if hasattr(self, '_current_index'):
                _, curr_texture_id, curr_quad_geom = self.getCachedCover(self._current_index)
            
            # Calculate current cover's quad dimensions
            if curr_quad_geom:
                curr_aspect, w, h = curr_quad_geom
            else:
                curr_aspect = self.cover_image.width() / self.cover_image.height() if self.cover_image and not self.cover_image.isNull() and self.cover_image.height() != 0 else 1.0
            
            curr_quad_h = max_quad_h
            curr_quad_w = curr_aspect * curr_quad_h
            if curr_quad_w > max_quad_w:
                curr_quad_w = max_quad_w
                curr_quad_h = curr_quad_w / curr_aspect
            
            if self.cover_image and not self.cover_image.isNull():
                if curr_texture_id is None:
                    curr_texture_id = self.createTextureFromQImage(self.cover_image)
                self.drawVHSBox(curr_quad_w, curr_quad_h, curr_texture_id)
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
                    aspect = self.cover_image.width() / self.cover_image.height() if self.cover_image.height() != 0 else 1.0
                    quad_h = max_quad_h
                    quad_w = aspect * quad_h
                    if quad_w > max_quad_w:
                        quad_w = max_quad_w
                        quad_h = quad_w / aspect
                    self.drawVHSBox(quad_w, quad_h, self.texture_id)
            else:
                vertical_spacing = 0.85  # Fixed spacing between covers
                
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
                for offset in range(-num_surrounding - extra_range, num_surrounding + extra_range + 1):
                    idx = self._current_index + offset
                    if idx < 0 or idx >= self._model.rowCount():
                        continue
                    
                    # Get cached cover data
                    cover_img, texture_id, quad_geom = self.getCachedCover(idx)
                    
                    # For current cover (offset == 0), always try to load if not cached
                    if cover_img is None and offset == 0:
                        cover_img = self.cover_image
                    
                    # Skip if no image available
                    if cover_img is None or cover_img.isNull():
                        continue
                    
                    # Create texture on-demand if not cached (OpenGL operations must be on main thread)
                    if texture_id is None:
                        texture_id = self.createTextureFromQImage(cover_img)
                        # Update cache with texture_id
                        with self.QMutexLocker(self._cover_cache_mutex):
                            self._cover_cache[idx] = (cover_img, texture_id, quad_geom)
                    
                    covers_drawn += 1
                    
                    # Calculate quad dimensions
                    if quad_geom:
                        aspect, w, h = quad_geom
                    elif cover_img and not cover_img.isNull():
                        aspect = cover_img.width() / cover_img.height() if cover_img.height() != 0 else 1.0
                    else:
                        aspect = 1.0
                    
                    quad_h = max_quad_h * 0.8  # Scale down a bit when showing multiple
                    quad_w = aspect * quad_h
                    if quad_w > max_quad_w * 0.8:
                        quad_w = max_quad_w * 0.8
                        quad_h = quad_w / aspect
                    
                    # Position the cover horizontally (changed from vertical)
                    # Apply scroll offset during animation
                    effective_offset = offset - scroll_offset
                    x_offset = effective_offset * vertical_spacing  # Using same spacing value, but horizontally
                    
                    # Slight opacity/brightness change for non-current covers
                    alpha = 1.0 if offset == 0 else 0.7
                    
                    glPushMatrix()
                    glTranslatef(x_offset, 0.0, -z)  # Changed from (0.0, -y_offset, -z)
                    glRotatef(self.y_rotation, 0.0, 1.0, 0.0)
                    
                    # Apply opacity for non-current covers
                    if offset != 0:
                        glColor4f(alpha, alpha, alpha, 1.0)
                    
                    self.drawVHSBox(quad_w, quad_h, texture_id)
                    
                    # Reset color
                    if offset != 0:
                        glColor4f(1.0, 1.0, 1.0, 1.0)
                    
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
        if event.button() == Qt.LeftButton:
            from PyQt5.QtCore import QTime
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

    def mouseMoveEvent(self, event):
        if self.last_mouse_x is not None:
            from PyQt5.QtCore import QTime
            import math
            current_time = QTime.currentTime()
            dx = event.x() - self.last_mouse_x
            
            # Convert pixel movement to cover offset
            # We need to calculate how much of the world space one pixel represents
            # at the current zoom level and projection settings
            
            # Camera distance from origin
            z = 3.0 + self.zoom_level
            
            # FOV is 30 degrees, convert to radians
            fov_rad = math.radians(30.0)
            
            # Calculate the width of the view frustum at distance z
            # Using tan(fov/2) * distance * 2
            view_height = 2.0 * z * math.tan(fov_rad / 2.0)
            aspect = self.width() / self.height() if self.height() != 0 else 1.0
            view_width = view_height * aspect
            
            # Pixels per world unit
            pixels_per_unit = self.width() / view_width
            
            # Cover spacing is 0.85 world units
            spacing = 0.85
            pixels_per_cover = pixels_per_unit * spacing
            
            # Convert mouse movement to cover offset
            # Negative to match intuitive drag direction (drag right = scroll left)
            cover_delta = -dx / pixels_per_cover
            
            self.drag_offset += cover_delta
            
            # Check if we've dragged past the threshold to cycle to next/previous movie
            # Similar to mouse wheel behavior
            if hasattr(self, '_model') and hasattr(self, '_current_index'):
                threshold = 0.5  # Half a cover width
                if self.drag_offset >= threshold:
                    # Dragged left - move to previous movie (cycle to end if at start)
                    self.drag_offset -= 1.0
                    self.wheelMovieChange.emit(1)  # Previous movie
                elif self.drag_offset <= -threshold:
                    # Dragged right - move to next movie (cycle to start if at end)
                    self.drag_offset += 1.0
                    self.wheelMovieChange.emit(-1)  # Next movie
            
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
        if event.button() == Qt.LeftButton:
            self.last_mouse_x = None
            
            # Calculate velocity from recent drag history
            if len(self.drag_history) > 0:
                total_delta = sum(d[0] for d in self.drag_history)
                total_time = sum(d[1] for d in self.drag_history)
                if total_time > 0:
                    # Velocity in covers per millisecond
                    self.drag_velocity = total_delta / total_time
                    # Apply momentum if velocity is significant
                    if abs(self.drag_velocity) > 0.001:
                        self.is_momentum_scrolling = True
                        if not hasattr(self, '_momentum_timer') or not self._momentum_timer:
                            self._momentum_timer = self.startTimer(16)  # 60 FPS
            
            self.drag_history = []
