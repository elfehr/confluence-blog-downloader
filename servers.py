class Server:
    api_endpoint = "/rest/api/space"

    def __init__(self, server, auth=None):
        self.url = server.rstrip("/") + self.api_endpoint
        self.authentification = auth

    def test_connection(self, verbose=False) -> bool:
        """ Test the status code returned by the Confluence API.

        Args:
            verbose: if True, print connection status code and hints to solve errors.

        Returns:
            True if the status code is less than 400 (sucess), otherwise false.
        """
        response = requests.get(self.url, auth=self.authentification)
        if verbose:
            status = response.status_code
            codes = {200: "Connection OK",
                     404: "URL not found or missing permissions",
                     429: "Too many requests"}
            print(response.url)
            if status in codes:
                print(response, codes[status])
        return response.ok

import requests

class Blog(Server):
    pass
    # def __init__(self, server, auth=None):
    #     super().__init__(server, auth)


class LocalBlog():
    def __init__(self, path):
    self.attachments_folder
    self.folder = path

    @property
    def folder(self):
        return self.__base_folder

    @folder.setter
    def folder(self, value):
        self.__base_folder = Path(value).expanduser().resolve().absolute()


# Variables
server = 'https://confluence.example.com'
# space = 'MS'  # todo: change its name
# howmanypages = 1
# pages_at_once = 1
user = 'username'
password = '********'
# folder = '~/Documents/MS'

# tests
# for server in [
#         Server(server, auth=(user, password)),
#         Server(server+"/", auth=(user, password)),
#         Server(server)]:
#     assert server.test_connection(verbose=True)

# for server in [
#         Blog(server, auth=(user, password)),
#         Blog(server+"/", auth=(user, password)),
#         Blog(server)]:
#     assert server.test_connection(verbose=True)
