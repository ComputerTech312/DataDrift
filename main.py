import sys
import json
import paramiko
import asyncio
from functools import partial
from scp import SCPClient
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLineEdit, QSplitter, QTreeView, QProgressBar,
    QMessageBox, QToolBar, QStatusBar, QAbstractItemView, QFileDialog, QInputDialog, QTextEdit,
    QFileSystemModel
)
from PyQt5.QtCore import QAbstractItemModel, QModelIndex, Qt, QDir
import os


class SCPClientApp(QWidget):
    def __init__(self):
        super().__init__()
        self.connection_file = "connections.json"
        self.remote_path = "."  # Current path on the remote server
        self.ssh = None
        self.sftp = None
        self.scp = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle("DataDrift")
        self.setGeometry(300, 300, 1200, 700)

        # Main layout
        layout = QVBoxLayout()

        # Load saved connections
        self.load_connections()

        # Toolbar
        self.toolbar = QToolBar()
        self.toolbar.addAction("Connect", lambda: asyncio.run(self.connect_ssh()))
        self.toolbar.addAction("Disconnect", self.disconnect_ssh)
        self.toolbar.addAction("Upload", lambda: asyncio.run(self.upload_file()))
        self.toolbar.addAction("Download", lambda: asyncio.run(self.download_file()))
        self.toolbar.addAction("Open File", lambda: asyncio.run(self.open_file()))
        self.toolbar.addAction("Save File", lambda: asyncio.run(self.save_file()))
        self.toolbar.addAction("Delete", lambda: asyncio.run(self.delete_file()))
        self.toolbar.addAction("Refresh Remote", lambda: asyncio.run(self.load_remote_directory()))
        layout.addWidget(self.toolbar)

        # Splitter for Local and Remote File Browsers
        self.splitter = QSplitter(Qt.Horizontal)

        # Local File Browser
        self.local_file_model = QFileSystemModel()
        self.local_file_model.setRootPath(QDir.rootPath())
        self.local_tree = QTreeView()
        self.local_tree.setModel(self.local_file_model)
        self.local_tree.setRootIndex(self.local_file_model.index(QDir.homePath()))
        self.local_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.local_tree.setDragEnabled(True)
        self.splitter.addWidget(self.local_tree)

        # Remote File Browser
        self.remote_tree = QTreeView()
        self.remote_model = RemoteFileModel()  # Use custom model for remote files
        self.remote_tree.setModel(self.remote_model)
        self.remote_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.remote_tree.setAcceptDrops(True)
        self.remote_tree.doubleClicked.connect(self.remote_directory_navigate)  # For directory navigation
        self.splitter.addWidget(self.remote_tree)

        # Text Editor for File Edit
        self.text_editor = QTextEdit()
        self.splitter.addWidget(self.text_editor)
        self.text_editor.setVisible(False)

        layout.addWidget(self.splitter)

        # Progress Bar for file transfer
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Status Bar for connection status
        self.status_bar = QStatusBar()
        layout.addWidget(self.status_bar)

        # Set layout
        self.setLayout(layout)

    def load_connections(self):
        """ Load saved connections from JSON file """
        try:
            with open(self.connection_file, 'r') as file:
                self.saved_connections = json.load(file)
        except FileNotFoundError:
            self.saved_connections = {}

    async def connect_ssh(self):
        """ Establish SSH connection and list remote directory """
        host, ok = QInputDialog.getText(self, 'Input Dialog', 'Enter SSH host:')
        username, ok = QInputDialog.getText(self, 'Input Dialog', 'Enter SSH username:')
        password, ok = QInputDialog.getText(self, 'Input Dialog', 'Enter SSH password:', QLineEdit.Password)

        if host and username and password:
            try:
                await asyncio.to_thread(self._connect_ssh_thread, host, username, password)
                QMessageBox.information(self, "Connection Success", "Connected to the server successfully!")
                self.status_bar.showMessage(f"Connected to {host}")

                # Load the remote directory asynchronously
                await self.load_remote_directory()

            except Exception as e:
                QMessageBox.critical(self, "Connection Failed", f"Error: {e}")

    def _connect_ssh_thread(self, host, username, password):
        """ Run the actual SSH connection in a separate thread """
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(host, username=username, password=password)
        self.sftp = self.ssh.open_sftp()
        self.scp = SCPClient(self.ssh.get_transport())

    async def load_remote_directory(self):
        """ Load the remote directory into the remote tree view after SSH connection """
        if self.ssh is None or self.sftp is None:
            QMessageBox.warning(self, "No Connection", "You must be connected to a server to refresh the remote directory.")
            return

        try:
            # Use asyncio to run SFTP directory listing in a non-blocking way
            files = await asyncio.to_thread(self.sftp.listdir, self.remote_path)
            self.populate_remote_file_tree(files)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load remote directory: {e}")
            print(f"Error loading remote directory: {e}")

    def populate_remote_file_tree(self, remote_files):
        """ Populate remote tree view with files from the remote server """
        self.remote_model = RemoteFileModel(remote_files)  # Create a new model with remote files
        self.remote_tree.setModel(self.remote_model)  # Update the remote tree view

        # Update the status bar
        self.status_bar.showMessage(f"Loaded remote directory: {self.remote_path}")

    def remote_directory_navigate(self, index):
        """ Navigate into directories on the remote server """
        selected_item = self.remote_tree.model().data(index, Qt.DisplayRole)
        new_path = os.path.join(self.remote_path, selected_item)

        if self.is_directory(new_path):
            self.remote_path = new_path
            asyncio.run(self.load_remote_directory())  # Reload directory view
        else:
            print(f"{new_path} is not a directory.")

    def is_directory(self, path):
        """ Check if a remote path is a directory """
        try:
            return self.sftp.stat(path).st_mode & 0o040000  # Check if it's a directory
        except IOError:
            return False

    def disconnect_ssh(self):
        """ Disconnect the SSH session """
        if self.ssh:
            try:
                self.ssh.close()
                self.sftp = None
                self.ssh = None
                self.status_bar.showMessage("Disconnected")
                QMessageBox.information(self, "Disconnected", "Disconnected from the server.")
            except Exception as e:
                QMessageBox.critical(self, "Disconnection Failed", f"Error disconnecting: {e}")
        else:
            QMessageBox.warning(self, "No Connection", "No active connection to disconnect.")

    async def upload_file(self):
        """ Upload a file from local to remote """
        if self.ssh is None or self.sftp is None:
            QMessageBox.warning(self, "No Connection", "You must be connected to a server to upload files.")
            return

        local_index = self.local_tree.selectedIndexes()[0]
        local_file_path = self.local_file_model.filePath(local_index)

        try:
            await asyncio.to_thread(self.scp.put, local_file_path, self.remote_path)
            QMessageBox.information(self, "Upload Success", f"Uploaded {local_file_path} to remote server.")
        except Exception as e:
            QMessageBox.critical(self, "Upload Failed", f"Error uploading file: {e}")

    async def download_file(self):
        """ Download a file from remote to local """
        if self.ssh is None or self.sftp is None:
            QMessageBox.warning(self, "No Connection", "You must be connected to a server to download files.")
            return

        remote_index = self.remote_tree.selectedIndexes()[0]
        remote_file_name = self.remote_tree.model().data(remote_index, Qt.DisplayRole)
        remote_file_path = os.path.join(self.remote_path, remote_file_name)

        local_download_dir = QFileDialog.getExistingDirectory(self, "Select Download Directory")

        if local_download_dir:
            try:
                await asyncio.to_thread(self.scp.get, remote_file_path, local_download_dir)
                QMessageBox.information(self, "Download Success", f"Downloaded {remote_file_path} to {local_download_dir}.")
            except Exception as e:
                QMessageBox.critical(self, "Download Failed", f"Error downloading file: {e}")

    async def open_file(self):
        """ Open a file from the remote server to view and edit """
        if self.ssh and self.sftp:
            remote_index = self.remote_tree.selectedIndexes()[0]
            remote_file_name = self.remote_tree.model().data(remote_index, Qt.DisplayRole)
            remote_file_path = os.path.join(self.remote_path, remote_file_name)

            try:
                with await asyncio.to_thread(self.sftp.file, remote_file_path, 'r') as remote_file:
                    file_contents = remote_file.read().decode()

                # Display file contents in text editor
                self.text_editor.setPlainText(file_contents)
                self.text_editor.setVisible(True)
                self.status_bar.showMessage(f"Opened file: {remote_file_name}")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error opening file: {e}")
        else:
            QMessageBox.warning(self, "No Connection", "You must be connected to a server to open files.")

    async def save_file(self):
        """ Save the edited file back to the remote server """
        if self.ssh and self.sftp:
            remote_index = self.remote_tree.selectedIndexes()[0]
            remote_file_name = self.remote_tree.model().data(remote_index, Qt.DisplayRole)
            remote_file_path = os.path.join(self.remote_path, remote_file_name)

            try:
                # Get the updated content from the text editor
                updated_content = self.text_editor.toPlainText()

                # Write the updated content back to the remote file
                with await asyncio.to_thread(self.sftp.file, remote_file_path, 'w') as remote_file:
                    remote_file.write(updated_content.encode())

                QMessageBox.information(self, "Save Success", f"Saved changes to {remote_file_name}")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error saving file: {e}")
        else:
            QMessageBox.warning(self, "No Connection", "You must be connected to a server to save files.")

    async def delete_file(self):
        """ Delete a file from the remote server """
        if self.ssh and self.sftp:
            remote_index = self.remote_tree.selectedIndexes()[0]
            remote_file_name = self.remote_tree.model().data(remote_index, Qt.DisplayRole)
            remote_file_path = os.path.join(self.remote_path, remote_file_name)

            try:
                # Delete the file on the remote server
                await asyncio.to_thread(self.sftp.remove, remote_file_path)
                await self.load_remote_directory()  # Refresh the remote directory
                QMessageBox.information(self, "Delete Success", f"Deleted {remote_file_name}")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error deleting file: {e}")
        else:
            QMessageBox.warning(self, "No Connection", "You must be connected to a server to delete files.")


class RemoteFileModel(QAbstractItemModel):
    """ Custom model to hold remote files and directories """
    def __init__(self, data=None, parent=None):
        super(RemoteFileModel, self).__init__(parent)
        self._data = data if data else []

    def rowCount(self, parent=QModelIndex()):
        return len(self._data) if not parent.isValid() else 0

    def columnCount(self, parent=QModelIndex()):
        return 1

    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            return self._data[index.row()]
        return None

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        return self.createIndex(row, column, self._data[row])

    def parent(self, index):
        return QModelIndex()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SCPClientApp()
    window.show()
    sys.exit(app.exec())
