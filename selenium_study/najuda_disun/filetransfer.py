#pip install pywinauto


import os
import olefile
import subprocess
from pywinauto import application
app = application.Application()

hwpconv="C:\Program Files\Microsoft Office\Office15\BATCHHWPCONV.EXE"
app.start(hwpconv)

