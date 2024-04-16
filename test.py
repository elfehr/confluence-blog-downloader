# import pytest
import re
import datetime
import requests
import warnings
import unicodedata
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
    end: int = None
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
        assert response.status_code == 200, response.status_code
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
        self._maybe_print(f"Scraping {len(posts)} posts:")
        for post_ID in posts:
            try:
                int(post_ID)
            except:
                warnings.warn(f"Skipping post {post_ID}: not a valid ID")
            else:
                post = BlogPost(blog, ID=post_ID)
                post.scrape_post()

class ConfluenceObject():
    def __init__(self, parent, ID: str):
        if isinstance(parent, Blog):
            self.blog = parent
        else:
            self.parent = parent
            self.blog = parent.blog
        self.ID = ID
        self._format_url()
        self._scrape_info()

    def _format_url(self):
        api_endpoint = "{}/rest/api/content/{}"
        self.url = api_endpoint.format(self.blog.server, self.ID)

    def _scrape_info(self):
        self.content = self.blog._request_wrapper(self.url, params={'expand': 'body.view,history'})
        self.title = self.content['title']
        self.author = self.content['history']['createdBy']['displayName']
        date = datetime.datetime.strptime(self.content['history']['createdDate'], '%Y-%m-%dT%H:%M:%S.%f%z')
        self.date_formatted = date.strftime('%c')
        self.date = datetime.date(date.year, date.month, date.day).isoformat()
        self.body = BeautifulSoup(self.content['body']['view']['value'], 'html5lib').body
        self._clean_html()
        self.blog._maybe_print(f"Post: {self.title} by {self.author}")

    def _clean_html(self):
        tags = self.body.find_all('script')
        for tag in tags:
            tag.decompose()
        tags = self.body.find_all('span', 'latexmath-mathinline')
        for tag in tags:
            tag.unwrap()
        tags = self.body.find_all('span', 'confluence-embedded-file-wrapper')
        for tag in tags:
            tag.unwrap()
        tags = self.body.find_all('span', 'MathJax_Preview')
        for tag in tags:
            tag.string = f'\({tag.string}\)'
            tag.unwrap()

    def _slugify(self, value):
        value = unicodedata.normalize('NFKC', value)
        value = re.sub(r'[^_\w\s-]', '', value)
        return re.sub(r'[\s]+', '_', value).strip('-_')

    def _scrape_comments(self):
        url = "{}/child/comment".format(self.url)
        content = self.blog._request_wrapper(url, params={'limit': '999'})
        depth = 0 if isinstance(self, BlogPost) else self.depth + 1
        self.comments = [Comment(self, post['id'], depth) for post in content['results']]

    def _scrape_attachments(self):
        url = "{}/child/attachment".format(self.url)
        content = self.blog._request_wrapper(url, params={'limit': '999'})
        for post in content['results']:
            url = post['_links']['download']
            for original_url in (url, url.replace('/attachments/', '/thumbnails/')):
                remote_filename = self.blog.server + original_url
                modified_url = self._format_attachment_filename(original_url)
                local_filename = self.blog.folder.joinpath(modified_url)
                if not local_filename.exists():
                    folder = local_filename.parent
                    if not folder.exists():
                        self.blog._maybe_print(f"Creating {folder}")
                        folder.mkdir(parents=True)
                    self.blog._maybe_print(f"Downloading {local_filename}")
                    response = self.blog.connection.get(remote_filename)
                    with open(local_filename, 'wb') as f:
                        f.write(response.content)
                else:
                    self.blog._maybe_print(f"Already exists: {local_filename}")

    def _format_attachment_filename(self, url):
        folder = Path(url.lstrip("/")).parent
        name, details = Path(url).name.split('?')
        version = re.search('(?<=version=)\d+', details).group(0)
        ext = Path(name).suffixes
        slug = self._slugify(Path(name).stem)
        name = ''.join([slug, f'_version{version}',  *ext])
        return folder.joinpath(name)


class BlogPost(ConfluenceObject):
    def scrape_post(self):
        self.blog._maybe_print(f"Building post {self.title}")
        self._scrape_attachments()
        self._scrape_comments()
        self._format_html()
        self._export_html()

    def _format_comments(self, parent: ConfluenceObject, soup: BeautifulSoup):
        for comment in parent.comments:
            margin = comment.depth * 2
            article = soup.new_tag('article', style=f'margin-left: {margin}em')
            id_tag = soup.new_tag('a', id=f'#comment-{comment.ID}')
            id_tag.string = f'(ID {comment.ID})'
            author_tag = soup.new_tag('address')
            author_tag.string = (f"By {comment.author} on {comment.date_formatted}")
            author_tag.extend([' ', id_tag])
            if comment.depth > 0:
                parent_tag = soup.new_tag("a", href=f'#comment-{parent.ID}')
                parent_tag.string = 'parent'
                author_tag.extend([' - ', parent_tag])
            article.append(soup.new_tag('header'))
            article.header.append(author_tag)
            article.append(comment.body)
            soup.body.append(article)
            self._format_comments(comment, soup)

    def _format_html(self):
        soup = BeautifulSoup('<html></html>', 'html5lib')
        soup.append(soup.new_tag('head'))
        soup.append(soup.new_tag('body'))

        # add metadata in <head>
        title_tag = soup.new_tag('title')
        title_tag.string = self.title
        mathjax1_tag = soup.new_tag('script', src=r'https://polyfill.io/v3/polyfill.min.js?features=es6')
        mathjax2_tag = soup.new_tag('script', src=r'https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js')
        soup.head.append(title_tag)
        soup.head.append(mathjax1_tag)
        soup.head.append(mathjax2_tag)

        # add metadata in <header>
        title_tag = soup.new_tag('h1')
        author_tag = soup.new_tag('address')
        id_tag = soup.new_tag('p')
        title_tag.string = self.title
        author_tag.string = f"By {self.author} on {self.date_formatted} (ID {self.ID})"
        soup.body.append(soup.new_tag('header'))
        soup.body.header.append(title_tag)
        soup.body.header.append(author_tag)

        # add post content in <main>
        soup.body.append(soup.new_tag('main'))
        soup.body.main.append(self.body)
        soup.body.main.body.unwrap()

        # add comments in an <article> each
        if self.comments:
            h2_tag = soup.new_tag('h2')
            h2_tag.string = 'Comments'
            soup.body.append(h2_tag)
            self._format_comments(self, soup)

        # edit links
        imgs = soup.find_all('img', attrs={'data-image-src': re.compile('/download/attachments/.*')})
        for img in imgs:
            big = Path('..').joinpath(self._format_attachment_filename(img['data-image-src']))
            small = str(big).replace('/attachments/', '/thumbnails/')
            new_img = soup.new_tag('img', src=small)
            img_link = soup.new_tag('a', href=big)
            self.blog._maybe_print(f"Replacing link to {big}")
            img_link.append(new_img)
            img.replace_with(img_link)

        soup.smooth()
        self.html = soup.prettify()

    def _export_html(self):
        folder = self.blog.folder.joinpath('blog')
        if not folder.exists():
            self.blog._maybe_print(f"Creating {folder}")
            folder.mkdir(parents=True)
        filename = folder.joinpath(f"{self.date}_{self._slugify(self.title)}.html")
        self.blog._maybe_print(f"Writing {filename}")
        with open(filename, 'w') as f:
            f.write(self.html)

class Comment(ConfluenceObject):
    def __init__(self, parent, ID: str, depth: int):
        super().__init__(parent, ID)
        self.depth = depth
        self._scrape_attachments()
        self._scrape_comments()


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

# # set up connection to confluence
blog = Blog(settings, connection)
# blog.test_connection(verbose=True)

# # list all blog posts
# blog.list_posts(merge=False)

# # different ways to scrape a list of posts
# blog.scrape_posts(ID='183140357')
# blog.scrape_posts(file='subset.csv', header=0)
# blog.scrape_posts(file='default')
blog.scrape_posts()

# # manually scrape a blog post
# post = BlogPost(blog, ID='167948585')
# post.scrape_post()

# todo:
# types of internal links:
# https://confluence.example.com/display/MS/2018/01/30/EOS?focusedCommentId=104032991#comment-104032991
# https://confluence.example.com/display/MS/MOS+meeting+--+21.12.02?preview=/188800496/188800502/201221.pdf
# https://confluence.example.com/download/attachments/198900289/image2021-3-17_13-11-21.png?version=1&amp;modificationDate=1615983081145&amp;api=v2
# https://confluence.example.com/pages/viewpage.action?pageId=148808992
# /pages/viewpage.action?pageId=104016022"
# /display/MS/
# /download/attachments
