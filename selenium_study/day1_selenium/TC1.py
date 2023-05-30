# TC1
# ---------
# 1) Open Web Brower( Chrome/firefox/IE )
# 2) Open URL https://opensource-demo.orangehrmlive.com
# 3) Provide username (Admin)
# 4) Provide password (admin123)
# 5) Click on login
# 6) Capture title of the home page.(Actual title)
# 7) Verify title of the page: OrangeHRM (Expected)
# 8) close browser

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

import time

# driver = webdriver.Chrome(executable_path=r"C:\Users\cyady\Desktop\project\QA\QA_tutorial\drivers\chromedriver_win32_113.0.5672")
#DeprecationWarning: executable_path has been deprecated, please pass in a Service object
Chrome_Options = Options()
Chrome_Options.add_experimental_option("detach", True)  #브라우저 꺼짐 방지

#1
driver = webdriver.Chrome(options=Chrome_Options, service=Service(ChromeDriverManager().install()))
#2
driver.implicitly_wait(2)
driver.maximize_window()
driver.get("https://opensource-demo.orangehrmlive.com")

driver.find_element(By.NAME, "username").clear()
driver.find_element(By.NAME, "password").clear()
#3
driver.find_element(By.NAME, "username").send_keys("Admin")
#4
driver.find_element(By.NAME, "password").send_keys("admin123")
#5
driver.find_element(By.CSS_SELECTOR, "#app > div.orangehrm-login-layout > div > div.orangehrm-login-container > div > div.orangehrm-login-slot > div.orangehrm-login-form > form > div.oxd-form-actions.orangehrm-login-action > button").click()
#6
act_title=driver.title
exp_title="OrangeHRM"

# driver.find_element(By.XPATH, "/html/body/div/div[1]/div[1]/aside/nav/div[2]/ul/li[6]/a/span").click()
#7
if act_title == exp_title:
    print("Login test passed")
else:
    print("Login test Failed")
#8
driver.close()

# driver.find_element_by_name("username").send_keys("Admin")
# driver.find_element_by_id("password").send_keys("admin123")
# driver.find_element_by_name("Login").click()









