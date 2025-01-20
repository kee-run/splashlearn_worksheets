import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
import json
import pandas as pd
import pdf_maker
import datetime, time
import yaml
import logging
import sys
import http.client as http_client  # Required for HTTP headers and logging

pyfilename = os.path.basename(__file__).split(".")[0]
# Function to get all links starting with the specified base URL
def get_links(url, base_url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        links = set()

        for a_tag in soup.find_all('a', href=True):
            full_url = urljoin(url, a_tag['href'])
            if full_url.startswith(base_url):
                links.add(full_url)

        return links
    except requests.exceptions.RequestException as e:
        print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5] ,f"Error fetching {url}: {e}")
        return set()

# Main function to crawl and collect links recursively
def crawl_links(start_url, base_url, max_depth=2, depth=0, visited=None):
    if visited is None:
        visited = set()

    if depth > max_depth:
        return visited

    links = get_links(start_url, base_url)

    for link in links:
        if link not in visited:
            visited.add(link)
            visited.update(crawl_links(link, base_url, max_depth, depth + 1, visited))

    return visited

def extract_grades_topics_and_links(url,grade,subject,topic,pdf_base):
    try:
        
        # Fetch the webpage content
        response = requests.get(url)
        response.raise_for_status()  # Check for HTTP request errors

        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract Grades
        grade_div = soup.find('div', class_='banner-grades mt-4')
        grades = []
        grade_present = False  # Initialize the flag for GRADE 3
        lower_grade_present = False
        if grade_div:
            grade_links = grade_div.find_all('a', class_='badge playable-tag-banner js-ws-grade-tag')
            grades = [link.text.strip() for link in grade_links]
            grade_present = ("GRADE "+ grade) in grades  # Check if GRADE 3 is in the grades
            lower_grade_present = ("GRADE "+ str(int(grade)-1)) in grades  # Check if GRADE 2 is in the grades
      
        # Stop if GRADE 3 is not present
        if not grade_present: # We don't want 2nd grade stuff. Okay if a higher grade is presnet.
            return None # json.dumps({"info": "Grade 3 not applicable"}, indent=4)
        # Extract Subject and Topics
        topic_div = soup.find('div', class_='banner-subject-topics')
        # print(topic_div)
        """<div class="banner-subject-topics">
            <div class="pt-2 text-center">
            <a href="/math-worksheets">
            <div class="badge playable-tag-banner playable-tag-banner-subject js-ws-subject-tag"> 
                                        MATH WORKSHEETS
                                    </div>
            </a>
            </div>
            <div class="pt-2 text-center">
            <a class="badge playable-tag-banner playable-tag-banner-topics js-ws-topic-tag-1" href="/math/data-handling-worksheets">
                                            DATA HANDLING WORKSHEETS
                                        </a>
            </div>
            </div>
        """
        subjects = []
        topics = []
        if topic_div:
            subject_links = topic_div.find_all('div', class_='badge playable-tag-banner playable-tag-banner-subject js-ws-subject-tag')
            subjects = [link.text.strip() for link in subject_links]
            topic_links = topic_div.find_all('a', class_='badge playable-tag-banner playable-tag-banner-topics js-ws-topic-tag-1')
            topics = [link.text.strip() for link in topic_links]
            # Extrat additional topics as well
            topic_links = topic_div.find_all('a', class_='badge playable-tag-banner playable-tag-banner-topics js-ws-topic-tag-2')  
            topics.append([link.text.strip() for link in topic_links])

        
        pdf_links = []
        for a_tag in soup.find_all('a', href=True):
            full_url = urljoin(url, a_tag['href'])
            if full_url.startswith(pdf_base):
                pdf_links.append(full_url)


        # Prepare JSON response
        result = {
            "grades": grades,
            "subjects": subjects,
            "topics": topics,
            "pdf_links": pdf_links  # Include the extracted PDF links
        }

        return json.dumps(result, indent=4)  # Return formatted JSON

    except requests.RequestException as e:
        return json.dumps({"error": f"An error occurred while fetching the webpage: {e}"}, indent=4)

# Function to flatten a list of lists


def flatten_list(lst):
    if isinstance(lst, list):
        # Also, de-duplicate after flattening the list. This is required because the same PDF link can be present in multiple topics
        return ', '.join(map(str, [item for sublist in lst for item in (sublist if isinstance(sublist, list) else [sublist])]))
    return lst

# Function to deduplicate a CSV file and overwrite the existing file
def deduplicate_csv_file(file_name):
    df_csv = pd.read_csv(file_name)
    # drop duplicates after considering all columns
    df_csv.drop_duplicates(inplace=True)
    # Write the results to the file ad overwrite the existing file
    df_csv.to_csv(file_name, mode='w', header=True, index=False)
    return

# Main code to crawl the website and collect links
def main():

    print(" ")
    
    # Ask the user if they want to do a test run or a full run
    full_run = input("Do you want to do a full run? (y/n): ")
    test_crawl = True
    if full_run.lower() == "y":
        print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5] ,"Full run selected.")
        test_crawl = False
    else:
        print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5] ,"Test run selected. L2 crawl will be limited to the first webpage.")
        test_crawl = True


    print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5] , "Starting now")

    # Config and secrets - Create objects to read config.yaml
    with open("config.yaml", "r") as file_object:
        config = yaml.load(file_object, Loader=yaml.SafeLoader)

    # Set logging levels
    log_level = config['default']['loglevel']  # Change to DEBUG for all troubleshooting
    log_http_debug = config['default']['loghttpdebug']  # Change to TRUE if required to log HTTP headers
    logging.basicConfig(stream=sys.stdout, format='%(asctime)s %(levelname)-8s %(message)s',
                        datefmt='%Y%m%d %H:%M:%S', level=int(log_level), encoding='utf-8')
    http_client.HTTPConnection.debuglevel = int(log_http_debug)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(int(log_level))
    requests_log.propagate = True

    # Write logs to both the logfile and stdout
    class Logger(object):
        def __init__(self):
            self.terminal = sys.stdout
            log_filename = f"logs/{pyfilename}_{str(datetime.datetime.today().date())}.log"
            os.makedirs(os.path.dirname(log_filename), exist_ok=True)
            self.log = open(log_filename, mode="a",
                            encoding='utf8')

        def write(self, message):
            self.terminal.write(message)
            self.log.write(message)

        def flush(self):
            # this flush method is needed for python 3 compatibility.
            # this handles the flush command by doing nothing.
            # you might want to specify some extra behavior here.
            pass

    sys.stdout = Logger()

    # Extract configuration values
    grade_filter = config['splashlearn']['grade'] # Grade to crawl
    topic = config['splashlearn']['topic'] 
    subject = config['splashlearn']['subject'] #Subject name is based on URL pattern. Options are math and ela.
    website = config['splashlearn']['website'] # Website to crawl
    grade = grade_filter.split("rd")[0]
    start_url = website + "/" + subject +"-worksheets" + "-for-" + grade_filter + "-graders"
    base_url =  start_url
    visited = None
    links = None

    # WGET and other crawls don't work well with this site. So, we will crawl the site and save the links to a file
    # This is the first level crawl

    # Do this if the file is not already created or is empty
    if not os.path.exists(f"{grade_filter}_grade_{subject}_webpages.txt") or os.path.getsize(f"{grade_filter}_grade_{subject}_webpages.txt") == 0:
        visited = crawl_links(start_url, base_url, max_depth=3)
        # Visited links have a page number at the end (e.g., https://www.splashlearn.com/math-worksheets-for-3rd-graders/page/3) Get the highest page number
        # and then create links for all the missing pages and add to visited\
        # Get the highest page number
        max_page = 1
        for link in visited:
            if "page" in link:
                page = int(link.split("page/")[1])
                if page > max_page:
                    max_page = page
        # Create links for all the missing pages and add to visited and reorder by page number

        for page in range(2, max_page+1):
            visited.add(f"{start_url}/page/{page}")
        # Sort the links by page number but remember page number is a string
        visited = sorted(visited, key=lambda x: int(x.split("page/")[1]) if "page" in x else 0)
        # Write the results to the file
        with open(f"{grade_filter}_grade_{subject}_webpages.txt", "w") as f:
            for link in visited:
                #restrict links to those that have the grade_filter in the URL
                if grade_filter in link:
                    f.write(f"{link}\n")
                    print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5] ,f"Crawled L1: {link}")
        # Print the total number of links collected in the file
        print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5] ,"Total number of L1 pages crawled:", len(set(visited)))

    df = pd.DataFrame(columns=['grades', 'subjects', 'topics', 'pdf_links'])
    
    # Next level crawl
    # For each page in the grade_filter+grade+topic links.txt file, get the links to each worksheet page which will have a base url of "https://www.splashlearn.com/s/math-worksheets/" and write the results to a file called grade_filter + +grade+topic+math+worksheets+pages.txt
    # Do this if the file is not already created or is empty
    if not os.path.exists(f"{grade_filter}_grade_{subject}_pdf_metadata.csv") or os.path.getsize(f"{grade_filter}_grade_{subject}_pdf_metadata.csv") == 0:
        visited = None
        links = None
        with open(f"{grade_filter}_grade_{subject}_webpages.txt", "r") as f:
            for line in f:
                page_url = line.strip()
                print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5] , "L2 crawling page:", page_url)
                worksheet_base = config['splashlearn']['worksheet_base'] # Worksheets have this URL pattern
                pdf_base = config['splashlearn']['pdf_base'] # PDFs have this URL pattern
                visited = crawl_links(page_url, worksheet_base, max_depth=2) # Only need the math worksheets page links which would have the same URL pattern for base_url
                # De-duplicate the links
                visited = set(visited)
                print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5] ,"Total number of math worksheets pages collected:", len(set(visited)))
                count = 0
                for link in visited:
                    # Extract the topic, grade and PDF link from the URL and include it in the file as comma delimited
                    print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5] ,f"Crawled L2: {link}")
                    grade_subject_links = extract_grades_topics_and_links(link,grade,subject,topic,pdf_base)
                    # Write to data only if it's not None
                    if grade_subject_links:
                        data = json.loads(grade_subject_links)
                        df = pd.json_normalize(data)
                        for column in df.columns:
                            if isinstance(df[column][0], list):
                                df[column] = df[column].apply(flatten_list)

                    # Write the results to the file
                        df.to_csv(f"{grade_filter}_grade_{subject}_pdf_metadata.csv", mode='a', header=False, index=False)
                    count += 1
                    if test_crawl and count > 10:
                        break
                # Stop if test crawl
                if test_crawl:
                    break
    # Print the total number of links collected in the file
        print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5] ,"Total number of PDFs collected in the dataframe:", len(df) )

    print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5] ,"Beggining PDF download and consolidation")
    
    # deduplicate the CSV file
    deduplicate_csv_file(f"{grade_filter}_grade_{subject}_pdf_metadata.csv")

    # sleep for 0.5 seconds to allow the file to be closed
    time.sleep(0.5)
    pdf_maker.build_pdf(f"{grade_filter}_grade_{subject}_pdf_metadata.csv", f"{grade_filter}_grade_{subject}_consolidated_PDFs.pdf")
    print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5] ,"All done. Consolidated PDFs are in the file", f"{grade_filter}_grade_{subject}_consolidated_PDFs.pdf")

if __name__ == "__main__":
    main()