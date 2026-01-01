"""
Lighting Controls Widget - UI panel for adjusting lighting and material constants.

This widget provides sliders and spinboxes for all lighting configuration
constants used in the CoverFlow 3D rendering.
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                              QSlider, QDoubleSpinBox, QGroupBox, QScrollArea,
                              QFrame, QPushButton, QCheckBox, QSizePolicy, QToolButton,
                              QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal, QSettings, QPropertyAnimation, QParallelAnimationGroup
from . import lighting_config
import importlib


class CollapsibleBox(QWidget):
    """A collapsible group box widget."""
    
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        
        self.toggle_button = QToolButton()
        self.toggle_button.setStyleSheet("QToolButton { border: none; font-weight: bold; font-size: 12px; }")
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.RightArrow)
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(15, 5, 5, 5)
        self.content_layout.setSpacing(5)
        self.content_area.setLayout(self.content_layout)
        self.content_area.setVisible(False)
        
        lay = QVBoxLayout(self)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toggle_button)
        lay.addWidget(self.content_area)
        
        self.toggle_button.clicked.connect(self.toggle)
    
    def toggle(self):
        checked = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.content_area.setVisible(checked)
    
    def addWidget(self, widget):
        self.content_layout.addWidget(widget)
    
    def setExpanded(self, expanded):
        self.toggle_button.setChecked(expanded)
        self.toggle()


class ControlRow(QWidget):
    """A single control row with label, slider, and spinbox."""
    valueChanged = pyqtSignal(float)
    
    def __init__(self, label, min_val, max_val, default_val, step=0.01, decimals=2, parent=None):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        
        # Label
        self.label = QLabel(label)
        self.label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        layout.addWidget(self.label)
        
        # Slider
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(1000)  # Use 1000 steps for precision
        self.slider.setValue(int((default_val - min_val) / (max_val - min_val) * 1000))
        self.slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.slider.valueChanged.connect(self._onSliderChanged)
        layout.addWidget(self.slider, 1)
        
        # Spinbox
        self.spinbox = QDoubleSpinBox()
        self.spinbox.setMinimum(min_val)
        self.spinbox.setMaximum(max_val)
        self.spinbox.setSingleStep(step)
        self.spinbox.setDecimals(decimals)
        self.spinbox.setValue(default_val)
        self.spinbox.setMinimumWidth(80)
        self.spinbox.valueChanged.connect(self._onSpinboxChanged)
        layout.addWidget(self.spinbox)
        
        self._updating = False
    
    def _onSliderChanged(self, slider_val):
        if self._updating:
            return
        self._updating = True
        # Convert slider value (0-1000) to actual value
        actual_val = self.min_val + (slider_val / 1000.0) * (self.max_val - self.min_val)
        self.spinbox.setValue(actual_val)
        self.valueChanged.emit(actual_val)
        self._updating = False
    
    def _onSpinboxChanged(self, spin_val):
        if self._updating:
            return
        self._updating = True
        # Convert spinbox value to slider value (0-1000)
        if self.max_val > self.min_val:
            slider_val = int((spin_val - self.min_val) / (self.max_val - self.min_val) * 1000)
            self.slider.setValue(slider_val)
        self.valueChanged.emit(spin_val)
        self._updating = False
    
    def getValue(self):
        return self.spinbox.value()
    
    def setValue(self, value):
        self._updating = True
        self.spinbox.setValue(value)
        if self.max_val > self.min_val:
            slider_val = int((value - self.min_val) / (self.max_val - self.min_val) * 1000)
            self.slider.setValue(slider_val)
        self._updating = False


class ColorControlRow(QWidget):
    """A control row for RGB color values (0-1 range) with individual sliders."""
    valueChanged = pyqtSignal(tuple)
    
    def __init__(self, label, default_color=(1.0, 1.0, 1.0), max_value=1.0, parent=None):
        super().__init__(parent)
        self._updating = False
        self.max_value = max_value
        
        # Main vertical layout
        mainLayout = QVBoxLayout()
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.setSpacing(2)
        self.setLayout(mainLayout)
        
        # Label
        self.label = QLabel(label)
        self.label.setStyleSheet("font-weight: bold;")
        mainLayout.addWidget(self.label)
        
        # Red channel
        rLayout = QHBoxLayout()
        rLayout.setSpacing(5)
        rLabel = QLabel("R:")
        rLabel.setMinimumWidth(15)
        rLayout.addWidget(rLabel)
        
        self.r_slider = QSlider(Qt.Horizontal)
        self.r_slider.setMinimum(0)
        self.r_slider.setMaximum(1000)
        self.r_slider.setValue(int(default_color[0] / max_value * 1000))
        self.r_slider.valueChanged.connect(lambda: self._onSliderChanged('r'))
        rLayout.addWidget(self.r_slider, 1)
        
        self.r_spinbox = QDoubleSpinBox()
        self.r_spinbox.setMinimum(0.0)
        self.r_spinbox.setMaximum(max_value)
        self.r_spinbox.setSingleStep(0.01)
        self.r_spinbox.setDecimals(3)
        self.r_spinbox.setValue(default_color[0])
        self.r_spinbox.setMinimumWidth(70)
        self.r_spinbox.valueChanged.connect(lambda: self._onSpinboxChanged('r'))
        rLayout.addWidget(self.r_spinbox)
        
        mainLayout.addLayout(rLayout)
        
        # Green channel
        gLayout = QHBoxLayout()
        gLayout.setSpacing(5)
        gLabel = QLabel("G:")
        gLabel.setMinimumWidth(15)
        gLayout.addWidget(gLabel)
        
        self.g_slider = QSlider(Qt.Horizontal)
        self.g_slider.setMinimum(0)
        self.g_slider.setMaximum(1000)
        self.g_slider.setValue(int(default_color[1] / max_value * 1000))
        self.g_slider.valueChanged.connect(lambda: self._onSliderChanged('g'))
        gLayout.addWidget(self.g_slider, 1)
        
        self.g_spinbox = QDoubleSpinBox()
        self.g_spinbox.setMinimum(0.0)
        self.g_spinbox.setMaximum(max_value)
        self.g_spinbox.setSingleStep(0.01)
        self.g_spinbox.setDecimals(3)
        self.g_spinbox.setValue(default_color[1])
        self.g_spinbox.setMinimumWidth(70)
        self.g_spinbox.valueChanged.connect(lambda: self._onSpinboxChanged('g'))
        gLayout.addWidget(self.g_spinbox)
        
        mainLayout.addLayout(gLayout)
        
        # Blue channel
        bLayout = QHBoxLayout()
        bLayout.setSpacing(5)
        bLabel = QLabel("B:")
        bLabel.setMinimumWidth(15)
        bLayout.addWidget(bLabel)
        
        self.b_slider = QSlider(Qt.Horizontal)
        self.b_slider.setMinimum(0)
        self.b_slider.setMaximum(1000)
        self.b_slider.setValue(int(default_color[2] / max_value * 1000))
        self.b_slider.valueChanged.connect(lambda: self._onSliderChanged('b'))
        bLayout.addWidget(self.b_slider, 1)
        
        self.b_spinbox = QDoubleSpinBox()
        self.b_spinbox.setMinimum(0.0)
        self.b_spinbox.setMaximum(max_value)
        self.b_spinbox.setSingleStep(0.01)
        self.b_spinbox.setDecimals(3)
        self.b_spinbox.setValue(default_color[2])
        self.b_spinbox.setMinimumWidth(70)
        self.b_spinbox.valueChanged.connect(lambda: self._onSpinboxChanged('b'))
        bLayout.addWidget(self.b_spinbox)
        
        mainLayout.addLayout(bLayout)
    
    def _onSliderChanged(self, channel):
        if self._updating:
            return
        self._updating = True
        
        if channel == 'r':
            value = self.r_slider.value() / 1000.0 * self.max_value
            self.r_spinbox.setValue(value)
        elif channel == 'g':
            value = self.g_slider.value() / 1000.0 * self.max_value
            self.g_spinbox.setValue(value)
        elif channel == 'b':
            value = self.b_slider.value() / 1000.0 * self.max_value
            self.b_spinbox.setValue(value)
        
        self.valueChanged.emit(self.getValue())
        self._updating = False
    
    def _onSpinboxChanged(self, channel):
        if self._updating:
            return
        self._updating = True
        
        if channel == 'r':
            self.r_slider.setValue(int(self.r_spinbox.value() / self.max_value * 1000))
        elif channel == 'g':
            self.g_slider.setValue(int(self.g_spinbox.value() / self.max_value * 1000))
        elif channel == 'b':
            self.b_slider.setValue(int(self.b_spinbox.value() / self.max_value * 1000))
        
        self.valueChanged.emit(self.getValue())
        self._updating = False
    
    def getValue(self):
        return (self.r_spinbox.value(), self.g_spinbox.value(), self.b_spinbox.value())
    
    def setValue(self, color):
        self._updating = True
        self.r_spinbox.setValue(color[0])
        self.r_slider.setValue(int(color[0] / self.max_value * 1000))
        self.g_spinbox.setValue(color[1])
        self.g_slider.setValue(int(color[1] / self.max_value * 1000))
        self.b_spinbox.setValue(color[2])
        self.b_slider.setValue(int(color[2] / self.max_value * 1000))
        self._updating = False


class LightingControlsWidget(QWidget):
    """Main widget containing all lighting controls."""
    controlsChanged = pyqtSignal()
    
    def __init__(self, parent=None, bgColorA='rgb(50, 50, 50)', bgColorB='rgb(25, 25, 25)', 
                 bgColorC='rgb(0, 0, 0)', fgColor='rgb(255, 255, 255)'):
        super().__init__(parent)
        
        self.bgColorA = bgColorA
        self.bgColorB = bgColorB
        self.bgColorC = bgColorC
        self.fgColor = fgColor
        
        # Main layout
        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)
        
        # Title
        titleLabel = QLabel("Lighting Controls")
        titleLabel.setStyleSheet(f"font-weight: bold; font-size: 14px;")
        mainLayout.addWidget(titleLabel)
        
        # Scroll area for controls
        scrollArea = QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setStyleSheet(f"background: {self.bgColorC}; border-radius: 5px;")
        mainLayout.addWidget(scrollArea)
        
        # Container for all controls
        containerWidget = QWidget()
        containerLayout = QVBoxLayout()
        containerWidget.setLayout(containerLayout)
        scrollArea.setWidget(containerWidget)
        
        # Store control widgets for later access
        self.controls = {}
        
        # ========== LIGHTING SECTION (Collapsible) ==========
        lightingSection = CollapsibleBox("Lighting")
        lightingSection.setExpanded(False)  # Start collapsed
        containerLayout.addWidget(lightingSection)
        
        self.controls['SPOTLIGHT_POSITION_X'] = ControlRow(
            "Position X", -5.0, 5.0, lighting_config.SPOTLIGHT_POSITION_X, 0.01, 2
        )
        self.controls['SPOTLIGHT_POSITION_X'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_POSITION_X'])
        
        self.controls['SPOTLIGHT_POSITION_Y'] = ControlRow(
            "Position Y", -5.0, 5.0, lighting_config.SPOTLIGHT_POSITION_Y, 0.01, 2
        )
        self.controls['SPOTLIGHT_POSITION_Y'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_POSITION_Y'])
        
        self.controls['SPOTLIGHT_POSITION_Z'] = ControlRow(
            "Position Z", -5.0, 5.0, lighting_config.SPOTLIGHT_POSITION_Z, 0.01, 2
        )
        self.controls['SPOTLIGHT_POSITION_Z'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_POSITION_Z'])
        
        self.controls['SPOTLIGHT_TARGET_X'] = ControlRow(
            "Target X", -5.0, 5.0, lighting_config.SPOTLIGHT_TARGET_X, 0.01, 2
        )
        self.controls['SPOTLIGHT_TARGET_X'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_TARGET_X'])
        
        self.controls['SPOTLIGHT_TARGET_Y'] = ControlRow(
            "Target Y", -5.0, 5.0, lighting_config.SPOTLIGHT_TARGET_Y, 0.01, 2
        )
        self.controls['SPOTLIGHT_TARGET_Y'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_TARGET_Y'])
        
        self.controls['SPOTLIGHT_TARGET_Z'] = ControlRow(
            "Target Z", -5.0, 5.0, lighting_config.SPOTLIGHT_TARGET_Z, 0.01, 2
        )
        self.controls['SPOTLIGHT_TARGET_Z'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_TARGET_Z'])
        
        self.controls['SPOTLIGHT_CONE_ANGLE'] = ControlRow(
            "Cone Angle", 0.0, 90.0, lighting_config.SPOTLIGHT_CONE_ANGLE, 0.1, 1
        )
        self.controls['SPOTLIGHT_CONE_ANGLE'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_CONE_ANGLE'])
        
        self.controls['SPOTLIGHT_INNER_CONE_ANGLE'] = ControlRow(
            "Inner Cone Angle", 0.0, 90.0, lighting_config.SPOTLIGHT_INNER_CONE_ANGLE, 0.1, 1
        )
        self.controls['SPOTLIGHT_INNER_CONE_ANGLE'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_INNER_CONE_ANGLE'])
        
        self.controls['SPOTLIGHT_CENTER_BOOST'] = ControlRow(
            "Center Boost", 0.0, 20.0, lighting_config.SPOTLIGHT_CENTER_BOOST, 0.1, 1
        )
        self.controls['SPOTLIGHT_CENTER_BOOST'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_CENTER_BOOST'])
        
        self.controls['SPOTLIGHT_INTENSITY'] = ControlRow(
            "Intensity", 0.0, 100.0, lighting_config.SPOTLIGHT_INTENSITY, 0.1, 1
        )
        self.controls['SPOTLIGHT_INTENSITY'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_INTENSITY'])
        
        self.controls['SPOTLIGHT_ATTENUATION_LINEAR'] = ControlRow(
            "Attenuation Linear", 0.0, 1.0, lighting_config.SPOTLIGHT_ATTENUATION_LINEAR, 0.001, 3
        )
        self.controls['SPOTLIGHT_ATTENUATION_LINEAR'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_ATTENUATION_LINEAR'])
        
        self.controls['SPOTLIGHT_ATTENUATION_QUADRATIC'] = ControlRow(
            "Attenuation Quadratic", 0.0, 1.0, lighting_config.SPOTLIGHT_ATTENUATION_QUADRATIC, 0.0001, 4
        )
        self.controls['SPOTLIGHT_ATTENUATION_QUADRATIC'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_ATTENUATION_QUADRATIC'])
        
        self.controls['SPOTLIGHT_CENTER_COLOR'] = ColorControlRow(
            "Center Color", lighting_config.SPOTLIGHT_CENTER_COLOR
        )
        self.controls['SPOTLIGHT_CENTER_COLOR'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_CENTER_COLOR'])
        
        self.controls['SPOTLIGHT_EDGE_COLOR'] = ColorControlRow(
            "Edge Color", lighting_config.SPOTLIGHT_EDGE_COLOR
        )
        self.controls['SPOTLIGHT_EDGE_COLOR'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_EDGE_COLOR'])
        
        self.controls['SPOTLIGHT_COLOR_BLEND_EXPONENT'] = ControlRow(
            "Color Blend Exponent", 0.0, 20.0, lighting_config.SPOTLIGHT_COLOR_BLEND_EXPONENT, 0.1, 1
        )
        self.controls['SPOTLIGHT_COLOR_BLEND_EXPONENT'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_COLOR_BLEND_EXPONENT'])
        
        self.controls['SPOTLIGHT_COLOR_BLEND_START'] = ControlRow(
            "Color Blend Start", 0.0, 1.0, lighting_config.SPOTLIGHT_COLOR_BLEND_START, 0.01, 2
        )
        self.controls['SPOTLIGHT_COLOR_BLEND_START'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_COLOR_BLEND_START'])
        
        self.controls['SPOTLIGHT_COLOR_BLEND_END'] = ControlRow(
            "Color Blend End", 0.0, 1.0, lighting_config.SPOTLIGHT_COLOR_BLEND_END, 0.01, 2
        )
        self.controls['SPOTLIGHT_COLOR_BLEND_END'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SPOTLIGHT_COLOR_BLEND_END'])
        
        self.controls['AMBIENT_LIGHT'] = ControlRow(
            "Ambient Light", 0.0, 1.0, lighting_config.AMBIENT_LIGHT, 0.01, 2
        )
        self.controls['AMBIENT_LIGHT'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['AMBIENT_LIGHT'])
        
        # Spotlight wireframe checkbox
        self.spotlightWireframeCheckbox = QCheckBox("Show Spotlight Wireframe")
        self.spotlightWireframeCheckbox.setChecked(lighting_config.SPOTLIGHT_WIREFRAME_ENABLED)
        self.spotlightWireframeCheckbox.stateChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.spotlightWireframeCheckbox)
        
        # Shadow enabled checkbox
        self.shadowEnabledCheckbox = QCheckBox("Enable Shadows")
        self.shadowEnabledCheckbox.setChecked(lighting_config.SHADOW_ENABLED)
        self.shadowEnabledCheckbox.stateChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.shadowEnabledCheckbox)
        
        self.controls['SHADOW_MAP_SIZE'] = ControlRow(
            "Shadow Map Size", 512, 4096, lighting_config.SHADOW_MAP_SIZE, 128, 0
        )
        self.controls['SHADOW_MAP_SIZE'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SHADOW_MAP_SIZE'])
        
        self.controls['SHADOW_BIAS'] = ControlRow(
            "Shadow Bias", 0.0, 0.1, lighting_config.SHADOW_BIAS, 0.0001, 4
        )
        self.controls['SHADOW_BIAS'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SHADOW_BIAS'])
        
        self.controls['SHADOW_DARKNESS'] = ControlRow(
            "Shadow Darkness", 0.0, 1.0, lighting_config.SHADOW_DARKNESS, 0.01, 2
        )
        self.controls['SHADOW_DARKNESS'].valueChanged.connect(self._updateConfig)
        lightingSection.addWidget(self.controls['SHADOW_DARKNESS'])
        
        # ========== BOX MATERIAL SECTION (Collapsible) ==========
        boxMaterialSection = CollapsibleBox("Box Material")
        boxMaterialSection.setExpanded(False)  # Start collapsed
        containerLayout.addWidget(boxMaterialSection)
        
        self.controls['MATERIAL_BASE_COLOR'] = ColorControlRow(
            "Texture Multiplier", lighting_config.MATERIAL_BASE_COLOR
        )
        self.controls['MATERIAL_BASE_COLOR'].valueChanged.connect(self._updateConfig)
        boxMaterialSection.addWidget(self.controls['MATERIAL_BASE_COLOR'])
        
        self.controls['MATERIAL_METALLIC'] = ControlRow(
            "Metallic", 0.0, 1.0, lighting_config.MATERIAL_METALLIC, 0.01, 2
        )
        self.controls['MATERIAL_METALLIC'].valueChanged.connect(self._updateConfig)
        boxMaterialSection.addWidget(self.controls['MATERIAL_METALLIC'])
        
        self.controls['MATERIAL_ROUGHNESS'] = ControlRow(
            "Roughness", 0.0, 1.0, lighting_config.MATERIAL_ROUGHNESS, 0.001, 3
        )
        self.controls['MATERIAL_ROUGHNESS'].valueChanged.connect(self._updateConfig)
        boxMaterialSection.addWidget(self.controls['MATERIAL_ROUGHNESS'])
        
        self.controls['MATERIAL_AO'] = ControlRow(
            "AO", 0.0, 1.0, lighting_config.MATERIAL_AO, 0.01, 2
        )
        self.controls['MATERIAL_AO'].valueChanged.connect(self._updateConfig)
        boxMaterialSection.addWidget(self.controls['MATERIAL_AO'])
        
        self.controls['BOX_COLOR'] = ColorControlRow(
            "Box Color", lighting_config.BOX_COLOR
        )
        self.controls['BOX_COLOR'].valueChanged.connect(self._updateConfig)
        boxMaterialSection.addWidget(self.controls['BOX_COLOR'])
        
        # ========== GROUND MATERIAL SECTION (Collapsible) ==========
        groundMaterialSection = CollapsibleBox("Ground Material")
        groundMaterialSection.setExpanded(False)  # Start collapsed
        containerLayout.addWidget(groundMaterialSection)
        
        self.controls['GROUND_BASE_COLOR'] = ColorControlRow(
            "Ground Base Color", lighting_config.GROUND_BASE_COLOR, max_value=2.0
        )
        self.controls['GROUND_BASE_COLOR'].valueChanged.connect(self._updateConfig)
        groundMaterialSection.addWidget(self.controls['GROUND_BASE_COLOR'])
        
        # Reset button
        resetButton = QPushButton("Reset to Defaults")
        resetButton.clicked.connect(self._resetToDefaults)
        resetButton.setStyleSheet(f"background: {self.bgColorA}; border-radius: 5px; padding: 8px;")
        containerLayout.addWidget(resetButton)
        
        # Save as Defaults button
        saveDefaultsButton = QPushButton("Save as Defaults")
        saveDefaultsButton.clicked.connect(self._saveAsDefaults)
        saveDefaultsButton.setStyleSheet(f"background: {self.bgColorA}; border-radius: 5px; padding: 8px;")
        containerLayout.addWidget(saveDefaultsButton)
        
        # Add stretch at bottom
        containerLayout.addStretch()
    
    def _updateConfig(self, *args):
        """Update the lighting_config module with current values."""
        # Update all numeric controls
        for key, control in self.controls.items():
            if isinstance(control, (ControlRow, ColorControlRow)):
                value = control.getValue()
                setattr(lighting_config, key, value)
        
        # Update spotlight wireframe checkbox
        lighting_config.SPOTLIGHT_WIREFRAME_ENABLED = self.spotlightWireframeCheckbox.isChecked()
        
        # Update shadow enabled checkbox
        lighting_config.SHADOW_ENABLED = self.shadowEnabledCheckbox.isChecked()
        
        # Emit signal to notify that controls changed
        self.controlsChanged.emit()
    
    def _resetToDefaults(self):
        """Reset all controls to their default values."""
        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            'Reset to Defaults',
            'Are you sure you want to reset all lighting settings to their default values?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.No:
            return
        
        # Reload the module to get original defaults
        importlib.reload(lighting_config)
        
        # Update all controls
        for key, control in self.controls.items():
            default_val = getattr(lighting_config, key)
            control.setValue(default_val)
        
        self.spotlightWireframeCheckbox.setChecked(lighting_config.SPOTLIGHT_WIREFRAME_ENABLED)
        self.shadowEnabledCheckbox.setChecked(lighting_config.SHADOW_ENABLED)
        
        # Trigger update
        self._updateConfig()
    
    def _saveAsDefaults(self):
        """Save current values as defaults to lighting_config.py file."""
        import os
        
        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            'Save as Defaults',
            'Are you sure you want to save the current lighting settings as defaults?\n\nThis will modify the lighting_config.py file.',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.No:
            return
        
        # Get the path to lighting_config.py
        config_path = os.path.join(os.path.dirname(__file__), 'lighting_config.py')
        
        # Read the current file
        with open(config_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Create updated content
        new_lines = []
        for line in lines:
            # Check if this line defines a constant we want to update
            updated = False
            for key, control in self.controls.items():
                if line.strip().startswith(f'{key} ='):
                    value = control.getValue()
                    if isinstance(value, tuple):
                        # Format as tuple with 3 decimal places
                        new_lines.append(f'{key} = ({value[0]:.3f}, {value[1]:.3f}, {value[2]:.3f})\n')
                    else:
                        # Determine decimal places based on magnitude
                        if abs(value) < 0.01 and value != 0:
                            new_lines.append(f'{key} = {value:.4f}\n')
                        elif abs(value) < 1.0:
                            new_lines.append(f'{key} = {value:.3f}\n')
                        elif abs(value) >= 100:
                            new_lines.append(f'{key} = {value:.1f}\n')
                        else:
                            new_lines.append(f'{key} = {value:.1f}\n')
                    updated = True
                    break
            
            # Check for checkbox settings
            if not updated:
                if line.strip().startswith('SPOTLIGHT_WIREFRAME_ENABLED ='):
                    is_checked = self.spotlightWireframeCheckbox.isChecked()
                    new_lines.append(f'SPOTLIGHT_WIREFRAME_ENABLED = {is_checked}\n')
                    updated = True
                elif line.strip().startswith('SHADOW_ENABLED ='):
                    is_checked = self.shadowEnabledCheckbox.isChecked()
                    new_lines.append(f'SHADOW_ENABLED = {is_checked}\n')
                    updated = True
            
            # If not updated, keep the original line
            if not updated:
                new_lines.append(line)
        
        # Write back to file
        with open(config_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        # Reload the module to pick up changes
        importlib.reload(lighting_config)
    
    def refreshFromConfig(self):
        """Refresh all controls from current config values (for hot-reload)."""
        for key, control in self.controls.items():
            current_val = getattr(lighting_config, key)
            control.setValue(current_val)
        
        self.spotlightWireframeCheckbox.setChecked(lighting_config.SPOTLIGHT_WIREFRAME_ENABLED)
        self.shadowEnabledCheckbox.setChecked(lighting_config.SHADOW_ENABLED)
    
    def saveSettings(self, settings: QSettings):
        """Save all lighting control values to QSettings."""
        settings.beginGroup('LightingControls')
        
        # Save all numeric and color controls
        for key, control in self.controls.items():
            value = control.getValue()
            if isinstance(value, tuple):
                # Color values - save as list
                settings.setValue(key, list(value))
            else:
                settings.setValue(key, value)
        
        # Save checkbox states
        settings.setValue('SPOTLIGHT_WIREFRAME_ENABLED', self.spotlightWireframeCheckbox.isChecked())
        settings.setValue('SHADOW_ENABLED', self.shadowEnabledCheckbox.isChecked())
        
        settings.endGroup()
    
    def loadSettings(self, settings: QSettings):
        """Load all lighting control values from QSettings."""
        settings.beginGroup('LightingControls')
        
        # Load all numeric and color controls
        for key, control in self.controls.items():
            default_val = getattr(lighting_config, key)
            if isinstance(default_val, tuple):
                # Color values - load as list and convert to tuple
                loaded = settings.value(key, list(default_val), type=list)
                if loaded and len(loaded) >= 3:
                    value = (float(loaded[0]), float(loaded[1]), float(loaded[2]))
                else:
                    value = default_val
            else:
                value = settings.value(key, default_val, type=float)
            
            control.setValue(value)
            setattr(lighting_config, key, value)
        
        # Load checkbox states
        wireframe_enabled = settings.value('SPOTLIGHT_WIREFRAME_ENABLED', 
                                           lighting_config.SPOTLIGHT_WIREFRAME_ENABLED, type=bool)
        self.spotlightWireframeCheckbox.setChecked(wireframe_enabled)
        lighting_config.SPOTLIGHT_WIREFRAME_ENABLED = wireframe_enabled
        
        shadow_enabled = settings.value('SHADOW_ENABLED', 
                                        lighting_config.SHADOW_ENABLED, type=bool)
        self.shadowEnabledCheckbox.setChecked(shadow_enabled)
        lighting_config.SHADOW_ENABLED = shadow_enabled
        
        settings.endGroup()
