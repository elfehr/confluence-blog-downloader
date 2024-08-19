# -*- coding: utf-8 -*-

# TODO:
# read variables from command line
# read variables from config file?
# put into module with docstring
# tests?
# replace the assert by proper errors / exceptions / tests
# next step: download attachments
# if ConfluenceObject has write(), it should have get_filename

from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# Variables
server = 'https://confluence.example.com'
space = 'MS'  # todo: change its name
howmanypages = 1
pages_at_once = 1
user = 'username'
password = '********'
folder = '~/Documents/MS'


class Space:
    """ Settings to access and save a confluence space's blog.

    Attributes:
        server (string): Absolute URL of the confluence server.
        space (string): Short name of the space.confluence server.
        page_start (int): Index of the initial page to retrieve.
        pages_at_once (int): Limit to the number of pages requested at once.
        url (string): URL containing the parameters for the next request.
        folder (string): Local folder where the data is to be saved.
        auth: Authentification method to use for the requests.

    Methods:
        set_folder: Set the folder attibute.
        set_authentification: Set the auth attribute.
        get_posts: Return a list of BlogPost objects.
        test_connection: Try a request and print the status code.
        create_folder: Create the local folder to save the data.
    """

    def __init__(self, server: str, space: str,
                 page_start: int = 0, pages_at_once: int = 5,
                 folder: str = None, auth: list[str] = None):
        """
        Arguments:
            server: Absolute URL of the confluence server.
              Example: 'https://confluence.example.com'.
            space: Short name of the space.confluence server.
              Example: 'A' for a space at https://example.com/display/A/
            page_start: Index of the initial page to retrieve.
              Page 0 is the most recent post.
            pages_at_once: Limit to the number of pages requested at once.
            folder: Local folder where the data is to be saved.
        """
        self.server = server
        self.space = space
        self.page_start = page_start
        self.pages_at_once = pages_at_once
        self.url = (f'{self.server}/rest/api/space/' +
                    f'{self.space}/content/blogpost/' +
                    '?expand=body.view,history' +
                    f'&start={self.page_start}' +
                    f'&limit={self.pages_at_once}')

        if auth:
            self.set_authentification(*auth)
        else:
            self.auth = None
        if folder:
            self.set_folder(folder)
        else:
            self.folder = None

    def set_folder(self, folder: str) -> None:
        """Set the path to the folder where the posts are to be saved."""
        self.folder = Path(folder).expanduser().resolve().absolute()

    def set_authentification(self, user: str, password: str) -> None:
        """Set the authentifiation method for this space."""
        self.auth = (user, password)

    def test_connection(self) -> None:
        """Print the connection status code and hints to solve errors."""
        url = (f'{self.server}/rest/api/space/' +
               f'{self.space}/content/blogpost/?limit=1')
        status = requests.get(url, auth=self.auth).status_code

        if status == 200:
            print('Connection OK')
        else:
            print(f'Error: code {status}')
            if status == 404:
                print(f'Either {self.server}/display/{self.space}/ does not '
                      'exist, or you need additional authenticatification.')

    def get_posts(self) -> list['BlogPost']:
        """Return the next batch of blog posts.

        Start at the currently stored url and fetch pages_at_once posts.
        """
        response = requests.get(self.url, auth=self.auth)
        content = response.json()
        assert(response.status_code == 200)
        assert(len(content['results']) == self.pages_at_once)

        posts = [BlogPost(self, post) for post in content['results']]
        self.url = f'{self.server}{content["_links"]["next"]}'
        return posts

    def create_folder(self) -> bool:
        """Create local folder if necessary."""
        assert(self.folder)
        if not self.folder.exists():
            print(f'Creating folder {self.folder}')
            self.folder.mkdir(parents=True)


class ConfluenceObject():
    """Parent class for confluence objects such as blog posts,
    comments, attachments...

    Attributes:
        json (string): JSON representation of the object.
        server (string): Absolute URL of the confluence server.
        auth: Authentification method to use for the requests.
        folder (string): Local folder where the data is to be saved.
        attachments_url (string): URL to request the list of attachments.

    Methods:
        set_folder: Set the folder attibute.
        set_authentification: Set the auth attribute.
        get_data: Return the attributes we want in the HTML code.
        get_attachments: Return a list of Attachments objects.
        write: Write the object to a file (placeholder).
    """

    def __init__(self, space, json):
        """
        Arguments:
            space: parent Space object.
            json: JSON representation of the object.
        """
        self.json = json
        self.space = space

    def get_data(self):
        """Return a dictionnary of the post's body, title, author and date."""
        soup = BeautifulSoup(self.json['body']['view']['value'], 'html5lib')
        title = self.json['title']
        author = self.json['history']['createdBy']['displayName']
        date = datetime.strptime(self.json['history']['createdDate'],
                                 '%Y-%m-%dT%H:%M:%S.%f%z').strftime('%c')
        return {'content': soup.body, 'title': title,
                'author': author, 'date': date}

    def get_attachments(self):
        """Return a list of the object's attachments."""
        self.attachments_url = (f'{self.space.server}' +
                                f'{self.json["_expandable"]["children"]}' +
                                '/attachment?expand=body.view,history' +
                                '&limit=999&depth=all')
        response = requests.get(self.attachments_url, auth=self.space.auth)
        content = response.json()
        assert(response.status_code == 200)
        attachments = [Attachment(self.space, post)
                       for post in content['results']]
        return attachments

    def write(self):
        pass


class BlogPost(ConfluenceObject):
    """ConfluenceObject representing a blog post.

    Additional methods:
        get_filename: Return the path to the local file.
        get_comments: Return a list of the post's Comment objects.
        build_html: Returns the HTML representation of the post.
    """

    def get_filename(self) -> Path:
        """Returns the path to the post's file, in a flat hierarchy."""
        filename = self.json['_links']['webui']
        filename = filename.replace(f'/display/{self.space}/', '')
        filename = filename.replace('/', '-') + '.html'
        return self.space.folder.joinpath(filename)

    def build_html(self, post, comments=[]):
        """Returns the HTML code to build the page."""
        soup = BeautifulSoup('<html></html>', 'html5lib')
        soup.append(soup.new_tag("head"))
        soup.append(soup.new_tag("body"))

        # add metadata in <head>
        title_tag = soup.new_tag("title")
        title_tag.string = post['title']
        soup.head.append(title_tag)

        # add metadata in <header>
        h1_tag = soup.new_tag("h1")
        h1_tag.string = post['title']
        author_tag = soup.new_tag("p")
        author_tag.string = f'By {post["author"]} on {post["date"]}'
        soup.body.append(soup.new_tag("header"))
        soup.body.header.append(h1_tag)
        soup.body.header.append(author_tag)

        # add post content in <main>
        soup.body.append(soup.new_tag("main"))
        soup.body.main.append(post['content'])
        soup.body.main.body.unwrap()

        # add comments in an <article> each
        if comments:
            h2_tag = soup.new_tag("h2")
            h2_tag.string = 'Comments'
            soup.body.append(h2_tag)
        for comment in comments:
            comment_data = comment.get_data()
            article = soup.new_tag("article")
            article.append(soup.new_tag("footer"))
            author_tag = soup.new_tag("p")
            author_tag.string = (f'By {comment_data["author"]}' +
                                 f' on {comment_data["date"]}')
            article.footer.append(author_tag)
            article.footer.append(comment_data["content"])
            soup.body.append(article)

        return soup

    def get_comments(self):
        """Return a list of the post's comments."""
        self.comments_url = (f'{self.space.server}' +
                             f'{self.json["_expandable"]["children"]}' +
                             '/comment?expand=body.view,history' +
                             '&limit=999&depth=all')
        response = requests.get(self.comments_url, auth=self.space.auth)
        content = response.json()
        assert(response.status_code == 200)
        comments = [Comment(self, post) for post in content['results']]
        return comments

    def write(self):
        """Write the post to a file."""
        self.filename = self.get_filename()
        post = self.get_data()
        comments = self.get_comments()
        html = self.build_html(post, comments)
        with open(self.filename, 'w') as f:
            f.write(html.prettify())


class Comment(ConfluenceObject):
    """ConfluenceObject representing a comment."""
    # TODO remove write() method (error not implemented: no method to write a comment?)
    pass


class Attachment(ConfluenceObject):
    """ConfluenceObject representing an attachment.

    Additional methods:
        get_filename: Return the path to the local file."""

    def create_folder(self):
        pass
        # assert(self.space.folder)
        # if not self.space.folder.exists():
        #     print(f'Creating folder {self.space.folder}')
        #     self.space.folder.mkdir(parents=True)

    def get_filename(self) -> Path:
        """Returns the path to the file."""
        filename = self.json['_links']['download'][1:]
        return self.space.folder.joinpath(filename)

    def write(self):
        """TODO STOPPED HERE"""
        attachments = self.get_attachments()
        for attachment in attachments[:1]:
            print(attachment.json['_links']['download'])
            print(attachment.get_filename())
            # assert(attachment.json['_expandable']['previousVersion'] == '')
            # assert(attachment.json['_expandable']['nextVersion'] == '')


def main():
    MS = Space(server, space, pages_at_once=2, folder=folder)
    MS.set_authentification(user, password)
    # MS.test_connection()

    blogs = MS.get_posts()  # get batch
    # print([blog.json['title'] for blog in blogs])
    blogs[0].write()
    blogs[0].write_attachments()


if __name__ == "__main__":
    main()

# print(url)
# response = requests.get(url, auth=(user, password))
# print(response.status_code)
# print(response.json())
# tests: vary all params, neg/0/pos
