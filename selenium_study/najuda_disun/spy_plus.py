from pywinauto import application, findwindows, keyboard

app = application.Application(backend='win32')


app.connect(title_re='Microsoft Excel')

procs = findwindows.find_elements()

for proc in procs:
    print(f"{proc} / process : {proc.process_id}")

print("------------------------------------------")

dlg = app['Microsoft Excel']
dlg.print_control_identifiers()
dlg.child_window(title="예(&Y)", class_name="Button").click()




