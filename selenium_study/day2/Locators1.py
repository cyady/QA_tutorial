#webdriver 모듈 가져오는게 먼져
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

Chrome_Options = Options()
driver=webdriver.Chrome()


Chrome_Options.add_experimental_option("detach", True)  #브라우저 꺼짐 방지
driver.implicitly_wait(2)


driver = webdriver.Chrome(options=Chrome_Options, service=Service(ChromeDriverManager().install()))

driver.get("https://demo.nopcommerce.com/")
driver.maximize_window()    #maximize window

#NAME
# driver.find_element(By.NAME, "q").send_keys("Lenovo Thinkpad X1 Carbon Laptop")

#Linktext & partial Linktext
# driver.find_element(By.LINK_TEXT, "Register").click()
# driver.find_element(By.PARTIAL_LINK_TEXT, "Reg").click()




# driver.close()  #브라우저 한개닫기
driver.quit()   #브라우저 다 닫기


