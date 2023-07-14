#엑셀에 붙여넣기
#pip install python-docx
#pip install pywin32
import time

from docx import Document
import win32com.client, os

from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE

doc = Document(r"C:\Users\cyady\Downloads\7.10특징주 (2).docx")    #day_docx

# for i, paragraph in enumerate(doc.paragraphs):
#     print(str(i+1) + ":" + paragraph.text)

table_first = doc.tables[0] #특징주
table_second = doc.tables[1] #시간외

impact = []
for r in table_first.rows:
    data_list_first = []
    for cell in r.cells:
        for para in cell.paragraphs:
            # print(para.text)
            data_list_first.append(para.text)
    # print(', '.join(data_list_first))
    impact.append(data_list_first)

for i in impact:
    for j in i:
        print(j, end="|")
    print()
print()
print("----------------")
print()
over_t = []
for row in table_second.rows:
    data_list_second = []
    for cell in row.cells:
        for para in cell.paragraphs:
            # print(para.text)
            data_list_second.append(para.text)
    # print(', '.join(data_list_second))
    over_t.append(data_list_second)

for i in over_t:
    for j in i:
        print(j, end="|")
    print()


# print(data_list_second)
# 데이터를 잘 긁어오는것을 확인완료


#
# excel = win32com.client.Dispatch("Excel.Application")
# excel.Visible = True
#
# # wb = excel.Workbooks.Add()  #엑셀 프로그램에 Workbook 추가(객체 생성)
# wb = excel.Workbooks.Open("C:\\Users\\cyady\\Desktop\\증권\\자료모음\\특징주 DB\\특징주DB.xlsm")
#
# # ws1 = wb.ActiveSheet -  현재 활성화 되어있는 시트를 객체로 설정
#
# ws_temp = wb.Worksheets.Add()
# ws_temp.NAME = "TEMP_today"
#
# ws_DB = wb.Worksheets("특징주DB")  #-시트 이름으로 객체 설정
# ws_DB.Select()
# time.sleep(0.1)
#
# data_range = ws_DB.UsedRange()
#
# for i in data_range:
#     row_data = []
#     for j in i:
#         cell_value = j
#         row_data.append(str(cell_value))
#         # print(row_data[0])
#     print(', '.join(row_data))
#     if(row_data[0] > str(20230710)):
#         time.sleep(3)
#
