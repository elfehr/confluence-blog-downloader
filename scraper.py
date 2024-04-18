import requests
import subprocess

from confluenceObjects import ScraperSettings, Blog, BlogPost


# server settings
server = 'https://confluence.example.com'
space = 'MS'
settings = ScraperSettings(server=server, space=space)

# connection to use to make all requests (optional)
user = 'username'
password = subprocess.run(['pass', 'work/confluence'],
                          stdout=subprocess.PIPE).stdout.decode('utf-8').splitlines()[0]
proxy = {'http': 'socks5://localhost:2280',
         'https': 'socks5://localhost:2280'}
connection = requests.Session()
connection.proxies.update(proxy) # if proxy is needed
connection.auth = (user, password) # if password is needed

# test that the blog is accessible
blog = Blog(settings, connection)
blog.test_connection(verbose=True)
# blog.verbose= False # silence all operations

# # index all blog posts into list_blogposts.csv
# blog.list_posts() # append to current index
# blog.list_posts(merge=False) # replace current index

# # different ways to scrape a list of posts
# blog.scrape_posts() # scrape all posts listed in list_blogposts.csv
# blog.scrape_posts(file='default') # same
# blog.scrape_posts(file='subset.csv', header=0) # scrape posts in file
# blog.scrape_posts(ID=['183140357', '198900289']) # scrape listed posts
# blog.scrape_posts(ID='183140357') # scrape single post

# # manually scrape a blog post
post = BlogPost(blog, ID='167948585')
post.scrape_post()
blog.create_index() # manually update the index

connection.close()
