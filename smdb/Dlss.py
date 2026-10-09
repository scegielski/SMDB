"""Asynchronous single-pass DLSS NR using the local native player runtime."""
import os
from pathlib import Path
import struct
import datetime
import weakref
import mmap
import uuid
from PyQt5 import QtCore, QtGui, sip


def runtimeDirectory():
    bundled = Path(__file__).parent / 'native' / 'runtime'
    configured = os.environ.get('SMDB_DLSS_RUNTIME')
    candidates = ([Path(configured)] if configured else []) + [bundled]
    candidates += sorted((Path.home() / 'Documents' / 'Codex').glob('*/bui/work/dlss5-nr-player'), reverse=True)
    for path in candidates:
        if all((path / name).is_file() for name in ('_nvngx.dll', 'nvngx_dlssnr.dll', 'caller/nvngx.dll')):
            return path
    return None


class DlssProcessor(QtCore.QObject):
    failed = QtCore.pyqtSignal(str)
    frameProcessed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = Path(__file__).parent / 'native' / 'dlss_worker.exe'
        self.runtime = runtimeDirectory()
        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(self._readOutput)
        self.process.readyReadStandardError.connect(self._readLog)
        self.process.errorOccurred.connect(lambda _error: self._fail(self.process.errorString()))
        self.process.finished.connect(self._finished)
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(15000)
        self.timer.timeout.connect(lambda: self._fail('DLSS processing timed out'))
        self._buffer = bytearray()
        self._busy = None
        self._pending = None
        self._deferredView = None
        self._lastSource = None
        self._lastTimestamp = None
        self.log = ''
        self._stopping = False
        self.frameCount = 0
        self.intensityPercent = 100
        self.useGpuPresentation = True
        self._warmSize = None
        self._sharedBuffer = None
        self._sharedSize = 0
        self._sharedName = None
        folder = Path(QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.AppLocalDataLocation))
        folder.mkdir(parents=True, exist_ok=True)
        self.logPath = folder / 'smtv-dlss.log'
        self.record('worker=' + str(self.worker) + '; runtime=' + str(self.runtime))

    def record(self, message):
        try:
            with self.logPath.open('a', encoding='utf-8') as output:
                output.write(datetime.datetime.now().isoformat(timespec='seconds') + ' ' + message + '\n')
        except OSError:
            pass

    def available(self):
        return self.worker.is_file() and self.runtime is not None

    def needsWarm(self, width, height):
        size = (width, height)
        return (self.available() and self._warmSize != size
                and not (self._busy and self._busy[1:3] == size))

    def deferFrame(self, view):
        # Keep a reference to the latest decoded frame, not a converted CPU image.
        self._deferredView = (weakref.ref(view), view._dlssGeneration)

    def submit(self, view, image, timestamp, warmOnly=False):
        if not self.available():
            self._fail('DLSS runtime or native worker is missing')
            return
        job = (weakref.ref(view), image, timestamp, view._dlssGeneration, warmOnly)
        if self._busy:
            self._pending = job  # Latest frame only; never accumulate a playback backlog.
            return
        self._send(job)

    def _send(self, job):
        self._stopping = False
        if self.process.state() == QtCore.QProcess.NotRunning:
            self.process.setProgram(str(self.worker))
            self.process.setArguments([str(self.runtime)])
            self.record('Starting worker')
            self.process.start()
        viewRef, image, timestamp, generation, warmOnly = job
        view = viewRef()
        if view is None or sip.isdeleted(view) or not (view.dlssEnabled or (warmOnly and view._dlssPrewarm)) or view._dlssGeneration != generation:
            return
        reset = (self._lastSource != (viewRef, generation) or self._lastTimestamp is None
                 or timestamp < self._lastTimestamp or timestamp - self._lastTimestamp > 500000)
        if not warmOnly:
            self._lastSource = (viewRef, generation)
            self._lastTimestamp = timestamp
        image = image.convertToFormat(QtGui.QImage.Format_RGBA8888)
        pointer = image.constBits(); pointer.setsize(image.byteCount())
        self._busy = (viewRef, image.width(), image.height(), generation, warmOnly)
        self._buffer.clear()
        self.timer.start()
        gpuPresentation = self.useGpuPresentation and view._gpuView.supported()
        flags = (2 if warmOnly else int(reset)) | 8 | (16 if gpuPresentation else 0)
        self._busy += (gpuPresentation,)
        if os.name == 'nt':
            length = image.byteCount()
            if self._sharedSize != length:
                if self._sharedBuffer is not None:
                    self._sharedBuffer.close()
                self._sharedName = 'SMTV-DLSS-' + uuid.uuid4().hex
                self._sharedBuffer = mmap.mmap(-1, length * 2, tagname=self._sharedName)
                self._sharedSize = length
            self._sharedBuffer[:length] = bytes(pointer)
            name = self._sharedName.encode('ascii')
            packet = struct.pack('<IIIII', image.width(), image.height(), flags | 4, self.intensityPercent, len(name)) + name
        else:
            packet = struct.pack('<IIII', image.width(), image.height(), flags, self.intensityPercent) + bytes(pointer)
        self.process.write(packet)

    def _readLog(self):
        message = bytes(self.process.readAllStandardError()).decode(errors='replace')
        self.log = (self.log + message)[-10000:]
        if message.strip():
            self.record(message.strip())

    def _readOutput(self):
        self._buffer.extend(bytes(self.process.readAllStandardOutput()))
        if self._busy is None or len(self._buffer) < 4:
            return
        length = struct.unpack('<I', self._buffer[:4])[0]
        viewRef, width, height, generation, warmOnly, gpuPresentation = self._busy
        if length != width * height * 4:
            self._fail('DLSS initialization or evaluation failed')
            return
        if len(self._buffer) < (4 if self._sharedBuffer is not None else length + 4):
            return
        self.timer.stop()
        self._warmSize = (width, height)
        view = viewRef()
        if not warmOnly and view is not None and not sip.isdeleted(view) and view.dlssEnabled and view._dlssGeneration == generation:
            if gpuPresentation:
                try:
                    view.showDlssGpuFrame(self._sharedName + '-gpu', width, height)
                except Exception as error:
                    # ANGLE/remote-desktop contexts may lack NVIDIA interop.
                    # Keep DLSS functional using the existing CPU display path.
                    self.record('GPU presentation unavailable; using CPU fallback: ' + str(error))
                    self.useGpuPresentation = False
                    view._gpuView.hide()
                    self._busy = self._pending = self._deferredView = None
                    self._buffer.clear()
                    view._frameSurface.submitFrame()
                    return
            else:
                pixels = (self._sharedBuffer[length:length*2] if self._sharedBuffer is not None
                          else bytes(self._buffer[4:4+length]))
                image = QtGui.QImage(pixels, width, height,
                                     QtGui.QImage.Format_RGBA8888).copy()
                view.showDlssFrame(image)
            self.frameCount += 1
            if self.frameCount == 1:
                self.record(f'First processed frame displayed: {width}x{height}')
            self.frameProcessed.emit()
        self._busy = None
        self._buffer.clear()
        job, self._pending = self._pending, None
        deferred, self._deferredView = self._deferredView, None
        if job:
            self._send(job)
        elif deferred:
            view = deferred[0]()
            if view is not None and not sip.isdeleted(view) and view.dlssEnabled and view._dlssGeneration == deferred[1]:
                view._frameSurface.submitFrame()

    def _fail(self, message):
        if self._stopping:
            return
        self.record('ERROR: ' + message)
        self.stop()
        self.failed.emit(message)

    def _finished(self, code, status):
        if not self._stopping:
            self._fail('DLSS worker stopped; normal video restored')

    def stop(self):
        self._stopping = True
        self.frameCount = 0
        self._warmSize = None
        self.timer.stop()
        self._pending = self._busy = None
        self._deferredView = None
        self._buffer.clear()
        self._lastSource = self._lastTimestamp = None
        if self.process.state() != QtCore.QProcess.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)
        if self._sharedBuffer is not None:
            self._sharedBuffer.close()
            self._sharedBuffer = None
            self._sharedName = None
            self._sharedSize = 0
