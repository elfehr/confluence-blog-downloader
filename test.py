# import pytest
import requests
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup
from dataclasses import dataclass

@dataclass
class ScraperSettings:
    """ Storage for the parameters of the scraper:
    Attributes:
        server (str): URL of the confluence server, ex: "https://confluence.example.com"
        space (str): space key of the confluence space whose blog to download, ex "KEY"
        start (int): index of first blog post to download (starting approximately by most recent)
        end (int): index of last blog post to download
        folder (str): local folder where the data is to be saved
    """
    server: str
    space: str = None
    start: int = 0
    end: int = 10
    folder: str = "."


class Server:
    """ Confluence server and the credentials to access it. """
    verbose = True
    posts = []

    def __init__(self, settings: ScraperSettings, connection: requests.sessions.Session = None):
        self.settings = settings
        self.server = settings.server.rstrip("/")
        self._format_url()
        if connection is None:
            self.connection = requests.Session()
        else:
            self.connection = connection

    def _format_url(self):
        api_endpoint = "{}/rest/api/space"
        self.url = api_endpoint.format(self.server)

    def _maybe_print(self, *args):
        if self.verbose:
            print(*args)

    def _request_wrapper(self, url, **args):
        response = self.connection.get(url, **args)
        self._maybe_print(response.url)
        assert(response.status_code == 200)
        return response.json()

    def _scrape_list_stop(self, content):
        return False

    def test_connection(self, verbose: bool = False) -> bool:
        """ Test the status code returned by the Confluence API.
        Args:
            verbose: if True, print connection status code and hints to solve errors
        Returns True if the status code indicates success and the response is decodable json
        """
        response = self.connection.get(self.url)
        status = response.status_code
        if verbose:
            codes = {200: "Connection OK",
                     401: "Authentification error",
                     404: "URL not found or missing permissions",
                     429: "Too many requests"}
            print(response.url)
            if status in codes:
                print(response, codes[status])
            else:
                print(response)
        if status == 200:
            try:
                response.json()
            except requests.exceptions.JSONDecodeError:
                if verbose:
                    print(f"Response is not decodable json: {str(response.content):.100}")
                    return False
        return response.ok

    def scrape_list(self, url, params=None, merge=True):
        """ Scrape a list of posts and store references to their IDs.
        Args:
            url (str): API endpoint URL for the first page of the list
            params (dict): additional request parameters
        """
        try:
            content = self._request_wrapper(url, params=params)
            while True:
                for post in content['results']:
                    self.posts.append({'ID': post['id'], 'type': post['type'], 'title': post['title']})
                if ('next' not in content['_links'].keys()) or self._scrape_list_stop(content):
                    break
                else:
                    self._maybe_print("Continuing:")
                    next_url = self.server + content['_links']['next']
                    content = self._request_wrapper(next_url)
        finally:
            self.export_list(merge=merge)

    def export_list(self, merge=True):
        """ Write in a csv the scraped list of posts.
            merge (bool): whether to merge with or replace the current file """
        if len(self.posts) > 0:
            if not self.folder.exists():
                self._maybe_print(f"Creating {self.folder}")
                self.folder.mkdir(parents=True)
            post_type = self.posts[0]['type']
            filename = self.folder.joinpath(f'list_{post_type}s.csv')
            df = pd.DataFrame(self.posts).set_index('ID')
            if merge and filename.exists():
                df = pd.concat([df, pd.read_csv(filename).set_index('ID')]).drop_duplicates()
            df.to_csv(filename)



class Blog(Server):
    """ Blog of a confluence space. """

    def _format_url(self):
        api_endpoint = "{}/rest/api/space/{}/content/blogpost"
        self.url = api_endpoint.format(self.server, self.settings.space)
        self.folder = Path(settings.folder).expanduser().joinpath(self.settings.space)

    def list_posts(self, merge=True):
        """ Export a list of blog posts.
        Args:
            merge (bool): if True, merge with the current file. If False, replace it
        """
        self.scrape_list(self.url, params={'start': self.settings.start}, merge=merge)

    def _scrape_list_stop(self, content):
        self._maybe_print(f"Found  {content['start'] + content['size']} / {self.settings.end} pages")
        if self.settings.end is None:
            return False
        else:
            return content['start'] + content['limit'] >= self.settings.end

    def scrape_posts(self, ID=None, file='default', header=None):
        """ Scrape the listed blog posts.
        Args:
            ID (str): post ID or list thereof
            file (str): name of a file containing a list of post IDs
        """
        if ID is not None:
            if isinstance(ID, str):
                posts = [ID]
            else:
                posts = ID
        else:
            if file == 'default':
                filename = self.folder.joinpath(f'list_blogposts.csv')
                header = 'infer'
            else:
                filename = self.folder.joinpath(file)
            self._maybe_print(f"Reading posts from {filename}")
            df = pd.read_csv(filename, header=header)
            if 'ID' in df.columns:
                posts = df['ID'].T.to_numpy(dtype=str).tolist()
            else:
                posts = df[0].T.to_numpy(dtype=str).tolist()
        self._maybe_print(f"Scraping {len(posts)} posts: {posts}")




server = 'https://confluence.example.com'
space = 'MS'
user = 'username'
password = '********'
proxy = {'http': 'socks5://localhost:2280',
         'https': 'socks5://localhost:2280'}
settings = ScraperSettings(server=server, space=space)
connection = requests.Session()
connection.proxies.update(proxy)
connection.auth = (user, password)

blog = Blog(settings, connection)
# blog.test_connection(verbose=True)
# blog.list_posts(merge=False)
blog.scrape_posts(ID='167948585')
# blog.scrape_posts(file='test')
# blog.scrape_posts(file='default')
# blog.scrape_posts()
posts = blog.posts

# blog.export_list()


# r = connection.get("https://confluence.example.com/rest/api/space/MS/content/blogpost?start=0")

# @pytest.fixture
# def RequestSettings_server_only():
#     return ScraperSettings(server=server, space=space)

# @pytest.fixture
# def RequestSettings_space():
#     return ScraperSettings(server=server, space=space)

# @pytest.fixture
# def RequestSettings_password():
#     return ScraperSettings(server=server, auth=(user, password))

# @pytest.fixture
# def RequestSettings_space_password():
#     return ScraperSettings(server=server, space=space, auth=(user, password))

# def test_Server_noauth(RequestSettings_server_only):
#         server = Server(RequestSettings_server_only)
#         assert server.test_connection()

# def test_Server_space_password(RequestSettings_password):
#         server = Server(RequestSettings_password)
#         assert server.test_connection()

# def test_Blog_noauth(RequestSettings_space):
#         blog = Blog(RequestSettings_space)
#         assert blog.test_connection()

# def test_Blog_space_password(RequestSettings_space_password):
#         blog = Blog(RequestSettings_space_password)
#         assert blog.test_connection()
