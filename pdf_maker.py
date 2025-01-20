import os
import csv
import requests
import fitz  # PyMuPDF
from collections import defaultdict
import datetime

pyfilename = os.path.basename(__file__).split(".")[0]
def check_csv_duplicates(csv_path):
    """
    Identify any duplicate PDF links (column index 3) in a CSV *without* headers.
    Return a set of all links that appear more than once.
    """
    seen_links = set()
    duplicates = set()

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for line_num, row in enumerate(reader, start=1):
            # Skip completely empty lines
            if not row:
                continue

            # Expect at least 4 columns: [grades, subjects, topics, pdf_links]
            if len(row) < 4:
                continue

            pdf_link = row[3].strip()
            if pdf_link in seen_links:
                duplicates.add(pdf_link)
            else:
                seen_links.add(pdf_link)

    if duplicates:
        for link in duplicates:
            print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5],"\nWARNING: This PDF link is a duplicate and will be skipped if encountered again:", link)

    return duplicates

import time
def download_pdf(url, filepath):
    """
    Downloads a PDF from the given URL and saves it to the specified filepath.
    Returns True if successful, False otherwise.
    """
    
    try:
        
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open(filepath, 'wb') as f:
            f.write(r.content)
        #sleep for 0.5 second to avoid getting blocked
        time.sleep(0.5)
        
        print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5] ,f"    --> Downloaded to {filepath}")
        return True
    except Exception as e:
        print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5] ,f"    Failed to download {url}: {e}")
        return False

def add_headers_to_pdf(pdf_path, topics, grades):
    doc = fitz.open(pdf_path)
    topics_str = ", ".join(topics)
    grades_str = ", ".join(grades)
    font_size = 12
    font_name = "helvetica-bold"
    for page in doc:
        page.insert_text((10, 15), topics_str,fontsize=font_size,
            fontname=font_name)
        page.insert_text((page.rect.width - 195, 50), grades_str,fontsize=font_size,
            fontname=font_name)

    # 1) Construct a temporary file name
    temp_path = pdf_path + ".temp"

    # 2) Save to the temp file with deflate / garbage collection if you want
    doc.save(temp_path, deflate=True, garbage=4)

    # 3) Close the doc
    doc.close()

    # 4) Rename temp file to original, overwriting it
    os.replace(temp_path, pdf_path)


def build_topic_hierarchy(csv_path, duplicate_links):
    """
    Reads the CSV file (no header) and returns a nested dictionary structure:
      {
          main_topic_1: {
             (subtopic1, subtopic2, ...): [pdf_file_1, pdf_file_2, ...],
             (...): [...]
          },
          main_topic_2: { ... },
          ...
      }
    Only includes rows where Grade 3 is present in the 'grades' column (index 0).
    'pdf_links' is column index 3.

    For each qualifying row:
      - Skips the row if the link is in 'duplicate_links'.
      - Checks if the PDF is already downloaded in 'downloaded_pdfs/'.
        If it exists, skip that row entirely.
        Otherwise, download the PDF.
      - Stamps headers (topics top-left, grades top-right).
    """
    pdf_folder = "downloaded_pdfs"
    os.makedirs(pdf_folder, exist_ok=True)

    hierarchy = defaultdict(lambda: defaultdict(list))

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for line_num, row in enumerate(reader, start=1):
            if not row:  # skip empty lines
                continue
            if len(row) < 4:
                continue

            row_grades = row[0].strip()
            row_topics = row[2].strip()
            pdf_link = row[3].strip()

            # If this link is known to be a duplicate, skip it
            if pdf_link in duplicate_links:
                continue

            # We only care about rows containing Grade 3
            grades_list = [g.strip() for g in row_grades.split(',')]
            if 'GRADE 3' not in grades_list:
                continue

            # Parse topics
            topics_list = [t.strip() for t in row_topics.split(',')]

            if not topics_list:
                continue  # Skip if no topics found
            # The first topic is the "main topic"
            main_topic = topics_list[0]
            # Add the grade and main topic name to the beggining of the PDF filename
            pdf_filename = f"GRADE3_{main_topic}_{os.path.basename(pdf_link)}"
            pdf_path = os.path.join(pdf_folder, pdf_filename)

            print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5],f"\nProcessing link (line {line_num}): {pdf_link}")

            # If the file is already downloaded, skip
            if os.path.exists(pdf_path):
                print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5],f"    File already exists, skipping download: {pdf_path}")
                # If you want to RE-stamp each time, call add_headers_to_pdf here:
                add_headers_to_pdf(pdf_path, topics_list, grades_list)
            else:
                # Download if not present
                success = download_pdf(pdf_link, pdf_path)
                if not success:
                    continue  # skip if download failed
                # Stamp headers after download
                add_headers_to_pdf(pdf_path, topics_list, grades_list)

           
            # The first topic is the "main topic"
            main_topic = topics_list[0]
            # Any subsequent topics are "subtopics"
            sub_topics = tuple(topics_list[1:]) if len(topics_list) > 1 else ()

            hierarchy[main_topic][sub_topics].append(pdf_path)
    
    return hierarchy


def create_consolidated_pdf(hierarchy, output_pdf):
    """
    Creates a consolidated PDF using the nested dictionary `hierarchy`.
    The final PDF will have:
      - Page 0: A cover page
      - Page 1: A textual Table of Contents
      - Pages 2+ : Merged PDFs, sorted by main topic (alphabetical),
                   then by sub-topic (alphabetical).
    Page numbers are added at the bottom of each merged page (excluding cover & TOC).
    """

    # 1) Create a brand-new PDF in memory:
    final_doc = fitz.open()

    # 2) Add a cover page and insert the cover text
    cover_page = final_doc.new_page(width=612, height=792)
    cover_page.insert_text(
        (72, 72),
        "Arya's 2025 H1 Math Worksheets",
        fontsize=24,
        fontname="helv"
    )

    # 3) Add X blank TOC pages (some blank pages for buffer) and insert "Table of Contents"
    # moved to later to accomodate for multi page Table of Contents.
    for _ in range(3):
        final_doc.new_page(width=612, height=792)


    # 4) Sort the main topics in alphabetical order
    main_topics_sorted = sorted(hierarchy.keys())
    # We maintain a TOC list: [ [level, title, page_number], ... ]
    toc_list = []

    # We've already used pages 0 (cover) and 1 (TOC).
    # So the next insertion starts at page index = 2
    # For set_toc, we need 1-based page numbers, so page index=2 => page number=3
    current_page_num = 3 # Space for table of contents and worksheets

    # 5) Merge each set of PDFs, and record their places in the TOC
    for main_topic in main_topics_sorted:
         # Level-1 TOC entry
        toc_list.append([1, main_topic, current_page_num + 1])
        subtopics_dict = hierarchy[main_topic]
        sorted_subtopics = sorted(subtopics_dict.keys())
        
        for subtopic_tuple in sorted_subtopics:
            if subtopic_tuple:
                # e.g. subtopic_tuple = ("Quadratic", "Word Problems")
                subtopic_title = ", ".join(subtopic_tuple)
                toc_list.append([2, subtopic_title, current_page_num + 1])
            # Merge the PDFs for this subtopic
            pdf_files = subtopics_dict[subtopic_tuple]
           
            for pdf_file in pdf_files:
                print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5],f"Merging PDF into final document: {pdf_file}")
                with fitz.open(pdf_file) as sub_doc:
                    num_pages = len(sub_doc)
                    final_doc.insert_pdf(sub_doc, from_page=0, to_page=num_pages - 1)
                    current_page_num += num_pages

    # 6) Page numbering (skip cover=0 and TOC and notes =1-100)
    total_pages = final_doc.page_count
    print(pyfilename, datetime.datetime.utcnow().strftime("%Y%m%d %H:%M:%S.%f")[:-5],f"Total pages: {total_pages}")
    for i in range(total_pages):
        if i < 2:
            continue
        page = final_doc[i]
        page_num_str = str(i)

        # Roughly estimate each character ~6 points wide at 12pt font:
        approx_char_width = 6
        text_w = approx_char_width * len(page_num_str)

        x_coord = (page.rect.width - text_w) / 2
        y_coord = page.rect.height - 25

        page.insert_text(
            (x_coord, y_coord),
            page_num_str,
            fontsize=12,
            fontname="helv"
        )


    # 7) Build a text-based TOC (index=1)
    toc_page_index = 1
    toc_page = final_doc[toc_page_index]

    # Insert the initial TOC heading on page 1:
    toc_page.insert_text((72, 72), "Table of Contents", fontsize=18, fontname="helv")

    # We'll start listing entries at y=110
    y_cursor = 110
    line_height = 20  # vertical spacing per TOC line
    # Write TOC to a CSV file
    with open("toc.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["level", "title", "page_number"])
        for level, title, page_number in toc_list:
            writer.writerow([level, title, page_number])

    for level, title, page_number in toc_list:
        # If we are near the bottom of the page, go to the next TOC page
        if y_cursor + line_height > toc_page.rect.height - 40:
            # don't create a brand new page for page but just go to the next page
            toc_page_index += 1

            toc_page = final_doc[toc_page_index]

            # Optionally label continuation:
            
            toc_page.insert_text((72, 72), "Table of Contents (Continued)", fontsize=18, fontname="helv")

            # Reset y-cursor on this new page
            y_cursor = 110

        indent = 20 * (level - 1)
        toc_line = f"{title} ................ {page_number}"

        # Write this entry
        # Add a check box on the left of each toc_line entry. checkbox should be blank and not filled
   
        # star character
        starchar = "★"
        

        toc_page.insert_text((40, y_cursor+30), "□", fontsize=100, fontname="helv", color=(0.7, 0.7, 0.7))
        toc_page.insert_text((20, y_cursor+30), "□", fontsize=100, fontname="helv", color=(0.7, 0.7, 0.7))
        
        # insert 3 stars at the end of each line
        toc_page.insert_text((500, y_cursor+28), starchar, fontsize=100, fontname="times-roman", color=(0.9, 0.9, 0.9))
        toc_page.insert_text((520, y_cursor+28), starchar, fontsize=100, fontname="times-roman", color=(0.9, 0.9, 0.9))
        toc_page.insert_text((480, y_cursor+28), starchar, fontsize=100, fontname="times-roman", color=(0.9, 0.9, 0.9))

        toc_page.insert_text((72 + indent, y_cursor), toc_line, fontsize=12, fontname="helv")
        y_cursor += line_height

    # 8) Also set the PDF's internal TOC (bookmarks)
    final_doc.set_toc(toc_list)

    # 9) Save and close
    final_doc.save(output_pdf,deflate=True)
    final_doc.close()



def build_pdf(input_csv, output_pdf):
    
    # 1) Identify duplicates (rows with repeated link in col 3).
    duplicates = check_csv_duplicates(input_csv)

    # 2) Build hierarchy, skipping duplicates, blank lines, lines <4 cols, etc.
    topic_hierarchy = build_topic_hierarchy(input_csv, duplicates)

    # 3) Merge everything into a final PDF (with cover and TOC).
    create_consolidated_pdf(topic_hierarchy, output_pdf)

