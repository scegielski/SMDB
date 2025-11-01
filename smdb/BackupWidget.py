from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtWidgets import QMessageBox
from pathlib import Path
import os
import shutil
import time
import fnmatch
import stat

from .MoviesTableModel import MoviesTableModel, Columns, defaultColumnWidths
from .MovieTableView import MovieTableView
from .utilities import bToGb, bToMb, getFolderSize, getFolderSizes, handleRemoveReadonly, runFile, formatSizeDiff


class BackupWidget(QtWidgets.QFrame):
    """Widget that handles all backup functionality including UI and operations."""
    
    def __init__(self, parent, settings, bgColorA, bgColorB, bgColorC, bgColorD, 
                 moviesSmdbData, backupListSmdbFile, outputCallback):
        super().__init__(parent)
        
        self.parent = parent
        self.settings = settings
        self.bgColorA = bgColorA
        self.bgColorB = bgColorB
        self.bgColorC = bgColorC
        self.bgColorD = bgColorD
        self.moviesSmdbData = moviesSmdbData
        self.listSmdbFile = backupListSmdbFile
        self.output = outputCallback
        
        # State variables
        self.folder = self.settings.value('backupFolder', "", type=str)
        self.analysed = False
        self.spaceTotal = 0
        self.spaceUsed = 0
        self.spaceFree = 0
        self.spaceUsedPercent = 0
        self.bytesToBeCopied = 0
        self.sourceFolderSizes = dict()
        self.destFolderSizes = dict()
        
        # Table setup
        self.listTableView = MovieTableView()
        self.listDefaultColumns = [Columns.Title.value,
                                         Columns.Path.value,
                                         Columns.BackupStatus.value,
                                         Columns.SrcSize.value,
                                         Columns.DstSize.value,
                                         Columns.SizeDiff.value,
                                         Columns.Size.value]
        
        try:
            self.listColumns = self.settings.value('backupListTableColumns',
                                                         self.listDefaultColumns,
                                                         type=list)
            self.listColumns = [int(m) for m in self.listColumns]
        except TypeError:
            self.listColumns = self.listDefaultColumns

        try:
            self.listColumnWidths = self.settings.value('backupListTableColumnWidths',
                                                              defaultColumnWidths,
                                                              type=list)
            self.listColumnWidths = [int(m) for m in self.listColumnWidths]
        except TypeError:
            self.listColumnWidths = defaultColumnWidths

        self.listColumnsVisible = []
        self.listHeaderActions = []
        self.listTableModel = None
        self.listTableProxyModel = None
        self.listSmdbData = None
        
        # UI elements
        self.folderEdit = QtWidgets.QLineEdit()
        self.spaceBarLayout = QtWidgets.QHBoxLayout()
        self.spaceUsedWidget = QtWidgets.QWidget()
        self.spaceChangedWidget = QtWidgets.QWidget()
        self.spaceAvailableWidget = QtWidgets.QWidget()
        self.spaceAvailableLabel = QtWidgets.QLabel("")
        
        # Initialize UI
        self.initUI()
        
    def initUI(self):
        """Initialize the backup widget UI."""
        self.setFrameShape(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.setLineWidth(5)
        self.setStyleSheet(f"background: {self.bgColorB};"
                          f"border-radius: 10px;")

        backupListVLayout = QtWidgets.QVBoxLayout()
        self.setLayout(backupListVLayout)

        backupListLabel = QtWidgets.QLabel("Backup List")
        backupListVLayout.addWidget(backupListLabel)

        # Setup table view
        self.listTableView.setSortingEnabled(True)
        self.listTableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.listTableView.verticalHeader().hide()
        self.listTableView.setStyleSheet(f"background: {self.bgColorC};"
                                               f"alternate-background-color: {self.bgColorD};")
        self.listTableView.setAlternatingRowColors(True)
        self.listTableView.setShowGrid(False)

        # Right click header menu
        hh = self.listTableView.horizontalHeader()
        hh.setSectionsMovable(True)
        hh.setStyleSheet(f"background: {self.bgColorB};"
                         f"border-radius: 0px;")
        hh.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        hh.customContextMenuRequested[QtCore.QPoint].connect(self.headerRightMenuShow)

        # Right click menu
        self.listTableView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.listTableView.customContextMenuRequested[QtCore.QPoint].connect(
            self.listTableRightMenuShow)

        backupListVLayout.addWidget(self.listTableView)

        # Buttons
        backupListButtonsHLayout = QtWidgets.QHBoxLayout()
        backupListVLayout.addLayout(backupListButtonsHLayout)

        addButton = QtWidgets.QPushButton('Add')
        addButton.setStyleSheet(f"background: {self.bgColorA};"
                                "border-radius: 5px")
        addButton.clicked.connect(self.listAdd)
        backupListButtonsHLayout.addWidget(addButton)

        removeButton = QtWidgets.QPushButton('Remove')
        removeButton.setStyleSheet(f"background: {self.bgColorA};"
                                   "border-radius: 5px")
        removeButton.clicked.connect(self.listRemove)
        backupListButtonsHLayout.addWidget(removeButton)

        removeNoDifferenceButton = QtWidgets.QPushButton('Remove Folders With No Difference')
        removeNoDifferenceButton.setFixedSize(300, 20)
        removeNoDifferenceButton.setStyleSheet(f"background: {self.bgColorA};"
                                               f"border-radius: 5px;")
        removeNoDifferenceButton.clicked.connect(self.listRemoveNoDifference)
        backupListButtonsHLayout.addWidget(removeNoDifferenceButton)

        analyseButton = QtWidgets.QPushButton("Analyse")
        analyseButton.setStyleSheet(f"background: {self.bgColorA};"
                                    "border-radius: 5px;")
        analyseButton.clicked.connect(self.analyse)
        backupListButtonsHLayout.addWidget(analyseButton)

        backupButton = QtWidgets.QPushButton("Backup")
        backupButton.setStyleSheet(f"background: {self.bgColorA};"
                                   "border-radius: 5px;")
        backupButton.clicked.connect(lambda: self.run(moveFiles=False))
        backupListButtonsHLayout.addWidget(backupButton)

        moveButton = QtWidgets.QPushButton("Move")
        moveButton.setStyleSheet(f"background: {self.bgColorA};"
                                 "border-radius: 5px;")
        moveButton.clicked.connect(lambda: self.run(moveFiles=True))
        backupListButtonsHLayout.addWidget(moveButton)

        # Backup folder selection
        backupFolderHLayout = QtWidgets.QHBoxLayout()
        backupListVLayout.addLayout(backupFolderHLayout)

        backupFolderLabel = QtWidgets.QLabel("Destination Folder")
        backupFolderHLayout.addWidget(backupFolderLabel)

        self.folderEdit.setStyleSheet(f"background: {self.bgColorC};"
                                            f"border-radius: 5px;")
        self.folderEdit.setReadOnly(True)
        self.folderEdit.setText(self.folder)
        backupFolderHLayout.addWidget(self.folderEdit)

        browseButton = QtWidgets.QPushButton("Browse")
        browseButton.setStyleSheet(f"background: {self.bgColorA};"
                                   "border-radius: 5px;")
        browseButton.clicked.connect(self.browseFolder)
        browseButton.setFixedSize(80, 20)
        backupFolderHLayout.addWidget(browseButton)

        self.spaceAvailableLabel.setAlignment(QtCore.Qt.AlignRight)
        backupFolderHLayout.addWidget(self.spaceAvailableLabel)

        # Disk space visualization
        backupSpaceLayout = QtWidgets.QHBoxLayout()
        backupListVLayout.addLayout(backupSpaceLayout)

        spaceLabel = QtWidgets.QLabel("Disk Space")
        spaceLabel.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        backupSpaceLayout.addWidget(spaceLabel)

        spaceBarWidget = QtWidgets.QWidget()
        backupSpaceLayout.addWidget(spaceBarWidget)

        self.spaceBarLayout.setSpacing(0)
        self.spaceBarLayout.setContentsMargins(0, 0, 0, 0)
        spaceBarWidget.setLayout(self.spaceBarLayout)

        self.spaceUsedWidget.setStyleSheet("background: rgb(0,255,0);"
                                           "border-radius: 0px 0px 0px 0px;")
        self.spaceBarLayout.addWidget(self.spaceUsedWidget)

        self.spaceChangedWidget.setStyleSheet("background: rgb(255,255,0);"
                                              "border-radius: 0px 0px 0px 0px;")
        self.spaceBarLayout.addWidget(self.spaceChangedWidget)

        self.spaceAvailableWidget.setStyleSheet("background: rgb(100,100,100);"
                                                "border-radius: 0px 0px 0px 0px;")
        self.spaceBarLayout.addWidget(self.spaceAvailableWidget)

        self.spaceBarLayout.setStretch(0, 0)
        self.spaceBarLayout.setStretch(1, 0)
        self.spaceBarLayout.setStretch(2, 1000)
        
        # Initialize folder display if previously set
        if self.folder and os.path.exists(self.folder):
            self.folderEdit.setText(self.folder)
            self.updateDiskSpaceInfo()

    def updateDiskSpaceInfo(self):
        """Update disk space information for the current destination folder."""
        if not self.folder or not os.path.exists(self.folder):
            return
            
        drive = os.path.splitdrive(self.folder)[0]
        if not drive:
            return
            
        self.spaceTotal, self.spaceUsed, self.spaceFree = shutil.disk_usage(drive)
        self.spaceUsedPercent = self.spaceUsed / self.spaceTotal
        self.spaceBarLayout.setStretch(0, int(self.spaceUsedPercent * 1000))
        self.spaceBarLayout.setStretch(2, int((1.0 - self.spaceUsedPercent) * 1000))

        self.spaceAvailableLabel.setText("%dGb  Of  %dGb  Used       %dGb Free" % \
                                         (bToGb(self.spaceUsed),
                                          bToGb(self.spaceTotal),
                                          bToGb(self.spaceFree)))

    def headerRightMenuShow(self, QPoint):
        """Show header context menu - delegate to parent."""
        if hasattr(self.parent, 'headerRightMenuShow'):
            self.parent.headerRightMenuShow(QPoint,
                                           self.listTableView,
                                           self.listColumnsVisible,
                                           self.listTableModel)

    def browseFolder(self):
        """Browse for destination folder."""
        # Use special shell folder for "This PC" on Windows to show all drive letters
        import sys
        
        # Start from previously saved folder if it exists, otherwise C:\ on Windows
        if self.folder and os.path.exists(self.folder):
            browseDir = self.folder
        elif sys.platform == 'win32':
            browseDir = "C:\\"
        else:
            browseDir = "/"
        
        # Use DontUseNativeDialog=False (default) to get native Windows dialog
        # which allows easier navigation to different drives
        selectedFolder = \
            QtWidgets.QFileDialog.getExistingDirectory(self,
                                                       "Select Backup Folder",
                                                       browseDir,
                                                       QtWidgets.QFileDialog.ShowDirsOnly |
                                                       QtWidgets.QFileDialog.DontResolveSymlinks)

        if selectedFolder and os.path.exists(selectedFolder):
            self.folder = selectedFolder
            self.folderEdit.setText(self.folder)
            
            # Save to settings
            self.settings.setValue('backupFolder', self.folder)
            
            # Update disk space info
            self.updateDiskSpaceInfo()

    def analyse(self):
        """Analyze status for all items in the list."""
        import time
        
        # Start profiling
        start_time = time.time()
        timing_data = {
            'total_items': 0,
            'folder_size_calc': 0,
            'file_comparison': 0,
            'status_updates': 0,
            'ui_updates': 0,
        }
        
        if not self.folder:
            mb = QtWidgets.QMessageBox()
            mb.setText("Destination folder is not set")
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
            return

        numItems = self.listTableProxyModel.rowCount()
        if numItems == 0:
            return
        
        timing_data['total_items'] = numItems
        
        # Get progress bar and status bar from parent
        progressBar = getattr(self.parent, 'progressBar', None)
        statusBar = self.parent.statusBar() if hasattr(self.parent, 'statusBar') else None
        
        if progressBar:
            progressBar.setMaximum(numItems)
        
        # Initialize state
        self.listTableModel.aboutToChangeLayout()
        self.bytesToBeCopied = 0
        self.sourceFolderSizes = {}
        self.destFolderSizes = {}
        
        # Track timing for ETA calculation
        analyse_start_time = time.time()
        
        for row in range(numItems):
            row_start = time.time()
            
            # Process events and check cancellation only every 10 items (reduce UI overhead)
            if row % 10 == 0:
                QtCore.QCoreApplication.processEvents()
            
            # Check for cancellation
            if getattr(self.parent, 'isCanceled', False):
                if statusBar:
                    statusBar.showMessage('Cancelled')
                self.parent.isCanceled = False
                if progressBar:
                    progressBar.setValue(0)
                self.listTableModel.changedLayout()
                return

            # Get source information
            modelIndex = self.listTableProxyModel.index(row, 0)
            sourceIndex = self.listTableProxyModel.mapToSource(modelIndex)
            sourceRow = sourceIndex.row()
            title = self.listTableModel.getTitle(sourceRow)
            year = self.listTableModel.getYear(sourceRow)
            titleYear = f"{title}({year})"
            sourceFolderName = self.listTableModel.getFolderName(sourceRow)
            sourcePath = self.listTableModel.getPath(sourceRow)
            
            # Find actual source path
            if hasattr(self.parent, 'findMovie'):
                sourcePath = self.parent.findMovie(sourcePath, sourceFolderName)
            if not sourcePath:
                continue
                
            destPath = os.path.join(self.folder, sourceFolderName)

            # Get file lists and calculate sizes in one pass (optimization: avoid double scanning)
            size_start = time.time()
            size_start = time.time()
            sourceFilesAndSizes = getFolderSizes(sourcePath)
            sourceFolderSize = sum(sourceFilesAndSizes.values())
            
            self.listTableModel.setSize(sourceIndex, '%05d Mb' % bToMb(sourceFolderSize))
            self.sourceFolderSizes[sourceFolderName] = sourceFolderSize

            # Get destination folder info on-demand
            if os.path.exists(destPath):
                destFilesAndSizes = getFolderSizes(destPath)
                destFolderSize = sum(destFilesAndSizes.values())
            else:
                destFilesAndSizes = {}
                destFolderSize = 0
                
            self.destFolderSizes[sourceFolderName] = destFolderSize
            
            # Set the new backup size columns
            self.listTableModel.setSrcSize(sourceIndex, '%05d Mb' % bToMb(sourceFolderSize))
            self.listTableModel.setDstSize(sourceIndex, '%05d Mb' % bToMb(destFolderSize))
            sizeDiff = sourceFolderSize - destFolderSize
            self.listTableModel.setSizeDiff(sourceIndex, formatSizeDiff(sizeDiff))
            
            timing_data['folder_size_calc'] += time.time() - size_start

            # Check destination folder existence
            compare_start = time.time()
            if not os.path.exists(destPath):
                self.listTableModel.setBackupStatus(sourceIndex, "Folder Missing")
                self.bytesToBeCopied += sourceFolderSize
                if row % 10 == 0 or row == numItems - 1:
                    if progressBar:
                        progressBar.setValue(row + 1)
                    self._updateStatusMessage(statusBar, row + 1, numItems, analyse_start_time)
                continue

            # Assume no difference until proven otherwise
            self.listTableModel.setBackupStatus(sourceIndex, "No Difference")
            replaceFolder = False

            # Check for missing or different files in destination
            for filename, sourceFileSize in sourceFilesAndSizes.items():
                fullDestPath = os.path.join(destPath, filename)
                
                if not os.path.exists(fullDestPath):
                    self.listTableModel.setBackupStatus(sourceIndex, "Files Missing (Destination)")
                    replaceFolder = True
                    break

                destFileSize = destFilesAndSizes.get(filename, os.path.getsize(fullDestPath))
                if sourceFileSize != destFileSize:
                    sourceMB = bToMb(sourceFileSize)
                    destMB = bToMb(destFileSize)
                    self.output(f'{titleYear} - File: {filename} - Src: {sourceMB:.2f} MB, Dst: {destMB:.2f} MB')
                    self.listTableModel.setBackupStatus(sourceIndex, "File Size Difference")
                    replaceFolder = True
                    break

            # Check for extra files in destination
            if not replaceFolder:
                for filename in destFilesAndSizes.keys():
                    if filename not in sourceFilesAndSizes:
                        fullSourcePath = os.path.join(sourcePath, filename)
                        self.output(f'Missing source file {fullSourcePath}')
                        self.listTableModel.setBackupStatus(sourceIndex, "Files Missing (Source)")
                        replaceFolder = True
                        break
            
            timing_data['file_comparison'] += time.time() - compare_start

            # Update bytes to copy
            status_start = time.time()
            if replaceFolder:
                self.bytesToBeCopied += sourceFolderSize - destFolderSize
            timing_data['status_updates'] += time.time() - status_start

            # Update UI only every 10 items to reduce overhead
            ui_start = time.time()
            if row % 10 == 0 or row == numItems - 1:
                if progressBar:
                    progressBar.setValue(row + 1)
                self._updateStatusMessage(statusBar, row + 1, numItems, analyse_start_time)
            timing_data['ui_updates'] += time.time() - ui_start

        # Finalize
        self.listTableModel.changedLayout()
        if statusBar:
            statusBar.showMessage("Done")
        if progressBar:
            progressBar.setValue(0)

        # Update space visualization
        self._updateSpaceVisualization()
        self.analysed = True
        
        # Output profiling results
        total_time = time.time() - start_time
        self.output("\n=== Analyse Performance Profile ===")
        self.output(f"Total items analyzed: {timing_data['total_items']}")
        self.output(f"Total time: {total_time:.2f}s")
        self.output(f"Average time per item: {total_time / max(timing_data['total_items'], 1):.3f}s")
        self.output(f"\nBreakdown:")
        self.output(f"  Folder size calculation: {timing_data['folder_size_calc']:.2f}s ({timing_data['folder_size_calc']/total_time*100:.1f}%)")
        self.output(f"  File comparison: {timing_data['file_comparison']:.2f}s ({timing_data['file_comparison']/total_time*100:.1f}%)")
        self.output(f"  Status updates: {timing_data['status_updates']:.2f}s ({timing_data['status_updates']/total_time*100:.1f}%)")
        self.output(f"  UI updates: {timing_data['ui_updates']:.2f}s ({timing_data['ui_updates']/total_time*100:.1f}%)")
        overhead = total_time - sum([timing_data['folder_size_calc'], timing_data['file_comparison'], 
                                      timing_data['status_updates'], timing_data['ui_updates']])
        self.output(f"  Overhead: {overhead:.2f}s ({overhead/total_time*100:.1f}%)")
        self.output("=" * 35 + "\n")

    def _updateStatusMessage(self, statusBar, current, total, start_time):
        """Helper to update status bar message with ETA."""
        if statusBar:
            elapsed = time.time() - start_time
            if current > 0:
                avg_time_per_item = elapsed / current
                remaining_items = total - current
                eta_seconds = avg_time_per_item * remaining_items
                
                # Format ETA
                if eta_seconds < 60:
                    eta_str = f"{int(eta_seconds)}s"
                elif eta_seconds < 3600:
                    minutes = int(eta_seconds / 60)
                    seconds = int(eta_seconds % 60)
                    eta_str = f"{minutes}m {seconds}s"
                else:
                    hours = int(eta_seconds / 3600)
                    minutes = int((eta_seconds % 3600) / 60)
                    eta_str = f"{hours}h {minutes}m"
                
                message = f"Analysing folders ({current}/{total}) - ETA: {eta_str}"
            else:
                message = f"Analysing folders ({current}/{total})"
            
            statusBar.showMessage(message)
            QtCore.QCoreApplication.processEvents()

    def _updateSpaceVisualization(self):
        """Helper to update the space usage visualization."""
        newSize = self.spaceUsed + self.bytesToBeCopied
        
        if newSize > self.spaceTotal:
            # Not enough space - show error
            self.spaceUsedWidget.setStyleSheet("background: rgb(255,0,0);"
                                               "border-radius: 0px 0px 0px 0px;")
            self.spaceBarLayout.setStretch(0, 1000)
            self.spaceBarLayout.setStretch(1, 0)
            self.spaceBarLayout.setStretch(2, 0)
            
            spaceNeeded = newSize - self.spaceTotal
            mb = QtWidgets.QMessageBox()
            mb.setText(f"Error: Not enough space in backup folder: {self.folder}. "
                       f"Need {bToGb(spaceNeeded):.2f} Gb more space")
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
        else:
            # Enough space - show green
            self.spaceUsedWidget.setStyleSheet("background: rgb(0,255,0);"
                                               "border-radius: 0px 0px 0px 0px;")
            changePercent = self.bytesToBeCopied / self.spaceTotal
            self.spaceBarLayout.setStretch(0, int(self.spaceUsedPercent * 1000))
            self.spaceBarLayout.setStretch(1, int(changePercent * 1000))
            self.spaceBarLayout.setStretch(2, int((1.0 - self.spaceUsedPercent - changePercent) * 1000))
        
        # Update space labels
        self.spaceFree = self.spaceTotal - newSize
        self.spaceAvailableLabel.setText(f"{bToGb(newSize)}Gb  Of  {bToGb(self.spaceTotal)}Gb  Used       {bToGb(self.spaceFree)}Gb Free")

    def run(self, moveFiles=False):
        """Run the backup/move operation."""
        if not self.folder:
            mb = QtWidgets.QMessageBox()
            mb.setText("Destination folder is not set")
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
            return

        if not self.analysed:
            mb = QtWidgets.QMessageBox()
            mb.setText("Run analyses first by pressing Analyse button")
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
            return

        if hasattr(self.parent, 'isCanceled'):
            self.parent.isCanceled = False
        self.listTableModel.aboutToChangeLayout()

        progress = 0
        lastBytesPerSecond = 0
        totalBytesCopied = 0
        totalTimeToCopy = 0
        averageBytesPerSecond = 0
        bytesRemaining = self.bytesToBeCopied
        estimatedHoursRemaining = 0
        estimatedMinutesRemaining = 0

        numItems = self.listTableProxyModel.rowCount()
        
        progressBar = self.parent.progressBar if hasattr(self.parent, 'progressBar') else None
        statusBar = self.parent.statusBar() if hasattr(self.parent, 'statusBar') else None
        
        if progressBar:
            progressBar.setMaximum(numItems)
            
        for row in range(numItems):
            self.listTableView.selectRow(row)
            QtCore.QCoreApplication.processEvents()
            if hasattr(self.parent, 'isCanceled') and self.parent.isCanceled:
                if statusBar:
                    statusBar.showMessage('Cancelled')
                self.parent.isCanceled = False
                if progressBar:
                    progressBar.setValue(0)
                self.listTableModel.changedLayout()
                return

            progress += 1
            if progressBar:
                progressBar.setValue(progress)

            modelIndex = self.listTableProxyModel.index(row, 0)
            sourceIndex = self.listTableProxyModel.mapToSource(modelIndex)
            sourceRow = sourceIndex.row()
            title = self.listTableModel.getTitle(sourceRow)

            try:
                sourcePath = self.listTableModel.getPath(sourceRow)
                sourceFolderName = self.listTableModel.getFolderName(sourceRow)
                sourceFolderSize = self.sourceFolderSizes[sourceFolderName]
                destFolderSize = self.destFolderSizes[sourceFolderName]
                destPath = os.path.join(self.folder, sourceFolderName)

                backupStatus = self.listTableModel.getBackupStatus(sourceIndex.row())

                message = "Backing up" if not moveFiles else "Moving "
                message += " folder (%05d/%05d): %-50s" \
                           "   Size: %06d Mb" \
                           "   Last rate = %06d Mb/s" \
                           "   Average rate = %06d Mb/s" \
                           "   %10d Mb Remaining" \
                           "   Time remaining: %03d Hours %02d minutes" % \
                           (progress,
                            numItems,
                            title,
                            bToMb(sourceFolderSize),
                            bToMb(lastBytesPerSecond),
                            bToMb(averageBytesPerSecond),
                            bToMb(bytesRemaining),
                            estimatedHoursRemaining,
                            estimatedMinutesRemaining)

                if statusBar:
                    statusBar.showMessage(message)
                QtCore.QCoreApplication.processEvents()

                # Time the copy
                startTime = time.perf_counter()
                bytesCopied = 0

                if backupStatus == 'File Size Difference' or \
                   backupStatus == 'Files Missing (Source)' or \
                   backupStatus == 'Files Missing (Destination)':

                    startTime = time.perf_counter()

                    # Copy/move any files that are missing or have different sizes
                    for f in os.listdir(sourcePath):
                        sourceFilePath = os.path.join(sourcePath, f)
                        if os.path.isdir(sourceFilePath):
                            sourceFileSize = getFolderSize(sourceFilePath)
                        else:
                            sourceFileSize = os.path.getsize(sourceFilePath)

                        destFilePath = os.path.join(destPath, f)

                        if not os.path.exists(destFilePath):
                            bytesCopied += sourceFileSize
                            if os.path.isdir(sourceFilePath):
                                shutil.copytree(sourceFilePath, destFilePath)
                            else:
                                shutil.copy(sourceFilePath, destFilePath)
                        else:
                            destFileSize = 0
                            if os.path.exists(destFilePath):
                                if os.path.isdir(destFilePath):
                                    destFileSize = getFolderSize(destFilePath)
                                else:
                                    destFileSize = os.path.getsize(destFilePath)

                            if sourceFileSize != destFileSize:
                                bytesCopied += sourceFileSize
                                if os.path.isdir(sourceFilePath):
                                    shutil.rmtree(destFilePath,
                                                  ignore_errors=False,
                                                  onerror=handleRemoveReadonly)
                                    shutil.copytree(sourceFilePath, destFilePath)
                                else:
                                    shutil.copy(sourceFilePath, destFilePath)

                        if moveFiles:
                            shutil.rmtree(sourceFilePath,
                                          ignore_errors=False,
                                          onerror=handleRemoveReadonly)

                    # Remove any files in the destination dir that are not in the source dir
                    for f in os.listdir(destPath):
                        destFilePath = os.path.join(destPath, f)
                        sourceFilePath = os.path.join(sourcePath, f)
                        if not os.path.exists(sourceFilePath):
                            if os.path.isdir(destFilePath):
                                shutil.rmtree(destFilePath,
                                              ignore_errors=False,
                                              onerror=handleRemoveReadonly)
                            else:
                                os.chmod(destFilePath, stat.S_IWRITE)
                                os.remove(destFilePath)

                    bytesRemaining += destFolderSize
                    bytesRemaining -= sourceFolderSize
                elif backupStatus == 'Folder Missing':
                    shutil.copytree(sourcePath, destPath)
                    bytesCopied = sourceFolderSize
                    bytesRemaining -= sourceFolderSize
                else:
                    bytesCopied = 0
                    sourceFolderSize = 0

                if sourceFolderSize != 0:
                    endTime = time.perf_counter()
                    secondsToCopy = endTime - startTime
                    lastBytesPerSecond = bytesCopied / secondsToCopy
                    totalTimeToCopy += secondsToCopy
                    totalBytesCopied += bytesCopied
                    averageBytesPerSecond = totalBytesCopied / totalTimeToCopy
                    if averageBytesPerSecond != 0:
                        estimatedSecondsRemaining = bytesRemaining // averageBytesPerSecond
                        estimatedMinutesRemaining = (estimatedSecondsRemaining // 60) % 60
                        estimatedHoursRemaining = estimatedSecondsRemaining // 3600
            except Exception as e:
                self.output(f"Problem copying movie: {title} - {e}")

        self.listTableModel.changedLayout()
        if statusBar:
            statusBar.showMessage("Done")
        if progressBar:
            progressBar.setValue(0)

    def listAdd(self):
        """Add selected movies from main table to backup list."""
        if not hasattr(self.parent, 'moviesTableView'):
            return
            
        self.listTableModel.layoutAboutToBeChanged.emit()
        for modelIndex in self.parent.moviesTableView.selectionModel().selectedRows():
            if not self.parent.moviesTableView.isRowHidden(modelIndex.row()):
                sourceIndex = self.parent.moviesTableProxyModel.mapToSource(modelIndex)
                sourceRow = sourceIndex.row()
                moviePath = self.parent.moviesTableModel.getPath(sourceRow)
                self.listTableModel.addMovie(self.moviesSmdbData, moviePath)

        self.listTableModel.changedLayout()
        self.analysed = False

    def listRemove(self):
        """Remove selected items from backup list."""
        selectedRows = self.listTableView.selectionModel().selectedRows()
        if len(selectedRows) == 0:
            return

        self.listTableModel.aboutToChangeLayout()
        rowsToDelete = list()
        for index in selectedRows:
            sourceIndex = self.listTableProxyModel.mapToSource(index)
            rowsToDelete.append(sourceIndex.row())

        for row in sorted(rowsToDelete, reverse=True):
            self.listTableModel.removeMovie(row)

        self.listTableModel.changedLayout()

    def listRemoveNoDifference(self):
        """Remove all items with 'No Difference' status."""
        self.listTableModel.aboutToChangeLayout()
        rowsToDelete = list()
        for row in range(self.listTableModel.rowCount()):
            if self.listTableModel.getBackupStatus(row) == "No Difference":
                rowsToDelete.append(row)

        for row in sorted(rowsToDelete, reverse=True):
            self.listTableModel.removeMovie(row)

        self.listTableModel.changedLayout()

    def listRemoveMissingInSource(self):
        """Remove destination folders that don't exist in source list."""
        if not self.folder:
            mb = QtWidgets.QMessageBox()
            mb.setText("Destination folder is not set")
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
            return

        sourceFolders = list()
        for row in range(self.listTableModel.rowCount()):
            sourceFolders.append(self.listTableModel.getFolderName(row))

        destPathsToDelete = list()
        with os.scandir(self.folder) as files:
            for f in files:
                if f.is_dir() and fnmatch.fnmatch(f, '*(*)'):
                    destFolder = f.name
                    if destFolder not in sourceFolders:
                        destPath = os.path.join(self.folder, destFolder)
                        self.output(f'delete: {destPath}')
                        destPathsToDelete.append(destPath)

        if len(destPathsToDelete) != 0:
            mb = QtWidgets.QMessageBox()
            mb.setText("Delete these folders that do not exist in source list?")
            mb.setInformativeText('\n'.join([p for p in destPathsToDelete]))
            mb.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            mb.setDefaultButton(QMessageBox.Cancel)
            if mb.exec() == QMessageBox.Ok:
                for p in destPathsToDelete:
                    self.output(f"Deleting: {p}")
                    shutil.rmtree(p,
                                  ignore_errors=False,
                                  onerror=handleRemoveReadonly)

    def listAddAllMoviesFrom(self, moviesFolder):
        """Add all movies from a specific folder to backup list."""
        if not hasattr(self.parent, 'moviesTableModel'):
            return
            
        self.listTableModel.layoutAboutToBeChanged.emit()
        numItems = self.parent.moviesTableModel.rowCount()
        for row in range(numItems):
            path = self.parent.moviesTableModel.getPath(row)
            if moviesFolder == os.path.dirname(path):
                self.listTableModel.addMovie(self.moviesSmdbData, path)
        self.listTableModel.changedLayout()
        self.analysed = False

    def openSourceFolder(self):
        """Open the source folder for selected backup item."""
        proxyIndex = self.listTableView.selectionModel().selectedRows()[0]
        sourceIndex = self.listTableProxyModel.mapToSource(proxyIndex)
        sourceRow = sourceIndex.row()
        moviePath = self.listTableModel.getPath(sourceRow)
        folderName = self.listTableModel.getFolderName(sourceRow)
        
        if hasattr(self.parent, 'findMovie'):
            moviePath = self.parent.findMovie(moviePath, folderName)
        if not moviePath:
            self.output("Folder doesn't exist")
            return
        runFile(moviePath)

    def openDestinationFolder(self):
        """Open the destination folder for selected backup item."""
        if not self.folder:
            return
        proxyIndex = self.listTableView.selectionModel().selectedRows()[0]
        sourceIndex = self.listTableProxyModel.mapToSource(proxyIndex)
        sourceRow = sourceIndex.row()
        movieFolder = self.listTableModel.getFolderName(sourceRow)
        moviePath = os.path.join(self.folder, movieFolder)
        if os.path.exists(moviePath):
            runFile(moviePath)
        else:
            self.output("Folder doesn't exist")

    def listTableRightMenuShow(self, QPos):
        """Show context menu for backup table."""
        rightMenu = QtWidgets.QMenu(self.listTableView)
        rightMenu.clear()

        selectAllAction = QtWidgets.QAction("Select All", self)
        selectAllAction.triggered.connect(lambda: self.tableSelectAll())
        rightMenu.addAction(selectAllAction)

        # Add all movies from folders
        if hasattr(self.parent, 'moviesFolder') and hasattr(self.parent, 'additionalMoviesFolders'):
            movieFolders = list()
            movieFolders.extend(self.parent.additionalMoviesFolders)
            movieFolders.append(self.parent.moviesFolder)
            actions = list()
            for f in movieFolders:
                tmpAction = QtWidgets.QAction(f"Add all movies from {f}")
                tmpAction.triggered.connect(lambda a, folder=f: self.listAddAllMoviesFrom(folder))
                rightMenu.addAction(tmpAction)
                actions.append(tmpAction)

        playAction = QtWidgets.QAction("Play", self)
        playAction.triggered.connect(self.playMovie)
        rightMenu.addAction(playAction)

        openSourceFolderAction = QtWidgets.QAction("Open Source Folder", self)
        openSourceFolderAction.triggered.connect(self.openSourceFolder)
        rightMenu.addAction(openSourceFolderAction)

        openDestinationFolderAction = QtWidgets.QAction("Open Destination Folder", self)
        openDestinationFolderAction.triggered.connect(self.openDestinationFolder)
        rightMenu.addAction(openDestinationFolderAction)

        removeFromBackupListAction = QtWidgets.QAction("Remove From Backup List", self)
        removeFromBackupListAction.triggered.connect(self.listRemove)
        rightMenu.addAction(removeFromBackupListAction)

        removeNoDifferenceAction = QtWidgets.QAction("Remove Entries With No Differences", self)
        removeNoDifferenceAction.triggered.connect(self.listRemoveNoDifference)
        rightMenu.addAction(removeNoDifferenceAction)

        removeMissingInSourceAction = QtWidgets.QAction("Remove destination folders missing in source", self)
        removeMissingInSourceAction.triggered.connect(self.listRemoveMissingInSource)
        rightMenu.addAction(removeMissingInSourceAction)

        from enum import Enum
        
        class MoveTo(Enum):
            DOWN = 0
            UP = 1
            TOP = 2

        moveToTopAction = QtWidgets.QAction("Move To Top", self)
        moveToTopAction.triggered.connect(lambda: self.listMoveRow(MoveTo.TOP))
        rightMenu.addAction(moveToTopAction)

        moveUpAction = QtWidgets.QAction("Move Up", self)
        moveUpAction.triggered.connect(lambda: self.listMoveRow(MoveTo.UP))
        rightMenu.addAction(moveUpAction)

        moveDownAction = QtWidgets.QAction("Move Down", self)
        moveDownAction.triggered.connect(lambda: self.listMoveRow(MoveTo.DOWN))
        rightMenu.addAction(moveDownAction)

        if self.listTableProxyModel.rowCount() > 0:
            if len(self.listTableView.selectionModel().selectedRows()) > 0:
                modelIndex = self.listTableView.selectionModel().selectedRows()[0]
                if hasattr(self.parent, 'clickedTable'):
                    self.parent.clickedTable(modelIndex,
                                            self.listTableModel,
                                            self.listTableProxyModel)

        rightMenu.exec_(QtGui.QCursor.pos())

    def playMovie(self):
        """Play selected movie - delegate to parent."""
        if hasattr(self.parent, 'playMovie'):
            self.parent.playMovie(self.listTableView, self.listTableProxyModel)

    def tableSelectAll(self):
        """Select all items in backup table."""
        self.listTableView.selectAll()

    def listMoveRow(self, moveTo):
        """Move selected rows in backup list."""
        from enum import Enum
        
        class MoveTo(Enum):
            DOWN = 0
            UP = 1
            TOP = 2
            
        selectedRows = self.listTableView.selectionModel().selectedRows()
        if len(selectedRows) == 0:
            return

        minProxyRow = selectedRows[0].row()
        maxProxyRow = selectedRows[-1].row()
        minSourceRow = self.listTableProxyModel.mapToSource(selectedRows[0]).row()
        maxSourceRow = self.listTableProxyModel.mapToSource(selectedRows[-1]).row()

        if ((moveTo == MoveTo.UP or moveTo == MoveTo.TOP) and minSourceRow == 0) or \
                (moveTo == MoveTo.DOWN and maxSourceRow >= (self.listTableModel.getDataSize() - 1)):
            return

        self.listTableView.selectionModel().clearSelection()

        dstRow = 0
        topRow = 0
        bottomRow = 0
        if moveTo == MoveTo.UP:
            dstRow = minSourceRow - 1
            topRow = minProxyRow - 1
            bottomRow = maxProxyRow - 1
        elif moveTo == MoveTo.DOWN:
            dstRow = minSourceRow + 1
            topRow = minProxyRow + 1
            bottomRow = maxProxyRow + 1
        elif moveTo == MoveTo.TOP:
            dstRow = 0
            topRow = 0
            bottomRow = maxProxyRow - minProxyRow

        self.listTableModel.moveRow(minSourceRow, maxSourceRow, dstRow)
        topLeft = self.listTableProxyModel.index(topRow, 0)
        
        if hasattr(self.parent, 'moviesTableModel'):
            lastColumn = self.parent.moviesTableModel.getLastColumn()
        else:
            lastColumn = len(self.listColumns) - 1
            
        bottomRight = self.listTableProxyModel.index(bottomRow, lastColumn)

        selection = self.listTableView.selectionModel().selection()
        selection.select(topLeft, bottomRight)
        self.listTableView.selectionModel().select(selection,
                                                        QtCore.QItemSelectionModel.ClearAndSelect)

        # Write to file if parent has writeSmdbFile method
        if hasattr(self.parent, 'writeSmdbFile'):
            self.parent.writeSmdbFile(self.listSmdbFile,
                                     self.listTableModel,
                                     titlesOnly=True)

    def refreshBackupList(self):
        """Refresh the backup list table - delegate to parent."""
        if hasattr(self.parent, 'refreshTable'):
            (self.listSmdbData,
             self.listTableModel,
             self.listTableProxyModel,
             self.listColumnsVisible,
             smdbData) = self.parent.refreshTable(self.listSmdbFile,
                                                  self.listTableView,
                                                  self.listColumns,
                                                  self.listColumnWidths,
                                                  Columns.Rank.value)
            return (self.listSmdbData,
                    self.listTableModel,
                    self.listTableProxyModel,
                    self.listColumnsVisible,
                    smdbData)
        return None
