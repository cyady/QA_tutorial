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
driver.maximize_window()    #maximize window

#driver.get("https://automationpractice.com/index.php")
#
#
# driver.find_element(By.ID, "details-button").click()
# driver.find_element(By.ID, "proceed-link").click()

driver.get("https://www.musinsa.com/app/")

rank = driver.find_elements(By.CLASS_NAME, "slick-slide")
print(len(rank))    #total number of rankkink

rank_active = driver.find_elements(By.CLASS_NAME, "slick-slide slick-active slick-current")
print(rank_active)  #list

rank_main = driver.find_elements(By.CLASS_NAME, "main_ranking_item main_contents_maxwidth")
print(rank_main)  #list

rank_hoverbox = driver.find_elements(By.CLASS_NAME, "ranking_item hover_box")
print(rank_hoverbox)   #list

Tag_a = driver.find_elements(By.TAG_NAME, "a")
print(len(Tag_a))   #2455 total number of links on homepage