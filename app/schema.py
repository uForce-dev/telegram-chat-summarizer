from pydantic import BaseModel


class SummaryRequest(BaseModel):
    channel_id: str
    user_id: str
    post_id: str
