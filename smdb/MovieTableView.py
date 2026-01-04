from PyQt5 import QtWidgets, QtCore


class MovieTableView(QtWidgets.QTableView):
    wheelSpun = QtCore.pyqtSignal(int)

    def wheelEvent(self, event):
        if event.modifiers() & QtCore.Qt.ControlModifier:
            dy = event.angleDelta().y()
            self.wheelSpun.emit(1 if dy > 0 else (-1 if dy < 0 else 0))
            event.accept()
        else:
            # Custom wheel scrolling: one row per wheel click
            delta = event.angleDelta().y()
            
            if delta != 0:
                # Get the vertical scrollbar
                scrollBar = self.verticalScrollBar()
                
                # Calculate number of steps (typically 120 units per notch)
                steps = delta / 120
                
                # Use the singleStep value which should be set to row height
                step_size = scrollBar.singleStep()
                
                # Calculate the scroll amount (negative steps for scrolling down)
                scroll_amount = -int(steps * step_size)
                
                # Apply the scroll
                new_value = scrollBar.value() + scroll_amount
                scrollBar.setValue(new_value)
                
                event.accept()
            else:
                super().wheelEvent(event)
