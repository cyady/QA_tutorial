from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from datetime import datetime, timedelta
from shutil import copy, move
import pyautogui
import pyperclip, time
import os, sys, filetransfer, getpass

week = datetime.today().weekday()   # 월 = 0, 일 = 6

if week ==0: #monday
    delta = 3

if week ==5: # saturday
    delta = 1
if week==6: # sunday
    delta = 2
else:
    delta = 1

if datetime.today().hour >= 19:
    delta -=1

#--------------
yesm = datetime.today() - timedelta(delta)

# id_define = input("네이버 id : ")
id_define = "cyady"
# pw_define = input("네이버 pw : ")
pw_define = "Canemorte4@"
# user = input("사용자 윈도우 계정(다운로드 폴더 접근) : ")
user = getpass.getuser()
print( "user :", user)
mark = "."
today = str(yesm.month) + mark + str(yesm.day) + " 특징주"
print(today)

Chrome_Options = Options()
driver=webdriver.Chrome()

Chrome_Options.add_experimental_option("detach", True)  #브라우저 꺼짐 방지
driver.implicitly_wait(2)

try:
    driver = webdriver.Chrome(options=Chrome_Options, service=Service(ChromeDriverManager().install()))
    print("used, ChromeDriverManager")
except:
    driver = webdriver.Chrome(options=Chrome_Options, service=Service(r"C:\Users\cyady\Desktop\project\QA\QA_tutorial\drivers\chromedriver-win64\chromedriver.exe"))
    print("used, path of driver")
finally:
    driver.maximize_window()


#자동로그인 방지에 막힘 복붙으로 접근해야함



driver.get("https://cafe.naver.com/stocktraining")
# login
driver.find_element(By.ID, "gnb_login_layer").click()
#
elem_id = driver.find_element(By.ID, "id")
elem_id.click()
pyperclip.copy(id_define)
elem_id.send_keys(Keys.CONTROL, 'v')
time.sleep(0.1)
#
elem_pw = driver.find_element(By.ID, "pw")
elem_pw.click()
pyperclip.copy(pw_define)
elem_pw.send_keys(Keys.CONTROL, 'v')
time.sleep(0.1+0.12)
#
driver.find_element(By.ID, "log.login").click()
# login done

driver.execute_script('window.open("https://cafe.naver.com/ca-fe/cafes/29798500/members/dT13403RZ-ERPYhWwNk69A#");')  #구글 창 새 탭으로 열기
time.sleep(1)
driver.implicitly_wait(10)
driver.switch_to.window(driver.window_handles[-1])  #새로 연 탭으로 이동
driver.implicitly_wait(10)

driver.find_element(By.XPATH, "/html/body/div/div/div[1]/div/div[1]/button").click()
driver.find_element(By.XPATH, "/html/body/div/div/div[1]/div/div[1]/button").click()
time.sleep(0.1)
N1=5 #to the article
N2=10 # to filedownload

actions = ActionChains(driver)
for i in range(N1):
    actions.send_keys(Keys.TAB)
    actions.perform()
    # print(i)

actions.send_keys(Keys.ENTER)
actions.perform()

driver.implicitly_wait(10)
driver.switch_to.window(driver.window_handles[2])
driver.implicitly_wait(10)
time.sleep(1)

# time.sleep(3)

# html = driver.page_source
# soup = BeautifulSoup(html, 'html.parser')
# print(soup)
print(driver.current_url)
# driver.save_screenshot('screenshot.png')    #알아서 덮어 쓰는것으로 보인다.

#메타태그로 인해 요소 팔로우가 불가능하다는걸 알게됨
# <META NAME="ROBOTS" CONTENT="NOINDEX, NOFOLLOW">
driver.execute_script("window.scrollTo(1190, 410)")
driver.implicitly_wait(10)

# 클릭하면 move_to_element(target)동작이 자연스럽게 이루어지는 것으로 추정
driver.find_element(By.ID, "topLayerQueryInput").click()
driver.implicitly_wait(10)
print("clicked1")
time.sleep(1)

target = driver.find_element(By.ID, "topLayerQueryInput")
s_target=target.location
print("start flag : ", s_target)


s_Y=driver.execute_script("return window.pageYOffset")
print(s_Y)

x=int(s_target['x'])
y=int(s_target['y'])

print("x,y = ", x,y)

time.sleep(5)
print("want Mouse Position : ", pyautogui.position())


pyautogui.moveTo(s_target['x']+230, s_target['y']-19, duration=0.01) #그냥 좌표로 한방에 이동, 화면에서 검색창이 차지하는 위치 기준
pyautogui.click()
print("current Mouse Position : ", pyautogui.position())

print("clicked2")

time.sleep(0.2)
actions.send_keys(Keys.TAB)
actions.perform()

actions.send_keys(Keys.ENTER)
actions.perform()

time.sleep(2)   #다운완료 후 리턴이 올때까지 sleep이면 좋을듯
pyautogui.click()

actions.send_keys(Keys.TAB)
actions.perform()

actions.send_keys(Keys.TAB)
actions.perform()

actions.send_keys(Keys.TAB)
actions.perform()

actions.send_keys(Keys.ENTER)
actions.perform()

print("enter")
print("file downloaded")

time.sleep(2)
driver.quit()

forder_path = 'C:' + '\\Users\\'+ user + '\\Downloads\\'
print("forder_path : " , forder_path)
Tofolder = './DB'
print(forder_path)
each_file_path_and_gen_t = []
for each_file_name in os.listdir(forder_path):
    each_file_path = forder_path+each_file_name
    each_file_gen_time = os.path.getctime(each_file_path)
    each_file_path_and_gen_t.append(
        (each_file_path, each_file_gen_time)
    )


def removeff(path):
    if os.path.isfile(path):
        os.remove(path)

    return 'copied'

print("--------------")

most_recent_file = sorted(each_file_path_and_gen_t, key=lambda x : x[1], reverse=True)
print(most_recent_file)
most_recent_file_fi = str(most_recent_file[0][0])
most_recent_file_se = str(most_recent_file[1][0])
file_path_extension_fi = os.path.splitext(most_recent_file_fi)[1]
file_path_name_fi = os.path.splitext(most_recent_file_fi)[0]
name_fi = str(most_recent_file[0][0])
name_se = str(most_recent_file[1][0])
file_path_extension_se = os.path.splitext(most_recent_file_se)[1]
file_path_name_se = os.path.splitext(most_recent_file_se)[0]

print(file_path_name_fi, file_path_extension_fi)
print(file_path_name_se, file_path_extension_se)

try:
    if(name_fi == '특징주DB.xlsm'):    # 첫번째가 DB
        removeff(Tofolder + file_path_name_fi)
        copy(most_recent_file_fi, Tofolder)
        removeff(most_recent_file_fi)
        removeff(most_recent_file_se)
        print("first - DB")
        time.sleep(2)
        sys.exit()
    if(name_se == '특징주DB.xlsm'):    # 두번째가 DB
        removeff(Tofolder + "\\" + file_path_name_se)
        copy(most_recent_file_se, Tofolder)
        removeff(most_recent_file_fi)
        removeff(most_recent_file_se)
        print("second - DB")
        time.sleep(2)
        sys.exit
    else:     # 첫번째도 두번째도 DB가 아님 == 첫번째가 DB임
        #파일변환
        fpp = filetransfer.changeHWP(name_fi, forder_path)
        print("fpp_path : ", fpp)
        removeff(Tofolder + fpp.split('\\')[3])
        move(fpp, Tofolder)
        print(move)
        removeff(most_recent_file_fi)

finally:
    print("DONE")
