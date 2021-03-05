from bs4 import BeautifulSoup
import requests
import json
import re
import argparse
import logging
from datetime import datetime

TITLE_URL = 'https://www.imdb.com/title/'
ITEMS_PER_PAGE = 250
headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Safari/537.36',
    'cookie': 'uu=BCYihWn5TKKaAVAGnUqVJnXhZA34jSYbcttTq77o6RfBeimjvgDYjkHkOcreGAMS3wLXLLvNGQCr%0D%0AS9yqepwxzluTRS5jFI3cK-pFN0LFKFPu0w6Weq1XmkD4YWoK8Qs8pHc_64NAOUICbf2xMzu0BQqH%0D%0ALQ%0D%0A; session-id=137-5925263-2677462; adblk=adblk_no; ubid-main=135-8181497-7395039; session-id-time=2082787201l; session-token=QSz2ApPDPPG78JQrfFv74C4nTZPK2TMD5uDkPb7/KiC7nNMFzFdJbp39GmGu/6GUfT7pByqef4e1Ye3xXRi8T7TwTg1KDPBi2WrOVQAFdk3p3407rLW9ssYTGZBnn3QZG33Lnr7DHoGGk91Gt7SDUkzjFd/Uk1dUHgGV8Ky6MnghcPlhyLrUAh0jbOzNtNDK; csm-hit=tb:JWFEENP0VSV4SJB5G9H1+s-TKZ72WJEJ7K24XW7EWPC|1610456055733&t:1610456055734&adb:adblk_yes; beta-control=tmd=in'
}


class App:
    def __init__(self):
        logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)s %(message)s')
        logger = logging.getLogger('imdb-search application')
        logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler(datetime.now().strftime('logs/app.%Y-%m-%d_%H-%M-%S.log'))
        fh.setLevel(logging.DEBUG)
        logger.addHandler(fh)

        self.logger = logger

    def read_config(self, filename):
        self.logger.info("try to read configuration file")
        default_filename = 'config.default.json'
        filename = default_filename if filename is None else filename
        with open(filename, 'r') as myfile:
            data = myfile.read()

        return json.loads(data)

    def build_query(self, config_obj):
        self.logger.info('build query string')
        query = "&".join([f'{key}={",".join(map(str, value))}' for key, value in config_obj.items()])
        query += f'&view=simple&count={ITEMS_PER_PAGE}'

        return query

    def process_request(self, URL):
        self.logger.info(f'process request {URL}')
        response = requests.get(URL, headers=headers)
        self.logger.info(f'response status is {response.status_code}')

        return response

    def get_links(self, query_str, count=10):
        SEARCH_URL = 'https://www.imdb.com/search/title/'
        links_list = []
        pages_count = count // ITEMS_PER_PAGE + (1 if count % ITEMS_PER_PAGE > 0 else 0)

        for page_number in range(pages_count):
            self.logger.info(
                f"Get {page_number * ITEMS_PER_PAGE + 1}-{(page_number + 1) * ITEMS_PER_PAGE} titles links")
            start_query_param = "" if page_number == 0 else f'start={page_number * ITEMS_PER_PAGE + 1}'
            response_data = self.process_request(SEARCH_URL + f'?{query_str + start_query_param}')
            soup = BeautifulSoup(response_data.content, 'html.parser')

            links_limit = count % ITEMS_PER_PAGE if page_number == pages_count - 1 else ITEMS_PER_PAGE
            for tag in soup.findAll('span', attrs={'class': 'lister-item-header'}, limit=links_limit):
                link_to_page = re.match(r'^/title/(.+)', tag.a['href']).group(1)
                links_list.append(link_to_page)

        return links_list

    def get_movie_data(self, link):
        movie_data = {}
        self.logger.info(f'Get title data by {link}')
        response_data = self.process_request(TITLE_URL + link)
        if response_data.status_code != 200:
            self.logger.error("Getting title data is not success")
            return None

        self.logger.info(f'Try to parse title data by {link}')
        soup = BeautifulSoup(response_data.content, 'html.parser')
        tag_title = soup.find('div', attrs={'data-testid': 'hero-title-block__original-title'})
        if tag_title is None:
            tag_title = soup.find('div', attrs={'data-testid': 'hero-title-block__title'})
            movie_data['title'] = tag_title.text.strip()
        else:
            movie_data['title'] = tag_title.text.replace('Original title:', "").strip()

        tag_genres = soup.find('div', attrs={'data-testid': 'genres'})
        movie_data['genres'] = [x.text for x in tag_genres.contents]

        tag_rating = soup.find('div', attrs={'data-testid': 'hero-title-block__aggregate-rating__score'})
        movie_data['rating'] = tag_rating.text.split('/')[0]

        tag_cast = soup.find_all('div', attrs={'class': re.compile('CastItemSummary')})
        movie_data['top_cast'] = [x.a.text for x in tag_cast][:5]

        tag_metadata = soup.find('ul', attrs={'data-testid': 'hero-title-block__metadata'})
        movie_type = tag_metadata.li.text
        movie_type = 'Movie' if re.match(r'^\d+$', movie_type) is not None else movie_type
        movie_data['type'] = movie_type

        try:
            details = {}
            tag_details = soup.find('div', attrs={'data-testid': 'title-details-section'})
            for x in tag_details.ul:
                if x.ul is not None:
                    detail_name = x.select('.ipc-metadata-list-item__label')[0].text.lower().replace(' ', '_')
                    detail_list = [x.text for x in x.ul.find_all('li')]
                    detail_list = detail_list if len(detail_list) > 1 else detail_list[0]
                    details[detail_name] = detail_list

            movie_data['details'] = details
        except AttributeError:
            self.logger.error("Parsing details data is not success")

        try:
            box_office = {}
            tag_box_office = soup.find('div', attrs={'data-testid': 'title-boxoffice-section'})
            for x in tag_box_office.ul:
                if x.ul is not None:
                    detail_name = x.select('.ipc-metadata-list-item__label')[0].text.lower().replace(' ', '_')
                    detail_list = [x.text for x in x.ul.find_all('li')]
                    detail_list = detail_list if len(detail_list) > 1 else detail_list[0]
                    box_office[detail_name] = detail_list

            movie_data['box_office'] = box_office
        except AttributeError:
            self.logger.error("Parsing box_office data is not success")

        try:
            tech_specs = {}
            tag_tech_specs = soup.find('div', attrs={'data-testid': 'title-techspecs-section'})
            for x in tag_tech_specs.ul:
                if x.ul is not None:
                    detail_name = x.select('.ipc-metadata-list-item__label')[0].text.lower().replace(' ', '_')
                    detail_list = [x.text for x in x.ul.find_all('li')]
                    detail_list = detail_list if len(detail_list) > 1 else detail_list[0]
                    tech_specs[detail_name] = detail_list

            movie_data['tech_specs'] = tech_specs
        except AttributeError:
            self.logger.error("Parsing tech_specs data is not success")

        return movie_data


if __name__ == '__main__':
    app = App()
    app.logger.info("start app")

    # parse args
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', type=str)
    parser.add_argument('-n', type=int)
    parser.add_argument('-f', type=str)
    args = parser.parse_args()
    config_filename = args.c
    titles_count = args.n
    titles_count = 10 if titles_count is None or titles_count > 1000 or titles_count < 1 else titles_count
    result_filename = f'{args.f}.json' if args.f is not None else "titles.json"

    # read config
    config_obj = app.read_config(config_filename)

    # get data
    titles_data = []
    try:
        query_str = app.build_query(config_obj)
        links = app.get_links(query_str, count=titles_count)
        for link in links:
            title_data = app.get_movie_data(link)
            if title_data is not None:
                titles_data.append(title_data)
        app.logger.info("Handling data is success")
    except BaseException:
        app.logger.exception("Unhandled Exception")
        app.logger.info("Handling data is not success")
    finally:
        with open(result_filename, 'w') as myfile:
            myfile.write(json.dumps(titles_data))

        app.logger.info("app shutdown")
        logging.shutdown()
