import os
import time
import re
import json
import requests
from bs4 import BeautifulSoup
import zipfile
from http.cookiejar import MozillaCookieJar
from urllib.parse import urljoin

class ScraperManager:
    def __init__(self):
        self.scrapers = {}

        self.data_file_name = "scraper.json"
        self.data = self.load_data()
        #self.dir_path = f"comics"
        self.dir_path = f"../scraped"
        os.makedirs(self.dir_path, exist_ok=True)

    def __str__(self):
        return f"<ScraperManager scrapers:{self.scrapers} data:{self.data}>"

    def add(self,scraper):
        self.scrapers[scraper.title] = scraper

    def load_data(self):
        try:
            with open(self.data_file_name, "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return {}

    def save_data(self):
        with open(self.data_file_name, "w") as file:
            json.dump(self.data, file, indent=4)        

    def run(self,title,use_stored_data=True,gallery_based=False):
        count = 0
        restarted = False

        scraper = self.scrapers.get(title)
        params = scraper.params
        if use_stored_data and self.data.get(scraper.title):
            restarted = True
            #read data and adjust params
            #print( self.data.get(scraper.title) )
            for key, value in self.data.get(scraper.title).items():
                params[key] = value

        #run
        print(f"Running scraper {scraper.title}")
        
        # Create or add to the zip file
        zip_filename = os.path.join(self.dir_path, f"{scraper.title}.cbz")
        with zipfile.ZipFile(zip_filename, 'a') as zipf:
            existing_files = set(zipf.namelist())
            if not gallery_based and restarted:
                i = len(existing_files)
                #print(f"...restarting with #{i}")
            else:
                i = 1
                #print(f"normal start")

            for data in scraper.generator(params):
                #print(f"Scraped data: {data}")
                # scraper generator MUST return data.img_url
                # scraper generator MAY return other entries in data to be stored as parameters for future generator calls
                img_url = data["img_url"]
                # img url 2 filename
                picname = "".join(char if char.isalnum() or char == '.' else "_" for char in img_url)
                numbered_picname = f"{i:05d}-{picname}"
                existing_picnames = [filename[6:] for filename in zipf.namelist()]
                
                #if not restarted or numbered_picname not in zipf.namelist():
                if not restarted or picname not in existing_picnames:
                    img_data = requests.get(img_url).content
                    zipf.writestr(numbered_picname, img_data)
                    count += 1
                    #print(f"Added {numbered_picname} to zip")
                    
                    #Saving data for restart
                    #print(f"Saving {data}")
                    self.data[scraper.title] = data
                    self.save_data()
                #else:
                    #print(f"Skipped {numbered_picname}")
                i += 1

        if count > 0:
            print(f"DONE - added {count} pages to cbz file")
        else:
            print("DONE")



class Scraper:
    def __init__(self, title, generator, params):
        self.title = title
        self.generator = generator
        self.params = params

    def __str__(self):
        return f"<Scraper title:{self.title} params:{self.params} generator:{self.generator}>"

    @staticmethod
    def incognitymous(params):
        """A generator function that yields image URLs from a gallery page."""
        session = requests.Session()

        cookie_jar = MozillaCookieJar(params["cookie_filename"])
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
        session.cookies.update(cookie_jar)
            
        response = session.get(params["page_url"])
        if response.status_code != 200:
            print(f"Failed to download gallery page, status code: {response.status_code}")
            print(f"You might need to update the cookie")
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        for link in soup.find_all(class_='lb-link'):
            img_url = link.get('href')
            if img_url:
                yield {
                    "img_url": img_url
                }

    @staticmethod
    def serpent(params):
        session = requests.Session()
        current_page = params["page_url"]
        while True:
            # Request the current page
            response = session.get(current_page)
            if response.status_code != 200:
                break
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract the image URL from the <picture> tag if we're not skipping the page
            if not current_page.split('/')[-1].startswith("S"):
                picture_tag = soup.find('picture')
                if picture_tag:
                    img_tag = picture_tag.find('img')
                    if img_tag and img_tag.get('src'):
                        yield {
                            "img_url": urljoin(current_page, img_tag.get('src')),
                            "page_url": current_page
                        } 

            # Find the 'Next' link and decide whether to continue or skip
            next_link = soup.find(lambda tag: tag.name == "a" and "Next" in tag.text and 'lnk' in tag.get('class', []))
            if next_link and next_link.get('href'):
                next_page = urljoin(current_page, next_link.get('href'))

                # Check if the link is in silver, indicating the end
                if 'silver' in str(next_link):
                    break  # End condition met
                current_page = next_page  # Prepare the URL for the next page
            else:
                break  # No next link found            

    @staticmethod
    def succubus(params):
        session = requests.Session()
        current_page = params["page_url"]
        while True:
            # Request the current page
            response = session.get(current_page)
            if response.status_code != 200:
                break
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find the image element
            img_tag = soup.find("img", id="comicimage")
            if img_tag and img_tag.get('src'):
                yield {
                    "img_url":img_tag['src'],
                    "page_url": current_page
                } 
            time.sleep(0.5)
            # Update the current page to the next one (if exists)
            next_link = soup.find("a", rel="next", class_="comicnavlink")
            if next_link and "comicnavlink-grayedout" not in next_link.get("class", []):
                current_page = urljoin(current_page, next_link['href'])
            else:
                break  # Stop if there's no 'next' page or if it's the end
        
    @staticmethod
    def cummoner(params):
        session = requests.Session()
        current_page = params["page_url"]
        while True:
            # Request the current page
            response = session.get(current_page)
            if response.status_code != 200:
                break
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find the image element
            comic_div = soup.find('div', id='comic')
            if comic_div:
                img_tag = comic_div.find('img')
                if img_tag and img_tag.get('src'):
                    yield {
                        "img_url":img_tag['src'],
                        "page_url": current_page
                    }

            # time.sleep(0.5)
            # Update the current page to the next one (if exists)
            next_link = soup.find('a', class_='navi comic-nav-next navi-next')
            if next_link and next_link.get('href'):
                current_page = next_link['href']
            else:
                break # Stop if there's no 'next' page or if it's the end

    @staticmethod
    def elven(params):
        session = requests.Session()
        current_page = params["page_url"]
        while True:
            # Request the current page
            response = session.get(current_page)
            if response.status_code != 200:
                break
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find the image element
            comic_div = soup.find('div', id='one-comic-option')
            if comic_div:
                img_tags = comic_div.find_all('img')
                for img in img_tags:
                    if img.get('src'):
                        yield {
                            "img_url":img['src'],
                            "page_url": current_page
                        }
            
            # Update the current page to the next one (if exists)
            next_link = soup.find('a', class_='next-comic')
            if next_link and next_link.get('href'):
                current_page = next_link['href']
            else:
                break # Stop if there's no 'next' page 

    @staticmethod
    def oglaf(params):
        session = requests.Session()
        current_page = params["page_url"]

        cookie_jar = MozillaCookieJar(params["cookie_filename"])
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
        session.cookies.update(cookie_jar)

        while True:
            # Request the current page
            response = session.get(current_page)
            if response.status_code != 200:
                break
            soup = BeautifulSoup(response.text, 'html.parser')

            # Check if the page URL contains "/{nr}/" where {nr} >= 2
            if not re.search(r'/\d+/', current_page) or re.search(r'/1/', current_page):
                # Scrape the headline image if the condition is met
                headline_div = soup.find('div', id='tt')
                if headline_div and headline_div.find('img'):
                    yield {
                        "img_url": headline_div.find('img')['src'],
                        "page_url": current_page
                    }

            # Scrape the webcomic's image
            comic_img = soup.find('img', id='strip')
            if comic_img and comic_img.get('src'):
                yield {
                    "img_url":comic_img['src'],
                    "page_url": current_page
                }

            # Find the next page link
            next_link = soup.find('a', rel='next', class_='button next')
            if next_link and next_link.get('href'):
                current_page = f"https://www.oglaf.com{next_link['href']}"
            else:
                break

    @staticmethod
    def alderwood(params):
        session = requests.Session()
        current_page = params["page_url"]
        while True:
            # Request the current page
            response = session.get(current_page)
            if response.status_code != 200:
                break
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find the image element
            img_tag = soup.find("img", id="comicimage")
            if img_tag and img_tag.get('src'):
                yield {
                    "img_url":img_tag['src'],
                    "page_url": current_page
                } 
            # time.sleep(0.5)
            # Update the current page to the next one (if exists)
            next_link = soup.find("a", rel="next")
            if next_link and "comicnavlink-grayedout" not in next_link.get("class", []):
                current_page = f"https://alderwood.the-comic.org{next_link['href']}"
            else:
                break  # Stop if there's no 'next' page or if it's the end

    @staticmethod
    def alfie(params):
        session = requests.Session()
        current_page = params["page_url"]
        while True:
            # Request the current page
            response = session.get(current_page)
            if response.status_code != 200:
                break
            soup = BeautifulSoup(response.text, 'html.parser')
            # Find the image element
            comic_div = soup.find('div', id='comic')
            if comic_div:
                img_tag = comic_div.find("img")
                if img_tag and img_tag.get('src'):
                    yield {
                        "img_url":img_tag['src'],
                        "page_url": current_page
                    }
            #time.sleep(0.5)
            # Update the current page to the next one (if exists)
            next_link = soup.find("a", class_="comic-nav-next")
            if next_link and "comic-nav-void" not in next_link.get("class", []):
                current_page = next_link['href']
            else:
                break  # Stop if there's no 'next' page or if it's the end
    
    @staticmethod
    def menageatrois(params):
        session = requests.Session()
        current_page = params["page_url"]
        while True:
            # Request the current page
            response = session.get(current_page)
            if response.status_code != 200:
                break
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find the image element
            img_tag = soup.find("img", id="cc-comic")
            if img_tag and img_tag.get('src'):
                yield {
                    "img_url":img_tag['src'],
                    "page_url": current_page
                } 
            # time.sleep(0.5)
            # Update the current page to the next one (if exists)
            next_link = soup.find("a", rel="next")
            if next_link:
                current_page = next_link['href']
            else:
                break  # Stop if there's no 'next' page or if it's the end