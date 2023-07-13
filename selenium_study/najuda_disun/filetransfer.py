#pip install pywinauto
#pip install chardet    - 인코딩 정보 찾기
#pip install aspose-words   - docx파일 읽기위해 필요

from pywinauto import application, findwindows, keyboard
import pyperclip, time, re, chardet
import aspose.words as aw

import os
import olefile
import subprocess

app = application.Application(backend='uia')
app2 = application.Application(backend='uia')
hwpconv="C:\Program Files\Microsoft Office\Office15\BATCHHWPCONV.EXE"
app.start(hwpconv)

procs = findwindows.find_elements()

for proc in procs:
    print(f"{proc} / process : {proc.process_id}")

dlg = app['Microsoft Word를 위한 아래아한글 문서 일괄 변환 도구']

dir_hwp = r"C:\Users\cyady\Downloads"
pyperclip.copy(dir_hwp)

dlg["RadioButton2"].click()
dlg["...Button"].click()
time.sleep(0.1)

N=5
for tab in range(N):
    keyboard.send_keys('{TAB}')
keyboard.send_keys('{ENTER}')

keyboard.send_keys('^v')    #ctrl + v
keyboard.send_keys('{ENTER}')


day="7.10특징주 {(}2{)}.hwp"
dlg.child_window(title="파일 이름(N):", auto_id="1148", control_type="Edit").type_keys(day,
                                                                                   with_spaces=True,
                                                                                   with_tabs=True
                                                                                   )
keyboard.send_keys('{ENTER}')
dlg.child_window(title="변환", auto_id="1", control_type="Button").click()

try:
    dlg.child_window(title="예", auto_id="1013", control_type="Button").click()
except:
    print("first file.")
finally:
    dlg.child_window(title="종료", auto_id="2", control_type="Button").click()
    # dlg.print_control_identifiers()

day_doc=dir_hwp + "\\" +day.replace("hwp","docx")
day_docx=re.sub("{|}","",day_doc)
print(day_docx)

# Initialize the license to avoid trial version limitations
# while reading the word file in python
# editWordLicense = aw.License()
# editWordLicense.set_license("Aspose.Word.lic")

# Load the source document that needs to be read
docToRead = aw.Document(day_docx)

# Read all the contents from the node types paragraph
for paragraph in docToRead.get_child_nodes(aw.NodeType.PARAGRAPH, True) :
    paragraph = paragraph.as_paragraph()
    print(paragraph.to_string(aw.SaveFormat.TEXT))


