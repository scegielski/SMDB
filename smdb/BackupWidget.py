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
from .utilities import bToGb, bToMb, getFolderSize, getFolderSizes, handleRemoveReadonly, runFile


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
        self.backupListSmdbFile = backupListSmdbFile
        self.output = outputCallback
        
        # Backup state variables
        self.backupFolder = self.settings.value('backupFolder', "", type=str)
        self.backupAnalysed = False
        self.spaceTotal = 0
        self.spaceUsed = 0
        self.spaceFree = 0
        self.spaceUsedPercent = 0
        self.bytesToBeCopied = 0
        self.sourceFolderSizes = dict()
        self.destFolderSizes = dict()
        
        # Table setup
        self.backupListTableView = MovieTableView()
        self.backupListDefaultColumns = [Columns.Title.value,
                                         Columns.Path.value,
                                         Columns.BackupStatus.value,
                                         Columns.Size.value]
        
        try:
            self.backupListColumns = self.settings.value('backupListTableColumns',
                                                         self.backupListDefaultColumns,
                                                         type=list)
            self.backupListColumns = [int(m) for m in self.backupListColumns]
        except TypeError:
            self.backupListColumns = self.backupListDefaultColumns

        try:
            self.backupListColumnWidths = self.settings.value('backupListTableColumnWidths',
                                                              defaultColumnWidths,
                                                              type=list)
            self.backupListColumnWidths = [int(m) for m in self.backupListColumnWidths]
        except TypeError:
            self.backupListColumnWidths = defaultColumnWidths

        self.backupListColumnsVisible = []
        self.backupListHeaderActions = []
        self.backupListTableModel = None
        self.backupListTableProxyModel = None
        self.backupListSmdbData = None
        
        # UI elements
        self.backupFolderEdit = QtWidgets.QLineEdit()
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
        self.backupListTableView.setSortingEnabled(True)
        self.backupListTableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.backupListTableView.verticalHeader().hide()
        self.backupListTableView.setStyleSheet(f"background: {self.bgColorC};"
                                               f"alternate-background-color: {self.bgColorD};")
        self.backupListTableView.setAlternatingRowColors(True)
        self.backupListTableView.setShowGrid(False)

        # Right click header menu
        hh = self.backupListTableView.horizontalHeader()
        hh.setSectionsMovable(True)
        hh.setStyleSheet(f"background: {self.bgColorB};"
                         f"border-radius: 0px;")
        hh.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        hh.customContextMenuRequested[QtCore.QPoint].connect(self.headerRightMenuShow)

        # Right click menu
        self.backupListTableView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.backupListTableView.customContextMenuRequested[QtCore.QPoint].connect(
            self.backupListTableRightMenuShow)

        backupListVLayout.addWidget(self.backupListTableView)

        # Buttons
        backupListButtonsHLayout = QtWidgets.QHBoxLayout()
        backupListVLayout.addLayout(backupListButtonsHLayout)

        addButton = QtWidgets.QPushButton('Add')
        addButton.setStyleSheet(f"background: {self.bgColorA};"
                                "border-radius: 5px")
        addButton.clicked.connect(self.backupListAdd)
        backupListButtonsHLayout.addWidget(addButton)

        removeButton = QtWidgets.QPushButton('Remove')
        removeButton.setStyleSheet(f"background: {self.bgColorA};"
                                   "border-radius: 5px")
        removeButton.clicked.connect(self.backupListRemove)
        backupListButtonsHLayout.addWidget(removeButton)

        removeNoDifferenceButton = QtWidgets.QPushButton('Remove Folders With No Difference')
        removeNoDifferenceButton.setFixedSize(300, 20)
        removeNoDifferenceButton.setStyleSheet(f"background: {self.bgColorA};"
                                               f"border-radius: 5px;")
        removeNoDifferenceButton.clicked.connect(self.backupListRemoveNoDifference)
        backupListButtonsHLayout.addWidget(removeNoDifferenceButton)

        analyseButton = QtWidgets.QPushButton("Analyse")
        analyseButton.setStyleSheet(f"background: {self.bgColorA};"
                                    "border-radius: 5px;")
        analyseButton.clicked.connect(self.backupAnalyse)
        backupListButtonsHLayout.addWidget(analyseButton)

        backupButton = QtWidgets.QPushButton("Backup")
        backupButton.setStyleSheet(f"background: {self.bgColorA};"
                                   "border-radius: 5px;")
        backupButton.clicked.connect(lambda: self.backupRun(moveFiles=False))
        backupListButtonsHLayout.addWidget(backupButton)

        moveButton = QtWidgets.QPushButton("Move")
        moveButton.setStyleSheet(f"background: {self.bgColorA};"
                                 "border-radius: 5px;")
        moveButton.clicked.connect(lambda: self.backupRun(moveFiles=True))
        backupListButtonsHLayout.addWidget(moveButton)

        # Backup folder selection
        backupFolderHLayout = QtWidgets.QHBoxLayout()
        backupListVLayout.addLayout(backupFolderHLayout)

        backupFolderLabel = QtWidgets.QLabel("Destination Folder")
        backupFolderHLayout.addWidget(backupFolderLabel)

        self.backupFolderEdit.setStyleSheet(f"background: {self.bgColorC};"
                                            f"border-radius: 5px;")
        self.backupFolderEdit.setReadOnly(True)
        self.backupFolderEdit.setText(self.backupFolder)
        backupFolderHLayout.addWidget(self.backupFolderEdit)

        browseButton = QtWidgets.QPushButton("Browse")
        browseButton.setStyleSheet(f"background: {self.bgColorA};"
                                   "border-radius: 5px;")
        browseButton.clicked.connect(self.backupBrowseFolder)
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
        
        # Initialize backup folder display if previously set
        if self.backupFolder and os.path.exists(self.backupFolder):
            self.backupFolderEdit.setText(self.backupFolder)
            self.updateDiskSpaceInfo()

    def updateDiskSpaceInfo(self):
        """Update disk space information for the current backup folder."""
        if not self.backupFolder or not os.path.exists(self.backupFolder):
            return
            
        drive = os.path.splitdrive(self.backupFolder)[0]
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
                                           self.backupListTableView,
                                           self.backupListColumnsVisible,
                                           self.backupListTableModel)

    def backupBrowseFolder(self):
        """Browse for backup destination folder."""
        # Use special shell folder for "This PC" on Windows to show all drive letters
        import sys
        
        # Start from previously saved backup folder if it exists, otherwise C:\ on Windows
        if self.backupFolder and os.path.exists(self.backupFolder):
            browseDir = self.backupFolder
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
            self.backupFolder = selectedFolder
            self.backupFolderEdit.setText(self.backupFolder)
            
            # Save to settings
            self.settings.setValue('backupFolder', self.backupFolder)
            
            # Update disk space info
            self.updateDiskSpaceInfo()

    def backupAnalyse(self):
        """Analyze backup status for all items in the backup list."""
        if not self.backupFolder:
            mb = QtWidgets.QMessageBox()
            mb.setText("Destination folder is not set")
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
            return

        numItems = self.backupListTableProxyModel.rowCount()
        
        # Get progress bar from parent
        progressBar = self.parent.progressBar if hasattr(self.parent, 'progressBar') else None
        statusBar = self.parent.statusBar() if hasattr(self.parent, 'statusBar') else None
        
        if progressBar:
            progressBar.setMaximum(numItems)
        progress = 0
        
        self.backupListTableModel.aboutToChangeLayout()
        self.bytesToBeCopied = 0
        self.sourceFolderSizes = {}
        self.destFolderSizes = {}
        
        for row in range(numItems):
            QtCore.QCoreApplication.processEvents()
            if hasattr(self.parent, 'isCanceled') and self.parent.isCanceled:
                if statusBar:
                    statusBar.showMessage('Cancelled')
                self.parent.isCanceled = False
                if progressBar:
                    progressBar.setValue(0)
                self.backupListTableModel.changedLayout()
                return

            progress += 1
            if progressBar:
                progressBar.setValue(progress)

            modelIndex = self.backupListTableProxyModel.index(row, 0)
            sourceIndex = self.backupListTableProxyModel.mapToSource(modelIndex)
            sourceRow = sourceIndex.row()
            title = self.backupListTableModel.getTitle(sourceRow)
            sourceFolderName = self.backupListTableModel.getFolderName(sourceRow)
            sourcePath = self.backupListTableModel.getPath(sourceRow)
            
            # Use parent's findMovie method if available
            if hasattr(self.parent, 'findMovie'):
                sourcePath = self.parent.findMovie(sourcePath, sourceFolderName)
            if not sourcePath:
                continue
            destPath = os.path.join(self.backupFolder, sourceFolderName)

            sourceFolderSize = getFolderSize(sourcePath)
            self.backupListTableModel.setSize(sourceIndex, '%05d Mb' % bToMb(sourceFolderSize))
            self.sourceFolderSizes[sourceFolderName] = sourceFolderSize

            destFolderSize = 0
            if os.path.exists(destPath):
                destFolderSize = getFolderSize(destPath)
            self.destFolderSizes[sourceFolderName] = destFolderSize

            sourceFilesAndSizes = getFolderSizes(sourcePath)
            if os.path.exists(destPath):
                destFilesAndSizes = getFolderSizes(destPath)

            if not os.path.exists(destPath):
                self.backupListTableModel.setBackupStatus(sourceIndex, "Folder Missing")
                self.bytesToBeCopied += sourceFolderSize
                continue
            else:
                self.backupListTableModel.setBackupStatus(sourceIndex, "No Difference")

            replaceFolder = False

            # Check if any of the destination files are missing or have different sizes
            for f in sourceFilesAndSizes.keys():
                fullDestPath = os.path.join(destPath, f)
                if not os.path.exists(fullDestPath):
                    self.backupListTableModel.setBackupStatus(sourceIndex, "Files Missing (Destination)")
                    replaceFolder = True
                    break

                if not replaceFolder:
                    if f in destFilesAndSizes:
                        destFileSize = destFilesAndSizes[f]
                    else:
                        destFileSize = os.path.getsize(fullDestPath)
                    sourceFileSize = sourceFilesAndSizes[f]
                    if sourceFileSize != destFileSize:
                        self.output(f'{title} file size difference.  File:{f} Source={sourceFileSize} Dest={destFileSize}')
                        self.backupListTableModel.setBackupStatus(sourceIndex, "File Size Difference")
                        replaceFolder = True
                        break

            # Check if the destination has files that the source doesn't
            if not replaceFolder:
                for f in destFilesAndSizes.keys():
                    fullSourcePath = os.path.join(sourcePath, f)
                    if not os.path.exists(fullSourcePath):
                        self.output(f'missing source file {fullDestPath}')
                        self.backupListTableModel.setBackupStatus(sourceIndex, "Files Missing (Source)")
                        replaceFolder = True
                        break

            if replaceFolder:
                self.bytesToBeCopied -= destFolderSize
                self.bytesToBeCopied += sourceFolderSize

            message = "Analysing folder (%d/%d): %s" % (progress + 1, numItems, title)
            if statusBar:
                statusBar.showMessage(message)
            QtCore.QCoreApplication.processEvents()

        self.backupListTableModel.changedLayout()
        if statusBar:
            statusBar.showMessage("Done")
        if progressBar:
            progressBar.setValue(0)

        # Update space visualization
        if (self.spaceUsed + self.bytesToBeCopied > self.spaceTotal):
            self.spaceUsedWidget.setStyleSheet("background: rgb(255,0,0);"
                                               "border-radius: 0px 0px 0px 0px;")
            self.spaceBarLayout.setStretch(0, 1000)
            self.spaceBarLayout.setStretch(1, 0)
            self.spaceBarLayout.setStretch(2, 0)
            mb = QtWidgets.QMessageBox()
            spaceNeeded = self.spaceUsed + self.bytesToBeCopied - self.spaceTotal
            mb.setText("Error: Not enough space in backup folder: %s."
                       "   Need %.2f Gb more space" % (self.backupFolder, bToGb(spaceNeeded)))
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
        else:
            self.spaceUsedWidget.setStyleSheet("background: rgb(0,255,0);"
                                               "border-radius: 0px 0px 0px 0px;")
            changePercent = self.bytesToBeCopied / self.spaceTotal
            self.spaceBarLayout.setStretch(0, int(self.spaceUsedPercent * 1000))
            self.spaceBarLayout.setStretch(1, int(changePercent * 1000))
            self.spaceBarLayout.setStretch(2, int((1.0 - self.spaceUsedPercent - changePercent) * 1000))

        newSize = self.spaceUsed + self.bytesToBeCopied
        self.spaceFree = self.spaceTotal - newSize
        newSpacePercent = newSize / self.spaceTotal
        self.spaceAvailableLabel.setText("%dGb  Of  %dGb  Used       %dGb Free" % \
                                         (bToGb(newSize),
                                          bToGb(self.spaceTotal),
                                          bToGb(self.spaceFree)))

        self.backupAnalysed = True

    def backupRun(self, moveFiles=False):
        """Run the backup/move operation."""
        if not self.backupFolder:
            mb = QtWidgets.QMessageBox()
            mb.setText("Destination folder is not set")
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
            return

        if not self.backupAnalysed:
            mb = QtWidgets.QMessageBox()
            mb.setText("Run analyses first by pressing Analyse button")
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
            return

        if hasattr(self.parent, 'isCanceled'):
            self.parent.isCanceled = False
        self.backupListTableModel.aboutToChangeLayout()

        progress = 0
        lastBytesPerSecond = 0
        totalBytesCopied = 0
        totalTimeToCopy = 0
        averageBytesPerSecond = 0
        bytesRemaining = self.bytesToBeCopied
        estimatedHoursRemaining = 0
        estimatedMinutesRemaining = 0

        numItems = self.backupListTableProxyModel.rowCount()
        
        progressBar = self.parent.progressBar if hasattr(self.parent, 'progressBar') else None
        statusBar = self.parent.statusBar() if hasattr(self.parent, 'statusBar') else None
        
        if progressBar:
            progressBar.setMaximum(numItems)
            
        for row in range(numItems):
            self.backupListTableView.selectRow(row)
            QtCore.QCoreApplication.processEvents()
            if hasattr(self.parent, 'isCanceled') and self.parent.isCanceled:
                if statusBar:
                    statusBar.showMessage('Cancelled')
                self.parent.isCanceled = False
                if progressBar:
                    progressBar.setValue(0)
                self.backupListTableModel.changedLayout()
                return

            progress += 1
            if progressBar:
                progressBar.setValue(progress)

            modelIndex = self.backupListTableProxyModel.index(row, 0)
            sourceIndex = self.backupListTableProxyModel.mapToSource(modelIndex)
            sourceRow = sourceIndex.row()
            title = self.backupListTableModel.getTitle(sourceRow)

            try:
                sourcePath = self.backupListTableModel.getPath(sourceRow)
                sourceFolderName = self.backupListTableModel.getFolderName(sourceRow)
                sourceFolderSize = self.sourceFolderSizes[sourceFolderName]
                destFolderSize = self.destFolderSizes[sourceFolderName]
                destPath = os.path.join(self.backupFolder, sourceFolderName)

                backupStatus = self.backupListTableModel.getBackupStatus(sourceIndex.row())

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

        self.backupListTableModel.changedLayout()
        if statusBar:
            statusBar.showMessage("Done")
        if progressBar:
            progressBar.setValue(0)

    def backupListAdd(self):
        """Add selected movies from main table to backup list."""
        if not hasattr(self.parent, 'moviesTableView'):
            return
            
        self.backupListTableModel.layoutAboutToBeChanged.emit()
        for modelIndex in self.parent.moviesTableView.selectionModel().selectedRows():
            if not self.parent.moviesTableView.isRowHidden(modelIndex.row()):
                sourceIndex = self.parent.moviesTableProxyModel.mapToSource(modelIndex)
                sourceRow = sourceIndex.row()
                moviePath = self.parent.moviesTableModel.getPath(sourceRow)
                self.backupListTableModel.addMovie(self.moviesSmdbData, moviePath)

        self.backupListTableModel.changedLayout()
        self.backupAnalysed = False

    def backupListRemove(self):
        """Remove selected items from backup list."""
        selectedRows = self.backupListTableView.selectionModel().selectedRows()
        if len(selectedRows) == 0:
            return

        self.backupListTableModel.aboutToChangeLayout()
        rowsToDelete = list()
        for index in selectedRows:
            sourceIndex = self.backupListTableProxyModel.mapToSource(index)
            rowsToDelete.append(sourceIndex.row())

        for row in sorted(rowsToDelete, reverse=True):
            self.backupListTableModel.removeMovie(row)

        self.backupListTableModel.changedLayout()

    def backupListRemoveNoDifference(self):
        """Remove all items with 'No Difference' status."""
        self.backupListTableModel.aboutToChangeLayout()
        rowsToDelete = list()
        for row in range(self.backupListTableModel.rowCount()):
            if self.backupListTableModel.getBackupStatus(row) == "No Difference":
                rowsToDelete.append(row)

        for row in sorted(rowsToDelete, reverse=True):
            self.backupListTableModel.removeMovie(row)

        self.backupListTableModel.changedLayout()

    def backupListRemoveMissingInSource(self):
        """Remove destination folders that don't exist in source list."""
        if not self.backupFolder:
            mb = QtWidgets.QMessageBox()
            mb.setText("Destination folder is not set")
            mb.setIcon(QtWidgets.QMessageBox.Critical)
            mb.exec()
            return

        sourceFolders = list()
        for row in range(self.backupListTableModel.rowCount()):
            sourceFolders.append(self.backupListTableModel.getFolderName(row))

        destPathsToDelete = list()
        with os.scandir(self.backupFolder) as files:
            for f in files:
                if f.is_dir() and fnmatch.fnmatch(f, '*(*)'):
                    destFolder = f.name
                    if destFolder not in sourceFolders:
                        destPath = os.path.join(self.backupFolder, destFolder)
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

    def backupListAddAllMoviesFrom(self, moviesFolder):
        """Add all movies from a specific folder to backup list."""
        if not hasattr(self.parent, 'moviesTableModel'):
            return
            
        self.backupListTableModel.layoutAboutToBeChanged.emit()
        numItems = self.parent.moviesTableModel.rowCount()
        for row in range(numItems):
            path = self.parent.moviesTableModel.getPath(row)
            if moviesFolder == os.path.dirname(path):
                self.backupListTableModel.addMovie(self.moviesSmdbData, path)
        self.backupListTableModel.changedLayout()
        self.backupAnalysed = False

    def openBackupSourceFolder(self):
        """Open the source folder for selected backup item."""
        proxyIndex = self.backupListTableView.selectionModel().selectedRows()[0]
        sourceIndex = self.backupListTableProxyModel.mapToSource(proxyIndex)
        sourceRow = sourceIndex.row()
        moviePath = self.backupListTableModel.getPath(sourceRow)
        folderName = self.backupListTableModel.getFolderName(sourceRow)
        
        if hasattr(self.parent, 'findMovie'):
            moviePath = self.parent.findMovie(moviePath, folderName)
        if not moviePath:
            self.output("Folder doesn't exist")
            return
        runFile(moviePath)

    def openBackupDestinationFolder(self):
        """Open the destination folder for selected backup item."""
        if not self.backupFolder:
            return
        proxyIndex = self.backupListTableView.selectionModel().selectedRows()[0]
        sourceIndex = self.backupListTableProxyModel.mapToSource(proxyIndex)
        sourceRow = sourceIndex.row()
        movieFolder = self.backupListTableModel.getFolderName(sourceRow)
        moviePath = os.path.join(self.backupFolder, movieFolder)
        if os.path.exists(moviePath):
            runFile(moviePath)
        else:
            self.output("Folder doesn't exist")

    def backupListTableRightMenuShow(self, QPos):
        """Show context menu for backup table."""
        rightMenu = QtWidgets.QMenu(self.backupListTableView)
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
                tmpAction.triggered.connect(lambda a, folder=f: self.backupListAddAllMoviesFrom(folder))
                rightMenu.addAction(tmpAction)
                actions.append(tmpAction)

        playAction = QtWidgets.QAction("Play", self)
        playAction.triggered.connect(self.playMovie)
        rightMenu.addAction(playAction)

        openSourceFolderAction = QtWidgets.QAction("Open Source Folder", self)
        openSourceFolderAction.triggered.connect(self.openBackupSourceFolder)
        rightMenu.addAction(openSourceFolderAction)

        openDestinationFolderAction = QtWidgets.QAction("Open Destination Folder", self)
        openDestinationFolderAction.triggered.connect(self.openBackupDestinationFolder)
        rightMenu.addAction(openDestinationFolderAction)

        removeFromBackupListAction = QtWidgets.QAction("Remove From Backup List", self)
        removeFromBackupListAction.triggered.connect(self.backupListRemove)
        rightMenu.addAction(removeFromBackupListAction)

        removeNoDifferenceAction = QtWidgets.QAction("Remove Entries With No Differences", self)
        removeNoDifferenceAction.triggered.connect(self.backupListRemoveNoDifference)
        rightMenu.addAction(removeNoDifferenceAction)

        removeMissingInSourceAction = QtWidgets.QAction("Remove destination folders missing in source", self)
        removeMissingInSourceAction.triggered.connect(self.backupListRemoveMissingInSource)
        rightMenu.addAction(removeMissingInSourceAction)

        from enum import Enum
        
        class MoveTo(Enum):
            DOWN = 0
            UP = 1
            TOP = 2

        moveToTopAction = QtWidgets.QAction("Move To Top", self)
        moveToTopAction.triggered.connect(lambda: self.backupListMoveRow(MoveTo.TOP))
        rightMenu.addAction(moveToTopAction)

        moveUpAction = QtWidgets.QAction("Move Up", self)
        moveUpAction.triggered.connect(lambda: self.backupListMoveRow(MoveTo.UP))
        rightMenu.addAction(moveUpAction)

        moveDownAction = QtWidgets.QAction("Move Down", self)
        moveDownAction.triggered.connect(lambda: self.backupListMoveRow(MoveTo.DOWN))
        rightMenu.addAction(moveDownAction)

        if self.backupListTableProxyModel.rowCount() > 0:
            if len(self.backupListTableView.selectionModel().selectedRows()) > 0:
                modelIndex = self.backupListTableView.selectionModel().selectedRows()[0]
                if hasattr(self.parent, 'clickedTable'):
                    self.parent.clickedTable(modelIndex,
                                            self.backupListTableModel,
                                            self.backupListTableProxyModel)

        rightMenu.exec_(QtGui.QCursor.pos())

    def playMovie(self):
        """Play selected movie - delegate to parent."""
        if hasattr(self.parent, 'playMovie'):
            self.parent.playMovie(self.backupListTableView, self.backupListTableProxyModel)

    def tableSelectAll(self):
        """Select all items in backup table."""
        self.backupListTableView.selectAll()

    def backupListMoveRow(self, moveTo):
        """Move selected rows in backup list."""
        from enum import Enum
        
        class MoveTo(Enum):
            DOWN = 0
            UP = 1
            TOP = 2
            
        selectedRows = self.backupListTableView.selectionModel().selectedRows()
        if len(selectedRows) == 0:
            return

        minProxyRow = selectedRows[0].row()
        maxProxyRow = selectedRows[-1].row()
        minSourceRow = self.backupListTableProxyModel.mapToSource(selectedRows[0]).row()
        maxSourceRow = self.backupListTableProxyModel.mapToSource(selectedRows[-1]).row()

        if ((moveTo == MoveTo.UP or moveTo == MoveTo.TOP) and minSourceRow == 0) or \
                (moveTo == MoveTo.DOWN and maxSourceRow >= (self.backupListTableModel.getDataSize() - 1)):
            return

        self.backupListTableView.selectionModel().clearSelection()

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

        self.backupListTableModel.moveRow(minSourceRow, maxSourceRow, dstRow)
        topLeft = self.backupListTableProxyModel.index(topRow, 0)
        
        if hasattr(self.parent, 'moviesTableModel'):
            lastColumn = self.parent.moviesTableModel.getLastColumn()
        else:
            lastColumn = len(self.backupListColumns) - 1
            
        bottomRight = self.backupListTableProxyModel.index(bottomRow, lastColumn)

        selection = self.backupListTableView.selectionModel().selection()
        selection.select(topLeft, bottomRight)
        self.backupListTableView.selectionModel().select(selection,
                                                        QtCore.QItemSelectionModel.ClearAndSelect)

        # Write to file if parent has writeSmdbFile method
        if hasattr(self.parent, 'writeSmdbFile'):
            self.parent.writeSmdbFile(self.backupListSmdbFile,
                                     self.backupListTableModel,
                                     titlesOnly=True)

    def refreshBackupList(self):
        """Refresh the backup list table - delegate to parent."""
        if hasattr(self.parent, 'refreshTable'):
            (self.backupListSmdbData,
             self.backupListTableModel,
             self.backupListTableProxyModel,
             self.backupListColumnsVisible,
             smdbData) = self.parent.refreshTable(self.backupListSmdbFile,
                                                  self.backupListTableView,
                                                  self.backupListColumns,
                                                  self.backupListColumnWidths,
                                                  Columns.Rank.value)
            return (self.backupListSmdbData,
                    self.backupListTableModel,
                    self.backupListTableProxyModel,
                    self.backupListColumnsVisible,
                    smdbData)
        return None
