class NotionRequestError(Exception):
    """Exception raised for errors in Notion API requests."""
    
    def __init__(self, message, response=None):
        self.message = message
        self.response = response
        super().__init__(self.message)