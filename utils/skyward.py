from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
import platform
import time
import os
import subprocess
import traceback
import logging
import base64

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def save_screenshot_base64(driver, name):
    try:
        screenshot = driver.get_screenshot_as_base64()
        logger.info(f"Screenshot {name} (base64): {screenshot}")
        return screenshot
    except Exception as e:
        logger.error(f"Failed to take screenshot {name}: {str(e)}")
        return None

class SkywardGPA:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.driver = None
        self.grades_raw = {}
        self.grades = {}
        self.period_gpas = {}
        self.weighted_period_gpas = {}
        self.period_order = ['1U1', '1U2', 'NW1', '2U1', '2U2', 'NW2', 'EX1', 'SM1', 
                            '3U1', '3U2', 'NW3', '4U1', '4U2', 'NW4', 'EX2', 'SM2', 'YR']
        self.ordered_periods = []

    def calculate(self):
        try:
            logger.info("Setting up Chrome options...")
            options = webdriver.ChromeOptions()
            
            if platform.system() == 'Linux':  # Render
                chrome_binary = '/usr/bin/google-chrome'
                logger.info(f"Using Chrome binary: {chrome_binary}")
                options.binary_location = chrome_binary
                
                # Memory optimization arguments
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-gpu')
                options.add_argument('--headless=new')
                options.add_argument('--disable-extensions')
                options.add_argument('--disable-software-rasterizer')
                options.add_argument('--disable-features=VizDisplayCompositor')
                options.add_argument('--window-size=1920,1080')  # Full size for better rendering
                options.add_argument('--start-maximized')
                options.add_argument('--force-device-scale-factor=1')
                options.add_argument('--disable-web-security')  # Allow cross-origin requests
                options.add_argument('--disable-features=IsolateOrigins,site-per-process')  # Better frame handling
            else:  # Local
                options.add_argument('--headless=new')
            
            # Common options
            options.add_argument('--ignore-certificate-errors')
            options.add_experimental_option('excludeSwitches', ['enable-logging'])
            
            logger.info("Initializing Chrome driver...")
            try:
                self.driver = webdriver.Chrome(options=options)
                self.driver.set_page_load_timeout(60)  # Increased timeout
                self.driver.set_script_timeout(60)     # Increased timeout
                logger.info("Chrome driver initialized successfully")
            except Exception as e:
                logger.error(f"Error initializing Chrome driver: {str(e)}")
                return self._create_error_response("Failed to initialize Chrome driver")

            try:
                self.login()
                save_screenshot_base64(self.driver, "after_login")
                self.navigate_to_gradebook()
                self.extract_grades()
                self.calculate_gpas()
                
                # Ensure we have valid data
                if not self.grades or not self.ordered_periods:
                    logger.warning("No grades found, but no errors occurred")
                    return self._create_error_response("No grades found in Skyward")
                
                return {
                    'success': True,
                    'error': None,
                    'grades_raw': self.grades_raw,
                    'grades': self.grades,
                    'unweighted_gpas': self.period_gpas,
                    'weighted_gpas': self.weighted_period_gpas,
                    'ordered_periods': self.ordered_periods
                }
            except Exception as e:
                logger.error(f"Error during grade calculation: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                if self.driver:
                    save_screenshot_base64(self.driver, "error_state")
                return self._create_error_response(str(e))
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception as e:
                    logger.error(f"Error closing driver: {str(e)}")

    def _create_error_response(self, error_message):
        """Helper method to create a standardized error response"""
        return {
            'success': False,
            'error': error_message,
            'grades_raw': {},
            'grades': {},
            'unweighted_gpas': {},
            'weighted_gpas': {},
            'ordered_periods': []
        }

    def login(self):
        try:
            logger.info("Attempting to access login page...")
            login_url = "https://skyward-alvinprod.iscorp.com/scripts/wsisa.dll/WService=wsedualvinisdtx/fwemnu01.w"
            self.driver.get(login_url)
            
            # Wait for username input with direct XPath
            logger.info("Waiting for login form...")
            username_xpath = '/html/body/form[1]/div/div/div[4]/div[2]/div[1]/div[2]/div/table/tbody/tr[1]/td[2]/input'
            username_input = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.XPATH, username_xpath))
            )
            
            # Fill credentials using direct XPaths
            username_input.clear()
            username_input.send_keys(self.username)
            time.sleep(0.5)
            
            password_xpath = '/html/body/form[1]/div/div/div[4]/div[2]/div[1]/div[2]/div/table/tbody/tr[2]/td[2]/input'
            password_input = self.driver.find_element(By.XPATH, password_xpath)
            password_input.clear()
            password_input.send_keys(self.password)
            time.sleep(0.5)
            
            # Click sign in button with direct XPath
            sign_in_xpath = '/html/body/form[1]/div/div/div[4]/div[2]/div[1]/div[2]/div/table/tbody/tr[7]/td/a'
            sign_in_button = self.driver.find_element(By.XPATH, sign_in_xpath)
            sign_in_button.click()
            logger.info("Credentials submitted")

            # Wait for new window or URL change
            try:
                logger.info("Waiting for login response...")
                time.sleep(2)  # Brief pause for window creation
                
                # Check for multiple windows
                if len(self.driver.window_handles) > 1:
                    logger.info("New window detected, switching...")
                    self.driver.switch_to.window(self.driver.window_handles[-1])
                    success = True
                else:
                    # Wait for URL change
                    WebDriverWait(self.driver, 10).until(
                        lambda d: "sfhome01.w" in d.current_url
                    )
                    success = True
                
                if success:
                    logger.info("Successfully logged in")
                    time.sleep(2)  # Wait for page to stabilize
                    save_screenshot_base64(self.driver, "login_success")
                    return
                else:
                    raise Exception("Failed to verify successful login")

            except Exception as e:
                logger.error(f"Login verification failed: {str(e)}")
                save_screenshot_base64(self.driver, "login_error")
                raise Exception("Login failed. Please try again in a few minutes.")

        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            save_screenshot_base64(self.driver, "login_failure")
            raise

    def navigate_to_gradebook(self):
        try:
            logger.info("Navigating to gradebook...")
            time.sleep(2)  # Wait for page to stabilize
            
            # Take screenshot to debug
            save_screenshot_base64(self.driver, "before_navigation")
            
            # Click the plus button using exact XPath
            logger.info("Looking for plus button...")
            plus_xpath = '/html/body/div[1]/div[2]/div[2]/div[1]/div/ul[1]/li/a'
            
            try:
                # Wait and click plus button
                plus_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, plus_xpath))
                )
                logger.info("Found plus button, clicking...")
                plus_button.click()
                time.sleep(1.5)  # Wait longer for menu animation
                
                # Click gradebook using exact XPath
                logger.info("Looking for gradebook link...")
                gradebook_xpath = '/html/body/div[1]/div[2]/div[2]/div[1]/div/ul[2]/li[3]/a'
                gradebook_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, gradebook_xpath))
                )
                logger.info("Found gradebook link, clicking...")
                gradebook_button.click()
                time.sleep(1)  # Wait for click to register
                
                # Wait for gradebook table to load
                logger.info("Waiting for gradebook to load...")
                table_xpath = '/html/body/div[1]/div[2]/div[2]/div[2]/div/div[4]/div[4]/div[2]/div[1]/div/div[1]/div[1]/table'
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.XPATH, table_xpath))
                )
                
                # Additional wait for table to be fully loaded
                time.sleep(2)
                logger.info("Gradebook loaded successfully")
                save_screenshot_base64(self.driver, "gradebook_loaded")
                
            except Exception as e:
                logger.error(f"Navigation failed: {str(e)}")
                save_screenshot_base64(self.driver, "navigation_error")
                raise

        except Exception as e:
            logger.error(f"Navigation error: {str(e)}")
            save_screenshot_base64(self.driver, "navigation_error")
            raise

    def extract_grades(self):
        try:
            logger.info("Starting grade extraction...")
            logger.info("Finding grading periods...")
            
            # Get all period headers at once
            grading_periods_xpath = '/html/body/div[1]/div[2]/div[2]/div[2]/div/div[4]/div[4]/div[2]/div[1]/div/div[1]/div[1]/table/thead/tr/th'
            grading_periods = WebDriverWait(self.driver, 20).until(
                EC.presence_of_all_elements_located((By.XPATH, grading_periods_xpath))
            )
            logger.info(f"Found {len(grading_periods)} grading periods")
    
            # Get period labels
            period_labels = []
            for period in grading_periods:
                try:
                    label = period.get_attribute('innerText')
                    period_labels.append(label if label else '-')
                except:
                    period_labels.append('-')
            logger.info(f"Raw period labels found: {period_labels}")

            # Get all valid periods
            self.ordered_periods = [period for period in self.period_order 
                                  if period in period_labels]
            logger.info(f"Valid periods found: {self.ordered_periods}")

            # Wait for grades table and ensure it's loaded
            logger.info("Getting grades table...")
            grades_table_xpath = '/html/body/div[1]/div[2]/div[2]/div[2]/div/div[4]/div[4]/div[2]/div[1]/div/div[1]/div[2]/table/tbody'
            grades_table = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.XPATH, grades_table_xpath))
            )
            
            # Get all rows first
            rows_xpath = f"{grades_table_xpath}/tr"
            class_rows = WebDriverWait(self.driver, 20).until(
                EC.presence_of_all_elements_located((By.XPATH, rows_xpath))
            )
            logger.info(f"Found {len(class_rows)} rows in grades table")
            
            # Wait for class names container and get class names
            logger.info("Getting class names...")
            classes_xpath = '/html/body/div[1]/div[2]/div[2]/div[2]/div/div[4]/div[4]/div[2]/div[2]/div[2]/table/tbody'
            classes_container = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.XPATH, classes_xpath))
            )
            
            # Scroll the container into view and wait
            self.driver.execute_script("arguments[0].scrollIntoView(true);", classes_container)
            time.sleep(2)  # Allow time for any dynamic content to load
            
            # Get class names using XPath
            class_names_xpath = f"{classes_xpath}//td//span/a"
            class_name_elements = WebDriverWait(self.driver, 20).until(
                EC.presence_of_all_elements_located((By.XPATH, class_names_xpath))
            )
            class_names = [elem.text for elem in class_name_elements]
            logger.info(f"Found {len(class_names)} classes: {class_names}")

            # Process grades row by row with explicit waits
            for i, (class_row, class_name) in enumerate(zip(class_rows, class_names), 1):
                try:
                    logger.info(f"Processing {class_name} ({i}/{len(class_rows)})")
                    
                    # Scroll the row into view
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", class_row)
                    time.sleep(0.5)  # Short wait after scrolling
                    
                    # Get cells with XPath
                    cells = class_row.find_elements(By.TAG_NAME, "td")
                    logger.info(f"Found {len(cells)} grade cells for {class_name}")
                    
                    class_grades = {}
                    for cell_index, cell in enumerate(cells):
                        try:
                            if cell_index >= len(period_labels):
                                break
                            
                            # Wait for cell to be visible
                            WebDriverWait(self.driver, 5).until(
                                EC.visibility_of(cell)
                            )
                            
                            text = cell.get_attribute('innerText')
                            logger.info(f"Cell {cell_index} for {class_name}: {text}")
                            if text and text.replace('.', '').isnumeric():
                                period = period_labels[cell_index]
                                class_grades[period] = float(text)
                        except Exception as cell_error:
                            logger.error(f"Error processing cell {cell_index} for {class_name}: {str(cell_error)}")
                            continue

                    if class_grades:
                        logger.info(f"Grades found for {class_name}: {class_grades}")
                        self.grades_raw[class_name] = class_grades
                        filtered_grades = {period: grade for period, grade in class_grades.items() 
                                        if period in self.ordered_periods}
                        if filtered_grades:
                            self.grades[class_name] = filtered_grades
                            logger.info(f"Filtered grades for {class_name}: {filtered_grades}")
                    
                    # Take a screenshot after processing each class
                    save_screenshot_base64(self.driver, f"class_{i}_{class_name.replace(' ', '_')}")
                            
                except Exception as e:
                    logger.error(f"Error processing row {i}: {str(e)}")
                    save_screenshot_base64(self.driver, f"error_class_{i}")
                    continue

            logger.info("Grade extraction completed successfully")
            logger.info(f"Total classes processed: {len(self.grades)}")
            logger.info(f"Final grades dictionary: {self.grades}")
            logger.info(f"Final ordered periods: {self.ordered_periods}")

            # Take a final screenshot
            save_screenshot_base64(self.driver, "final_grades_state")

        except Exception as e:
            logger.error(f"Error in extract_grades: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            save_screenshot_base64(self.driver, "extract_grades_error")
            raise

    def calculate_gpas(self):
        for period in self.ordered_periods:
            total_gpa = 0
            num_classes = 0
            
            for class_name, class_grades in self.grades.items():
                if period in class_grades:
                    grade = class_grades[period]
                    gpa = 6.0 - (100 - grade) * 0.1
                    total_gpa += gpa
                    num_classes += 1
            
            if num_classes > 0:
                self.period_gpas[period] = total_gpa / num_classes

        for period in self.ordered_periods:
            total_gpa = 0
            num_classes = 0
            
            for class_name, class_grades in self.grades.items():
                if period in class_grades:
                    grade = class_grades[period]
                    
                    if "APA" in class_name:
                        base_gpa = 7.0
                    elif "AP" in class_name:
                        base_gpa = 8.0
                    else:
                        base_gpa = 6.0
                    
                    weighted_gpa = base_gpa - (100 - grade) * 0.1
                    total_gpa += weighted_gpa
                    num_classes += 1
            
            if num_classes > 0:
                self.weighted_period_gpas[period] = total_gpa / num_classes
