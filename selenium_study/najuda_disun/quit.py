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
driver.maximize_window()

driver.quit()