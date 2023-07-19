

from pywinauto import application, findwindows, keyboard
import pyperclip, time, os

def removeff(path):
    if os.path.isfile(path):
        os.remove(path)

    return 'copied'
def changeHWP(name_fi, forder_path):
    app = application.Application(backend='uia')
    app2 = application.Application(backend='uia')
    hwpconv = "./BATCHHWPCONV.EXE"
    app.start(hwpconv)

    procs = findwindows.find_elements()

    for proc in procs:
        print(f"{proc} / process : {proc.process_id}")

    dlg = app['Microsoft Word를 위한 아래아한글 문서 일괄 변환 도구']
    dir_hwp = forder_path
    pyperclip.copy(dir_hwp)

    dlg["RadioButton2"].click()
    dlg["...Button"].click()
    time.sleep(0.1)

    N = 5
    for tab in range(N):
        keyboard.send_keys('{TAB}')
    keyboard.send_keys('{ENTER}')

    keyboard.send_keys('^v')  # ctrl + v
    keyboard.send_keys('{ENTER}')

    day = name_fi
    # day="7.10특징주 {(}2{)}.hwp"
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

    day_docx = day.replace("hwp", "docx")
    # day_docx = re.sub("{|}", "", day_doc)
    print(day_docx)
    removeff(dir_hwp + '\\' +name_fi)
    return day_docx

#데이터를 리스트에 채우기