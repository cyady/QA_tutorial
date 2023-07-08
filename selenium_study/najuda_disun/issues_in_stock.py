#pip install webdriver-manager
#pip install lxml
#pip install html_parser

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import pyperclip, time

week = datetime.today().weekday()   # 월 = 0, 일 = 6

if week ==0: #sunday
    delta = 3
else:
    delta =1

#--------------
yesm = datetime.today() - timedelta(delta)

mark = "."
today = str(yesm.month) + mark + str(yesm.day) + " 특징주"
print(today)

Chrome_Options = Options()
driver=webdriver.Chrome()

Chrome_Options.add_experimental_option("detach", True)  #브라우저 꺼짐 방지
driver.implicitly_wait(2)

driver = webdriver.Chrome(options=Chrome_Options, service=Service(ChromeDriverManager().install()))
driver.maximize_window()

id_define = "cyady"
pw_define = "canemorte4!"
#자동로그인 방지에 막힘



driver.get("https://cafe.naver.com/stocktraining")
# login
driver.find_element(By.ID, "gnb_login_layer").click()
#
elem_id = driver.find_element(By.ID, "id")
elem_id.click()
pyperclip.copy(id_define)
elem_id.send_keys(Keys.CONTROL, 'v')
time.sleep(1)
#
elem_pw = driver.find_element(By.ID, "pw")
elem_pw.click()
pyperclip.copy(pw_define)
elem_pw.send_keys(Keys.CONTROL, 'v')
time.sleep(1)
#
driver.find_element(By.ID, "log.login").click()
# login done

driver.execute_script('window.open("https://cafe.naver.com/ca-fe/cafes/29798500/members/dT13403RZ-ERPYhWwNk69A#");')  #구글 창 새 탭으로 열기
time.sleep(1)
driver.switch_to.window(driver.window_handles[-1])  #새로 연 탭으로 이동



N1=6 #to the article
N2=11 # to filedownload
actions = ActionChains(driver)
for i in range(N1):
    actions.send_keys(Keys.TAB)
    print(i)
actions.perform()

actions.send_keys(Keys.ENTER)
actions.perform()

driver.implicitly_wait(5)
driver.switch_to.window(driver.window_handles[2])
time.sleep(3)

html = driver.page_source
soup = BeautifulSoup(html, 'html.parser')
print(soup)
print(driver.current_url)
driver.save_screenshot('screenshot.png')

driver.find_element(By.ID, "writerInfoeltjsl88").click()
for i in range(N2):
    actions.send_keys(Keys.TAB)
    print(i)
actions.perform()

actions.send_keys(Keys.TAB)
actions.perform()
actions.send_keys(Keys.ENTER)
actions.perform()
print("file downloaded")


#
# driver.find_element(By.ID, "menuLink226").click()
# driver.find_element(By.PARTIAL_LINK_TEXT, today).click()
# driver.fin_element(By.XPATH, "/html/body/div/div/div/div[2]/div[2]/div[1]/div[1]/a").click()
# driver.fin_element(By.XPATH, "/html/body/div/div/div/div[2]/div[2]/div[1]/div[1]/div/ul/li/div[1]/span").click

