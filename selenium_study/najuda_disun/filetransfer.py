#pip install pywinauto
#pip install chardet    - 인코딩 정보 찾기

from pywinauto import application, findwindows, keyboard
import pyperclip, time, re, chardet

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
#
# from docx import Document
# #r"C:\Users\cyady\Downloads\7.10특징주 (2).docx"
# doc = Document(day_docx)
#
# table_first = doc.tables[0]
# table_second = doc.tables[1]
#
#
# for row in table_first.rows:
#     data_list_first = []
#     for cell in row.cells:
#         for para in cell.paragraphs:
#             # print(para.text)
#             data_list_first.append(para.text)
#     print(', '.join(data_list_first))
#
#
# for row in table_second.rows:
#     data_list_second = []
#     for cell in row.cells:
#         for para in cell.paragraphs:
#             # print(para.text)
#             data_list_second.append(para.text)
#     print(', '.join(data_list_second))
#
# print(data_list_second)
# # 데이터를 잘 긁어오는것을 확인완료
#

#데이터를 리스트에 채우기





