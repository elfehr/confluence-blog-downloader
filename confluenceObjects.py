import re
import logging
import datetime
import unicodedata
from pathlib import Path
from dataclasses import dataclass

import requests
import pandas as pd
from bs4 import BeautifulSoup


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
    """ Confluence server and the credentials to access it.
    Attributes:
        verbose (bool): whether to print debugging information
        posts (dict): list of post IDs contained in the blog, to be written to list_blogposts.csv
        settings (ScraperSettings): user settings to get the list of posts
        connection (requests.sessions.Session): request session to reuse the connection to the server
        server (src): URL of confluence server
        url (src): URL of the API endpoint
    """
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
        Args:
            merge (bool): whether to merge with or replace the current file
        """
        if len(self.posts) > 0:
            if not self.folder.exists():
                self._maybe_print(f"Creating {self.folder}")
                self.folder.mkdir(parents=True)
            post_type = self.posts[0]['type']
            filename = self.folder.joinpath(f'list_{post_type}s.csv')
            df = pd.DataFrame(self.posts)
            dup = df.duplicated(subset='ID').sum()
            if dup > 0:
                self._warn(f"The API returned {dup} duplicated posts, which means that {dup} others posts have not been indexed and will not be downloaded automatically unless their IDs have been collected before.")
            if merge and filename.exists():
                old = pd.read_csv(filename, dtype=str)
                self._maybe_print(f"Merging new list of {len(df)} posts (amoung which {dup} duplicates) with previous list of {len(old)} posts.")
                df = pd.concat([df, old]).drop_duplicates(subset='ID').set_index('ID')
            self._maybe_print(f"Saving list of {len(df)} posts in {filename}")
            df.to_csv(filename)

    def _warn(self, message):
        logging.warn(' ' + message)


class Blog(Server):
    """ Blog of a confluence space.
    Additional attributes:
        folder (Path): local path to the folder where to save the blog posts
    """
    def _format_url(self):
        api_endpoint = "{}/rest/api/space/{}/content/blogpost"
        self.url = api_endpoint.format(self.server, self.settings.space)
        self.folder = Path(self.settings.folder).expanduser().joinpath(self.settings.space)

    def list_posts(self, merge=True):
        """ Export a list of blog posts.
        Args:
            merge (bool): if True, merge with the current file. If False, replace it
        """
        self.scrape_list(self.url, params={'start': self.settings.start}, merge=merge)

    def _scrape_list_stop(self, content):
        self._maybe_print(f"Found  {content['start'] + content['size']} / {self.settings.end} pages.")
        if self.settings.end is None:
            return False
        else:
            return content['start'] + content['limit'] >= self.settings.end

    def scrape_posts(self, ID=None, file='default', header=None):
        """ Scrape the listed blog posts and save them.
        Args:
            ID (str): post ID or list thereof
            file (str): name of a file containing a list of post IDs
            header (int): whether the file has a header, to be passed to pandas.read_csv()
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
                self.blog._warn(f"Skipping post {post_ID}: not a valid ID.")
            else:
                post = BlogPost(self, ID=post_ID)
                post.scrape_post()
        self.create_index()

    def create_index(self):
        """ Create index.html listing all files in the blog subfolder """
        url = "{}/rest/api/space/{}".format(self.server, self.settings.space)
        try:
            content = self._request_wrapper(url)
            name = content['name']
        except:
            name = self.settings.space

        soup = BeautifulSoup('<html></html>', 'html5lib')
        soup.append(soup.new_tag('head'))
        soup.append(soup.new_tag('body'))
        soup.body.append(soup.new_tag('header'))
        soup.body.append(soup.new_tag('main'))

        # metadata
        title1_tag = soup.new_tag('title')
        title2_tag = soup.new_tag('h1')
        title1_tag.string = name
        title2_tag.string = name
        soup.head.append(title1_tag)
        soup.body.header.append(title2_tag)

        # posts
        year = None
        month = None
        ul_tag = soup.new_tag('ul')
        for post in sorted(self.folder.joinpath('blog').iterdir()):
            date = datetime.datetime.strptime(post.name[:10], '%Y-%m-%d')
            new_year = date.strftime('%Y')
            new_month = date.strftime('%B')
            if new_month != month or new_year != year:
                if len(ul_tag.contents) > 0:
                    self._maybe_print(f"{len(ul_tag.contents)} posts")
                    soup.body.main.append(ul_tag)
                self._maybe_print(f"Indexing posts from {new_year}, {new_month}")
                if new_year != year:
                    year = new_year
                    year_tag = soup.new_tag('h2')
                    year_tag.string = new_year
                    soup.body.main.append(year_tag)
                month = new_month
                month_tag = soup.new_tag('h3')
                month_tag.string = new_month
                soup.body.main.append(month_tag)
                ul_tag = soup.new_tag('ul')
            list_tag = soup.new_tag('li')
            link_tag = soup.new_tag('a', href=post.relative_to(self.folder))
            link_tag.string = post.name
            ul_tag.append(list_tag)
            list_tag.append(link_tag)
        soup.body.main.append(ul_tag)

        filename = self.folder.joinpath('index.html')
        self._maybe_print(f"Writing {filename}")
        with open(filename, 'w') as f:
            f.write(soup.prettify())

class ConfluenceObject():
    """ Generic confluence post, either blog post or comment.
    Attributes:
        blog (Blog): confluence blog on which the object is posted
        parent (ConfluenceObject): parent comment
        comments (ConfluenceObject): list of children comments
        ID (str): post ID of the post
        url (str): URL of the API endpoint for the post
        content (dict): json response of the confluenc API
        title (str): post title
        author (str): post author
        date (str): post date in ISO format
        date_formatted (str): post date in locale format
        body (BeautifulSoup): HTML body of the post
    """
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
                try:
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
                except Exception as e:
                    self.blog._warn(f"Skipping saving {local_filename}: {e}")

    def _format_attachment_filename(self, url):
        folder = Path(url.lstrip("/")).parent
        name, details = Path(url).name.split('?')
        version = re.search('(?<=version=)\d+', details).group(0)
        ext = Path(name).suffixes
        slug = self._slugify(Path(name).stem)
        name = ''.join([slug, f'_version{version}',  *ext])
        return folder.joinpath(name)


class BlogPost(ConfluenceObject):
    """ Confluence blog post """

    def scrape_post(self):
        """ Download attachments and save a HTML version of the post. """
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

        # edit  <img>
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
    """ Confluence comment. """
    def __init__(self, parent, ID: str, depth: int):
        super().__init__(parent, ID)
        self.depth = depth
        self._scrape_attachments()
        self._scrape_comments()
