class DatabasesManager(object):

    def __init__(self, api):
        self.api = api

    def get_info(self, database_id):
        return self.api._get(f"databases/{database_id}")
