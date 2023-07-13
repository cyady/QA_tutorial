#pip install pywinauto

from pywinauto import application, findwindows, keyboard
import pyperclip, time


import os
import olefile
import subprocess

app = application.Application(backend='uia')

hwpconv="C:\Program Files\Microsoft Office\Office15\BATCHHWPCONV.EXE"
app.start(hwpconv)

procs = findwindows.find_elements()

for proc in procs:
    print(f"{proc} / process : {proc.process_id}")

dlg = app['Microsoft Word를 위한 아래아한글 문서 일괄 변환 도구']

dir_hwp = r"C:\Users\cyady\Downloads\\7.10특징주 (1).hwp"
pyperclip.copy(dir_hwp)

dlg["RadioButton2"].click()
dlg["...Button"].click()

time.sleep(0.1)

dlg2.print_control_identifiers()


dlg2["Toolbar4"].click()


keyboard.send_keys('^v')    #ctrl + v
keyboard.send_keys('{ENTER}')


