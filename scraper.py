import requests

from confluenceObjects import ScraperSettings, Blog, BlogPost


# server settings
server = 'https://confluence.example.com'
space = 'MS'
settings = ScraperSettings(server=server, space=space)

# connection to use to make all requests (optional)
user = 'username'
password = '********'
proxy = {'http': 'socks5://localhost:2280',
         'https': 'socks5://localhost:2280'}
connection = requests.Session()
connection.proxies.update(proxy) # if proxy is needed
connection.auth = (user, password) # if password is needed

# test that the blog is accessible
blog = Blog(settings, connection)
blog.test_connection(verbose=True)

# # index all blog posts into list_blogposts.csv
# blog.list_posts() # append to current index
# blog.list_posts(merge=False) # replace current index

# # different ways to scrape a list of posts
# blog.scrape_posts() # scrape all posts listed in list_blogposts.csv
# blog.scrape_posts(file='default') # same
# blog.scrape_posts(file='subset.csv', header=0) # scrape posts in file
# blog.scrape_posts(ID=['183140357', '198900289']) # scrape listed posts
# blog.scrape_posts(ID='183140357') # scrape single post

# manually scrape a blog post
post = BlogPost(blog, ID='167948585')
post.scrape_post()

# TODO: internal links of types:
# https://confluence.example.com/display/MS/2018/01/30/EOS?focusedCommentId=104032991#comment-104032991
# https://confluence.example.com/display/MS/MOS+meeting+--+21.12.02?preview=/188800496/188800502/201221.pdf
# https://confluence.example.com/download/attachments/198900289/image2021-3-17_13-11-21.png?version=1&amp;modificationDate=1615983081145&amp;api=v2
# https://confluence.example.com/pages/viewpage.action?pageId=148808992
# /pages/viewpage.action?pageId=104016022"
# /display/MS/
# /download/attachments
